# XHS Note Downloader Skill

[English](README.md) | [简体中文](README.zh-CN.md)

A Codex Desktop Skill for exporting image assets from Xiaohongshu notes that the user owns or is explicitly authorized to archive.

The Skill uses the external XHS-Downloader MCP for metadata and downloads, preserves image bytes and carousel order, and produces validated JSON/CSV manifests. It excludes shops, prices, videos, watermark removal, private content, CAPTCHA bypass, and unauthorized bulk collection.

## Repository layout

```text
skills/xhs-public-note-assets/
  SKILL.md
  agents/openai.yaml
  scripts/
    bootstrap_xhs_downloader.py
    configure_cookie.py
    build_capture_from_mcp.py
    materialize_export.py
    validate_export.py
  references/
tests/
```

No downloaded media, Cookie, token, account-specific data, browser profile, or absolute personal path belongs in this repository.

## Install the Skill

Ask Codex to install the GitHub repository path:

```text
skills/xhs-public-note-assets
```

The installed Skill name is `xhs-public-note-assets`.

## Set up XHS-Downloader MCP

XHS-Downloader is a separate GPL-3.0 dependency and is not bundled here. The helper requires Git and Python 3.12:

```text
python skills/xhs-public-note-assets/scripts/bootstrap_xhs_downloader.py \
  --python /path/to/python3.12 \
  --install-dir /path/to/XHS-Downloader-2.7
```

The generated local launcher:

- pins the tested `fastmcp==2.14.5` contract;
- listens on `127.0.0.1:5556`, not the LAN;
- normalizes current Xiaohongshu page-state values such as `new Map([])`;
- keeps upstream code and its GPL license separate from this MIT repository.

Start it with the generated `.venv` Python and `run_mcp_local.py`, then configure Codex Desktop:

```text
Name: xhsDownloader
Transport: Streamable HTTP
URL: http://127.0.0.1:5556/mcp/
```

## Optional Cookie

Some public notes now require a current `xsec_token`, and obtaining it can require a signed-in profile session. Configure Cookie privately only if the user chooses to do so:

```text
python skills/xhs-public-note-assets/scripts/configure_cookie.py \
  --settings /path/to/XHS-Downloader-2.7/Volume/settings.json
```

The terminal prompt is hidden. The helper removes accidental CR/LF/tab characters and never prints the value. Never paste Cookie into chat, commit it, place it in command arguments, or copy it into manifests. Rotate the Cookie if it appears in any log.

## Use

```text
Use $xhs-public-note-assets to archive this authorized Xiaohongshu image note and produce a verified manifest.
```

For a profile, inventory first, keep only authorized `normal`/image notes, and pass the complete URL including its temporary `xsec_token` directly to MCP. All exported manifest URLs are canonicalized and stripped of signed query parameters.

## Verified behavior

The current integration was forward-tested on XHS-Downloader 2.7 with a five-image `normal` note. All five JPEGs downloaded locally, decoded successfully at `3600 × 4800`, and had unique SHA-256 hashes. The repository contains no test media or account data.

This is a compatibility observation, not a promise that Xiaohongshu endpoints will remain unchanged.

## Development

```text
python -m pip install Pillow
python -m unittest discover -s tests -v
python scripts/validate_skill.py
```

Also run Codex `skill-creator/scripts/quick_validate.py` against `skills/xhs-public-note-assets` before publishing.

## License

MIT for this repository. XHS-Downloader remains governed by GPL-3.0. Exported content remains subject to the content owner's rights and applicable platform terms.
