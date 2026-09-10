import sys
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_repository import check_reference_versions


class ReferencePinTests(unittest.TestCase):
    lock = dict(libraryVersion='2.0.0.0', tcunitVersion='1.3.0.0',
                resolvedVendorLibraries={'Tc2_System': '3.10.2.0'})

    def check(self, name, version, direct=False):
        resolution = f'{name}, {version} (Vendor)'
        node = (f'<LibraryReference Include="{resolution}"/>' if direct else
                f'<PlaceholderReference Include="{name}"><DefaultResolution>{resolution}</DefaultResolution></PlaceholderReference>')
        doc = ET.fromstring(f'<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003"><ItemGroup>{node}</ItemGroup></Project>')
        return check_reference_versions(doc, self.lock)

    def test_accepts_exact_vendor_library_and_tcunit_pins(self):
        for name, version in (('Tc2_System', '3.10.2.0'), ('TcForge', '2.0.0.0'), ('TcUnit', '1.3.0.0')):
            for direct in (True, False):
                self.assertEqual(self.check(name, version, direct), [])

    def test_rejects_changed_version_and_wildcard(self):
        for name in ('Tc2_System', 'TcForge', 'TcUnit'):
            for version in ('9.9.9.9', '*'):
                self.assertTrue(self.check(name, version))

    def test_rejects_unpinned_reference(self):
        self.assertTrue(self.check('NewDependency', '1.0.0.0'))

    def test_rejects_placeholder_resolving_different_library(self):
        doc = ET.fromstring('<Project><PlaceholderReference Include="Tc2_System"><DefaultResolution>Other, 3.10.2.0 (Vendor)</DefaultResolution></PlaceholderReference></Project>')
        self.assertTrue(check_reference_versions(doc, self.lock))


if __name__ == '__main__':
    unittest.main()
