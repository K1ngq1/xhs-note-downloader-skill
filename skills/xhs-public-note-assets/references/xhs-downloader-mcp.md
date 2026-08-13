# XHS-Downloader MCP Integration

This skill can use the external [JoeanAmier/XHS-Downloader](https://github.com/JoeanAmier/XHS-Downloader) project as its primary metadata and download backend. The upstream project is GPL-3.0 and is not bundled or relicensed by this MIT repository.

## Compatibility contract

The integration targets the stable `2.7` MCP contract:

- Streamable HTTP endpoint: `http://127.0.0.1:5556/mcp/`
- `get_detail_data(url)` returns `message` and note metadata in `data` without downloading.
- `download_detail(url, index, return_data)` downloads files. Use `index: null` for the full image set and `return_data: true` so the note metadata is returned.
- The MCP result does not contain local output paths. Never treat its success message as proof that a local export is complete.

If these tools or arguments differ, stop and report an incompatible upstream version instead of guessing.

## One-time local setup

Install XHS-Downloader according to its own documentation. Source installations require Python 3.12. The repository helper creates an isolated 2.7 environment, pins the tested FastMCP version, generates a localhost-only launcher, and adds a runtime-only parser compatibility shim without bundling upstream source:

```text
python scripts/bootstrap_xhs_downloader.py --python /path/to/python3.12 --install-dir /path/to/XHS-Downloader-2.7
```

In Codex Desktop, open **Settings → MCP servers → Add server**, choose **Streamable HTTP**, name it `xhsDownloader`, and use:

```text
http://127.0.0.1:5556/mcp/
```

Restart Codex after saving. The standalone skill can call a configured server, but it cannot install or keep the external process running by itself.

## Deterministic download settings

Use a dedicated folder and the following values in XHS-Downloader's `Volume/settings.json`. Keep all other values from the generated settings file.

```json
{
  "work_path": "YOUR_OWN_ABSOLUTE_WORK_PATH",
  "folder_name": "xhs-mcp-download",
  "name_format": "作品ID",
  "image_format": "AUTO",
  "image_download": true,
  "video_download": false,
  "live_download": false,
  "folder_mode": true,
  "download_record": false,
  "author_archive": false
}
```

With this configuration, an image note is expected under:

```text
<work_path>/xhs-mcp-download/<note-id>/<note-id>_1.<original-extension>
```

Pass `<work_path>/xhs-mcp-download` as `--download-root` to `build_capture_from_mcp.py`.

## Cookie boundary

Cookie is optional in the upstream project. Leave it empty for public content unless the user independently chooses to configure it inside XHS-Downloader. When chosen, run `scripts/configure_cookie.py --settings /path/to/Volume/settings.json` in the user's terminal so the value is hidden and control characters are removed. This skill must never:

- read a Cookie from a browser;
- ask the user to paste a Cookie into chat;
- pass a Cookie as an MCP argument;
- copy a Cookie into a response file, capture, manifest, shell command, log, or repository.

When a public request fails, prefer the visible browser fallback or record a failure. Do not weaken this boundary.

## Current compatibility notes

- Xiaohongshu may return empty note IDs to an anonymous profile page. A privately configured Cookie can restore IDs for content the session may normally view.
- A bare `/explore/<note-id>` URL can fail even when the profile listed the note. Use the complete temporary URL returned by the authorized session, then strip all query parameters from capture and manifest data.
- Current page state may include JavaScript values such as `new Map([])`, `new Set([])`, or `undefined`. The generated localhost launcher normalizes only these parser inputs before delegating to upstream 2.7.
- Never treat the MCP success string alone as proof. Confirm files exist and decode, then run `validate_export.py`.
