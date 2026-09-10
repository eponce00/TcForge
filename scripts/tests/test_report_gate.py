import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_test_report import validate


class ReportGateTests(unittest.TestCase):
    def check(self, xml, count, identities=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.xml'
            path.write_text(xml, encoding='utf-8')
            return validate(path, count, identities)

    def test_accepts_complete_success(self):
        self.assertEqual(self.check('<testsuite><testcase name="a"/></testsuite>', 1), 1)

    def test_rejects_empty_and_partial(self):
        for xml in ['<testsuites/>', '<testsuite><testcase name="a"/></testsuite>']:
            with self.assertRaises(ValueError):
                self.check(xml, 2)

    def test_rejects_failed_error_and_skipped(self):
        for tag in ['failure', 'error', 'skipped']:
            with self.assertRaises(ValueError):
                self.check(f'<testsuite><testcase name="a"><{tag}/></testcase></testsuite>', 1)

    def test_rejects_duplicate_results(self):
        with self.assertRaises(ValueError):
            self.check('<testsuite><testcase name="a"/><testcase name="a"/></testsuite>', 2)

    def test_rejects_non_junit_xml(self):
        with self.assertRaises(ValueError):
            self.check('<unrelated><testcase name="a"/></unrelated>', 1)

    def test_accepts_exact_identities_in_any_order(self):
        report = '<testsuite><testcase classname="MAIN.s" name="b"/><testcase classname="MAIN.s" name="a"/></testsuite>'
        self.assertEqual(self.check(report, 2, {('MAIN.s', 'a'), ('MAIN.s', 'b')}), 2)

    def test_rejects_wrong_identity_with_correct_count(self):
        for suite, name in (('MAIN.other', 'a'), ('MAIN.s', 'obsolete'), ('', 'a')):
            with self.subTest(suite=suite, name=name), self.assertRaises(ValueError):
                self.check(f'<testsuite><testcase classname="{suite}" name="{name}"/></testsuite>',
                           1, {('MAIN.s', 'a')})

    def test_rejects_expected_identity_count_mismatch(self):
        with self.assertRaises(ValueError):
            self.check('<testsuite><testcase name="a"/></testsuite>', 1, set())


if __name__ == '__main__':
    unittest.main()
