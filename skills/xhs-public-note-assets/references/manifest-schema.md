# Manifest Schema

The materializer writes UTF-8 `manifest.json` and UTF-8 BOM `manifest.csv` at the output root. Manifest schema version `1` contains no temporary source paths or signed URLs.

## Export fields

| Field | Meaning |
| --- | --- |
| `schema_version` | Manifest format version, currently `1` |
| `export_type` | `xhs-public-image-notes` |
| `account_url` | Canonical public account URL |
| `captured_at` | ISO 8601 observation timestamp with timezone |
| `authorization_basis` | User-confirmed ownership or explicit authorization |
| `items` | Per-note result objects |
| `summary` | Counts and SHA-256 duplicate groups |

## Per-note fields

| Field | Meaning |
| --- | --- |
| `note_id` | Stable public note identifier |
| `title` | Visible original title |
| `source_url` | Canonical note URL without disposable query parameters |
| `content_type` | `image`, `video`, or `unavailable` |
| `expected_count` | Visible carousel count when known |
| `downloaded_count` | Verified local image count |
| `files` | Ordered relative output paths |
| `file_details` | Role, order, dimensions, format, bytes, and SHA-256 |
| `watermark_check` | Result, inspection scope, and checked local files |
| `status` | `complete`, `partial`, or `failed` |
| `failure_reason` | Explicit reason for non-complete items |
| `notes` | Other caveats |

## Status rules

- Use `complete` only when every expected image is present, readable, and conflict-free.
- Use `partial` when some image assets are missing, invalid, or conflict with existing output.
- Use `failed` for unsupported video, deleted/private notes, login blocks, or notes with no usable images.
- Duplicate images are reported but are not automatically failures.

## Watermark rules

- `true`: a visible watermark was confirmed in at least one recorded file.
- `false`: every exported file for that note was visually inspected and no visible watermark was found.
- `unknown`: no inspection or only a sample inspection was completed.

The validator rejects `false` unless the inspection scope is `all` and the checked file list exactly covers the exported files.
