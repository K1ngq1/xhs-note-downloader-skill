#!/usr/bin/env python3
"""Validate a materialized XHS public-note export without changing it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - depends on the caller runtime
    raise SystemExit(
        "Pillow is required for image decoding. Use the bundled Codex Python runtime "
        "or install Pillow in the active environment."
    ) from exc


SENSITIVE_VALUE_RE = re.compile(
    r"(?i)(xsec_token\s*=|cookie\s*:|authorization\s*:|bearer\s+[A-Za-z0-9._~-]+|"
    r"browser-use[\\/]assets|appdata[\\/]local[\\/]temp|(?:^|\s)/tmp/)"
)
FORBIDDEN_KEYS = {
    "cookie",
    "cookies",
    "authorization",
    "authorization_header",
    "headers",
    "signed_url",
    "source_path",
}
SIGNED_QUERY_KEYS = {
    "xsec_token",
    "xsec_source",
    "sign",
    "signature",
    "expires",
    "token",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an XHS public-note export")
    parser.add_argument("--output", required=True, type=Path, help="Export root")
    parser.add_argument("--json-report", type=Path, help="Optional report destination")
    return parser.parse_args()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_issue(target: list[dict[str, str]], code: str, message: str) -> None:
    target.append({"code": code, "message": message})


def scan_sensitive(
    value: Any,
    errors: list[dict[str, str]],
    location: str = "$",
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in FORBIDDEN_KEYS:
                add_issue(errors, "forbidden_key", f"{location}.{key} is not allowed")
            scan_sensitive(child, errors, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_sensitive(child, errors, f"{location}[{index}]")
    elif isinstance(value, str):
        if SENSITIVE_VALUE_RE.search(value):
            add_issue(errors, "sensitive_value", f"{location} contains sensitive material")
        parts = urlsplit(value)
        if parts.scheme in {"http", "https"}:
            keys = {key.lower() for key, _ in parse_qsl(parts.query, keep_blank_values=True)}
            leaked = sorted(keys & SIGNED_QUERY_KEYS)
            if leaked:
                add_issue(
                    errors,
                    "signed_query",
                    f"{location} contains signed query keys: {', '.join(leaked)}",
                )


def inside_root(root: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath([str(root), str(candidate)]) == str(root)
    except ValueError:
        return False


def inspect_file(
    output_root: Path,
    detail: dict[str, Any],
    errors: list[dict[str, str]],
) -> tuple[str, str] | None:
    relative = detail.get("path")
    if not isinstance(relative, str) or not relative:
        add_issue(errors, "invalid_path", "file detail has no relative path")
        return None
    candidate = (output_root / relative).resolve()
    if Path(relative).is_absolute() or not inside_root(output_root, candidate):
        add_issue(errors, "unsafe_path", f"Path escapes output root: {relative}")
        return None
    if not candidate.is_file():
        add_issue(errors, "missing_file", f"Missing file: {relative}")
        return None
    if candidate.stat().st_size == 0:
        add_issue(errors, "zero_byte", f"Zero-byte file: {relative}")
        return None
    try:
        with Image.open(candidate) as image:
            image.verify()
        with Image.open(candidate) as image:
            width, height = image.size
            image_format = (image.format or "").upper()
    except (OSError, ValueError) as exc:
        add_issue(errors, "decode_error", f"Cannot decode {relative}: {exc}")
        return None
    digest = file_digest(candidate)
    if detail.get("sha256") != digest:
        add_issue(errors, "hash_mismatch", f"SHA-256 mismatch: {relative}")
    if detail.get("bytes") != candidate.stat().st_size:
        add_issue(errors, "size_mismatch", f"Byte count mismatch: {relative}")
    if detail.get("width") != width or detail.get("height") != height:
        add_issue(errors, "dimension_mismatch", f"Dimension mismatch: {relative}")
    if detail.get("format") != image_format:
        add_issue(errors, "format_mismatch", f"Format mismatch: {relative}")
    return digest, relative


def validate_item(
    output_root: Path,
    item: Any,
    hashes: dict[str, list[str]],
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> None:
    if not isinstance(item, dict):
        add_issue(errors, "invalid_item", "Manifest item must be an object")
        return
    note_id = str(item.get("note_id", "unknown"))
    files = item.get("files")
    details = item.get("file_details")
    if not isinstance(files, list) or not isinstance(details, list):
        add_issue(errors, "invalid_file_list", f"{note_id}: files and file_details must be arrays")
        return
    detail_paths = [detail.get("path") for detail in details if isinstance(detail, dict)]
    if files != detail_paths:
        add_issue(errors, "order_mismatch", f"{note_id}: files and file_details order differ")
    if item.get("downloaded_count") != len(files):
        add_issue(errors, "count_mismatch", f"{note_id}: downloaded_count is incorrect")

    valid_files: list[str] = []
    for detail in details:
        if not isinstance(detail, dict):
            add_issue(errors, "invalid_file_detail", f"{note_id}: invalid file detail")
            continue
        inspected = inspect_file(output_root, detail, errors)
        if inspected:
            digest, relative = inspected
            hashes.setdefault(digest, []).append(relative)
            valid_files.append(relative)

    status = item.get("status")
    content_type = item.get("content_type")
    expected = item.get("expected_count")
    failure_reason = item.get("failure_reason")
    if status not in {"complete", "partial", "failed"}:
        add_issue(errors, "invalid_status", f"{note_id}: invalid status")
    if status == "complete":
        if content_type != "image" or len(valid_files) != len(files) or not files:
            add_issue(errors, "false_complete", f"{note_id}: complete item is not fully valid")
        if expected is not None and expected != len(files):
            add_issue(errors, "false_complete", f"{note_id}: expected count is not satisfied")
        if failure_reason:
            add_issue(errors, "false_complete", f"{note_id}: complete item has failure_reason")
    else:
        if not failure_reason:
            add_issue(errors, "missing_failure_reason", f"{note_id}: non-complete item needs a reason")
        else:
            add_issue(warnings, "non_complete_item", f"{note_id}: {status} ({failure_reason})")
    if content_type in {"video", "unavailable"} and files:
        add_issue(errors, "unexpected_files", f"{note_id}: non-image item contains files")

    watermark = item.get("watermark_check")
    if not isinstance(watermark, dict):
        add_issue(errors, "invalid_watermark", f"{note_id}: watermark_check must be an object")
        return
    result = watermark.get("result")
    scope = watermark.get("scope")
    checked_files = watermark.get("checked_files")
    if result not in {True, False, "unknown"} or scope not in {"none", "sample", "all"}:
        add_issue(errors, "invalid_watermark", f"{note_id}: invalid watermark result or scope")
    if not isinstance(checked_files, list) or any(path not in files for path in checked_files):
        add_issue(errors, "invalid_watermark_files", f"{note_id}: invalid checked file list")
    elif result is False and (scope != "all" or set(checked_files) != set(files)):
        add_issue(
            errors,
            "unverified_no_watermark",
            f"{note_id}: false requires all exported files to be inspected",
        )
    elif result is True and not checked_files:
        add_issue(errors, "unverified_watermark", f"{note_id}: true requires a checked file")


def run(output_root: Path) -> dict[str, Any]:
    output_root = output_root.resolve()
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    manifest_path = output_root / "manifest.json"
    csv_path = output_root / "manifest.csv"
    if not manifest_path.is_file():
        return {
            "valid": False,
            "errors": [{"code": "missing_manifest", "message": "manifest.json is missing"}],
            "warnings": [],
        }
    if not csv_path.is_file():
        add_issue(errors, "missing_csv", "manifest.csv is missing")
    elif not csv_path.read_bytes().startswith(b"\xef\xbb\xbf"):
        add_issue(errors, "csv_encoding", "manifest.csv must use UTF-8 BOM")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {
            "valid": False,
            "errors": [{"code": "invalid_manifest", "message": str(exc)}],
            "warnings": [],
        }
    if not isinstance(manifest, dict):
        return {
            "valid": False,
            "errors": [{"code": "invalid_manifest", "message": "Manifest root must be an object"}],
            "warnings": [],
        }
    scan_sensitive(manifest, errors)
    if manifest.get("schema_version") != 1:
        add_issue(errors, "schema_version", "Unsupported manifest schema version")
    if manifest.get("export_type") != "xhs-public-image-notes":
        add_issue(errors, "export_type", "Unexpected export_type")
    items = manifest.get("items")
    if not isinstance(items, list):
        add_issue(errors, "invalid_items", "items must be an array")
        items = []

    hashes: dict[str, list[str]] = {}
    for item in items:
        validate_item(output_root, item, hashes, errors, warnings)
    duplicate_groups = [paths for paths in hashes.values() if len(paths) > 1]
    if duplicate_groups:
        add_issue(
            warnings,
            "duplicate_assets",
            f"Found {len(duplicate_groups)} duplicate SHA-256 group(s)",
        )
    summary = manifest.get("summary")
    if not isinstance(summary, dict):
        add_issue(errors, "missing_summary", "summary must be an object")
    else:
        expected_summary = {
            "item_count": len(items),
            "complete_count": sum(item.get("status") == "complete" for item in items if isinstance(item, dict)),
            "partial_count": sum(item.get("status") == "partial" for item in items if isinstance(item, dict)),
            "failed_count": sum(item.get("status") == "failed" for item in items if isinstance(item, dict)),
            "image_count": sum(item.get("downloaded_count", 0) for item in items if isinstance(item, dict)),
            "duplicate_group_count": len(duplicate_groups),
            "duplicate_groups": duplicate_groups,
        }
        for key, expected_value in expected_summary.items():
            if summary.get(key) != expected_value:
                add_issue(errors, "summary_mismatch", f"summary.{key} is incorrect")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "item_count": len(items),
            "verified_file_count": sum(len(paths) for paths in hashes.values()),
            "duplicate_group_count": len(duplicate_groups),
        },
    }


def main() -> int:
    args = parse_args()
    report = run(args.output)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
