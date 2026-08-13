#!/usr/bin/env python3
"""Run lightweight repository-side validation for the packaged skill."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "xhs-public-note-assets"
MEDIA_SUFFIXES = {
    ".avif",
    ".gif",
    ".heic",
    ".jpeg",
    ".jpg",
    ".mkv",
    ".mov",
    ".mp4",
    ".png",
    ".webp",
}
SENSITIVE_PATTERNS = {
    "Cookie value": re.compile(r"(?:web_session|a1|webId)\s*=[^\s;]{8,}"),
    "signed XHS token": re.compile(r"xsec_token=[A-Za-z0-9_-]{12,}"),
    "authorization header": re.compile(r"Authorization\s*:\s*(?:Bearer|Basic)\s+", re.I),
    "personal Windows path": re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+"),
}


def main() -> None:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        raise SystemExit("SKILL.md has no YAML frontmatter")
    metadata = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            raise SystemExit("Invalid SKILL.md frontmatter line")
        metadata[key.strip()] = value.strip()
    if set(metadata) != {"name", "description"}:
        raise SystemExit("SKILL.md frontmatter must contain only name and description")
    if metadata["name"] != "xhs-public-note-assets":
        raise SystemExit("Unexpected skill name")
    interface = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
    if not re.search(
        r'^\s*default_prompt:\s*["\'].*\$xhs-public-note-assets.*["\']\s*$',
        interface,
        re.MULTILINE,
    ):
        raise SystemExit("Default prompt must mention the skill")
    for required_interface_text in (
        'type: "mcp"',
        'value: "xhsDownloader"',
        'transport: "streamable_http"',
        'url: "http://127.0.0.1:5556/mcp/"',
    ):
        if required_interface_text not in interface:
            raise SystemExit(
                f"agents/openai.yaml is missing: {required_interface_text}"
            )
    required = [
        SKILL / "scripts" / "bootstrap_xhs_downloader.py",
        SKILL / "scripts" / "configure_cookie.py",
        SKILL / "scripts" / "build_capture_from_mcp.py",
        SKILL / "scripts" / "materialize_export.py",
        SKILL / "scripts" / "validate_export.py",
        SKILL / "references" / "capture-schema.md",
        SKILL / "references" / "manifest-schema.md",
        SKILL / "references" / "xhs-downloader-mcp.md",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit(f"Missing required files: {missing}")

    media = [str(path.relative_to(ROOT)) for path in ROOT.rglob("*") if path.suffix.lower() in MEDIA_SUFFIXES]
    if media:
        raise SystemExit(f"Downloaded media must not be committed: {media}")

    public_text_files = [ROOT / "README.md", SKILL / "SKILL.md"]
    public_text_files.extend((SKILL / "agents").rglob("*"))
    public_text_files.extend((SKILL / "references").rglob("*"))
    public_text_files.extend((SKILL / "scripts").rglob("*.py"))
    for path in public_text_files:
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        for label, pattern in SENSITIVE_PATTERNS.items():
            if pattern.search(content):
                raise SystemExit(f"Potential {label} in {path.relative_to(ROOT)}")
    print("Repository skill validation passed")


if __name__ == "__main__":
    main()
