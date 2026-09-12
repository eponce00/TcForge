import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_online_change import validate_change, validate_retained, cycle_command


class OnlineChangeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.before = dict(
            boot=123,
            clamp_advance=1,
            clamp_retract=0,
            faulted=0,
            inhibited=0,
        )
        self.after = dict(
            self.before,
            boot=124,
            session=0,
            clamp_advance=0,
            inhibited=1,
        )

    def test_one_change_new_epoch_and_inhibited_passes(self):
        for mode in ("idle", "moving"):
            validate_change(self.before, self.after, 5, 6, mode)

    def test_cycling_restarts_ready_but_rejects_faults_and_lost_io(self):
        ready = dict(state=16, faulted=0, healthy=1, inhibited=1)
        self.assertEqual(cycle_command(ready), 2)
        self.assertEqual(cycle_command(dict(ready, state=1, inhibited=0)), 0)
        for invalid in (
            dict(ready, faulted=1),
            dict(ready, healthy=0),
            dict(ready, state=1),
        ):
            with self.assertRaises(AssertionError):
                cycle_command(invalid)

    def test_retracting_is_motion_but_idle_and_conflicting_coils_are_not(self):
        validate_change(
            dict(self.before, clamp_advance=0, clamp_retract=1),
            self.after,
            5,
            6,
            "moving",
        )
        for advance, retract in ((0, 0), (1, 1)):
            with self.assertRaises(AssertionError):
                validate_change(
                    dict(
                        self.before,
                        clamp_advance=advance,
                        clamp_retract=retract,
                    ),
                    self.after,
                    5,
                    6,
                    "moving",
                )

    def test_download_restart_or_no_change_cannot_pass(self):
        for count, boot in ((5, 124), (0, 124), (7, 124), (6, 123), (6, 0)):
            with self.subTest(count=count, boot=boot):
                with self.assertRaises(AssertionError):
                    validate_change(
                        self.before, dict(self.after, boot=boot), 5, count, "moving"
                    )

    def test_unhealthy_or_absent_motion_precondition_rejected(self):
        for field, value in (
            ("clamp_advance", 0),
            ("clamp_retract", 1),
            ("faulted", 1),
        ):
            with self.assertRaises(AssertionError):
                validate_change(
                    dict(self.before, **{field: value}), self.after, 5, 6, "moving"
                )

    def test_either_coil_or_uninhibited_intent_rejected(self):
        for field, value in (
            ("clamp_advance", 1),
            ("clamp_retract", 1),
            ("inhibited", 0),
            ("session", 12),
        ):
            with self.assertRaises(AssertionError):
                validate_change(
                    self.before, dict(self.after, **{field: value}), 5, 6, "moving"
                )

    def test_lifecycle_history_must_continue_without_reinitialization(self):
        before = dict(
            applicationMarker=49374,
            markerAtInitialization=0,
            completedSequence=2,
            diagnosticLastFault=1,
            alarmActive=True,
            alarmLatched=True,
            alarmAcked=False,
            cycles=100,
        )
        after = dict(before, cycles=200)
        validate_retained(before, after)
        for field, value in (
            ("applicationMarker", 0),
            ("completedSequence", 0),
            ("cycles", 1),
            ("diagnosticLastFault", 0),
            ("alarmLatched", False),
        ):
            with self.assertRaises(AssertionError):
                validate_retained(before, dict(after, **{field: value}))

    def test_compatible_edit_requires_continuous_motion_and_same_session(self):
        before = dict(self.before, session=42)
        validate_change(before, before, 5, 6, "moving", "preserve")
        for field, value in (
            ("boot", 124),
            ("session", 0),
            ("clamp_advance", 0),
            ("clamp_retract", 1),
            ("faulted", 1),
            ("inhibited", 1),
        ):
            with self.subTest(field=field), self.assertRaises(AssertionError):
                validate_change(
                    before, dict(before, **{field: value}), 5, 6, "moving", "preserve"
                )
        with self.assertRaises(AssertionError):
            validate_change(before, before, 5, 5, "moving", "preserve")


if __name__ == "__main__":
    unittest.main()
