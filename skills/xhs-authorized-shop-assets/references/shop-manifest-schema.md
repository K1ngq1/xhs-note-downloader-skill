# Shop Manifest Schema

The materializer writes UTF-8 `manifest.json` and UTF-8 BOM `manifest.csv`. Schema version `1` contains no temporary source paths or signed URLs.

## Export fields

| Field | Meaning |
| --- | --- |
| `export_type` | `xhs-authorized-shop-products` |
| `shop_url` | Canonical shop or merchant URL |
| `captured_at` | ISO 8601 price observation timestamp |
| `authorization_basis` | Confirmed ownership or explicit permission |
| `products` | Per-product results |
| `summary` | Product, image, status, and duplicate counts |

## Product fields

| Field | Meaning |
| --- | --- |
| `product_id` | Stable product identifier |
| `name` | Visible product name |
| `source_url` | Canonical URL without signed queries |
| `display_price` | Exact visible price/range text |
| `currency` | Usually `CNY`; blank when unavailable |
| `price_context` | Listing, promotion, range, variant, or ambiguity note |
| `expected_count` | Visible gallery/detail-image count when known |
| `downloaded_count` | Verified local image count |
| `files` | Ordered relative paths |
| `file_details` | Role, order, dimensions, format, bytes, and SHA-256 |
| `watermark_check` | Result, inspection scope, and checked files |
| `status` | `complete`, `partial`, or `failed` |
| `failure_reason` | Required for non-complete products |

`complete` requires a visible price and every expected image. Missing prices, missing images, conflicts, or incomplete lazy loading are `partial` when some useful data exists and `failed` otherwise.
