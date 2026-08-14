# Shop Capture Schema

Create temporary UTF-8 `shop-capture.json` after the authorized browser capture. The materializer accepts schema version `1`.

```json
{
  "schema_version": 1,
  "capture_backend": "codex_browser",
  "shop_url": "https://www.xiaohongshu.com/user/profile/SHOP_ID",
  "captured_at": "2026-08-14T10:00:00+08:00",
  "authorization": {
    "basis": "owner_or_explicitly_authorized",
    "confirmed_by_user": true
  },
  "products": [
    {
      "product_id": "PRODUCT_ID",
      "name": "Visible product name",
      "source_url": "https://www.xiaohongshu.com/goods-detail/PRODUCT_ID",
      "display_price": "¥199–¥239",
      "currency": "CNY",
      "price_context": "visible range before variant selection",
      "expected_count": 2,
      "assets": [
        {"source_path": "C:/temporary/PRODUCT_ID_1.webp", "order": 1, "role": "cover"},
        {"source_path": "C:/temporary/PRODUCT_ID_2.webp", "order": 2, "role": "detail"}
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

- Require `authorization.confirmed_by_user: true`.
- Use `capture_backend: codex_browser`; MCP note downloads are not a shop inventory backend.
- Use stable product IDs containing only letters, digits, `_`, or `-`.
- Preserve displayed price text exactly. Leave it empty only when `failure_reason` explains why it was unavailable.
- List assets in display order with contiguous positive `order` values. The first asset must be `cover` or `listing`; later assets use `detail`.
- Store local temporary paths only in the capture. Never include Cookie values, headers, browser profiles, signed CDN URLs, or tool traces.
- Use `watermark_check.result: false` only after every asset order has been visually inspected.
