#!/usr/bin/env python3
"""Run lightweight repository-side validation for the packaged skill."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = {
    "xhs-public-note-assets": {
        "required": [
            "scripts/bootstrap_xhs_downloader.py",
            "scripts/configure_cookie.py",
            "scripts/build_capture_from_mcp.py",
            "scripts/materialize_export.py",
            "scripts/validate_export.py",
            "references/capture-schema.md",
            "references/manifest-schema.md",
            "references/xhs-downloader-mcp.md",
        ],
        "mcp": True,
    },
    "xhs-authorized-shop-assets": {
        "required": [
            "scripts/materialize_shop_export.py",
            "scripts/validate_shop_export.py",
            "references/shop-capture-schema.md",
            "references/shop-manifest-schema.md",
        ],
        "mcp": False,
    },
}
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
    for name, settings in SKILLS.items():
        skill = ROOT / "skills" / name
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        if not match:
            raise SystemExit(f"{name}/SKILL.md has no YAML frontmatter")
        metadata = {}
        for line in match.group(1).splitlines():
            key, separator, value = line.partition(":")
            if not separator:
                raise SystemExit(f"Invalid {name} frontmatter line")
            metadata[key.strip()] = value.strip()
        if set(metadata) != {"name", "description"} or metadata["name"] != name:
            raise SystemExit(f"Invalid frontmatter for {name}")
        interface = (skill / "agents" / "openai.yaml").read_text(encoding="utf-8")
        prompt_pattern = rf'^\s*default_prompt:\s*["\'].*\${re.escape(name)}.*["\']\s*$'
        if not re.search(prompt_pattern, interface, re.MULTILINE):
            raise SystemExit(f"Default prompt must mention ${name}")
        if settings["mcp"]:
            for required_interface_text in (
                'type: "mcp"',
                'value: "xhsDownloader"',
                'transport: "streamable_http"',
                'url: "http://127.0.0.1:5556/mcp/"',
            ):
                if required_interface_text not in interface:
                    raise SystemExit(
                        f"{name}/agents/openai.yaml is missing: {required_interface_text}"
                    )
        required = [skill / relative for relative in settings["required"]]
        missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
        if missing:
            raise SystemExit(f"Missing required files: {missing}")

    plugin = ROOT / ".codex-plugin" / "plugin.json"
    installer = ROOT / "install.py"
    if not plugin.is_file() or not installer.is_file():
        raise SystemExit("Plugin manifest and install.py are required")
    plugin_data = plugin.read_text(encoding="utf-8")
    for required_text in ('"name": "xhs-note-downloader"', '"skills": "./skills/"'):
        if required_text not in plugin_data:
            raise SystemExit(f"plugin.json is missing: {required_text}")

    media = [str(path.relative_to(ROOT)) for path in ROOT.rglob("*") if path.suffix.lower() in MEDIA_SUFFIXES]
    if media:
        raise SystemExit(f"Downloaded media must not be committed: {media}")

    public_text_files = [
        ROOT / "README.md",
        ROOT / "README.zh-CN.md",
        ROOT / "install.py",
        plugin,
    ]
    for name in SKILLS:
        skill = ROOT / "skills" / name
        public_text_files.append(skill / "SKILL.md")
        public_text_files.extend((skill / "agents").rglob("*"))
        public_text_files.extend((skill / "references").rglob("*"))
        public_text_files.extend((skill / "scripts").rglob("*.py"))
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
