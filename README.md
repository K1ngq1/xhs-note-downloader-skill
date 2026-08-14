# XHS Authorized Assets Plugin

[English](README.md) | [简体中文](README.zh-CN.md)

A two-skill plugin for exporting authorized Xiaohongshu image notes and shop product assets.

It includes `xhs-public-note-assets` for image notes and `xhs-authorized-shop-assets` for authorized product-detail images and currently displayed prices. It excludes orders, stock or listing changes, videos, watermark removal, CAPTCHA bypass, and unauthorized bulk collection.

## One-command install

Windows:

```bat
py -3 -c "import urllib.request; exec(urllib.request.urlopen('https://raw.githubusercontent.com/K1ngq1/xhs-note-downloader-skill/main/install.py').read().decode('utf-8'))"
```

macOS / Linux:

```bash
python3 -c "import urllib.request; exec(urllib.request.urlopen('https://raw.githubusercontent.com/K1ngq1/xhs-note-downloader-skill/main/install.py').read().decode('utf-8'))"
```

This fast path copies both skills to `~/.agents/skills` using only the Python standard library. It does not install the optional XHS-Downloader runtime. Use `--replace` to update while retaining the previous installation as a timestamped backup.

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
skills/xhs-authorized-shop-assets/
  SKILL.md
  agents/openai.yaml
  scripts/
  references/
.codex-plugin/plugin.json
install.py
tests/
```

No downloaded media, Cookie, token, account-specific data, browser profile, or absolute personal path belongs in this repository.

## Install through an agent

Codex `$skill-installer` can also install both repository paths:

```text
skills/xhs-public-note-assets
skills/xhs-authorized-shop-assets
```

The plugin manifest exposes both focused skills in one package.

## Optional XHS-Downloader MCP

Shop capture uses the signed-in visible browser and does not require XHS-Downloader. Install the optional runtime only for the note MCP path. A combined one-command install is:

```bat
py -3.12 -c "import urllib.request; exec(urllib.request.urlopen('https://raw.githubusercontent.com/K1ngq1/xhs-note-downloader-skill/main/install.py').read().decode('utf-8'))" --with-runtime
```

XHS-Downloader is a separate GPL-3.0 dependency and is not bundled here. The helper requires Git and Python 3.12 and prefers `uv` when available:

```text
python skills/xhs-public-note-assets/scripts/bootstrap_xhs_downloader.py \
  --python /path/to/python3.12 \
  --install-dir /path/to/XHS-Downloader-2.7 \
  --installer auto
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

```text
Use $xhs-authorized-shop-assets to archive my authorized shop's product images and currently displayed prices.
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
