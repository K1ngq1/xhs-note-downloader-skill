from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "xhs-public-note-assets" / "scripts"


def load_script(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SetupHelpersTest(unittest.TestCase):
    def test_cookie_normalization_removes_header_control_characters(self) -> None:
        module = load_script("configure_cookie")
        self.assertEqual(module.normalize_cookie("  a=b;\r\n\tc=d;  "), "a=b;c=d;")

    def test_generated_launcher_is_localhost_only_and_has_parser_shim(self) -> None:
        module = load_script("bootstrap_xhs_downloader")
        launcher = module.launcher_text()
        self.assertIn('host="127.0.0.1"', launcher)
        self.assertNotIn('host="0.0.0.0"', launcher)
        self.assertIn("new Map", launcher)
        self.assertIn("new Set", launcher)
        self.assertIn("undefined", launcher)
        self.assertNotRegex(launcher, r"[A-Za-z]:\\Users\\")


if __name__ == "__main__":
    unittest.main()
