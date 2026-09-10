"""Execute discrete assembly scenarios against the real isolated TwinCAT composition."""
import argparse
import json
from pathlib import Path
import time
import traceback
import xml.etree.ElementTree as ET

from .live import AssemblySession, RpcTransport


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run(rpc, trace, suite):
    session = AssemblySession(rpc, trace)

    def check(name, action):
        node = ET.SubElement(suite, 'testcase', name=name, classname='TcForge.Assembly')
        start = time.perf_counter()
        try:
            action()
            print('PASS', name, flush=True)
        except Exception as exc:
            ET.SubElement(node, 'failure', message=str(exc)).text = traceback.format_exc()
            print('FAIL', name, str(exc), flush=True)
            raise
        finally:
            node.set('time', str(time.perf_counter() - start))

    def ready():
        session.plant.jammed = False
        session.plant.advanced_override = None
        session.plant.retracted_override = None
        session.quality_good = True
        session.shutdown_confirmed = True
        # Recover existing shutdown first; reconnect never silently resets the machine.
        session.until(lambda s: s['state'] == 0, command=4)
        session.tick(0)
        state = session.tick(5)
        require(state['response'] == 0, 'Explicit Reset rejected')
        session.tick(0)
        session.until(lambda s: s['state'] == 16, command=1)

    def protocol():
        # Feed the live model between rejection probes. Several network round trips
        # must not consume the entire watchdog window before the first IO frame.
        session.tick()
        require(rpc.call('claim', 0, session.boot) == 30, 'Zero client accepted')
        session.tick()
        require(rpc.call('claim', session.session + 1, session.boot) == 11, 'Second writer accepted')
        session.tick()
        require(rpc.call('claim', session.session, session.boot + 1) == 34, 'Wrong boot accepted')
        snapshot = session.tick()
        require(rpc.call('exchange', session.session, session.boot, session.sequence + 1, snapshot['cycle'], 0, 1, 1, 1, 99) == 30,
                'Invalid command admitted')
        require(rpc.snapshot()['applied'] == session.sequence, 'Invalid command changed applied sequence')
        state = session.tick()
        require(rpc.call('exchange', session.session, session.boot, session.sequence, state['cycle'], 1, 1, 1, 1, 0) == 35,
                'Duplicate frame accepted')
        require(rpc.snapshot()['applied'] == session.sequence, 'Rejected frame changed applied sequence')
        require(state['owner'] > 0, 'No cyclic owner')

    def full_cycle():
        ready()
        session.until(lambda s: s['advance'] == 1, command=2)
        session.until(lambda s: s['retract'] == 1)
        session.until(lambda s: s['state'] == 16)
        require(session.plant.position < 1e-9, 'Cycle did not physically retract the model')

    def stop():
        session.until(lambda s: s['advance'] == 1, command=2)
        session.until(lambda s: s['state'] == 0, command=3)
        require(session.plant.position < 1e-9, 'Controlled Stop did not retract')

    def abort():
        ready()
        session.until(lambda s: s['advance'] == 1, command=2)
        result = session.until(lambda s: s['state'] == 0, command=4)
        require(not result['advance'] and not result['retract'], 'Abort left coils on')

    def jam():
        ready()
        session.plant.jammed = True
        result = session.until(lambda s: s['faulted'] == 1, timeout=8, command=2)
        require(not result['advance'] and not result['retract'], 'Jam timeout did not remove outputs')

    def shutdown_confirmation():
        ready()
        session.until(lambda s: s['advance'] == 1, command=2)
        session.shutdown_confirmed = False
        result = session.tick(4)
        require(not result['advance'] and not result['retract'], 'Abort did not remove coils immediately')
        # Coils off is insufficient: a failed independent confirmation must latch a fault.
        result = session.until(lambda s: s['faulted'] == 1, timeout=4)
        require(not result['advance'] and not result['retract'], 'Shutdown timeout energized an output')
        session.tick(0)
        result = session.tick(5)
        require(result['response'] != 0 and result['faulted'], 'Reset bypassed missing shutdown confirmation')
        session.shutdown_confirmed = True
        session.tick(0)
        result = session.tick(5)
        require(result['response'] == 0 and not result['faulted'], 'Trusted confirmation did not allow explicit Reset')
        require(not result['advance'] and not result['retract'], 'Recovery restarted motion')

    def contradiction():
        ready()
        session.plant.advanced_override = True
        session.plant.retracted_override = True
        result = session.until(lambda s: s['faulted'] == 1)
        require(not result['advance'] and not result['retract'], 'Conflicting sensors did not inhibit outputs')

    def bad_quality():
        ready()
        session.until(lambda s: s['advance'] == 1, command=2)
        session.quality_good = False
        result = session.tick()
        require(not result['advance'] and not result['retract'], 'Lost IO quality did not inhibit outputs')

    def watchdog():
        nonlocal session
        ready()
        session.until(lambda s: s['advance'] == 1, command=2)
        plant = session.plant
        old_client = session.session
        time.sleep(0.4)
        state = rpc.snapshot()
        require(state['session'] == 0 and not state['healthy'], 'Stale writer retained session/quality')
        require(not state['advance'] and not state['retract'], 'Watchdog left output energized')
        require(rpc.call('exchange', old_client, session.boot, session.sequence + 1, state['cycle'], 0, 1, 1, 1, 2) == 12,
                'Expired session accepted a delayed Start')
        session = AssemblySession(rpc, trace, plant)
        state = session.tick()
        require(not state['advance'] and not state['retract'], 'Reconnect restarted motion')

    try:
        check('ExclusiveSessionAndRejectedFrames', protocol)
        check('HomeAndAssemblyClampCycle', full_cycle)
        check('ControlledStopRetractsClamp', stop)
        check('AbortRemovesBothCoils', abort)
        check('IndependentShutdownConfirmationAndRecovery', shutdown_confirmation)
        check('JammedCylinderTimesOut', jam)
        check('ContradictoryPositionSensors', contradiction)
        check('LostIOQualityInhibitsOutputs', bad_quality)
        check('SimulatorLossAndExplicitReconnect', watchdog)
        check('ExplicitRecoveryAfterReconnect', ready)
    finally:
        try:
            session.close()
            time.sleep(0.03)
            state = rpc.snapshot()
            require(not state['advance'] and not state['retract'], 'Released fixture not inhibited')
        except Exception:
            # Keep the original failure; the PLC watchdog is independent of cleanup.
            if not suite.findall('.//failure'):
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--transport', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    suite = ET.Element('testsuite', name='TcForge discrete assembly functional tests')
    properties = ET.SubElement(suite, 'properties')
    for name, value in {'target': args.target, 'port': str(args.port), 'time_mode': 'wall-clock'}.items():
        ET.SubElement(properties, 'property', name=name, value=value)
    rpc = None
    failed = False
    try:
        rpc = RpcTransport(args.transport, args.target, args.port)
        with (args.output / 'assembly-trace.jsonl').open('w', encoding='utf-8') as trace:
            run(rpc, trace, suite)
    except Exception as exc:
        failed = True
        if not suite.findall('.//failure'):
            node = ET.SubElement(suite, 'testcase', name='SetupOrCleanup')
            ET.SubElement(node, 'failure', message=str(exc)).text = traceback.format_exc()
    finally:
        if rpc:
            rpc.close()
        suite.set('tests', str(len(suite.findall('testcase'))))
        suite.set('failures', str(len(suite.findall('.//failure'))))
        ET.ElementTree(suite).write(args.output / 'assembly-junit.xml', encoding='utf-8', xml_declaration=True)
    if failed:
        raise SystemExit(1)
    print(f"All {len(suite.findall('testcase'))} assembly functional scenarios passed against the PLC.")


if __name__ == '__main__':
    main()
