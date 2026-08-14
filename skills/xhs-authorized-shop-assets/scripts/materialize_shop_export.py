#!/usr/bin/env python3
"""Materialize an authorized XHS shop capture into stable files and manifests."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow is required for image validation") from exc


ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
SENSITIVE_RE = re.compile(
    r"(?i)(xsec_token\s*=|cookie\s*:|authorization\s*:|bearer\s+[A-Za-z0-9._~-]+)"
)
EXTENSIONS = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "GIF": ".gif",
    "AVIF": ".avif",
}


class CaptureError(ValueError):
    """Raised when shop capture input is unsafe or invalid."""


def safe_text(value: Any, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise CaptureError(f"{field} must be a string")
    if SENSITIVE_RE.search(value):
        raise CaptureError(f"{field} contains sensitive material")
    return value.strip()


def canonical_url(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise CaptureError(f"{field} must be a string")
    text = value.strip()
    if re.search(r"(?i)(cookie\s*:|authorization\s*:|bearer\s+)", text):
        raise CaptureError(f"{field} contains sensitive header material")
    parts = urlsplit(text)
    host = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or not (
        host == "xiaohongshu.com" or host.endswith(".xiaohongshu.com")
    ):
        raise CaptureError(f"{field} must be an Xiaohongshu URL")
    return urlunsplit(("https", host, parts.path.rstrip("/") or "/", "", ""))


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def inspect_image(path: Path) -> tuple[int, int, str, str]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("missing or zero-byte source")
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        width, height = image.size
        image_format = (image.format or "").upper()
    extension = EXTENSIONS.get(image_format)
    if not extension:
        raise ValueError(f"unsupported image format: {image_format or 'unknown'}")
    return width, height, image_format, extension


def normalize_watermark(value: Any, orders: list[int]) -> dict[str, Any]:
    value = {} if value is None else value
    if not isinstance(value, dict):
        raise CaptureError("watermark_check must be an object")
    result = value.get("result", "unknown")
    scope = value.get("scope", "none")
    checked = value.get("checked_orders", [])
    if result not in {True, False, "unknown"} or scope not in {
        "none",
        "sample",
        "all",
    }:
        raise CaptureError("invalid watermark_check result or scope")
    if not isinstance(checked, list) or any(
        not isinstance(order, int) for order in checked
    ):
        raise CaptureError("watermark checked_orders must contain integers")
    checked = sorted(set(checked))
    if any(order not in orders for order in checked):
        raise CaptureError("watermark checked_orders contains an unknown order")
    if result is False and (
        not orders or scope != "all" or set(checked) != set(orders)
    ):
        raise CaptureError("watermark false requires inspection of every asset")
    if result is True and not checked:
        raise CaptureError("watermark true requires at least one inspected asset")
    return {"result": result, "scope": scope, "checked_orders": checked}


def normalize_assets(value: Any, product_id: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise CaptureError(f"{product_id}: assets must be an array")
    assets = []
    for raw in value:
        if not isinstance(raw, dict):
            raise CaptureError(f"{product_id}: asset must be an object")
        order = raw.get("order")
        role = raw.get("role")
        source = raw.get("source_path")
        if not isinstance(order, int) or order < 1:
            raise CaptureError(f"{product_id}: invalid asset order")
        if role not in {"listing", "cover", "detail"}:
            raise CaptureError(f"{product_id}: invalid asset role")
        if not isinstance(source, str) or not source.strip():
            raise CaptureError(f"{product_id}: source_path is required")
        assets.append(
            {"order": order, "role": role, "source": Path(source).expanduser()}
        )
    assets.sort(key=lambda item: item["order"])
    orders = [item["order"] for item in assets]
    if orders != list(range(1, len(orders) + 1)):
        raise CaptureError(f"{product_id}: asset orders must be contiguous from 1")
    if assets and assets[0]["role"] not in {"listing", "cover"}:
        raise CaptureError(f"{product_id}: first asset must be listing or cover")
    return assets


def append_note(existing: str, addition: str) -> str:
    return "; ".join(part for part in (existing, addition) if part)


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def materialize_product(
    raw: Any, output: Path, hashes: dict[str, list[str]]
) -> tuple[dict[str, Any], bool]:
    if not isinstance(raw, dict):
        raise CaptureError("each product must be an object")
    product_id = safe_text(raw.get("product_id"), "product_id")
    if not ID_RE.fullmatch(product_id):
        raise CaptureError(f"invalid product_id: {product_id!r}")
    name = safe_text(raw.get("name"), f"{product_id}.name")
    source_url = canonical_url(raw.get("source_url"), f"{product_id}.source_url")
    display_price = safe_text(
        raw.get("display_price"), f"{product_id}.display_price"
    )
    currency = safe_text(raw.get("currency"), f"{product_id}.currency")
    price_context = safe_text(
        raw.get("price_context"), f"{product_id}.price_context"
    )
    if display_price and (not currency or not price_context):
        raise CaptureError(
            f"{product_id}: visible prices require currency and price_context"
        )
    failure_reason = safe_text(
        raw.get("failure_reason"), f"{product_id}.failure_reason"
    )
    notes = safe_text(raw.get("notes"), f"{product_id}.notes")
    expected = raw.get("expected_count")
    if expected is not None and (not isinstance(expected, int) or expected < 0):
        raise CaptureError(
            f"{product_id}: expected_count must be non-negative or null"
        )
    assets = normalize_assets(raw.get("assets", []), product_id)
    watermark = normalize_watermark(
        raw.get("watermark_check"), [item["order"] for item in assets]
    )
    product_dir = output / "shop" / "products" / product_id
    product_dir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    details: list[dict[str, Any]] = []
    conflict = False
    width = max(2, len(str(max(len(assets), 1))))
    for asset in assets:
        try:
            image_width, image_height, image_format, extension = inspect_image(
                asset["source"]
            )
            source_hash = digest(asset["source"])
        except (OSError, ValueError) as exc:
            notes = append_note(notes, f"order {asset['order']}: {exc}")
            continue
        label = asset["role"] if asset["order"] == 1 else "detail"
        destination = (
            product_dir / f"{asset['order']:0{width}d}-{label}{extension}"
        )
        relative = destination.relative_to(output).as_posix()
        if destination.exists():
            if not destination.is_file() or digest(destination) != source_hash:
                conflict = True
                notes = append_note(notes, f"conflict: {relative}")
                continue
        else:
            shutil.copy2(asset["source"], destination)
        hashes.setdefault(source_hash, []).append(relative)
        files.append(relative)
        details.append(
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
        for detail in details
        if detail["order"] in watermark["checked_orders"]
    ]
    images_complete = (
        bool(files)
        and len(files) == len(assets)
        and not conflict
        and (expected is None or expected == len(files))
    )
    if images_complete and display_price:
        status = "complete"
        failure_reason = ""
    elif files or display_price:
        status = "partial"
        failure_reason = failure_reason or (
            "price_not_visible"
            if not display_price
            else "incomplete_or_conflicting_assets"
        )
    else:
        status = "failed"
        failure_reason = failure_reason or "no_usable_product_data"
    return (
        {
            "item_type": "product",
            "product_id": product_id,
            "name": name,
            "source_url": source_url,
            "display_price": display_price,
            "currency": currency,
            "price_context": price_context,
            "expected_count": expected,
            "downloaded_count": len(files),
            "files": files,
            "file_details": details,
            "watermark_check": {
                "result": watermark["result"],
                "scope": watermark["scope"],
                "checked_files": checked_files,
            },
            "status": status,
            "failure_reason": failure_reason,
            "notes": notes,
        },
        conflict,
    )


def write_csv(path: Path, products: list[dict[str, Any]]) -> None:
    fields = [
        "item_type",
        "product_id",
        "name",
        "source_url",
        "display_price",
        "currency",
        "price_context",
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
        for product in products:
            row = {field: product.get(field, "") for field in fields}
            row["files"] = ";".join(product["files"])
            row["watermark_visible"] = product["watermark_check"]["result"]
            row["watermark_scope"] = product["watermark_check"]["scope"]
            row["watermark_checked_files"] = ";".join(
                product["watermark_check"]["checked_files"]
            )
            writer.writerow(row)


def run(capture_path: Path, output: Path) -> int:
    try:
        payload = json.loads(capture_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CaptureError(f"cannot read capture: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise CaptureError("schema_version must be 1")
    authorization = payload.get("authorization")
    if not isinstance(authorization, dict) or authorization.get(
        "confirmed_by_user"
    ) is not True:
        raise CaptureError("user ownership or explicit authorization must be confirmed")
    basis = safe_text(authorization.get("basis"), "authorization.basis")
    if not basis:
        raise CaptureError("authorization.basis is required")
    if payload.get("capture_backend") != "codex_browser":
        raise CaptureError("capture_backend must be codex_browser")
    shop_url = canonical_url(payload.get("shop_url"), "shop_url")
    captured_at = safe_text(payload.get("captured_at"), "captured_at")
    try:
        observed_at = datetime.fromisoformat(captured_at)
    except ValueError as exc:
        raise CaptureError("captured_at must be an ISO 8601 timestamp") from exc
    if observed_at.tzinfo is None:
        raise CaptureError("captured_at must include a timezone")
    products_raw = payload.get("products")
    if not isinstance(products_raw, list) or not products_raw:
        raise CaptureError("products must be a non-empty array")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, list[str]] = {}
    products = []
    has_conflicts = False
    for raw in products_raw:
        product, conflict = materialize_product(raw, output, hashes)
        products.append(product)
        has_conflicts = has_conflicts or conflict
    duplicates = [paths for paths in hashes.values() if len(paths) > 1]
    manifest = {
        "schema_version": 1,
        "export_type": "xhs-authorized-shop-products",
        "shop_url": shop_url,
        "captured_at": captured_at,
        "authorization_basis": basis,
        "products": products,
        "summary": {
            "product_count": len(products),
            "complete_count": sum(
                item["status"] == "complete" for item in products
            ),
            "partial_count": sum(
                item["status"] == "partial" for item in products
            ),
            "failed_count": sum(item["status"] == "failed" for item in products),
            "image_count": sum(item["downloaded_count"] for item in products),
            "duplicate_group_count": len(duplicates),
            "duplicate_groups": duplicates,
        },
    }
    atomic_json(output / "manifest.json", manifest)
    write_csv(output / "manifest.csv", products)
    print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2))
    return 2 if has_conflicts else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize an authorized XHS shop export"
    )
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        return run(args.capture, args.output)
    except CaptureError as exc:
        print(f"capture error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
