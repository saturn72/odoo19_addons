# seo_slug — Custom URL Slugs for Odoo 19 eCommerce

Replaces Odoo's default `{name}-{id}` category (and, in future, product) URL slugs
with a human-readable, admin-controlled value stored in `s72_seo_name`.

| Default Odoo URL | With this module |
|---|---|
| `/shop/category/accessories-7` | `/shop/category/accessories` |
| `/shop/category/new-arrivals-12` | `/shop/category/new-arrivals` |

---

## Table of Contents

1. [Architecture](#architecture)
2. [Slug Rules](#slug-rules)
3. [Admin Usage](#admin-usage)
4. [Edge Cases & Limitations](#edge-cases--limitations)
5. [Roadmap — Product Slugs](#roadmap--product-slugs)
6. [Development Notes](#development-notes)

---

## Architecture

```
models/
  product_category.py   — adds s72_seo_name field; overrides create/write for
                          slug generation; overrides _search_render_results for
                          global search bar URLs
controllers/
  main.py               — overrides _get_shop_path() to emit custom-slug URLs;
                          adds /shop/category/<slug_name> route handler
views/
  product_category_views.xml   — adds "Website Slug" input to the backend
                                 product.public.category form
  website_sale_templates.xml   — overrides the categorie_link QWeb template so
                                 sidebar category links use s72_seo_name
```

### How routing works

Odoo 19's `ModelConverter` regex requires a **trailing numeric ID** in URL segments
(pattern: `name-123`). Custom slugs without an ID do **not** match the model
converter, so werkzeug falls through to our `<string:slug_name>` route, which
looks up the category by `s72_seo_name`. No route ordering tricks needed.

---

## Slug Rules

These rules are enforced in `ProductPublicCategory._clean_and_verify_slug()`:

1. **Slugify:** convert to lowercase; replace every character outside
   `[a-z0-9_-]` with `-`; collapse consecutive `-`; strip leading/trailing `-`.

2. **Non-ASCII names:** if the entire name slugifies to an empty string
   (e.g. Hebrew "כללי"), the slug falls back to `cat-{record_id}` rather than
   the misleading literal `category`.

3. **Uniqueness:** if the candidate slug is already used by another category,
   append `-1`, `-2`, … until a free slot is found. The current record is always
   excluded from the conflict search.

4. **Auto-generation on create:** when no `s72_seo_name` is supplied, one is
   generated from `name`. Because the record ID is needed for the non-ASCII
   fallback, generation happens in a post-`create()` write — this costs one
   extra SQL UPDATE per new category but is only triggered when the field is
   absent or was set to an invalid value.

5. **Name changes do NOT update the slug.** The slug and the display name are
   independent; change one without touching the other.

6. **Clearing the field** (admin deletes the value and saves) regenerates the
   slug from the current name using the same rules above.

7. **Explicitly set values** are slugified and de-duplicated, but are otherwise
   honoured as-is. If you set "My Category!" the stored value will be
   `my-category`.

---

## Admin Usage

Open **Website → eCommerce → Product Categories** (or
**Website → Configuration → eCommerce → Product Categories**).

Each category form shows a **Website Slug** field (below *Sequence* in the
developer group, or directly visible for regular admin users). Fill it in to
override the auto-generated value. Leave it blank to have it regenerated from
the category name on next save.

---

## Edge Cases & Limitations

| Scenario | Current behaviour |
|---|---|
| Category has only non-ASCII name (e.g. Hebrew) | Slug falls back to `cat-{id}` |
| Two categories in a batch write get the same desired slug | Each record is written individually; the second gets `slug-1` |
| Category URL in sitemap | Uses Odoo's default `_slug()` (`name-id` format) — not yet overridden |
| Old `name-id` format links (bookmarks, external backlinks) | Still routed by the default model-converter route → category page works, but canonical URL stays `name-id` |
| `s72_seo_name` ends with digits (e.g. `promo-2`) | Could theoretically conflict with ModelConverter's regex; tested safe in practice because regex requires `name-DIGITS` at end-of-segment |

### Known gaps (as of v19.0.1.0.0)

- **Sitemap** (`sitemap_shop`) still generates `name-id` URLs. Override
  `sitemap_shop` in the controller to use `s72_seo_name`.
- **No SQL UNIQUE constraint** on `s72_seo_name`. The Python-level uniqueness
  check has a race condition under high concurrency. Add a `_sql_constraints`
  entry when concurrent category creation becomes a concern.
- **No 301 redirect** from the old `name-id` URL to the new slug URL. External
  backlinks will keep working but will not consolidate SEO authority.

---

## Roadmap — Product Slugs

The same pattern can be applied to `product.template` (product pages):

### Model (`models/product_template.py`)
- Add `s72_seo_slug` field on `product.template`
- Override `create` / `write` with the same `_clean_and_verify_slug` logic
- Override `_get_product_url()` to return `/shop/{s72_seo_slug}`

### Controller
- Add route `/shop/<string:product_slug>` that looks up by `s72_seo_slug`
- This coexists with Odoo's existing `/shop/<model("product.template"):product>`
  route via the same ModelConverter-fallthrough mechanism

### Template
- Identify the QWeb template that generates product `href` (likely
  `website_sale.product_item` or similar) and override `t-att-href` to use
  `product.s72_seo_slug or slug(product)`

### Admin view
- Inherit `website_sale.product_template_form_view` and add the field

---

## Development Notes

### Running updates

```bash
cd /root/opt/docker-compose/odoo19
docker compose run --rm web odoo \
    -c /etc/odoo/odoo.conf -d odoo-db \
    -u seo_slug --stop-after-init
```

### Checking logs

```bash
docker exec odoo19-web-run-bf1881382d68 tail -30 /var/log/odoo/odoo.log
```

### Module version

`19.0.1.0.0` — increment the minor version in `__manifest__.py` with each
functional change to enable proper Odoo module upgrade tracking.

### Testing checklist

- [ ] Create category with ASCII name → slug = slugified name
- [ ] Create category with Hebrew name → slug = `cat-{id}`
- [ ] Create category with explicit slug set → slug = that value (slugified)
- [ ] Edit category, change slug → new slug saved correctly
- [ ] Edit category, clear slug → slug regenerated from name
- [ ] Two categories edited in bulk with same desired slug → no duplicates
- [ ] Navigate `/shop/category/{slug}` → correct category page
- [ ] Navigate `/shop/category/{slug}/page/2` → correct paginated page
- [ ] Navigate `/shop/category/{nonexistent}` → 404
- [ ] Sidebar category links use custom slug (not `name-id`)
- [ ] Breadcrumb links on product pages use custom slug
- [ ] Pagination links on category page use custom slug
