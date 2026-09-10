import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_opcua import validate_admission, write_report


class OpcUaEvidenceTests(unittest.TestCase):
    def test_multiple_or_absent_winners_fail(self):
        for replies in ([1, 1], [22, 22], [1, 0], [1]):
            with self.subTest(replies=replies), self.assertRaises(AssertionError):
                validate_admission(replies)

    def test_duplicate_and_unique_request_races_have_different_contracts(self):
        validate_admission([1, 22, 35], duplicate=True)
        validate_admission([22, 1, 22])
        with self.assertRaises(AssertionError):
            validate_admission([1, 35])

    def test_setup_or_cleanup_failure_cannot_be_reported_as_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            evidence = {'passed': False, 'error': 'Cleanup failed',
                        'checks': [{'name': 'command', 'passed': True}]}
            write_report(output, evidence)
            self.assertFalse(json.loads((output / 'opcua.json').read_text())['passed'])
            root = ET.parse(output / 'opcua.xml').getroot()
            self.assertEqual(root.get('failures'), '1')
            self.assertEqual(len(root.findall('.//failure')), 1)


if __name__ == '__main__':
    unittest.main()
