#!/usr/bin/env python3
"""Build a safe capture.json from XHS-Downloader MCP responses and local files."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


NOTE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".heic"}


class MCPResultError(ValueError):
    """Raised when an MCP result cannot be mapped safely."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert XHS-Downloader MCP results into capture schema version 1."
    )
    parser.add_argument(
        "--response",
        required=True,
        action="append",
        type=Path,
        help="UTF-8 JSON returned by get_detail_data or download_detail; repeat as needed",
    )
    parser.add_argument(
        "--download-root",
        required=True,
        type=Path,
        help="Configured XHS-Downloader folder containing <note-id>/<note-id>_N files",
    )
    parser.add_argument("--capture", required=True, type=Path, help="capture.json output")
    parser.add_argument("--account-url", help="Canonical authorized profile URL")
    parser.add_argument(
        "--authorization-confirmed",
        action="store_true",
        help="Confirm ownership or explicit authorization",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MCPResultError(f"Cannot read MCP response {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MCPResultError(f"MCP response root must be an object: {path}")
    return value


def unwrap_data(value: dict[str, Any], path: Path) -> dict[str, Any]:
    structured = value.get("structuredContent")
    if isinstance(structured, dict):
        value = structured
    data = value.get("data")
    if not isinstance(data, dict):
        raise MCPResultError(
            f"MCP response has no metadata object in data: {path}. "
            "Call download_detail with return_data=true."
        )
    return data


def canonical_xhs_url(value: str) -> str:
    parts = urlsplit(value.strip())
    hostname = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or not (
        hostname == "xiaohongshu.com" or hostname.endswith(".xiaohongshu.com")
    ):
        raise MCPResultError("Expected an http(s) Xiaohongshu URL")
    return urlunsplit(("https", hostname, parts.path.rstrip("/") or "/", "", ""))


def required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MCPResultError(f"MCP metadata is missing {key}")
    return value.strip()


def classify(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"图文", "图集", "image", "images", "carousel"}:
        return "image"
    if text in {"视频", "video"}:
        return "video"
    return "unavailable"


def expected_count(data: dict[str, Any]) -> int | None:
    addresses = data.get("下载地址")
    if isinstance(addresses, list):
        return len(addresses)
    return None


def find_assets(download_root: Path, note_id: str) -> dict[int, Path]:
    note_dir = download_root / note_id
    if not note_dir.is_dir():
        return {}
    pattern = re.compile(rf"^{re.escape(note_id)}_(\d+)(\.[A-Za-z0-9]+)$")
    by_order: dict[int, Path] = {}
    for candidate in note_dir.iterdir():
        if not candidate.is_file() or candidate.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        match = pattern.fullmatch(candidate.name)
        if not match:
            continue
        order = int(match.group(1))
        if order < 1 or order in by_order:
            raise MCPResultError(f"Duplicate or invalid image order in {note_dir}: {order}")
        by_order[order] = candidate.resolve()
    return by_order


def capture_assets(
    download_root: Path,
    note_id: str,
    found: dict[int, Path],
    count: int,
) -> list[dict[str, Any]]:
    note_dir = download_root / note_id
    return [
        {
            "source_path": str(
                found.get(order, note_dir / f"{note_id}_{order}.missing").resolve()
            ),
            "order": order,
            "role": "cover" if order == 1 else "detail",
        }
        for order in range(1, count + 1)
    ]


def item_from_data(data: dict[str, Any], download_root: Path) -> tuple[dict[str, Any], str]:
    note_id = required_text(data, "作品ID")
    if not NOTE_ID_RE.fullmatch(note_id):
        raise MCPResultError(f"Invalid 作品ID: {note_id!r}")
    author_id = required_text(data, "作者ID")
    content_type = classify(data.get("作品类型"))
    title = str(data.get("作品标题") or "").strip()
    source_url = f"https://www.xiaohongshu.com/explore/{note_id}"
    count = expected_count(data)
    assets: list[dict[str, Any]] = []
    failure_reason = ""
    notes = "capture_backend=xhs_downloader_mcp"

    if content_type == "image":
        found = find_assets(download_root, note_id)
        if count is None:
            count = max(found, default=0)
            notes += "; expected_count_inferred_from_local_files"
        assets = capture_assets(download_root, note_id, found, count)
        if not found:
            failure_reason = "mcp_download_files_not_found"
        elif set(found) != set(range(1, count + 1)):
            failure_reason = "mcp_download_incomplete"
            missing = sorted(set(range(1, count + 1)) - set(found))
            extra = sorted(set(found) - set(range(1, count + 1)))
            if missing:
                notes += "; missing_orders=" + ",".join(map(str, missing))
            if extra:
                notes += "; unexpected_orders=" + ",".join(map(str, extra))
    elif content_type == "video":
        count = 0
        failure_reason = "unsupported_video"
    else:
        count = count or 0
        failure_reason = "unsupported_or_unavailable_note"

    return (
        {
            "note_id": note_id,
            "title": title,
            "source_url": source_url,
            "content_type": content_type,
            "expected_count": count,
            "assets": assets,
            "failure_reason": failure_reason,
            "watermark_check": {
                "result": "unknown",
                "scope": "none",
                "checked_orders": [],
            },
            "notes": notes,
        },
        author_id,
    )


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def run(args: argparse.Namespace) -> int:
    if not args.authorization_confirmed:
        raise MCPResultError("Ownership or explicit authorization must be confirmed")
    download_root = args.download_root.resolve()
    items: list[dict[str, Any]] = []
    author_ids: set[str] = set()
    note_ids: set[str] = set()
    for response_path in args.response:
        item, author_id = item_from_data(
            unwrap_data(read_json(response_path), response_path), download_root
        )
        if item["note_id"] in note_ids:
            raise MCPResultError(f"Duplicate note response: {item['note_id']}")
        note_ids.add(item["note_id"])
        author_ids.add(author_id)
        items.append(item)

    if args.account_url:
        account_url = canonical_xhs_url(args.account_url)
    elif len(author_ids) == 1:
        account_url = (
            "https://www.xiaohongshu.com/user/profile/" + next(iter(author_ids))
        )
    else:
        raise MCPResultError("Use --account-url when responses contain multiple authors")

    payload = {
        "schema_version": 1,
        "capture_backend": "xhs_downloader_mcp",
        "account_url": account_url,
        "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "authorization": {
            "basis": "owner_or_explicitly_authorized",
            "confirmed_by_user": True,
        },
        "items": items,
    }
    atomic_write(args.capture, payload)
    print(
        json.dumps(
            {
                "capture": str(args.capture.resolve()),
                "item_count": len(items),
                "located_asset_count": sum(
                    sum(Path(asset["source_path"]).is_file() for asset in item["assets"])
                    for item in items
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    args = parse_args()
    try:
        return run(args)
    except MCPResultError as exc:
        print(f"MCP capture error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
