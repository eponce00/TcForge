"""Acceptance rules for controlled persistent-image recovery on the unmapped fixture."""

def validate_image(snapshot, kind, corrupt_recovery=None):
    if kind not in ('missing', 'backup_only', 'corrupt_current_with_backup'):
        raise ValueError('Unknown persistent-image case')
    if kind == 'corrupt_current_with_backup' and corrupt_recovery not in ('reinitialize', 'backup'):
        raise ValueError('Explicit corrupt-image recovery expectation is required')
    def require(condition, message):
        if not condition:
            raise AssertionError(message)
    require(snapshot['completedSequence'] == 0, 'Volatile command protocol survived restart')
    require(not snapshot['defaultOutput'] and snapshot['defaultInhibited'], 'Default output restored')
    require(not snapshot['restoreOutput'] and snapshot['restoreInhibited'], 'Untrusted saved output restored')
    require(snapshot['analogInhibited'] and snapshot['analogRaw'] == 17, 'Untrusted analog output restored')
    reinitialized = kind == 'missing' or (kind == 'corrupt_current_with_backup' and corrupt_recovery == 'reinitialize')
    if reinitialized:
        require(not snapshot['bootDataLoadedAtInitialization'], 'Reinitialized data reported loaded')
        require(not snapshot['oldBootDataAtInitialization'], 'Reinitialized data reported backup')
        require(snapshot['applicationMarker'] == snapshot['markerAtInitialization'] == 0,
                'Reinitialized data retained application marker')
        require(not snapshot['alarmLatched'] and snapshot['diagnosticLastFault'] == 0,
                'Reinitialized data retained diagnostic history')
    else:
        require(snapshot['oldBootDataAtInitialization'], 'Backup was not loaded')
        require(snapshot['applicationMarker'] == snapshot['markerAtInitialization'] == 49374,
                'Backup marker was not restored')
        require(snapshot['alarmLatched'] and snapshot['diagnosticLastFault'] != 0,
                'Backup diagnostic history missing')
    return {'passed': True, 'case': kind, 'recovery': 'reinitialize' if reinitialized else 'backup',
            'scope': 'Controlled image recovery, not power-loss durability'}
