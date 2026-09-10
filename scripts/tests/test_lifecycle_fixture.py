import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lifecycle_fixture import validate_restored, validate_seeded


def snapshots(policy='seed', loaded=True, old=False):
    armed = policy == 'seed'
    before = dict(applicationMarker=49374, defaultOutput=armed, defaultInhibited=not armed,
                  restoreOutput=armed, restoreInhibited=not armed, analogRaw=42 if armed else 17,
                  analogInhibited=not armed, alarmActive=True, alarmLatched=True, alarmAcked=False,
                  diagnosticLastFault=1, diagnosticFaulted=policy != 'reset')
    after = dict(before, markerAtInitialization=49374, completedSequence=0,
                 defaultOutput=False, defaultInhibited=True, diagnosticFaulted=False,
                 bootDataLoadedAtInitialization=loaded, oldBootDataAtInitialization=old)
    restored = armed and loaded and not old
    after.update(restoreOutput=restored, restoreInhibited=not restored,
                 analogRaw=42 if restored else 17, analogInhibited=not restored)
    return before, after


class LifecycleEvidenceTests(unittest.TestCase):
    def test_seed_restores_only_with_trusted_image(self):
        for loaded, old in ((True, False), (False, False), (True, True), (False, True)):
            with self.subTest(loaded=loaded, old=old):
                result = validate_restored(*snapshots(loaded=loaded, old=old), 'seed')
                self.assertEqual(result['output_restore_expected'], loaded and not old)

    def test_untrusted_image_cannot_pass_with_replayed_command(self):
        before, after = snapshots(loaded=False)
        after.update(restoreOutput=True, restoreInhibited=False, analogRaw=42, analogInhibited=False)
        with self.assertRaises(AssertionError):
            validate_restored(before, after, 'seed')

    def test_safe_and_reset_intent_stays_invalid_even_with_trusted_image(self):
        for policy in ('safe', 'reset'):
            before, after = snapshots(policy)
            self.assertFalse(validate_restored(before, after, policy)['output_restore_expected'])
            after.update(analogRaw=42, analogInhibited=False)
            with self.assertRaises(AssertionError):
                validate_restored(before, after, policy)

    def test_seed_requires_actual_device_preconditions(self):
        before, _ = snapshots()
        before.update(defaultOutput=False, defaultInhibited=True)
        with self.assertRaises(AssertionError):
            validate_seeded(before, 'seed')

    def test_marker_or_volatile_protocol_failure_cannot_pass(self):
        for field, value in (('applicationMarker', 0), ('markerAtInitialization', 0),
                             ('completedSequence', 1), ('diagnosticLastFault', 0)):
            with self.subTest(field=field):
                before, after = snapshots()
                after[field] = value
                with self.assertRaises(AssertionError):
                    validate_restored(before, after, 'seed')


if __name__ == '__main__':
    unittest.main()
