---
name: xhs-authorized-shop-assets
description: Archive product detail images and currently displayed prices from a Xiaohongshu shop that the user owns or is explicitly authorized to access. Use for 小红书店铺素材归档, 千帆商品抓取, 商品详情图下载, 店铺价格导出, authorized XHS shop export, or product asset manifest requests. Excludes orders, stock changes, publishing, private API bypass, and unauthorized competitor collection.
---

# Xiaohongshu Authorized Shop Assets

Archive authorized shop product images and timestamped visible prices without changing shop state. Use the signed-in Codex Browser for inventory and capture, then use the bundled scripts for deterministic organization and validation.

## Guardrails

- Confirm that the user owns or manages the shop, or has explicit permission from its owner.
- Work only with pages visible through the user's normal public or merchant session. Never bypass login, CAPTCHA, rate limits, access controls, or anti-bot checks.
- Keep the workflow read-only. Never edit, publish, unlist, order, add to cart, change stock, modify prices, or enter fulfillment flows.
- Treat every displayed price as an observation at `captured_at`, not a permanent catalog value. Preserve ranges, promotion labels, and variant ambiguity exactly as displayed.
- Never inspect, export, or log Cookie values, authorization headers, browser profiles, local storage, or signed query parameters.
- Preserve platform watermarks. Do not enlarge, convert, or remove them.
- Refuse unauthorized competitor-shop bulk collection.

## Workflow

1. Confirm authorization, the shop/account/product URL, and the output root.
2. Open the public shop or product link in Codex Browser. If the public desktop profile omits shop navigation and the user owns or manages the shop, open Xiaohongshu Qianfan at `https://ark.xiaohongshu.com` and let the user complete merchant login or verification.
3. Stay in read-only product-list and product-detail views. Build the complete product inventory before downloading anything.
4. Record each product's stable ID, visible name, canonical URL, exact displayed price text, currency, price context, visible image count, and access status.
5. Open each product detail page. Traverse the full gallery and lazy-loaded detail section. Prefer the largest visually equivalent image resource actually loaded by the authenticated page.
6. Exclude avatars, icons, recommendations, tracking pixels, unrelated banners, video posters, and duplicate thumbnails. Do not call private APIs or generate signatures.
7. Save temporary images outside the final export and write UTF-8 `shop-capture.json` according to [references/shop-capture-schema.md](references/shop-capture-schema.md).
8. Run `scripts/materialize_shop_export.py --capture <shop-capture.json> --output <output-root>` with Python 3.11+ and Pillow.
9. Visually inspect every exported image before setting `watermark_check.result` to `false`; otherwise keep it `unknown`.
10. Run `scripts/validate_shop_export.py --output <output-root>`. Complete only when every inventory item is `complete`, `partial`, or `failed` with an explicit reason.

## Price Rules

- Preserve the exact visible string, including `¥`, crossed-out context, promotion text, and ranges.
- Never infer one price from a range or from an unselected variant.
- Record the initially displayed state. Inspect variants only when the user explicitly requests it and the interaction remains within the read-only product page.
- Set `price_context` to a concise observation such as `listing`, `promotion`, `selected_variant`, `range`, or an ambiguity note.
- Record missing or login-blocked prices as `partial` or `failed`; never invent them.

## Failure Handling

- Pause for user action when login, merchant verification, CAPTCHA, or a slider appears.
- Do not interpret a missing public shop tab as an empty shop. Try an authorized merchant view or ask for a product/share link.
- Record deleted, private, unavailable, incompletely loaded, or variant-ambiguous products instead of silently omitting them.
- Treat an existing destination containing different bytes as a conflict. Do not overwrite or delete it.
- A successful page or network response is not proof of completion. Confirm every local file exists, decodes, and matches the inventory.

## Output

```text
<output-root>/
  shop/products/<product-id>/01-cover.webp
  shop/products/<product-id>/02-detail.webp
  manifest.json
  manifest.csv
```

See [references/shop-manifest-schema.md](references/shop-manifest-schema.md) for output fields. Report product count, verified image count, price caveats, partial or failed items, duplicate groups, watermark findings, capture time, and output path.
