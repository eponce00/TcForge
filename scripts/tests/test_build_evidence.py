import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_evidence as evidence


class BuildEvidenceTests(unittest.TestCase):
    def put(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding='utf-8')
        return path

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.put('toolchain.json', json.dumps(dict(xaeBaseline='3.1.4026.26', platform='TwinCAT RT (x64)', testAdsPort=853)))
        self.put('dependencies.lock.json', '{}')
        self.put('TwinCAT/Testing.plcproj', '<Project><Compile Include="Testing/Tests/FB_Test.TcPOU"/></Project>')
        self.put('TwinCAT/Testing/POUs/MAIN.TcPOU', '<TcPlcObject><POU><Declaration>PROGRAM MAIN VAR s : FB_Test; END_VAR</Declaration></POU></TcPlcObject>')
        self.put('TwinCAT/Testing/Tests/FB_Test.TcPOU', "<TcPlcObject><POU Name='FB_Test'><Implementation><ST>TEST('one');</ST></Implementation></POU></TcPlcObject>")
        self.put('scripts/compiler.ps1', '# compiler wrapper')
        self.put('helper/TcAutomation/Program.cs', '// helper source')
        self.put('helper/TcAutomation/bin/Release-v2/TcAutomation.exe', 'helper binary')
        # Dependency graph semantics have their own checker tests; retain byte checks here.
        def dependencies(record, captures):
            evidence.verify_file(record)
            for capture in captures.values():
                evidence.verify_file(capture)
        mock = patch.object(evidence, 'verify_dependencies', side_effect=dependencies)
        mock.start()
        self.addCleanup(mock.stop)
        self.token = self.root / 'artifacts/build-token.json'
        evidence.begin_build(self.root, self.root / 'helper', self.token)
        for name in evidence.BUILD_RESULTS:
            self.build_json('artifacts/' + name)
        for name in ('TcForge.Library', 'TcForge.Tests', 'TcForge', 'TcForge.Simulation'):
            self.put('artifacts/' + name + '-dependencies.xml', '<resolution/>')
        self.library = self.put('artifacts/TcForge.library', 'new library bytes')
        self.installed = self.put('installed/TcForge.library', 'new library bytes')
        self.manifest = self.root / 'artifacts/build.json'
        evidence.finish_build(self.root, self.token, self.library, self.root / 'dependencies.lock.json', self.manifest)

    def build_json(self, relative):
        return self.put(relative, json.dumps(dict(Success=True, ErrorCount=0, WarningCount=0,
                        RequestedXaeVersion='3.1.4026.26', EffectiveXaeVersion='3.1.4026.26')))

    def run_report(self, period, edit_properties=None, installed=True):
        token = self.root / f'artifacts/run-{period}.json'
        evidence.begin_test(self.root, self.manifest, self.library, period, '1.2.3.4.1.1', token,
                            self.installed if installed else None)
        group = ET.Element('testsuite', name='MAIN.s')
        properties = evidence.report_properties(token)
        properties.update(target='1.2.3.4.1.1', adsPort='853', cycleTime100ns=str(period * 10000))
        if edit_properties:
            edit_properties(properties)
        container = ET.SubElement(group, 'properties')
        for name, value in properties.items():
            ET.SubElement(container, 'property', name=name, value=value)
        ET.SubElement(group, 'testcase', classname='MAIN.s', name='one')
        report = self.root / f'artifacts/report-{period}.xml'
        ET.ElementTree(group).write(report, encoding='utf-8')
        activation = self.build_json(f'artifacts/activation-{period}.json')
        evidence.finish_test(self.root, token, report, activation)
        return report

    def test_accepts_two_fresh_bound_periods(self):
        reports = [self.run_report(1), self.run_report(10)]
        self.assertEqual(evidence.validate_release(self.root, self.manifest, self.library, reports),
                         evidence.read(self.manifest)['buildId'])

    def test_rejects_stale_source_and_compiler_tooling(self):
        for path in ('TwinCAT/Testing/Tests/FB_Test.TcPOU', 'scripts/compiler.ps1', 'dependencies.lock.json'):
            original = (self.root / path).read_text()
            self.put(path, original + ' ')
            with self.assertRaisesRegex(ValueError, 'Source/toolchain changed'):
                evidence.verify_build(self.root, self.manifest, self.library)
            self.put(path, original)

    def test_rejects_tampered_library_and_installed_mismatch(self):
        self.library.write_text('tampered')
        with self.assertRaises(ValueError):
            evidence.verify_build(self.root, self.manifest, self.library)
        self.library.write_text('new library bytes')
        self.installed.write_text('different installed library')
        with self.assertRaisesRegex(ValueError, 'Installed TcForge library differs'):
            self.run_report(1)

    def test_rejects_report_from_other_build_or_wrong_period(self):
        for change in (lambda props: props.update(buildId='other-build'),
                       lambda props: props.update(cycleTime100ns='100000')):
            with self.assertRaisesRegex(ValueError, 'Report identity/period/target differs'):
                self.run_report(1, change)

    def test_rejects_missing_period_and_missing_installed_verification(self):
        report = self.run_report(1)
        with self.assertRaisesRegex(ValueError, 'exactly one 1 ms and one 10 ms'):
            evidence.validate_release(self.root, self.manifest, self.library, [report])
        other = self.run_report(10, installed=False)
        with self.assertRaisesRegex(ValueError, 'verified installed'):
            evidence.validate_release(self.root, self.manifest, self.library, [report, other])

    def test_rejects_tampered_report_after_receipt(self):
        reports = [self.run_report(1), self.run_report(10)]
        reports[0].write_text(reports[0].read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'Changed evidence/library file'):
            evidence.validate_release(self.root, self.manifest, self.library, reports)

    def test_rejects_unbound_old_report(self):
        with self.assertRaisesRegex(ValueError, 'Report identity/period/target differs'):
            self.run_report(1, lambda props: props.pop('runId'))

    def test_rejects_helper_binary_changes(self):
        self.put('helper/TcAutomation/bin/Release-v2/TcAutomation.exe', 'new helper binary')
        with self.assertRaisesRegex(ValueError, 'Build helper source/binaries changed'):
            evidence.verify_build(self.root, self.manifest, self.library)

    def test_rejects_source_mutation_before_test_finish(self):
        original = evidence.verify_report
        def change_source(*args):
            self.put('scripts/compiler.ps1', '# changed after test began')
            original(*args)
        with patch.object(evidence, 'verify_report', side_effect=change_source):
            with self.assertRaisesRegex(ValueError, 'Source/toolchain changed'):
                self.run_report(1)

    def test_workflow_metadata_does_not_change_build_but_version_does(self):
        path = self.root / 'toolchain.json'
        lock = evidence.read(path)
        initial = evidence.source_snapshot(self.root)
        lock.update(notes='Qualification evidence complete', qualification='verified')
        evidence.write(path, lock)
        self.assertEqual(evidence.source_snapshot(self.root), initial)
        evidence.verify_build(self.root, self.manifest, self.library)
        lock['xaeBaseline'] = '3.1.4026.99'
        evidence.write(path, lock)
        with self.assertRaisesRegex(ValueError, 'Source/toolchain changed'):
            evidence.verify_build(self.root, self.manifest, self.library)
    def test_receipts_bind_immutable_bundle_not_mutable_latest_alias(self):
        build = evidence.read(self.manifest)
        canonical = Path(build['immutableManifestPath'])
        first = self.run_report(1)
        def overwrite_latest(_):
            self.manifest.write_text('{"new": "latest build alias"}')
            self.put('artifacts/TcForge.Tests-build.json', '{"new": "build output"}')
            self.put('artifacts/TcForge.Tests-dependencies.xml', '<new/>')
            self.library.write_text('new artifact from next build')
        second = self.run_report(10, overwrite_latest)
        receipt = evidence.read(str(second) + '.evidence.json')
        self.assertEqual(receipt['build']['path'], str(canonical))
        self.assertEqual(evidence.validate_release(self.root, canonical, Path(build['library']['path']),
                                                  [first, second]), build['buildId'])

    def test_failed_or_stale_build_proof_cannot_finish(self):
        token = self.root / 'artifacts/next-build-token.json'
        evidence.begin_build(self.root, self.root / 'helper', token)
        # Existing successful proof files predate this new token; never rebind them.
        with self.assertRaisesRegex(ValueError, 'predates this run'):
            evidence.finish_build(self.root, token, self.library, self.root / 'dependencies.lock.json',
                                  self.root / 'artifacts/next-build.json')
    def test_export_context_rejects_wrong_helper_and_endpoint(self):
        token = self.root / 'artifacts/context-run.json'
        evidence.begin_test(self.root, self.manifest, self.library, 1, '1.2.3.4.1.1', token, self.installed)
        helper = self.root / 'helper/TcAutomation/bin/Release-v2/TcAutomation.exe'
        self.assertEqual(evidence.report_context(token, helper, '1.2.3.4.1.1', 853, 1)['buildId'],
                         evidence.read(self.manifest)['buildId'])
        with self.assertRaisesRegex(ValueError, 'target/port/period'):
            evidence.report_context(token, helper, '1.2.3.4.1.1', 854, 1)
        foreign = self.put('foreign-helper.exe', 'helper binary')
        with self.assertRaisesRegex(ValueError, 'outside the bound helper root'):
            evidence.report_context(token, foreign, '1.2.3.4.1.1', 853, 1)
        helper.write_text('tampered helper')
        with self.assertRaisesRegex(ValueError, 'binary differs'):
            evidence.report_context(token, helper, '1.2.3.4.1.1', 853, 1)

    def test_release_still_requires_qualification_after_metadata_change(self):
        from check_repository import check
        self.put('README.md', 'fixture')
        lock = evidence.read(self.root / 'toolchain.json')
        lock.update(qualification='pending-validation', resolvedVendorLibraries={
            'Tc2_Standard': '1.0.0.0', 'Tc2_System': '1.0.0.0', 'Tc3_Module': '1.0.0.0'})
        evidence.write(self.root / 'toolchain.json', lock)
        with patch.object(evidence, 'validate_release', return_value='validated-separately'):
            pending = check(self.root, release=True, report=[], build_evidence=self.manifest, library=self.library)[0]
            self.assertIn('Release blocked: TwinCAT qualification is not verified', pending)
            lock['qualification'] = 'verified'
            evidence.write(self.root / 'toolchain.json', lock)
            verified = check(self.root, release=True, report=[], build_evidence=self.manifest, library=self.library)[0]
            self.assertNotIn('Release blocked: TwinCAT qualification is not verified', verified)
    def test_report_cannot_bypass_provenance_with_cases_outside_suite(self):
        token = self.root / 'artifacts/layout-run.json'
        value = evidence.begin_test(self.root, self.manifest, self.library, 1, '1.2.3.4.1.1', token, self.installed)
        report = self.put('artifacts/unbound-layout.xml',
                          '<testsuites><testsuite/><testcase classname="MAIN.s" name="one"/></testsuites>')
        with self.assertRaisesRegex(ValueError, 'Every report test must belong'):
            evidence.verify_report(self.root, report, value)
    def test_git_context_records_commit_and_dirty_without_status_paths(self):
        self.put('.git', 'gitdir: fixture')
        from types import SimpleNamespace
        commit = 'a' * 40
        with patch.object(evidence.subprocess, 'run', side_effect=[
                SimpleNamespace(stdout=commit + '\n'), SimpleNamespace(stdout=' M private-name.txt\n')]):
            metadata = evidence.git_metadata(self.root)
        self.assertEqual(metadata, {'commit': commit, 'dirty': True})
        self.assertNotIn('private-name', json.dumps(metadata))
        evidence.verify_git_metadata(self.root, {'git': metadata})

    def test_non_git_fixture_is_unknown_but_real_repository_requires_commit(self):
        metadata = evidence.git_metadata(self.root)
        self.assertEqual(metadata, {'commit': None, 'dirty': None})
        evidence.verify_git_metadata(self.root, {'git': metadata})
        self.put('.git', 'gitdir: fixture')
        with self.assertRaisesRegex(ValueError, 'real Git repository requires'):
            evidence.verify_git_metadata(self.root, {'git': metadata})
        with self.assertRaisesRegex(ValueError, 'Invalid Git revision context'):
            evidence.verify_git_metadata(self.root, {'git': {'commit': 'invalid', 'dirty': False}})


if __name__ == '__main__':
    unittest.main()
