"""Exercise the unmapped ArchitectureFixture on an explicitly selected bench PLC.

Requires activate_simulation.ps1 first. Stops/starts that PLC application; never
activates a project or changes the system configuration. Restores RUN and sends
Abort on exit. Uses real system task counters, not injected continuity state.
"""
import argparse
import ctypes
import json
import time
import traceback
from pathlib import Path
import xml.etree.ElementTree as ET

from lifecycle_fixture import connect

PREFIX = 'MAIN.architecture.'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class Fields:
    def __init__(self, connection):
        self.connection, self.fields = connection, {}

    def add(self, name):
        from pyads.pyads_ex import adsGetSymbolInfo
        # Enum names do not resolve to ctypes through AdsSymbol.plc_type.
        # Read the runtime's scalar width rather than guessing its base type.
        size = adsGetSymbolInfo(self.connection._port, self.connection._adr, name).size
        require(size in (1, 2, 4, 8), 'Unexpected scalar size: ' + name)
        self.fields[name] = self.connection.get_handle(name), size

    def read(self, name):
        handle, size = self.fields[name]
        data = self.connection.read_by_name('', ctypes.c_ubyte * size, handle=handle)
        return int.from_bytes(bytes(data), 'little')

    def write(self, name, value):
        handle, size = self.fields[name]
        self.connection.write_by_name('', list(int(value).to_bytes(size, 'little')),
                                      ctypes.c_ubyte * size, handle=handle)

    def close(self):
        for handle, _ in self.fields.values():
            try:
                self.connection.release_handle(handle)
            except Exception:
                pass


def validate_gap(data):
    require(data['gapCount'] == data['previousGapCount'] + 1 and data['gapCycleDelta'] > 1,
            'Exactly one real execution gap required')
    require(data['stoppedCyclesBefore'] == data['stoppedCyclesAfter'], 'PLC code advanced while STOP was asserted')
    for machine in ('Home', 'Start'):
        require(data['gap' + machine + 'Response'] == 51, machine + ' was not rejected on first resumed scan')
        require(not data['gap' + machine + 'Advance'] and not data['gap' + machine + 'Retract'] and
                data['gap' + machine + 'Inhibited'], machine + ' retained output intent at the gap')


def validate_ownership(data):
    require(data['ownershipOwnerTask'] > 0 and data['ownershipWitnessTask'] > 0 and
            data['ownershipOwnerTask'] != data['ownershipWitnessTask'], 'Two distinct real cyclic tasks required')
    require(data['ownershipInitialAdmission'] == 1 and data['ownershipInitialResult'] == 0 and
            data['ownershipInitiallyOn'], 'Owner did not first execute an admitted command')
    require(data['ownershipQueued'] == 1 and data['ownershipCancelled'] == 2 and
            data['ownershipRejected'] == 13, 'Conflict did not cancel queued work and reject subsequent work')
    require(data['ownershipConflict'] and not data['ownershipFinalOutput'] and not data['outSignal'],
            'Conflict was not latched or output was energized')
    require(data['lastExecutionTask'] == data['ownershipOwnerTask'], 'Command executed outside the owner')


def run(target, evidence):
    directory, pyads, connection = connect(target, 854)
    fields = Fields(connection)
    def read(name): return fields.read(PREFIX + name)
    def write(name, value): fields.write(PREFIX + name, value)
    def command(value):
        write('homeCommand', value)
        write('startCommand', value)
    def until(predicate, message, timeout=4):
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if predicate(): return
            time.sleep(.01)
        raise AssertionError(message)
    def state(value):
        return all(read(m + '.sequence.State') == value for m in ('homeMachine', 'startMachine'))
    def coil(name):
        return all(read(m + '.' + name) for m in ('homeMachine', 'startMachine'))
    def safe():
        return all(not read(m + '.' + name) for m in ('homeMachine', 'startMachine')
                   for name in ('outAdvance', 'outRetract'))
    initialized = False
    try:
        require(connection.read_state()[0] == pyads.ADSSTATE_RUN, 'Start with the bench PLC RUN')
        fixture_names = ['enabled', 'cycles', 'gapCount', 'gapCycleDelta', 'homeCommand', 'startCommand', 'advanced', 'retracted']
        gap_names = ['gapCount', 'gapCycleDelta']
        for name in ('Home', 'Start'):
            gap_names += ['gap' + name + suffix for suffix in ('Response', 'Advance', 'Retract', 'Inhibited')]
        for name in set(fixture_names + gap_names): fields.add(PREFIX + name)
        for machine in ('homeMachine', 'startMachine'):
            for name in ('sequence.State', 'outAdvance', 'outRetract', 'lastResponse', 'recoverOnOnlineChange'):
                fields.add(PREFIX + machine + '.' + name)
        ownership_names = ['ownershipPhase', 'ownershipKick', 'ownershipOwnerTask', 'ownershipWitnessTask',
                           'ownershipInitialAdmission', 'ownershipInitialResult', 'ownershipInitiallyOn',
                           'ownershipQueued', 'ownershipCancelled', 'ownershipRejected', 'ownershipFinalOutput']
        for name in ownership_names: fields.add('MAIN.' + name)
        for name in ('ownershipConflict', 'lastExecutionTask'):
            fields.add('MAIN.sharedOutput._operatorMailbox.' + name)
        fields.add('MAIN.sharedOutput.outSignal')
        for name in ('taskIndex', 'cycles'):
            fields.add('PRG_OwnershipWitness.' + name)
        witness_cycles = fields.read('PRG_OwnershipWitness.cycles')
        until(lambda: fields.read('PRG_OwnershipWitness.cycles') > witness_cycles,
              'Ownership witness must be cyclic before stopping the PLC')
        evidence['witnessTaskBefore'] = fields.read('PRG_OwnershipWitness.taskIndex')
        require(evidence['witnessTaskBefore'] > 0, 'Witness is not a cyclic task')
        require(fields.read('MAIN.ownershipPhase') == 0, 'Ownership case is one-shot; activate a fresh fixture')
        initialized = True
        write('enabled', 1)
        command(4); until(lambda: state(0), 'Initial Abort did not stop machines')
        command(0); command(5); command(0)
        command(1); until(lambda: state(16), 'Initial Home did not reach Ready')
        command(0); command(2); until(lambda: coil('outAdvance'), 'Both machines must be advancing before STOP')
        command(0)
        evidence['before'] = {'advance': coil('outAdvance'),
                              'preservationEnabled': all(not read(m + '.recoverOnOnlineChange') for m in ('homeMachine', 'startMachine'))}
        require(all(evidence['before'].values()), 'Motion/preservation precondition missing')
        gap = {'previousGapCount': read('gapCount')}
        started = time.perf_counter()
        connection.write_control(pyads.ADSSTATE_STOP, 0, 0, pyads.PLCTYPE_BYTE)
        require(connection.read_state()[0] == pyads.ADSSTATE_STOP, 'STOP not verified')
        gap['stoppedCyclesBefore'] = read('cycles')
        write('homeCommand', 1); write('startCommand', 2)
        time.sleep(.05)
        gap['stoppedCyclesAfter'] = read('cycles')
        connection.write_control(pyads.ADSSTATE_RUN, 0, 0, pyads.PLCTYPE_BYTE)
        gap['stopRunCallSeconds'] = time.perf_counter() - started
        require(connection.read_state()[0] == pyads.ADSSTATE_RUN, 'RUN not verified')
        until(lambda: read('gapCount') > gap['previousGapCount'], 'No resumed-scan gap captured')
        gap.update({name: read(name) for name in gap_names})
        evidence['interruption'] = gap
        validate_gap(gap)
        cycles = read('cycles')
        until(lambda: read('cycles') >= cycles + 30, 'Held-command observation did not advance')
        require(read('homeCommand') == 1 and read('startCommand') == 2 and safe(), 'Held command resumed motion')
        require(all(read(m + '.lastResponse') == 51 for m in ('homeMachine', 'startMachine')), 'Held command was later accepted')
        evidence['heldCommandsRejected'] = True
        command(4); until(lambda: state(0), 'Recovery Abort did not reach STOPPED')
        command(0); command(5)
        require(all(read(m + '.lastResponse') == 0 for m in ('homeMachine', 'startMachine')), 'Explicit Reset rejected')
        command(0); require(safe(), 'Reset resumed movement')
        command(1); until(lambda: state(16), 'Recovery Home did not complete')
        command(0); command(2); until(lambda: coil('outAdvance'), 'Fresh Start did not advance')
        write('retracted', 0); write('advanced', 1)
        until(lambda: coil('outRetract'), 'Fresh cycle did not retract')
        write('advanced', 0); write('retracted', 1)
        until(lambda: state(16), 'Fresh cycle did not complete')
        evidence['freshCycleCompleted'] = True
        fields.write('MAIN.ownershipKick', 1)
        try:
            until(lambda: fields.read('MAIN.ownershipPhase') == 4, 'Second task did not finish ownership fixture')
        finally:
            evidence['ownershipPhase'] = fields.read('MAIN.ownershipPhase')
        ownership = {name: fields.read('MAIN.' + name) for name in ownership_names if name != 'ownershipKick'}
        for name in ('ownershipConflict', 'lastExecutionTask'):
            ownership[name] = fields.read('MAIN.sharedOutput._operatorMailbox.' + name)
        ownership['outSignal'] = fields.read('MAIN.sharedOutput.outSignal')
        evidence['ownership'] = ownership
        validate_ownership(ownership)
    finally:
        try:
            if initialized:
                if connection.read_state()[0] != pyads.ADSSTATE_RUN:
                    connection.write_control(pyads.ADSSTATE_RUN, 0, 0, pyads.PLCTYPE_BYTE)
                command(4)
                until(safe, 'Cleanup did not remove both machines output intent')
                command(0)
                evidence['cleanupOutputsOff'] = safe() and not fields.read('MAIN.sharedOutput.outSignal')
                require(evidence['cleanupOutputsOff'], 'Fixture output cleanup failed')
        finally:
            fields.close(); connection.close(); directory.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    evidence = {'target': args.target, 'port': 854, 'passed': False,
                'scope': 'Real stop/start and serialized two-task misuse; no physical IO or arbitrary cross-task safety claim'}
    suite = ET.Element('testsuite', name='Architecture boundaries', tests='1')
    case = ET.SubElement(suite, 'testcase', name='interruption_and_ownership')
    try:
        run(args.target, evidence)
        evidence['passed'] = True
    except Exception as exc:
        evidence['failure'] = traceback.format_exc()
        ET.SubElement(case, 'failure', message=str(exc)).text = evidence['failure']
    (args.output / 'evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    suite.set('failures', '0' if evidence['passed'] else '1')
    ET.ElementTree(suite).write(args.output / 'junit.xml', encoding='utf-8', xml_declaration=True)
    print(json.dumps(evidence, indent=2))
    return 0 if evidence['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
