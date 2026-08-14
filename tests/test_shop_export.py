from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SHOP = ROOT / "skills" / "xhs-authorized-shop-assets"
MATERIALIZE = SHOP / "scripts" / "materialize_shop_export.py"
VALIDATE = SHOP / "scripts" / "validate_shop_export.py"


class ShopExportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="xhs-shop-test-")
        self.root = Path(self.temporary.name)
        self.sources = self.root / "中文商品素材"
        self.sources.mkdir()
        self.output = self.root / "店铺导出"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def image(self, name: str, color: tuple[int, int, int], fmt: str = "WEBP") -> Path:
        path = self.sources / name
        Image.new("RGB", (40, 30), color).save(path, format=fmt)
        return path

    def product(
        self,
        product_id: str,
        assets: list[Path],
        *,
        price: str = "¥199–¥239",
        expected: int | None = None,
        failure_reason: str = "",
    ) -> dict:
        return {
            "product_id": product_id,
            "name": f"中文商品 {product_id}",
            "source_url": (
                f"https://www.xiaohongshu.com/goods-detail/{product_id}"
                "?xsec_token=REMOVE_ME&xsec_source=pc"
            ),
            "display_price": price,
            "currency": "CNY" if price else "",
            "price_context": "visible range before variant selection",
            "expected_count": len(assets) if expected is None else expected,
            "assets": [
                {
                    "source_path": str(path),
                    "order": index,
                    "role": "cover" if index == 1 else "detail",
                }
                for index, path in enumerate(assets, 1)
            ],
            "failure_reason": failure_reason,
            "watermark_check": {
                "result": "unknown",
                "scope": "none",
                "checked_orders": [],
            },
            "notes": "",
        }

    def capture(self, products: list[dict], *, authorized: bool = True) -> Path:
        path = self.root / "shop-capture.json"
        payload = {
            "schema_version": 1,
            "capture_backend": "codex_browser",
            "shop_url": "https://ark.xiaohongshu.com/app/product/list?token=REMOVE",
            "captured_at": "2026-08-14T10:00:00+08:00",
            "authorization": {
                "basis": "owner_or_explicitly_authorized",
                "confirmed_by_user": authorized,
            },
            "products": products,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def run_script(self, script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )

    def materialize(self, capture: Path) -> subprocess.CompletedProcess[str]:
        return self.run_script(
            MATERIALIZE, "--capture", str(capture), "--output", str(self.output)
        )

    def validate(self) -> subprocess.CompletedProcess[str]:
        return self.run_script(VALIDATE, "--output", str(self.output))

    def manifest(self) -> dict:
        return json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))

    @staticmethod
    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_complete_and_partial_products_preserve_prices_and_order(self) -> None:
        cover = self.image("封面.webp", (200, 20, 20))
        detail = self.image("详情.png", (20, 200, 20), "PNG")
        missing_price = self.image("无价格.jpg", (20, 20, 200), "JPEG")
        capture = self.capture(
            [
                self.product("product-complete", [cover, detail]),
                self.product("product-price-missing", [missing_price], price=""),
            ]
        )
        result = self.materialize(capture)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = self.manifest()
        self.assertEqual(manifest["shop_url"], "https://ark.xiaohongshu.com/app/product/list")
        self.assertEqual(manifest["products"][0]["display_price"], "¥199–¥239")
        self.assertEqual(manifest["products"][0]["status"], "complete")
        self.assertEqual(manifest["products"][1]["status"], "partial")
        self.assertEqual(manifest["products"][1]["failure_reason"], "price_not_visible")
        self.assertEqual(
            manifest["products"][0]["files"],
            [
                "shop/products/product-complete/01-cover.webp",
                "shop/products/product-complete/02-detail.png",
            ],
        )
        self.assertNotIn("xsec_token", json.dumps(manifest))
        self.assertTrue((self.output / "manifest.csv").read_bytes().startswith(b"\xef\xbb\xbf"))
        validated = self.validate()
        self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)

    def test_authorization_conflict_and_sensitive_leak_checks(self) -> None:
        source = self.image("冲突.webp", (50, 60, 70))
        unauthorized = self.materialize(
            self.capture([self.product("unauthorized", [source])], authorized=False)
        )
        self.assertEqual(unauthorized.returncode, 1)
        self.assertIn("authorization", unauthorized.stderr.lower())

        first = self.materialize(self.capture([self.product("secure-product", [source])]))
        self.assertEqual(first.returncode, 0, first.stderr)
        manifest = self.manifest()
        manifest["products"][0]["notes"] = "xsec_token=LEAKED_VALUE"
        (self.output / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )
        leaked = self.validate()
        self.assertEqual(leaked.returncode, 1)
        self.assertIn("sensitive_value", leaked.stdout)

    def test_duplicate_reporting_and_conflict_does_not_overwrite(self) -> None:
        shared = self.image("重复.webp", (90, 80, 70))
        capture = self.capture(
            [
                self.product("duplicate-one", [shared]),
                self.product("duplicate-two", [shared]),
            ]
        )
        first = self.materialize(capture)
        self.assertEqual(first.returncode, 0, first.stderr)
        manifest = self.manifest()
        self.assertEqual(manifest["summary"]["duplicate_group_count"], 1)
        destination = (
            self.output
            / "shop"
            / "products"
            / "duplicate-one"
            / "01-cover.webp"
        )
        original = self.sha256(destination)
        Image.new("RGB", (40, 30), (1, 2, 3)).save(shared, format="WEBP")

        second = self.materialize(capture)
        self.assertEqual(second.returncode, 2, second.stderr)
        self.assertEqual(self.sha256(destination), original)
        self.assertEqual(self.manifest()["products"][0]["status"], "partial")
        self.assertEqual(
            self.manifest()["products"][0]["failure_reason"],
            "incomplete_or_conflicting_assets",
        )


if __name__ == "__main__":
    unittest.main()
