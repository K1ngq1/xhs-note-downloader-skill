#!/usr/bin/env python3
"""Install an isolated XHS-Downloader MCP runtime without bundling upstream code."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


UPSTREAM = "https://github.com/JoeanAmier/XHS-Downloader.git"
VERSION = "2.7"


def launcher_text() -> str:
    return '''from asyncio import run
from re import sub

from yaml import safe_load

from main import mcp_server
from source.expansion.converter import Converter


def convert_page_state(text: str) -> dict:
    text = text.removeprefix("window.__INITIAL_STATE__=")
    text = sub(r"new Map\\(\\[\\]\\)", "{}", text)
    text = sub(r"new Set\\(\\[\\]\\)", "[]", text)
    text = sub(r"\\bundefined\\b", "null", text)
    return safe_load(text)


Converter._convert_object = staticmethod(convert_page_state)

if __name__ == "__main__":
    run(mcp_server(host="127.0.0.1"))
'''


def run_checked(command: list[str], cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-dir", required=True, type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--version", default=VERSION)
    parser.add_argument(
        "--installer",
        choices=("auto", "uv", "pip"),
        default="auto",
        help="Use uv when available for faster dependency installation",
    )
    return parser.parse_args()


def python_version(python: str) -> tuple[int, int]:
    completed = subprocess.run(
        [
            python,
            "-c",
            "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    major, minor = completed.stdout.strip().split(".", 1)
    return int(major), int(minor)


def select_installer(requested: str) -> tuple[str, str | None]:
    uv = shutil.which("uv")
    if requested == "uv" and not uv:
        raise SystemExit("uv was requested but is not available on PATH")
    if requested == "uv" or (requested == "auto" and uv):
        return "uv", uv
    return "pip", None


def main() -> int:
    args = parse_args()
    if python_version(args.python) != (3, 12):
        raise SystemExit("XHS-Downloader 2.7 requires Python 3.12 via --python")
    installer, uv = select_installer(args.installer)
    root = args.install_dir.resolve()
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"Install directory must be empty: {root}")
    root.parent.mkdir(parents=True, exist_ok=True)
    run_checked(
        ["git", "clone", "--branch", args.version, "--depth", "1", UPSTREAM, str(root)]
    )
    if installer == "uv":
        run_checked([str(uv), "venv", "--python", args.python, ".venv"], root)
    else:
        run_checked([args.python, "-m", "venv", ".venv"], root)
    python = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if installer == "uv":
        run_checked(
            [
                str(uv),
                "pip",
                "install",
                "--python",
                str(python),
                "-r",
                "requirements.txt",
                "fastmcp==2.14.5",
            ],
            root,
        )
    else:
        run_checked(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "-r",
                "requirements.txt",
                "fastmcp==2.14.5",
            ],
            root,
        )
    (root / "run_mcp_local.py").write_text(launcher_text(), encoding="utf-8")
    print(f"Installed XHS-Downloader {args.version} at {root}")
    print(f"Dependency installer: {installer}")
    print(f"Start: {python} {root / 'run_mcp_local.py'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
