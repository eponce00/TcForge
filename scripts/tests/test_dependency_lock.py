import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dependency_lock import PROJECTS, check_project, parse_resolution_xml


def lib(name, version='1.0.0.0', deps=''):
    return f'<LibraryName>{name}</LibraryName><Version>{version}</Version><Distributor>Vendor</Distributor>{deps}'


def ref(name='Main', deps='', path='C:/machine-specific/library', identifier='111'):
    return f'<PlaceholderReference id="{identifier}"><PlaceholderName>{name}</PlaceholderName><Namespace>{name}</Namespace><RelativePath>{path}</RelativePath><EffectiveResolution>{lib(name, deps=deps)}</EffectiveResolution></PlaceholderReference>'


def xml(refs):
    return f'<TreeItem><IECProjectDef><References>{refs}</References></IECProjectDef></TreeItem>'


class DependencyLockTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def capture(self, text, name='capture.xml'):
        path = self.root / name
        path.write_text(text, encoding='utf-8')
        return path

    def test_nested_placeholder_and_explicit_library_dependencies(self):
        dep = '<Dependencies><Dependency isPlaceholder="true"><PlaceholderName>Child</PlaceholderName><EffectiveResolution>' + lib('Child') + '</EffectiveResolution></Dependency><Dependency isLibrary="true">' + lib('Concrete') + '</Dependency></Dependencies>'
        result = parse_resolution_xml(self.capture(xml(ref(deps=dep))))
        self.assertEqual([item['name'] for item in result['libraries']], ['Child', 'Concrete', 'Main'])
        self.assertEqual(len(result['dependencies']), 2)

    def test_machine_paths_ids_and_order_do_not_change_lock(self):
        a = parse_resolution_xml(self.capture(xml(ref('A') + ref('B'))))
        b = parse_resolution_xml(self.capture(xml(ref('B', path='D:/other', identifier='9') + ref('A', identifier='10'))))
        self.assertEqual(a, b)

    def test_namespaced_capture(self):
        a = parse_resolution_xml(self.capture(xml(ref())))
        b = parse_resolution_xml(self.capture(xml(ref()).replace('<TreeItem>', '<TreeItem xmlns="urn:test">')))
        self.assertEqual(a, b)

    def test_missing_references_rejected(self):
        with self.assertRaisesRegex(ValueError, 'nonempty'):
            parse_resolution_xml(self.capture(xml('')))

    def test_direct_unresolved_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unresolved direct'):
            parse_resolution_xml(self.capture(xml('<PlaceholderReference><PlaceholderName>Main</PlaceholderName></PlaceholderReference>')))

    def test_transitive_unresolved_rejected(self):
        dep = '<Dependencies><Dependency isPlaceholder="true"><PlaceholderName>Missing</PlaceholderName></Dependency></Dependencies>'
        with self.assertRaisesRegex(ValueError, 'Unresolved transitive'):
            parse_resolution_xml(self.capture(xml(ref(deps=dep))))

    def test_effective_wildcard_rejected(self):
        with self.assertRaisesRegex(ValueError, 'actual library signatures required'):
            parse_resolution_xml(self.capture(xml(ref()).replace('<Version>1.0.0.0</Version>', '<Version>*</Version>')))

    def test_duplicate_binding_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            parse_resolution_xml(self.capture(xml(ref() + ref())))

    def test_generated_system_reference_retained(self):
        result = parse_resolution_xml(self.capture(xml(ref('Tc3_GlobalTypes').replace('id="111"', 'id="111" systemLibrary="true"'))))
        self.assertTrue(result['references'][0]['systemLibrary'])
        self.assertEqual(result['libraries'][0]['name'], 'Tc3_GlobalTypes')

    def test_compare_checks_edges_not_only_installed_versions(self):
        capture = self.capture(xml(ref()))
        canonical = parse_resolution_xml(capture)
        lock = dict(schemaVersion=1, projects={name: copy.deepcopy(canonical) for name in PROJECTS})
        path = self.root / 'lock.json'
        path.write_text(json.dumps(lock), encoding='utf-8')
        self.assertEqual(check_project(path, PROJECTS[0], capture), canonical)
        lock['projects'][PROJECTS[0]]['dependencies'] = [dict(library='Main, 1.0.0.0 (Vendor)', dependency='Main, 1.0.0.0 (Vendor)', placeholder='Unexpected')]
        path.write_text(json.dumps(lock), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'bindings/edges'):
            check_project(path, PROJECTS[0], capture)

    def test_lock_missing_project_rejected(self):
        path = self.root / 'lock.json'
        path.write_text(json.dumps(dict(schemaVersion=1, projects={})), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'four build projects'):
            check_project(path, PROJECTS[0], self.capture(xml(ref())))

    def signed(self, capture, libraries):
        return '<TcForgeDependencyCapture>' + capture + '<LibrarySignatures>' + ''.join('<Library>' + item + '</Library>' for item in libraries) + '</LibrarySignatures></TcForgeDependencyCapture>'

    def test_wildcard_requires_unique_actual_signature(self):
        capture = xml(ref()).replace('<Version>1.0.0.0</Version>', '<Version>*</Version>')
        result = parse_resolution_xml(self.capture(self.signed(capture, [lib('Main', '2.3.4.5')])))
        self.assertEqual(result['libraries'][0]['version'], '2.3.4.5')
        self.assertEqual(result['signatureLibraries'], ['Main, 2.3.4.5 (Vendor)'])

    def test_multiple_signature_versions_do_not_guess_wildcard(self):
        capture = xml(ref()).replace('<Version>1.0.0.0</Version>', '<Version>*</Version>')
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            parse_resolution_xml(self.capture(self.signed(capture, [lib('Main'), lib('Main', '2.0.0.0')])))

    def test_concrete_reference_must_match_actual_signature(self):
        with self.assertRaisesRegex(ValueError, 'absent from actual'):
            parse_resolution_xml(self.capture(self.signed(xml(ref()), [lib('Main', '2.0.0.0')])))

    def test_signature_only_transitive_libraries_are_locked(self):
        result = parse_resolution_xml(self.capture(self.signed(xml(ref()), [lib('Main'), lib('Internal')])))
        self.assertEqual([item['name'] for item in result['libraries']], ['Internal', 'Main'])


if __name__ == '__main__':
    unittest.main()
