"""Read-only, bounded readiness checks after TwinCAT restart.

Each attempt runs in a fresh process so stale ADS handles/native client state do
not survive retries. No route repair, service control or PLC commands are issued.
"""
import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time


def wait_ready(command, timeout, attempt_timeout, interval, required=2,
               run=subprocess.run, clock=time.monotonic, sleep=time.sleep):
    if not all(math.isfinite(v) and v > 0 for v in (timeout, attempt_timeout, interval)) or required < 1:
        raise ValueError('Timeouts, interval and required successes must be positive')
    start = clock()
    deadline = start + timeout
    attempts = []
    consecutive = 0
    while clock() < deadline:
        remaining = deadline - clock()
        try:
            result = run(command, capture_output=True, text=True,
                         timeout=min(attempt_timeout, remaining), check=False)
            # Only the structured probe result enters the report, never stderr.
            payload = json.loads(result.stdout)
            if not isinstance(payload, dict):
                raise ValueError('Expected probe object')
            success = result.returncode == 0 and payload.get('ready') is True
            item = {'ready': success, 'probe': payload}
        except subprocess.TimeoutExpired:
            success = False
            item = {'ready': False, 'error': 'ProbeTimeout'}
        except (ValueError, TypeError):
            success = False
            item = {'ready': False, 'error': 'InvalidProbeResponse'}
        item['elapsed_seconds'] = round(clock() - start, 3)
        attempts.append(item)
        consecutive = consecutive + 1 if success else 0
        if consecutive >= required:
            return {'ready': True, 'attempts': attempts,
                    'elapsed_seconds': round(clock() - start, 3)}
        remaining = deadline - clock()
        if remaining > 0:
            sleep(min(interval, remaining))
    return {'ready': False, 'attempts': attempts,
            'elapsed_seconds': round(clock() - start, 3)}


async def ua_probe(config):
    from asyncua import Client
    from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256
    client = Client(config['endpoint'], timeout=3)
    client.application_uri = config['application_uri']
    await client.set_security(SecurityPolicyBasic256Sha256,
                              config['certificate'], config['key'],
                              server_certificate=config['server_certificate'])
    client.set_user(config['user'])
    client.set_password(os.environ[config['password_env']])
    async with client:
        ns = await client.get_namespace_index(config['namespace'])
        error = await client.get_node(f'ns={ns};i=1302').read_value()
        if error != 0:
            raise RuntimeError('OPC UA PLC device is not ready')
        return {'authenticated': True, 'device_error': error}


def probe(config):
    directory = None
    report = {'ready': False, 'stage': 'ads-system'}
    try:
        if os.name == 'nt':
            directory = os.add_dll_directory(config['ads_dll_directory'])
        import pyads
        with pyads.Connection(config['target'], 10000) as system:
            system.set_timeout(1500)
            report['system_state'] = list(system.read_state())
        if report['system_state'][0] != 5:
            return report
        report['stage'] = 'plc-cyclic'
        with pyads.Connection(config['target'], config['port']) as plc:
            plc.set_timeout(1500)
            if plc.read_state()[0] != 5:
                return report
            if config['fixture'] == 'Example':
                from verify_cyclic_task import verify
                report['cyclic'] = verify(plc)
            elif config['fixture'] == 'Testing':
                owner = plc.read_by_name('MAIN.rpcContext.ownerTask', pyads.PLCTYPE_DINT)
                if owner <= 0:
                    raise RuntimeError('Test task owner is uninitialized')
                symbol = f'TwinCAT_SystemInfoVarList._TaskInfo[{owner}].CycleCount'
                before = plc.read_by_name(symbol, pyads.PLCTYPE_UDINT)
                time.sleep(.15)
                after = plc.read_by_name(symbol, pyads.PLCTYPE_UDINT)
                if before == after:
                    raise RuntimeError('Test task is not advancing')
                report['cyclic'] = {'owner': owner, 'before': before, 'after': after}
            else:
                symbol = 'MAIN.lifecycle.cycles'
                before = plc.read_by_name(symbol, pyads.PLCTYPE_ULINT)
                time.sleep(.15)
                after = plc.read_by_name(symbol, pyads.PLCTYPE_ULINT)
                if before == after:
                    raise RuntimeError('Lifecycle task is not advancing')
                report['cyclic'] = {'before': before, 'after': after}
        if 'opcua' in config:
            report['stage'] = 'opcua'
            report['opcua'] = asyncio.run(ua_probe(config['opcua']))
        report['stage'] = 'ready'
        report['ready'] = True
    except Exception as exc:
        # Errors may contain server-controlled messages or secrets. Types and
        # numeric ADS codes are sufficient for retry diagnostics.
        report['error'] = type(exc).__name__
        code = getattr(exc, 'err_code', None)
        if isinstance(code, int):
            report['ads_error_code'] = code
    finally:
        if directory is not None:
            directory.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--timeout', type=float, default=300)
    parser.add_argument('--attempt-timeout', type=float, default=15)
    parser.add_argument('--interval', type=float, default=2)
    parser.add_argument('--probe', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    expected = {'Example': 851, 'Testing': 853, 'Simulation': 854}
    if config.get('fixture') not in expected or config.get('port') != expected[config['fixture']]:
        parser.error('Fixture must match Example/851, Testing/853 or Simulation/854')
    if args.probe:
        result = probe(config)
    else:
        if args.output is None or args.output.exists():
            parser.error('A new --output report path is required')
        result = wait_ready([sys.executable, str(Path(__file__).resolve()),
                             '--config', str(args.config.resolve()), '--probe'],
                            args.timeout, args.attempt_timeout, args.interval)
        result.update(target=config['target'], port=config['port'],
                      opcua_checked='opcua' in config,
                      scope='Read-only readiness; no restart or route repair')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['ready'] else 1


if __name__ == '__main__':
    sys.exit(main())
