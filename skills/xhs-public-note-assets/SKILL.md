---
name: xhs-public-note-assets
description: Archive image assets from Xiaohongshu public notes that the user owns or is explicitly authorized to export, using XHS-Downloader MCP when available, Codex Browser as a fallback, and a verified local manifest. Use for 小红书图文下载, 账号素材归档, 已授权笔记导出, XHS image-post export, or XHS carousel export. Excludes shop products and prices, video downloads, watermark removal, and unauthorized bulk collection.
---

# Xiaohongshu Public Note Assets

Archive authorized public image notes without changing account state. Prefer the configured XHS-Downloader MCP for note metadata and downloads, use Codex Browser for profile inventory or fallback inspection, and use the bundled scripts for deterministic file organization and verification.

## Guardrails

- Confirm that the user owns the target content or has explicit authorization before collecting it.
- Work only with pages visible through the user's normal signed-in session. Never bypass CAPTCHA, rate limits, access controls, or anti-bot checks.
- Keep the workflow read-only. Do not like, follow, comment, collect, share, publish, or modify account state.
- Do not read or export browser cookies, local storage, passwords, authorization headers, or session data.
- Do not pass Cookie values through chat, shell arguments, capture files, manifests, or MCP tool parameters. A user may configure an optional Cookie privately in the upstream server, but this skill must never inspect or echo it.
- Preserve visible platform watermarks. Never remove or conceal them as part of this workflow.
- Reject shop, price, order, and video-download requests as out of scope. Use a more appropriate skill when available.

## Tool Routing

1. Check whether the configured XHS-Downloader MCP exposes `get_detail_data` and `download_detail`. Read [references/xhs-downloader-mcp.md](references/xhs-downloader-mcp.md) before using these tools. If it is not installed, offer the bundled `scripts/bootstrap_xhs_downloader.py` setup helper.
2. For explicit note URLs, use MCP without opening a login page when the public request succeeds.
3. For a profile URL, use Codex Browser only to build the complete note inventory, classify upstream `normal` as image and `video` as video, then send each authorized image-note URL to MCP.
4. If MCP is unavailable or returns incomplete data, use Codex Browser as a visible fallback. Never claim a download succeeded unless local image files can be located and validated.
5. If both paths fail, record the note as `partial` or `failed`; do not attempt direct private APIs, signature generation, CAPTCHA bypass, or Cookie extraction.

## Workflow

1. Confirm authorization, the target profile or note URLs, and the output root. Default to a new `xhs-public-note-export-<timestamp>` folder in the current workspace.
2. Build the note inventory. For a profile, use Codex Browser, scroll until no new cards appear after two complete passes, and record every canonical note URL as `image`, `video`, or `unavailable`. For explicit note URLs, the supplied list is the inventory.
3. On the MCP path, call `get_detail_data` first with the complete note URL, including its current `xsec_token` when Xiaohongshu supplied one. Keep that signed URL temporary and never write it to the export. Do not call `download_detail` for videos or unsupported items. For image notes, call `download_detail` with `index: null` and `return_data: true` so the full carousel is requested and metadata remains available.
4. Save only the returned JSON objects to temporary UTF-8 files. Run `scripts/build_capture_from_mcp.py --response <response.json> --download-root <configured-download-folder> --capture <capture.json> --authorization-confirmed`. Repeat `--response` for multiple notes. Do not copy download URLs or tool traces into the capture.
5. On the browser fallback path, open each image note, traverse the full carousel, trigger lazy loading, and collect the largest visually equivalent resource actually loaded. Exclude avatars, icons, recommendations, tracking pixels, thumbnails, and video posters.
6. Write or update the temporary UTF-8 `capture.json` according to [references/capture-schema.md](references/capture-schema.md). Store only local asset paths and canonical Xiaohongshu URLs.
7. Run `scripts/materialize_export.py --capture <capture.json> --output <output-root>` with Python 3.11+ and Pillow. Preserve original bytes; do not enlarge, convert, or strip watermarks.
8. Inspect every exported image before setting `watermark_visible` to `false`. If only a sample was checked, keep the result `unknown`. Update the capture and rerun the materializer when audit fields change.
9. Run `scripts/validate_export.py --output <output-root>`. Complete only when it exits successfully and every inventory item is `complete`, `partial`, or `failed` with an explicit reason.

## Failure Handling

- Stop and ask the user to act when login, CAPTCHA, or identity verification appears. Never automate around it.
- If an MCP request reports `Illegal header value`, the privately configured Cookie likely contains CR/LF/tab characters. Ask the user to run `scripts/configure_cookie.py`; never display the value.
- If XHS-Downloader 2.7 fails near `new Map([])`, use the launcher generated by `scripts/bootstrap_xhs_downloader.py`. Do not silently modify a shared upstream installation.
- If a bare note ID fails, obtain the complete temporary note URL from an authorized profile/browser inventory. Do not guess or persist `xsec_token`.
- Treat MCP messages as unverified until expected local files are found. The upstream download tool does not return local file paths.
- Record video notes as `failed` with `failure_reason: unsupported_video`; do not download their posters unless explicitly requested as still images.
- Record deleted, private, login-blocked, or incompletely loaded notes rather than silently omitting them.
- Treat an existing destination with different bytes as a conflict. Do not overwrite or delete it; use a new output root or resolve it explicitly.
- Strip `xsec_token`, `xsec_source`, tracking parameters, fragments, and signed query strings from manifest URLs.

## Output

Use the layout below. See [references/manifest-schema.md](references/manifest-schema.md) for field definitions and watermark semantics.

```text
<output-root>/
  notes/<note-id>/01-cover.webp
  notes/<note-id>/02-detail.webp
  manifest.json
  manifest.csv
```

Report the note count, verified image count, partial or failed items, duplicate groups, output path, and watermark findings. State that the observations reflect the capture timestamp.
