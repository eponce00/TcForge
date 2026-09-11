import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_architecture_boundaries import validate_gap, validate_ownership


def gap_evidence():
    data = dict(previousGapCount=0, gapCount=1, gapCycleDelta=25,
                stoppedCyclesBefore=79, stoppedCyclesAfter=79)
    for machine in ('Home', 'Start'):
        data.update({f'gap{machine}Response': 51, f'gap{machine}Advance': 0,
                     f'gap{machine}Retract': 0, f'gap{machine}Inhibited': 1})
    return data


def ownership_evidence():
    return dict(ownershipOwnerTask=1, ownershipWitnessTask=2,
                ownershipInitialAdmission=1, ownershipInitialResult=0,
                ownershipInitiallyOn=True, ownershipQueued=1,
                ownershipCancelled=2, ownershipRejected=13,
                ownershipConflict=True, ownershipFinalOutput=False,
                outSignal=False, lastExecutionTask=1)


class ArchitectureEvidenceTests(unittest.TestCase):
    def test_valid_gap(self):
        validate_gap(gap_evidence())

    def test_requires_real_fresh_gap_and_stopped_execution(self):
        for name, value in (('gapCount', 0), ('gapCount', 2),
                            ('gapCycleDelta', 1), ('stoppedCyclesAfter', 80)):
            with self.subTest(name=name, value=value):
                data = gap_evidence(); data[name] = value
                with self.assertRaises(AssertionError): validate_gap(data)

    def test_either_command_or_coil_can_fail_first_scan(self):
        for machine in ('Home', 'Start'):
            for suffix, value in (('Response', 0), ('Advance', 1),
                                  ('Retract', 1), ('Inhibited', 0)):
                with self.subTest(machine=machine, field=suffix):
                    data = gap_evidence(); data[f'gap{machine}{suffix}'] = value
                    with self.assertRaises(AssertionError): validate_gap(data)

    def test_valid_ownership(self):
        validate_ownership(ownership_evidence())

    def test_missing_second_task_or_wrong_executor_cannot_pass(self):
        for name, value in (('ownershipWitnessTask', 0), ('ownershipWitnessTask', 1),
                            ('ownershipOwnerTask', 0), ('lastExecutionTask', 2)):
            with self.subTest(name=name, value=value):
                data = ownership_evidence(); data[name] = value
                with self.assertRaises(AssertionError): validate_ownership(data)

    def test_each_mailbox_stage_and_output_is_required(self):
        for name, value in (('ownershipInitialAdmission', 0), ('ownershipInitialResult', 1),
                            ('ownershipInitiallyOn', False), ('ownershipQueued', 0),
                            ('ownershipCancelled', 0), ('ownershipRejected', 1),
                            ('ownershipConflict', False), ('ownershipFinalOutput', True),
                            ('outSignal', True)):
            with self.subTest(name=name):
                data = ownership_evidence(); data[name] = value
                with self.assertRaises(AssertionError): validate_ownership(data)


if __name__ == '__main__':
    unittest.main()
