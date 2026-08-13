# Capture Schema

Create a temporary UTF-8 `capture.json` after MCP or browser collection. The materializer accepts schema version `1`.

```json
{
  "schema_version": 1,
  "capture_backend": "xhs_downloader_mcp",
  "account_url": "https://www.xiaohongshu.com/user/profile/ACCOUNT_ID",
  "captured_at": "2026-08-13T10:00:00+08:00",
  "authorization": {
    "basis": "owner_or_explicitly_authorized",
    "confirmed_by_user": true
  },
  "items": [
    {
      "note_id": "NOTE_ID",
      "title": "Visible title",
      "source_url": "https://www.xiaohongshu.com/explore/NOTE_ID",
      "content_type": "image",
      "expected_count": 2,
      "assets": [
        {"source_path": "C:/temporary/xhs-mcp-download/NOTE_ID/NOTE_ID_1.webp", "order": 1, "role": "cover"},
        {"source_path": "C:/temporary/xhs-mcp-download/NOTE_ID/NOTE_ID_2.webp", "order": 2, "role": "detail"}
      ],
      "failure_reason": "",
      "watermark_check": {
        "result": "unknown",
        "scope": "none",
        "checked_orders": []
      },
      "notes": ""
    }
  ]
}
```

## Rules

- Set `authorization.confirmed_by_user` to `true`; otherwise the materializer refuses to run.
- Set `capture_backend` to `xhs_downloader_mcp` or `codex_browser`. This field is provenance only and is not copied into the public manifest.
- Use `content_type: image`, `video`, or `unavailable`.
- Use stable public note IDs containing only letters, digits, `_`, or `-`.
- Use canonical account and note URLs. The materializer removes known Xiaohongshu tracking parameters as a second safety layer.
- List image assets in display order. `order` must start at `1`, remain unique, and be contiguous for complete notes.
- Set the first image role to `cover` and later images to `detail`.
- Use local asset paths only. Never put cookies, headers, MCP traces, signed CDN URLs, or browser profile paths in this file.
- For video or unavailable notes, use an empty `assets` array and a non-empty `failure_reason`.
- Set watermark `result` to `false` only when `scope` is `all` and every image order appears in `checked_orders`.
- Use `result: true` after a visible watermark is confirmed. Use `unknown` for sample or no inspection.
