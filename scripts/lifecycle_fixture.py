"""ADS access to the isolated, unmapped lifecycle qualification fixture."""
import os
import time


def connect(target, port):
    directory = os.add_dll_directory(r'C:\Program Files (x86)\Beckhoff\TwinCAT\Common64')
    import pyads
    connection = pyads.Connection(target, port)
    try:
        connection.open()
        connection.set_timeout(2000)
    except BaseException:
        connection.close()
        directory.close()
        raise
    return directory, pyads, connection


def observe(connection, pyads):
    fields = {
        'applicationMarker': pyads.PLCTYPE_UINT, 'markerAtInitialization': pyads.PLCTYPE_UINT,
        'completedSequence': pyads.PLCTYPE_UDINT, 'onlineChangeCount': pyads.PLCTYPE_UDINT,
        'cycles': pyads.PLCTYPE_ULINT, 'analogRaw': pyads.PLCTYPE_REAL,
        'diagnosticLastFault': pyads.PLCTYPE_DINT,
    }
    for name in ('defaultOutput', 'defaultInhibited', 'restoreOutput', 'restoreInhibited',
                 'analogInhibited', 'alarmActive', 'alarmLatched', 'alarmAcked',
                 'diagnosticFaulted', 'bootDataLoadedAtInitialization', 'oldBootDataAtInitialization'):
        fields[name] = pyads.PLCTYPE_BOOL
    return {name: connection.read_by_name('MAIN.lifecycle.' + name, kind) for name, kind in fields.items()}


def command(connection, pyads, code):
    sequence = connection.read_by_name('MAIN.lifecycle.completedSequence', pyads.PLCTYPE_UDINT) + 1
    if sequence > 0xFFFFFFFF:
        raise OverflowError('Lifecycle sequence exhausted; reinitialize the fixture')
    connection.write_by_name('MAIN.lifecycle.commandCode', code, pyads.PLCTYPE_UINT)
    connection.write_by_name('MAIN.lifecycle.commandSequence', sequence, pyads.PLCTYPE_UDINT)
    deadline = time.perf_counter() + 2
    while connection.read_by_name('MAIN.lifecycle.completedSequence', pyads.PLCTYPE_UDINT) != sequence:
        if time.perf_counter() > deadline:
            raise TimeoutError('Lifecycle fixture command was not completed')
        time.sleep(0.01)
    if not connection.read_by_name('MAIN.lifecycle.commandAccepted', pyads.PLCTYPE_BOOL):
        raise AssertionError('Lifecycle fixture rejected command')


def capture(target, port, seed=None):
    directory, pyads, connection = connect(target, port)
    try:
        if seed:
            command(connection, pyads, 1)
            if seed != 'seed':
                command(connection, pyads, {'safe': 2, 'reset': 3}[seed])
        result = observe(connection, pyads)
        if seed:
            validate_seeded(result, seed)
        return result
    finally:
        connection.close()
        directory.close()


def clear_outputs(target, port):
    directory, pyads, connection = connect(target, port)
    try:
        command(connection, pyads, 2)
        result = observe(connection, pyads)
        assert not result['defaultOutput'] and result['defaultInhibited'], 'Default fixture cleanup failed'
        assert not result['restoreOutput'] and result['restoreInhibited'], 'Restore fixture cleanup failed'
        assert result['analogInhibited'] and result['analogRaw'] == 17, 'Analog fixture cleanup failed'
        return result
    finally:
        connection.close()
        directory.close()


def validate_seeded(snapshot, policy):
    if policy not in ('seed', 'safe', 'reset'):
        raise ValueError('Unknown lifecycle state')
    assert snapshot['applicationMarker'] == 49374, 'Fixture marker was not seeded'
    armed = policy == 'seed'
    assert snapshot['defaultOutput'] == armed and snapshot['defaultInhibited'] != armed, 'Default fixture precondition failed'
    assert snapshot['restoreOutput'] == armed and snapshot['restoreInhibited'] != armed, 'Restore fixture precondition failed'
    assert snapshot['analogRaw'] == (42 if armed else 17) and snapshot['analogInhibited'] != armed, 'Analog fixture precondition failed'
    assert snapshot['alarmActive'] and snapshot['alarmLatched'] and not snapshot['alarmAcked'], 'Alarm fixture was not seeded'
    assert snapshot['diagnosticLastFault'] != 0, 'Diagnostic history was not seeded'
    assert snapshot['diagnosticFaulted'] == (policy != 'reset'), 'Diagnostic fixture precondition failed'


def validate_restored(before, after, policy):
    validate_seeded(before, policy)
    trusted_image = bool(after['bootDataLoadedAtInitialization']) and not after['oldBootDataAtInitialization']
    restore_expected = policy == 'seed' and trusted_image
    assert before['applicationMarker'] == after['applicationMarker'] == after['markerAtInitialization'] == 49374, 'Persistent application marker was not restored'
    assert after['completedSequence'] == 0, 'Volatile command protocol did not reset'
    assert not after['defaultOutput'] and after['defaultInhibited'], 'Default output restored intent'
    if restore_expected:
        assert after['restoreOutput'] and not after['restoreInhibited'], 'Valid saved inverted DO command not restored'
        assert after['analogRaw'] == 42 and not after['analogInhibited'], 'Saved AO command not restored'
    else:
        assert not after['restoreOutput'] and after['restoreInhibited'], 'Untrusted or invalidated saved DO command restored'
        assert after['analogRaw'] == 17 and after['analogInhibited'], 'Untrusted or invalidated saved AO command restored'
    assert after['alarmActive'] and after['alarmLatched'] and not after['alarmAcked'], 'Alarm latch was not preserved'
    assert after['diagnosticLastFault'] == before['diagnosticLastFault'] != 0, 'Fault history was not preserved'
    assert not after['diagnosticFaulted'], 'Active fault was incorrectly restored'

    return {'trusted_image': trusted_image, 'output_restore_expected': restore_expected,
            'scope': 'Observed runtime restoration policy; not power-loss durability'}
