"""OPC UA qualification on a dedicated bench. No server provisioning or secrets in reports.

Example mode requires inhibited outputs. Testing mode temporarily controls only the
explicit MAIN.rpcOutput/enableRpcPump test fixture; it restores its source lock,
resumes the pump and verifies ForceSafe in finally. Supply an already trusted
client certificate and an independently obtained server certificate.
"""
import argparse
import asyncio
from contextlib import AsyncExitStack
import hashlib
import json
import os
from pathlib import Path
import time
import xml.etree.ElementTree as ET


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def validate_admission(results, duplicate=False):
    require(len(results) >= 2, 'Concurrent test needs multiple clients')
    require(results.count(1) == 1, f'Expected one admission: {results}')
    require(all(r in ({1, 22, 35} if duplicate else {1, 22}) for r in results),
            f'Unexpected admission result: {results}')


def write_report(output, evidence):
    (output / 'opcua.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    suite = ET.Element('testsuite', name='TcForge.OPCUA', tests=str(len(evidence['checks']) + 1),
                       failures=str(sum(not c['passed'] for c in evidence['checks']) +
                                    (0 if evidence['passed'] else 1)))
    for check in evidence['checks']:
        case = ET.SubElement(suite, 'testcase', name=check['name'])
        if not check['passed']:
            ET.SubElement(case, 'failure').text = check.get('error', 'Failed')
    case = ET.SubElement(suite, 'testcase', name='completion-and-cleanup')
    if not evidence['passed']:
        ET.SubElement(case, 'failure').text = evidence.get('error', 'Incomplete qualification')
    ET.ElementTree(suite).write(output / 'opcua.xml', encoding='utf-8', xml_declaration=True)


async def qualify(args, evidence):
    from asyncua import Client, ua
    from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256
    import pyads

    if args.ads_dll_directory:
        dll_directory = os.add_dll_directory(str(args.ads_dll_directory))
    password = os.environ[args.password_env]
    prefix = 'MAIN.rpcOutput' if args.fixture == 'Testing' else 'MAIN.machine.advanceOutput'
    expected_port = 853 if args.fixture == 'Testing' else 851
    require(args.port == expected_port, 'Fixture does not match the specified ADS port')

    async def new_client(user=args.user, password_value=password, certificate=None, key=None, uri=None):
        client = Client(args.endpoint, timeout=10)
        client.application_uri = uri or args.application_uri
        await client.set_security(SecurityPolicyBasic256Sha256, certificate or args.certificate,
                                  key or args.key, server_certificate=args.server_certificate)
        if user is not None:
            client.set_user(user)
            client.set_password(password_value)
        return client

    async def check(name, action):
        item = {'name': name, 'passed': False}
        evidence['checks'].append(item)
        try:
            item['result'] = await action()
            item['passed'] = True
        except Exception as exc:
            # Never emit server response bodies or credentials from connection errors.
            item['error'] = type(exc).__name__ + ': ' + str(exc) if isinstance(exc, AssertionError) else type(exc).__name__
            raise

    with pyads.Connection(args.target, args.port) as ads:
        def read(path, kind=pyads.PLCTYPE_DINT):
            return ads.read_by_name(path, kind)

        def pump(enabled):
            ads.write_by_name('MAIN.enableRpcPump', enabled, pyads.PLCTYPE_BOOL)

        def output():
            return read(prefix + '.outSignal', pyads.PLCTYPE_BOOL)

        require(ads.read_state()[0] == 5, 'PLC must be in RUN')
        require(read(prefix + '._operatorMailbox.ownerTask') > 0, 'Owning cyclic task has not executed')
        if args.fixture == 'Example':
            require(read('MAIN.machine.outputsInhibited', pyads.PLCTYPE_BOOL), 'Example must be inhibited')
        else:
            require(read('MAIN.enableRpcPump', pyads.PLCTYPE_BOOL), 'Testing pump must initially be enabled')
        original_lock = read(prefix + '.bSourceLockedToProg', pyads.PLCTYPE_BOOL)
        sequence = time.time_ns() // 1000

        def request_id():
            nonlocal sequence
            sequence += 1
            return sequence

        client = await new_client()
        async with client:
            ns = await client.get_namespace_index(args.namespace)
            evidence['namespace_index'] = ns
            require(await client.get_node(f'ns={ns};i=1302').read_value() == 0, 'OPC UA backend reports an error')

            async def call(c, method, ident):
                return await c.get_node(f'ns={ns};s={prefix}').call_method(
                    c.get_node(f'ns={ns};s={prefix}#{method}'), ua.Variant(ident, ua.VariantType.UInt64))

            async def result(ident):
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    value = await call(client, 'OperatorCommandResult', ident)
                    if value not in (1, 22):
                        return value
                    await asyncio.sleep(.01)
                raise AssertionError('Command result timed out')

            async def safe():
                ident = request_id()
                require(await call(client, 'OperatorForceSafe', ident) == 1, 'ForceSafe not admitted')
                require(await result(ident) == 0, 'ForceSafe not completed')
                owner = read(prefix + '._operatorMailbox.ownerTask')
                require(read(prefix + '._operatorMailbox.lastExecutionTask') == owner and owner > 0,
                        'Command did not execute in cyclic owner')
                require(not output(), 'Safe output not off')
                require(await call(client, 'OperatorForceSafe', ident) == 35, 'Duplicate not rejected')
                return {'owner_task': owner, 'output': False}

            try:
                await check('safe-dispatch-and-duplicate', safe)

                async def invalid():
                    require(await call(client, 'OperatorForceSafe', 0) == 30, 'Zero ID accepted')
                    require(await call(client, 'OperatorCommandResult', request_id()) == 34, 'Unknown ID accepted')
                await check('invalid-and-unknown-request', invalid)

                async def concurrent():
                    async with AsyncExitStack() as stack:
                        clients = [await stack.enter_async_context(await new_client()) for _ in range(args.clients)]
                        shared = request_id()
                        replies = await asyncio.gather(*(call(c, 'OperatorForceSafe', shared) for c in clients))
                        validate_admission(replies, duplicate=True)
                        require(await result(shared) == 0, 'Concurrent winner did not execute')
                        require(not output(), 'Concurrent safe command left output on')
                        return replies
                await check('independent-client-duplicate-race', concurrent)

                if args.fixture == 'Testing':
                    async def priority():
                        async with AsyncExitStack() as stack:
                            clients = [await stack.enter_async_context(await new_client()) for _ in range(args.clients)]
                            pump(False)
                            await asyncio.sleep(.05)
                            ids = [request_id() for _ in clients]
                            replies = await asyncio.gather(*(call(c, 'OperatorSetOff', i) for c, i in zip(clients, ids)))
                            validate_admission(replies)
                            winner = ids[replies.index(1)]
                            ident = request_id()
                            require(await call(client, 'OperatorForceSafe', ident) == 1, 'Safe priority failed')
                            require(await result(winner) == 2, 'Superseded request not cancelled')
                            require(await call(client, 'OperatorSetOn', request_id()) == 22, 'Normal command displaced safe')
                            pump(True)
                            require(await result(ident) == 0, 'Safe winner did not execute')
                            require(not output(), 'Priority cleanup left output on')
                            return replies
                    await check('paused-owner-admission-and-priority', priority)

                    async def source_lock():
                        ads.write_by_name(prefix + '.bSourceLockedToProg', True, pyads.PLCTYPE_BOOL)
                        await asyncio.sleep(.05)
                        ident = request_id()
                        require(await call(client, 'OperatorSetOn', ident) == 1, 'Locked command not queued')
                        require(await result(ident) == 11, 'Owner did not reject locked operator command')
                        return await safe()
                    await check('source-lock-and-safe-exception', source_lock)
                else:
                    async def inhibition():
                        replies = []
                        for _ in range(12):
                            ident = request_id()
                            admission = await call(client, 'OperatorSetOn', ident)
                            final = await result(ident) if admission == 1 else None
                            require((admission == 1 and final == 2) or admission == 22, 'Inhibition did not cancel normal command')
                            require(not output(), 'Observed output on while inhibited')
                            replies.append([admission, final])
                        return replies
                    await check('inhibited-program-cancels-operator', inhibition)

                async def anonymous():
                    try:
                        async with await new_client(user=None):
                            raise AssertionError('Anonymous session accepted')
                    except ua.UaStatusCodeError as exc:
                        require(exc.code in (ua.StatusCodes.BadIdentityTokenRejected, ua.StatusCodes.BadUserAccessDenied),
                                'Anonymous test failed for an unrelated reason')
                        return type(exc).__name__
                await check('anonymous-denied', anonymous)

                if args.observer_user:
                    async def observer():
                        async with await new_client(args.observer_user, os.environ[args.observer_password_env]) as limited:
                            require(await limited.get_node(f'ns={ns};i=1302').read_value() == 0, 'Observer cannot read')
                            try:
                                await call(limited, 'OperatorForceSafe', request_id())
                                raise AssertionError('Observer executed command')
                            except ua.UaStatusCodeError as exc:
                                require(exc.code == ua.StatusCodes.BadUserAccessDenied, 'Observer failed for unrelated reason')
                    await check('observer-read-and-method-denial', observer)
            finally:
                if args.fixture == 'Testing':
                    ads.write_by_name(prefix + '.bSourceLockedToProg', original_lock, pyads.PLCTYPE_BOOL)
                    pump(True)
                    await asyncio.sleep(.05)
                await check('verified-safe-cleanup', safe)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--endpoint', required=True)
    p.add_argument('--target', required=True, help='ADS Net ID; existing route required')
    p.add_argument('--port', type=int, required=True)
    p.add_argument('--fixture', choices=['Example', 'Testing'], required=True)
    p.add_argument('--namespace', required=True)
    p.add_argument('--certificate', type=Path, required=True)
    p.add_argument('--key', type=Path, required=True)
    p.add_argument('--server-certificate', type=Path, required=True)
    p.add_argument('--application-uri', required=True)
    p.add_argument('--user', required=True)
    p.add_argument('--password-env', default='TCFORGE_OPCUA_PASSWORD')
    p.add_argument('--observer-user')
    p.add_argument('--observer-password-env', default='TCFORGE_OPCUA_OBSERVER_PASSWORD')
    p.add_argument('--ads-dll-directory', type=Path)
    p.add_argument('--clients', type=int, choices=range(2, 17), default=8)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    evidence = {'schema': 1, 'passed': False, 'checks': [], 'fixture': args.fixture,
                'target': args.target, 'port': args.port, 'endpoint': args.endpoint,
                'namespace': args.namespace, 'clients': args.clients,
                'scope': 'Configured fixture checks only; not complete production qualification',
                'observer_test_requested': bool(args.observer_user)}
    try:
        evidence['runner_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        evidence['server_certificate_sha256'] = hashlib.sha256(args.server_certificate.read_bytes()).hexdigest()
        asyncio.run(qualify(args, evidence))
        evidence['passed'] = True
    except Exception as exc:
        evidence['error'] = type(exc).__name__ + ': ' + str(exc) if isinstance(exc, AssertionError) else type(exc).__name__
    finally:
        write_report(args.output, evidence)
    print(json.dumps(evidence, indent=2))
    return 0 if evidence['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
