import sys
import tempfile
import unittest
from pathlib import Path
import shutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_repository import ROOT, check_development_layout


class DevelopmentLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for path in (ROOT / "TwinCAT").rglob("*"):
            if path.suffix in (".tsproj", ".plcproj", ".sln"):
                target = self.root / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)

    def edit(self, path, old, new):
        target = self.root / path
        text = target.read_text()
        self.assertIn(old, text)
        target.write_text(text.replace(old, new))

    def test_development_and_isolated_profiles(self):
        self.assertEqual(check_development_layout(self.root), [])

    def test_installed_fallback_is_rejected(self):
        self.edit("TwinCAT/Testing.plcproj", "[TcForge],", "TcForge,")
        self.assertTrue(
            any(
                "reference TcForge source" in e
                for e in check_development_layout(self.root)
            )
        )

    def test_support_library_must_be_referenceable(self):
        self.edit(
            "TwinCAT/TcForgeExample/TcForgeExample.plcproj",
            "<VirtualLibrary>true</VirtualLibrary>",
            "<VirtualLibrary>false</VirtualLibrary>",
        )
        self.assertTrue(
            any(
                "enable referenced-library" in e
                for e in check_development_layout(self.root)
            )
        )

    def test_task_identity_collision_is_rejected(self):
        self.edit("TwinCAT/TcForge.tsproj", 'AmsPort="353"', 'AmsPort="350"')
        self.assertTrue(
            any(
                "duplicate system task AmsPort" in e
                for e in check_development_layout(self.root)
            )
        )

    def test_source_library_boot_build_is_rejected(self):
        self.edit(
            "TwinCAT/TcForge.sln",
            "{C50D021A-2A7E-435E-BD9B-20A91E08C1DA}.Release|TwinCAT RT (x64).ActiveCfg",
            "{C50D021A-2A7E-435E-BD9B-20A91E08C1DA}.Release|TwinCAT RT (x64).Build.0",
        )
        self.assertTrue(
            any(
                "must not build boot projects" in e
                for e in check_development_layout(self.root)
            )
        )

    def test_missing_source_library_configuration_is_rejected(self):
        self.edit(
            "TwinCAT/TcForge.Example.sln",
            "{C50D021A-2A7E-435E-BD9B-20A91E08C1DA}.Release|TwinCAT RT (x64).ActiveCfg",
            "{00000000-0000-0000-0000-000000000000}.Release|TwinCAT RT (x64).ActiveCfg",
        )
        self.assertTrue(
            any(
                "missing explicit solution configuration" in e
                for e in check_development_layout(self.root)
            )
        )

    def test_missing_library_source_is_rejected(self):
        self.edit("TwinCAT/TcForge.Tests.tsproj", 'Name="TcForge"', 'Name="Unexpected"')
        self.assertTrue(
            any("membership" in e for e in check_development_layout(self.root))
        )

    def test_live_qualifiers_use_complete_assembly_plant(self):
        for name in (
            "verify_online_change.py",
            "verify_plc_stop_start.py",
            "verify_simulation_restart.py",
        ):
            with self.subTest(script=name):
                source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
                self.assertIn("AssemblyPlant", source)
                self.assertNotIn("TwoPositionCylinder", source)


if __name__ == "__main__":
    unittest.main()
