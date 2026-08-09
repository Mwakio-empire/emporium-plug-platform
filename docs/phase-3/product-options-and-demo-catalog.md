# Product options, variants and visual demo catalogue

## Implemented behaviour

- A product owns ordered option groups such as `Size`, `Colour`, `Capacity` or `Pack size`.
- Each option owns ordered values. Colour values may include a validated `#RRGGBB` swatch.
- A sellable variant selects exactly one value from every option group and has its own SKU, optional price override, optional image, active state and branch stock.
- A database-level product/signature constraint prevents duplicate combinations.
- Existing one-pair variants are migrated into the structured model without changing their IDs, order references or stock references.
- The product page groups controls by option, resolves the exact combination, and updates SKU, price, stock and the cart variant ID.
- Cart, POS and API output use the complete option summary rather than only the legacy free-text pair.

The legacy `attribute_name` and `attribute_value` columns remain temporarily for backward compatibility with existing integrations and records. New catalogue administration must use product options and generated combinations.

## Admin workflow

1. Open **System data → Products** and create or edit the product.
2. Add the required option groups in the product page, then save.
3. Open each option using its change link and add its allowed values. Use `Colour swatches` and a hex colour for colour groups.
4. Return to Products, select the product, then run **Generate missing combinations from configured options**.
5. Open each generated variant to set a price override or variant image where required.
6. Add branch stock through the audited inventory workflow. Creating a variant does not invent stock.

Adding a new option value later is safe: run the generator again and it creates only the missing combinations.

## Local visual fixture

The generated catalogue is deliberately prefixed with `DEMO-` SKUs and is intended for local/staging visual and transaction testing, not production merchandising.

```powershell
python manage.py seed_demo_catalog
```

The command is idempotent, requires the approved `Gaberone Plaza S18` branch and an active superuser for stock-audit attribution, uploads the four generated images through the configured Cloudinary account, and adjusts stock through `InventoryService`. Use `--skip-images` when validating database idempotency without contacting Cloudinary.

### Simulated review fixture

For interface testing, the demo products can receive three approved sample reviews each:

```powershell
python manage.py seed_demo_reviews
```

The command is idempotent and blocked in production. Sample reviews are visibly labelled `Sample review`, use inactive demo-only customer accounts, and are not marked as verified purchases. Remove the fixture before client content entry or production migration:

```powershell
python manage.py seed_demo_reviews --remove
```

## Verified evidence — 2026-07-30

- Four catalogue products, four original images, 27 combinations and 27 S18 stock lines created.
- Immediate second run: zero products, variants, images or stock lines changed.
- Browser: Hoodie `M + Orange` resolved to its own SKU and added to cart as `Size: M / Colour: Orange`.
- Browser: all four storefront card images loaded.
- Responsive browser check: 390 × 844, no horizontal overflow, option selectors and primary image loaded.
- Automated: 602 tests passed, one skipped SQLite row-lock test.
