from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="xhs-installer-test-")
        self.target = Path(self.temporary.name) / ".agents" / "skills"
        self.installer = load_module("xhs_install", ROOT / "install.py")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_installs_both_skills_and_is_idempotent(self) -> None:
        for name in self.installer.SKILL_NAMES:
            result = self.installer.install_skill(ROOT, self.target, name, False)
            self.assertIn("installed:", result)
            self.assertTrue((self.target / name / "SKILL.md").is_file())
        for name in self.installer.SKILL_NAMES:
            result = self.installer.install_skill(ROOT, self.target, name, False)
            self.assertIn("current:", result)

    def test_conflicting_install_requires_replace_and_keeps_backup(self) -> None:
        name = self.installer.SKILL_NAMES[0]
        self.installer.install_skill(ROOT, self.target, name, False)
        (self.target / name / "SKILL.md").write_text("different", encoding="utf-8")
        with self.assertRaises(self.installer.InstallError):
            self.installer.install_skill(ROOT, self.target, name, False)
        result = self.installer.install_skill(ROOT, self.target, name, True)
        self.assertIn("backed up", result)
        backups = list(self.target.glob(f"{name}.backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(
            (backups[0] / "SKILL.md").read_text(encoding="utf-8"), "different"
        )

    def test_bootstrap_prefers_uv_and_falls_back_to_pip(self) -> None:
        bootstrap = load_module(
            "xhs_bootstrap",
            ROOT
            / "skills"
            / "xhs-public-note-assets"
            / "scripts"
            / "bootstrap_xhs_downloader.py",
        )
        with mock.patch.object(bootstrap.shutil, "which", return_value="C:/bin/uv.exe"):
            self.assertEqual(bootstrap.select_installer("auto"), ("uv", "C:/bin/uv.exe"))
        with mock.patch.object(bootstrap.shutil, "which", return_value=None):
            self.assertEqual(bootstrap.select_installer("auto"), ("pip", None))
            with self.assertRaises(SystemExit):
                bootstrap.select_installer("uv")

    def test_raw_one_command_execution_without_file_global(self) -> None:
        command_target = Path(self.temporary.name) / "command-install"
        code = (ROOT / "install.py").read_text(encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                code,
                "--source",
                str(ROOT),
                "--target",
                str(command_target),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in self.installer.SKILL_NAMES:
            self.assertTrue((command_target / name / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
