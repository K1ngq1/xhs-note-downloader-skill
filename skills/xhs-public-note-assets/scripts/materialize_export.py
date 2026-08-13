#!/usr/bin/env python3
"""Materialize authorized MCP or browser assets into a safe XHS note export."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - depends on the caller runtime
    raise SystemExit(
        "Pillow is required for image decoding. Use the bundled Codex Python runtime "
        "or install Pillow in the active environment."
    ) from exc


SCHEMA_VERSION = 1
NOTE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
SENSITIVE_TEXT_RE = re.compile(
    r"(?i)(xsec_token\s*=|cookie\s*:|authorization\s*:|bearer\s+[A-Za-z0-9._~-]+)"
)
FORMAT_EXTENSIONS = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "GIF": ".gif",
    "AVIF": ".avif",
}


class CaptureError(ValueError):
    """Raised when capture input is unsafe or invalid."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Organize authorized Xiaohongshu image-note assets and write manifests."
    )
    parser.add_argument("--capture", required=True, type=Path, help="UTF-8 capture.json")
    parser.add_argument("--output", required=True, type=Path, help="Export root")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CaptureError(f"Cannot read capture JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise CaptureError("Capture root must be an object")
    return value


def canonical_xhs_url(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise CaptureError(f"{field} must be a string")
    parts = urlsplit(value.strip())
    hostname = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or not (
        hostname == "xiaohongshu.com" or hostname.endswith(".xiaohongshu.com")
    ):
        raise CaptureError(f"{field} must be an http(s) Xiaohongshu URL")
    netloc = hostname
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit(("https", netloc, parts.path.rstrip("/") or "/", "", ""))


def safe_text(value: Any, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise CaptureError(f"{field} must be a string")
    if SENSITIVE_TEXT_RE.search(value):
        raise CaptureError(f"{field} contains authentication or signed-token material")
    return value.strip()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_image(path: Path) -> tuple[int, int, str, str]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("missing or zero-byte source")
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        width, height = image.size
        image_format = (image.format or "").upper()
    extension = FORMAT_EXTENSIONS.get(image_format)
    if not extension:
        raise ValueError(f"unsupported image format: {image_format or 'unknown'}")
    return width, height, image_format, extension


def validate_capture(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise CaptureError(f"schema_version must be {SCHEMA_VERSION}")
    authorization = payload.get("authorization")
    if not isinstance(authorization, dict) or authorization.get("confirmed_by_user") is not True:
        raise CaptureError("User ownership or explicit authorization must be confirmed")
    if not safe_text(authorization.get("basis"), "authorization.basis"):
        raise CaptureError("authorization.basis is required")
    safe_text(payload.get("captured_at"), "captured_at")
    canonical_xhs_url(payload.get("account_url"), "account_url")
    backend = payload.get("capture_backend")
    if backend is not None and backend not in {"xhs_downloader_mcp", "codex_browser"}:
        raise CaptureError("capture_backend must be xhs_downloader_mcp or codex_browser")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise CaptureError("items must be a non-empty array")


def normalize_watermark(value: Any, orders: list[int]) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise CaptureError("watermark_check must be an object")
    result = value.get("result", "unknown")
    scope = value.get("scope", "none")
    checked_orders = value.get("checked_orders", [])
    if result not in {True, False, "unknown"}:
        raise CaptureError("watermark_check.result must be true, false, or unknown")
    if scope not in {"none", "sample", "all"}:
        raise CaptureError("watermark_check.scope must be none, sample, or all")
    if not isinstance(checked_orders, list) or any(
        not isinstance(order, int) or order < 1 for order in checked_orders
    ):
        raise CaptureError("watermark_check.checked_orders must contain positive integers")
    checked_orders = sorted(set(checked_orders))
    if any(order not in orders for order in checked_orders):
        raise CaptureError("watermark_check contains an order not present in assets")
    return {"result": result, "scope": scope, "checked_orders": checked_orders}


def normalize_assets(value: Any, note_id: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise CaptureError(f"{note_id}: assets must be an array")
    normalized: list[dict[str, Any]] = []
    for asset in value:
        if not isinstance(asset, dict):
            raise CaptureError(f"{note_id}: each asset must be an object")
        order = asset.get("order")
        role = asset.get("role")
        source_path = asset.get("source_path")
        if not isinstance(order, int) or order < 1:
            raise CaptureError(f"{note_id}: asset order must be a positive integer")
        if role not in {"cover", "detail"}:
            raise CaptureError(f"{note_id}: asset role must be cover or detail")
        if not isinstance(source_path, str) or not source_path.strip():
            raise CaptureError(f"{note_id}: source_path is required")
        normalized.append(
            {"order": order, "role": role, "source_path": Path(source_path).expanduser()}
        )
    normalized.sort(key=lambda item: item["order"])
    orders = [item["order"] for item in normalized]
    if len(orders) != len(set(orders)):
        raise CaptureError(f"{note_id}: asset orders must be unique")
    if orders and orders != list(range(1, len(orders) + 1)):
        raise CaptureError(f"{note_id}: asset orders must be contiguous from 1")
    if normalized and normalized[0]["role"] != "cover":
        raise CaptureError(f"{note_id}: first asset must be the cover")
    return normalized


def append_note(existing: str, addition: str) -> str:
    return "; ".join(part for part in (existing, addition) if part)


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def materialize_item(
    raw: Any,
    output_root: Path,
    hashes: dict[str, list[str]],
) -> tuple[dict[str, Any], bool]:
    if not isinstance(raw, dict):
        raise CaptureError("Each item must be an object")
    note_id = safe_text(raw.get("note_id"), "note_id")
    if not NOTE_ID_RE.fullmatch(note_id):
        raise CaptureError(f"Invalid note_id: {note_id!r}")
    title = safe_text(raw.get("title"), f"{note_id}.title")
    source_url = canonical_xhs_url(raw.get("source_url"), f"{note_id}.source_url")
    content_type = raw.get("content_type")
    if content_type not in {"image", "video", "unavailable"}:
        raise CaptureError(f"{note_id}: invalid content_type")
    expected_count = raw.get("expected_count")
    if expected_count is not None and (
        not isinstance(expected_count, int) or expected_count < 0
    ):
        raise CaptureError(f"{note_id}: expected_count must be null or a non-negative integer")
    failure_reason = safe_text(raw.get("failure_reason"), f"{note_id}.failure_reason")
    notes = safe_text(raw.get("notes"), f"{note_id}.notes")
    assets = normalize_assets(raw.get("assets", []), note_id)
    orders = [asset["order"] for asset in assets]
    watermark = normalize_watermark(raw.get("watermark_check"), orders)

    if content_type != "image":
        if assets:
            raise CaptureError(f"{note_id}: non-image items cannot contain assets")
        if not failure_reason:
            raise CaptureError(f"{note_id}: non-image items require failure_reason")
        return (
            {
                "item_type": "note",
                "note_id": note_id,
                "title": title,
                "source_url": source_url,
                "content_type": content_type,
                "expected_count": expected_count,
                "downloaded_count": 0,
                "files": [],
                "file_details": [],
                "watermark_check": {
                    "result": watermark["result"],
                    "scope": watermark["scope"],
                    "checked_files": [],
                },
                "status": "failed",
                "failure_reason": failure_reason,
                "notes": notes,
            },
            False,
        )

    item_dir = output_root / "notes" / note_id
    item_dir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    file_details: list[dict[str, Any]] = []
    conflicts = False
    width = max(2, len(str(max(len(assets), 1))))

    for asset in assets:
        source = asset["source_path"]
        try:
            image_width, image_height, image_format, extension = inspect_image(source)
            source_hash = file_digest(source)
        except (OSError, ValueError) as exc:
            notes = append_note(notes, f"order {asset['order']}: {exc}")
            continue

        label = "cover" if asset["order"] == 1 else "detail"
        filename = f"{asset['order']:0{width}d}-{label}{extension}"
        destination = item_dir / filename
        relative = destination.relative_to(output_root).as_posix()

        if destination.exists():
            if not destination.is_file() or file_digest(destination) != source_hash:
                conflicts = True
                notes = append_note(notes, f"conflict: {relative}")
                continue
        else:
            shutil.copy2(source, destination)

        hashes.setdefault(source_hash, []).append(relative)
        files.append(relative)
        file_details.append(
            {
                "path": relative,
                "role": asset["role"],
                "order": asset["order"],
                "width": image_width,
                "height": image_height,
                "format": image_format,
                "bytes": destination.stat().st_size,
                "sha256": source_hash,
            }
        )

    checked_files = [
        detail["path"]
        for detail in file_details
        if detail["order"] in watermark["checked_orders"]
    ]
    if not assets or not files:
        status = "failed"
        failure_reason = failure_reason or "no_usable_images"
    elif conflicts or len(files) != len(assets) or (
        expected_count is not None and len(files) != expected_count
    ):
        status = "partial"
        failure_reason = failure_reason or "incomplete_or_conflicting_assets"
    else:
        status = "complete"

    return (
        {
            "item_type": "note",
            "note_id": note_id,
            "title": title,
            "source_url": source_url,
            "content_type": content_type,
            "expected_count": expected_count,
            "downloaded_count": len(files),
            "files": files,
            "file_details": file_details,
            "watermark_check": {
                "result": watermark["result"],
                "scope": watermark["scope"],
                "checked_files": checked_files,
            },
            "status": status,
            "failure_reason": failure_reason,
            "notes": notes,
        },
        conflicts,
    )


def write_csv(path: Path, items: list[dict[str, Any]]) -> None:
    fields = [
        "item_type",
        "note_id",
        "title",
        "source_url",
        "content_type",
        "expected_count",
        "downloaded_count",
        "files",
        "watermark_visible",
        "watermark_scope",
        "watermark_checked_files",
        "status",
        "failure_reason",
        "notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in items:
            row = {field: item.get(field, "") for field in fields}
            row["files"] = ";".join(item["files"])
            row["watermark_visible"] = item["watermark_check"]["result"]
            row["watermark_scope"] = item["watermark_check"]["scope"]
            row["watermark_checked_files"] = ";".join(
                item["watermark_check"]["checked_files"]
            )
            writer.writerow(row)


def run(capture_path: Path, output_root: Path) -> int:
    payload = read_json(capture_path)
    validate_capture(payload)
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, list[str]] = {}
    items: list[dict[str, Any]] = []
    has_conflicts = False

    for raw_item in payload["items"]:
        item, item_conflicts = materialize_item(raw_item, output_root, hashes)
        items.append(item)
        has_conflicts = has_conflicts or item_conflicts

    duplicate_groups = [paths for paths in hashes.values() if len(paths) > 1]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "export_type": "xhs-public-image-notes",
        "account_url": canonical_xhs_url(payload["account_url"], "account_url"),
        "captured_at": safe_text(payload.get("captured_at"), "captured_at"),
        "authorization_basis": safe_text(
            payload["authorization"].get("basis"), "authorization.basis"
        ),
        "items": items,
        "summary": {
            "item_count": len(items),
            "complete_count": sum(item["status"] == "complete" for item in items),
            "partial_count": sum(item["status"] == "partial" for item in items),
            "failed_count": sum(item["status"] == "failed" for item in items),
            "image_count": sum(item["downloaded_count"] for item in items),
            "duplicate_group_count": len(duplicate_groups),
            "duplicate_groups": duplicate_groups,
        },
    }
    atomic_json(output_root / "manifest.json", manifest)
    write_csv(output_root / "manifest.csv", items)
    print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2))
    return 2 if has_conflicts else 0


def main() -> int:
    args = parse_args()
    try:
        return run(args.capture, args.output)
    except CaptureError as exc:
        print(f"capture error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
