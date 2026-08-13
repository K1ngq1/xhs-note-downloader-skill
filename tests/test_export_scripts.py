from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "xhs-public-note-assets"
BUILD_CAPTURE = SKILL / "scripts" / "build_capture_from_mcp.py"
MATERIALIZE = SKILL / "scripts" / "materialize_export.py"
VALIDATE = SKILL / "scripts" / "validate_export.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExportScriptsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="xhs-skill-test-")
        self.root = Path(self.temporary.name)
        self.sources = self.root / "中文素材"
        self.sources.mkdir()
        self.mcp_download = self.root / "MCP下载"
        self.mcp_download.mkdir()
        self.output = self.root / "中文导出"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def image(self, name: str, color: tuple[int, int, int], fmt: str = "WEBP") -> Path:
        path = self.sources / name
        Image.new("RGB", (32, 24), color).save(path, format=fmt)
        return path

    def item(
        self,
        note_id: str,
        sources: list[Path],
        *,
        expected: int | None = None,
        watermark_result: bool | str = "unknown",
        watermark_scope: str = "none",
        checked_orders: list[int] | None = None,
    ) -> dict:
        return {
            "note_id": note_id,
            "title": f"中文标题 {note_id}",
            "source_url": (
                f"https://www.xiaohongshu.com/explore/{note_id}"
                "?xsec_token=SHOULD_BE_REMOVED&xsec_source=pc_search"
            ),
            "content_type": "image",
            "expected_count": len(sources) if expected is None else expected,
            "assets": [
                {
                    "source_path": str(path),
                    "order": index,
                    "role": "cover" if index == 1 else "detail",
                }
                for index, path in enumerate(sources, 1)
            ],
            "failure_reason": "",
            "watermark_check": {
                "result": watermark_result,
                "scope": watermark_scope,
                "checked_orders": checked_orders or [],
            },
            "notes": "",
        }

    def capture(self, items: list[dict]) -> Path:
        path = self.root / "capture.json"
        payload = {
            "schema_version": 1,
            "account_url": (
                "https://www.xiaohongshu.com/user/profile/authorized-account"
                "?xsec_token=REMOVE_ME"
            ),
            "captured_at": "2026-08-13T10:00:00+08:00",
            "authorization": {
                "basis": "owner_or_explicitly_authorized",
                "confirmed_by_user": True,
            },
            "items": items,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def mcp_response(
        self,
        note_id: str,
        content_type: str,
        count: int,
        *,
        wrapped: bool = False,
    ) -> Path:
        data = {
            "作品ID": note_id,
            "作者ID": "authorized-account",
            "作品标题": f"MCP 中文标题 {note_id}",
            "作品类型": content_type,
            "作品链接": (
                f"https://www.xiaohongshu.com/explore/{note_id}"
                "?xsec_token=DO_NOT_COPY"
            ),
            "下载地址": [
                f"https://signed.example/{note_id}/{index}?xsec_token=DO_NOT_COPY"
                for index in range(1, count + 1)
            ],
        }
        payload = {"message": "ok", "data": data}
        if wrapped:
            payload = {"structuredContent": payload}
        path = self.root / f"{note_id}-response.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def build_capture(
        self,
        responses: list[Path],
        *,
        confirm: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(BUILD_CAPTURE)]
        for response in responses:
            command.extend(["--response", str(response)])
        command.extend(
            [
                "--download-root",
                str(self.mcp_download),
                "--capture",
                str(self.root / "capture.json"),
            ]
        )
        if confirm:
            command.append("--authorization-confirmed")
        return subprocess.run(command, text=True, capture_output=True, check=False)

    def materialize(self, capture: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(MATERIALIZE),
                "--capture",
                str(capture),
                "--output",
                str(self.output),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def validate(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATE), "--output", str(self.output)],
            text=True,
            capture_output=True,
            check=False,
        )

    def read_manifest(self) -> dict:
        return json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))

    def test_single_multi_video_and_idempotent_rerun(self) -> None:
        cover = self.image("封面.webp", (220, 30, 30))
        slide_1 = self.image("轮播一.png", (30, 220, 30), "PNG")
        slide_2 = self.image("轮播二.jpg", (30, 30, 220), "JPEG")
        items = [
            self.item(
                "single-note",
                [cover],
                watermark_result=False,
                watermark_scope="all",
                checked_orders=[1],
            ),
            self.item("multi-note", [slide_1, slide_2]),
            {
                "note_id": "video-note",
                "title": "视频笔记",
                "source_url": "https://www.xiaohongshu.com/explore/video-note",
                "content_type": "video",
                "expected_count": 0,
                "assets": [],
                "failure_reason": "unsupported_video",
                "watermark_check": {
                    "result": "unknown",
                    "scope": "none",
                    "checked_orders": [],
                },
                "notes": "",
            },
        ]
        capture = self.capture(items)
        first = self.materialize(capture)
        self.assertEqual(first.returncode, 0, first.stderr)
        manifest = self.read_manifest()
        self.assertNotIn("xsec_token", json.dumps(manifest))
        self.assertEqual(manifest["summary"]["complete_count"], 2)
        self.assertEqual(manifest["summary"]["failed_count"], 1)
        self.assertEqual(
            manifest["items"][1]["files"],
            ["notes/multi-note/01-cover.png", "notes/multi-note/02-detail.jpg"],
        )
        self.assertTrue((self.output / "manifest.csv").read_bytes().startswith(b"\xef\xbb\xbf"))
        before = sha256(self.output / "notes" / "single-note" / "01-cover.webp")

        second = self.materialize(capture)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(before, sha256(self.output / "notes" / "single-note" / "01-cover.webp"))
        validated = self.validate()
        self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)

    def test_duplicate_group_and_partial_missing_source(self) -> None:
        shared = self.image("shared.webp", (120, 80, 40))
        missing = self.sources / "missing.webp"
        capture = self.capture(
            [
                self.item("duplicate-a", [shared]),
                self.item("duplicate-b", [shared]),
                self.item("partial-note", [shared, missing], expected=2),
            ]
        )
        result = self.materialize(capture)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = self.read_manifest()
        self.assertEqual(manifest["summary"]["duplicate_group_count"], 1)
        self.assertEqual(manifest["items"][2]["status"], "partial")
        self.assertEqual(
            manifest["items"][2]["failure_reason"],
            "incomplete_or_conflicting_assets",
        )
        validated = self.validate()
        self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)

    def test_conflict_does_not_overwrite_existing_file(self) -> None:
        source = self.image("conflict.webp", (10, 20, 30))
        capture = self.capture([self.item("conflict-note", [source])])
        first = self.materialize(capture)
        self.assertEqual(first.returncode, 0, first.stderr)
        destination = self.output / "notes" / "conflict-note" / "01-cover.webp"
        original_hash = sha256(destination)
        Image.new("RGB", (32, 24), (200, 100, 50)).save(source, format="WEBP")

        second = self.materialize(capture)
        self.assertEqual(second.returncode, 2, second.stderr)
        self.assertEqual(original_hash, sha256(destination))
        item = self.read_manifest()["items"][0]
        self.assertEqual(item["status"], "failed")
        self.assertIn("conflict", item["notes"])

    def test_corrupt_output_and_token_leak_are_rejected(self) -> None:
        source = self.image("valid.webp", (50, 60, 70))
        capture = self.capture([self.item("secure-note", [source])])
        result = self.materialize(capture)
        self.assertEqual(result.returncode, 0, result.stderr)
        destination = self.output / "notes" / "secure-note" / "01-cover.webp"
        destination.write_bytes(b"not-an-image")
        invalid_image = self.validate()
        self.assertEqual(invalid_image.returncode, 1)
        self.assertIn("decode_error", invalid_image.stdout)

        result = self.materialize(self.capture([self.item("fresh-note", [source])]))
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = self.read_manifest()
        manifest["items"][0]["notes"] = "xsec_token=LEAK"
        (self.output / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        leaked = self.validate()
        self.assertEqual(leaked.returncode, 1)
        self.assertIn("sensitive_value", leaked.stdout)

    def test_materializer_refuses_unconfirmed_authorization(self) -> None:
        source = self.image("authorization.webp", (1, 2, 3))
        capture = self.capture([self.item("auth-note", [source])])
        payload = json.loads(capture.read_text(encoding="utf-8"))
        payload["authorization"]["confirmed_by_user"] = False
        capture.write_text(json.dumps(payload), encoding="utf-8")
        result = self.materialize(capture)
        self.assertEqual(result.returncode, 1)
        self.assertIn("authorization", result.stderr.lower())

    def test_mcp_bridge_builds_safe_complete_partial_and_video_capture(self) -> None:
        complete_dir = self.mcp_download / "mcp-complete"
        complete_dir.mkdir()
        Image.new("RGB", (32, 24), (11, 22, 33)).save(
            complete_dir / "mcp-complete_1.webp", format="WEBP"
        )
        Image.new("RGB", (32, 24), (44, 55, 66)).save(
            complete_dir / "mcp-complete_2.png", format="PNG"
        )
        partial_dir = self.mcp_download / "mcp-partial"
        partial_dir.mkdir()
        Image.new("RGB", (32, 24), (77, 88, 99)).save(
            partial_dir / "mcp-partial_1.jpeg", format="JPEG"
        )
        responses = [
            self.mcp_response("mcp-complete", "图文", 2, wrapped=True),
            self.mcp_response("mcp-partial", "图集", 2),
            self.mcp_response("mcp-video", "视频", 1),
        ]
        result = self.build_capture(responses)
        self.assertEqual(result.returncode, 0, result.stderr)
        capture = self.root / "capture.json"
        capture_text = capture.read_text(encoding="utf-8")
        self.assertNotIn("xsec_token", capture_text)
        self.assertNotIn("signed.example", capture_text)
        payload = json.loads(capture_text)
        self.assertEqual(payload["capture_backend"], "xhs_downloader_mcp")
        self.assertEqual(
            payload["account_url"],
            "https://www.xiaohongshu.com/user/profile/authorized-account",
        )
        self.assertEqual(len(payload["items"][1]["assets"]), 2)
        self.assertTrue(payload["items"][1]["assets"][1]["source_path"].endswith(".missing"))

        materialized = self.materialize(capture)
        self.assertEqual(materialized.returncode, 0, materialized.stderr)
        manifest = self.read_manifest()
        self.assertEqual(manifest["items"][0]["status"], "complete")
        self.assertEqual(manifest["items"][1]["status"], "partial")
        self.assertEqual(
            manifest["items"][1]["failure_reason"], "mcp_download_incomplete"
        )
        self.assertEqual(manifest["items"][2]["status"], "failed")
        self.assertEqual(manifest["items"][2]["failure_reason"], "unsupported_video")
        validated = self.validate()
        self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)

    def test_mcp_bridge_requires_authorization_confirmation(self) -> None:
        response = self.mcp_response("mcp-auth", "图文", 1)
        result = self.build_capture([response], confirm=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("authorization", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
