#!/usr/bin/env python3
"""Privately update XHS-Downloader's Cookie without placing it in arguments or logs."""

from __future__ import annotations

import argparse
import getpass
import json
import tempfile
from pathlib import Path


def normalize_cookie(value: str) -> str:
    return value.replace("\r", "").replace("\n", "").replace("\t", "").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", required=True, type=Path)
    parser.add_argument("--clear", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = args.settings.resolve()
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or "cookie" not in data:
        raise SystemExit("settings.json has no cookie field")
    cookie = "" if args.clear else normalize_cookie(getpass.getpass("Cookie (hidden): "))
    if not args.clear and not cookie:
        raise SystemExit("Cookie was empty; settings were not changed")
    data["cookie"] = cookie
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8-sig", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        json.dump(data, handle, ensure_ascii=False, indent=4)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)
    print("Cookie cleared" if args.clear else "Cookie configured (value not displayed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
