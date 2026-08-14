#!/usr/bin/env python3
"""Validate a materialized authorized XHS shop export without changing it."""

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
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow is required for image validation") from exc


SENSITIVE_RE = re.compile(
    r"(?i)(xsec_token\s*=|cookie\s*:|authorization\s*:|bearer\s+|"
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
SIGNED_KEYS = {"xsec_token", "xsec_source", "sign", "signature", "expires", "token"}


def issue(target: list[dict[str, str]], code: str, message: str) -> None:
    target.append({"code": code, "message": message})


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def scan_sensitive(value: Any, errors: list[dict[str, str]], location: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in FORBIDDEN_KEYS:
                issue(errors, "forbidden_key", f"{location}.{key} is not allowed")
            scan_sensitive(child, errors, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_sensitive(child, errors, f"{location}[{index}]")
    elif isinstance(value, str):
        if SENSITIVE_RE.search(value):
            issue(errors, "sensitive_value", f"{location} contains sensitive material")
        parts = urlsplit(value)
        if parts.scheme in {"http", "https"}:
            keys = {key.lower() for key, _ in parse_qsl(parts.query, keep_blank_values=True)}
            leaked = sorted(keys & SIGNED_KEYS)
            if leaked:
                issue(errors, "signed_query", f"{location} contains signed query keys")


def inspect_detail(
    output: Path, detail: Any, errors: list[dict[str, str]]
) -> tuple[str, str] | None:
    if not isinstance(detail, dict):
        issue(errors, "invalid_file_detail", "file detail must be an object")
        return None
    relative = detail.get("path")
    if not isinstance(relative, str) or not relative:
        issue(errors, "invalid_path", "file detail has no path")
        return None
    candidate = (output / relative).resolve()
    try:
        inside = os.path.commonpath([str(output), str(candidate)]) == str(output)
    except ValueError:
        inside = False
    if Path(relative).is_absolute() or not inside:
        issue(errors, "unsafe_path", f"path escapes output: {relative}")
        return None
    if not candidate.is_file() or candidate.stat().st_size == 0:
        issue(errors, "missing_or_zero_byte", f"missing or empty file: {relative}")
        return None
    try:
        with Image.open(candidate) as image:
            image.verify()
        with Image.open(candidate) as image:
            width, height = image.size
            image_format = (image.format or "").upper()
    except (OSError, ValueError) as exc:
        issue(errors, "decode_error", f"cannot decode {relative}: {exc}")
        return None
    file_hash = digest(candidate)
    checks = {
        "sha256": file_hash,
        "bytes": candidate.stat().st_size,
        "width": width,
        "height": height,
        "format": image_format,
    }
    for key, expected in checks.items():
        if detail.get(key) != expected:
            issue(errors, f"{key}_mismatch", f"{relative}: {key} mismatch")
    return file_hash, relative


def validate_product(
    output: Path,
    product: Any,
    hashes: dict[str, list[str]],
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> None:
    if not isinstance(product, dict):
        issue(errors, "invalid_product", "product must be an object")
        return
    product_id = str(product.get("product_id", "unknown"))
    files = product.get("files")
    details = product.get("file_details")
    if not isinstance(files, list) or not isinstance(details, list):
        issue(errors, "invalid_file_list", f"{product_id}: invalid file lists")
        return
    if files != [item.get("path") for item in details if isinstance(item, dict)]:
        issue(errors, "order_mismatch", f"{product_id}: file order differs")
    if product.get("downloaded_count") != len(files):
        issue(errors, "count_mismatch", f"{product_id}: downloaded_count is incorrect")
    valid_files = []
    for detail in details:
        inspected = inspect_detail(output, detail, errors)
        if inspected:
            file_hash, relative = inspected
            hashes.setdefault(file_hash, []).append(relative)
            valid_files.append(relative)
    status = product.get("status")
    failure = product.get("failure_reason")
    price = product.get("display_price")
    expected = product.get("expected_count")
    if status not in {"complete", "partial", "failed"}:
        issue(errors, "invalid_status", f"{product_id}: invalid status")
    elif status == "complete":
        if not price or not files or len(valid_files) != len(files):
            issue(errors, "false_complete", f"{product_id}: complete data is missing")
        if expected is not None and expected != len(files):
            issue(errors, "false_complete", f"{product_id}: expected images are missing")
        if failure:
            issue(errors, "false_complete", f"{product_id}: complete item has failure reason")
    else:
        if not failure:
            issue(errors, "missing_failure_reason", f"{product_id}: failure reason is required")
        else:
            issue(warnings, "non_complete_product", f"{product_id}: {status} ({failure})")
    watermark = product.get("watermark_check")
    if not isinstance(watermark, dict):
        issue(errors, "invalid_watermark", f"{product_id}: watermark_check is invalid")
        return
    checked = watermark.get("checked_files")
    result = watermark.get("result")
    scope = watermark.get("scope")
    if result not in {True, False, "unknown"} or scope not in {"none", "sample", "all"}:
        issue(errors, "invalid_watermark", f"{product_id}: watermark values are invalid")
    if not isinstance(checked, list) or any(path not in files for path in checked):
        issue(errors, "invalid_watermark_files", f"{product_id}: checked files are invalid")
    elif result is False and (
        not files or scope != "all" or set(checked) != set(files)
    ):
        issue(errors, "unverified_no_watermark", f"{product_id}: false requires full inspection")
    elif result is True and not checked:
        issue(errors, "unverified_watermark", f"{product_id}: true requires an inspected file")


def run(output: Path) -> dict[str, Any]:
    output = output.resolve()
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    manifest_path = output / "manifest.json"
    csv_path = output / "manifest.csv"
    if not manifest_path.is_file():
        return {"valid": False, "errors": [{"code": "missing_manifest", "message": "manifest.json is missing"}], "warnings": []}
    if not csv_path.is_file() or not csv_path.read_bytes().startswith(b"\xef\xbb\xbf"):
        issue(errors, "missing_or_invalid_csv", "manifest.csv must exist with UTF-8 BOM")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"valid": False, "errors": [{"code": "invalid_manifest", "message": str(exc)}], "warnings": []}
    if not isinstance(manifest, dict):
        return {"valid": False, "errors": [{"code": "invalid_manifest", "message": "manifest root must be an object"}], "warnings": []}
    scan_sensitive(manifest, errors)
    if manifest.get("schema_version") != 1 or manifest.get("export_type") != "xhs-authorized-shop-products":
        issue(errors, "manifest_type", "unexpected schema or export type")
    products = manifest.get("products")
    if not isinstance(products, list):
        issue(errors, "invalid_products", "products must be an array")
        products = []
    hashes: dict[str, list[str]] = {}
    for product in products:
        validate_product(output, product, hashes, errors, warnings)
    duplicates = [paths for paths in hashes.values() if len(paths) > 1]
    if duplicates:
        issue(warnings, "duplicate_assets", f"found {len(duplicates)} duplicate group(s)")
    expected_summary = {
        "product_count": len(products),
        "complete_count": sum(item.get("status") == "complete" for item in products if isinstance(item, dict)),
        "partial_count": sum(item.get("status") == "partial" for item in products if isinstance(item, dict)),
        "failed_count": sum(item.get("status") == "failed" for item in products if isinstance(item, dict)),
        "image_count": sum(item.get("downloaded_count", 0) for item in products if isinstance(item, dict)),
        "duplicate_group_count": len(duplicates),
        "duplicate_groups": duplicates,
    }
    summary = manifest.get("summary")
    if not isinstance(summary, dict):
        issue(errors, "missing_summary", "summary must be an object")
    else:
        for key, expected in expected_summary.items():
            if summary.get(key) != expected:
                issue(errors, "summary_mismatch", f"summary.{key} is incorrect")
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "product_count": len(products),
            "verified_file_count": sum(len(paths) for paths in hashes.values()),
            "duplicate_group_count": len(duplicates),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an authorized XHS shop export")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--json-report", type=Path)
    args = parser.parse_args()
    report = run(args.output)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
