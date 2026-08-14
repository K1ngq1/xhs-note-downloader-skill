#!/usr/bin/env python3
"""Install this repository's skills with only the Python standard library."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


REPOSITORY = "K1ngq1/xhs-note-downloader-skill"
DEFAULT_REF = "main"
SKILL_NAMES = ("xhs-public-note-assets", "xhs-authorized-shop-assets")


class InstallError(RuntimeError):
    """Raised for safe, actionable installation failures."""


def default_target() -> Path:
    configured = os.environ.get("AGENT_SKILLS_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".agents" / "skills"


def tree_digest(root: Path) -> str:
    result = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        result.update(len(relative).to_bytes(8, "big"))
        result.update(relative)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                result.update(chunk)
    return result.hexdigest()


def safe_extract(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            candidate = PurePosixPath(member.filename)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise InstallError(f"unsafe archive member: {member.filename}")
        bundle.extractall(destination)


def download_source(repository: str, ref: str, cache_root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_root = cache_root / f"{stamp}-{uuid.uuid4().hex[:8]}"
    run_root.mkdir(parents=True, exist_ok=False)
    archive = run_root / "source.zip"
    url = f"https://github.com/{repository}/archive/refs/heads/{ref}.zip"
    request = urllib.request.Request(url, headers={"User-Agent": "xhs-skill-installer/0.2"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            archive.write_bytes(response.read())
        safe_extract(archive, run_root)
    except (OSError, urllib.error.URLError, zipfile.BadZipFile) as exc:
        raise InstallError(f"unable to download {repository}@{ref}: {exc}") from exc
    candidates = [path for path in run_root.iterdir() if path.is_dir() and (path / "skills").is_dir()]
    if len(candidates) != 1:
        raise InstallError(f"downloaded archive has no unique skills root; cache kept at {run_root}")
    print(f"Download cache: {run_root}")
    return candidates[0]


def resolve_source(args: argparse.Namespace) -> Path:
    if args.source:
        source = args.source.expanduser().resolve()
        if not (source / "skills").is_dir():
            raise InstallError(f"source has no skills directory: {source}")
        return source
    script_path = globals().get("__file__")
    if script_path:
        local = Path(script_path).resolve().parent
        if (local / "skills").is_dir():
            return local
    cache = args.cache_dir.expanduser().resolve()
    return download_source(args.repository, args.ref, cache)


def install_skill(source: Path, target_root: Path, name: str, replace: bool) -> str:
    source_skill = source / "skills" / name
    if not (source_skill / "SKILL.md").is_file():
        raise InstallError(f"source skill is missing: {name}")
    destination = target_root / name
    if destination.is_dir() and tree_digest(destination) == tree_digest(source_skill):
        return f"current: {destination}"
    if destination.exists() and not replace:
        raise InstallError(
            f"destination exists with different content: {destination}; rerun with --replace"
        )
    target_root.mkdir(parents=True, exist_ok=True)
    staging = target_root / f".{name}.install-{uuid.uuid4().hex}"
    shutil.copytree(source_skill, staging)
    backup = None
    if destination.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = target_root / f"{name}.backup-{stamp}-{uuid.uuid4().hex[:6]}"
        destination.rename(backup)
    staging.rename(destination)
    message = f"installed: {destination}"
    if backup:
        message += f" (previous version backed up at {backup})"
    return message


def default_runtime_dir() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "xhs-downloader" / "2.7"
    return Path.home() / ".local" / "share" / "xhs-downloader" / "2.7"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install XHS authorized asset skills")
    parser.add_argument("--target", type=Path, default=default_target())
    parser.add_argument("--source", type=Path, help="Local repository root")
    parser.add_argument("--repository", default=REPOSITORY)
    parser.add_argument("--ref", default=DEFAULT_REF)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "xhs-note-downloader-installer",
    )
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--with-runtime", action="store_true")
    parser.add_argument("--runtime-dir", type=Path, default=default_runtime_dir())
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--installer", choices=("auto", "uv", "pip"), default="auto")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        source = resolve_source(args)
        target = args.target.expanduser().resolve()
        for name in SKILL_NAMES:
            print(install_skill(source, target, name, args.replace))
        if args.with_runtime:
            bootstrap = target / "xhs-public-note-assets" / "scripts" / "bootstrap_xhs_downloader.py"
            command = [
                args.python,
                str(bootstrap),
                "--install-dir",
                str(args.runtime_dir.expanduser().resolve()),
                "--python",
                args.python,
                "--installer",
                args.installer,
            ]
            subprocess.run(command, check=True)
        print("Installation complete. Restart the agent if the new skills are not visible.")
        return 0
    except (InstallError, OSError, subprocess.CalledProcessError) as exc:
        print(f"install error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
