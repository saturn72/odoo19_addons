import logging
import re
from datetime import datetime, timezone

from odoo import models

_logger = logging.getLogger(__name__)

# Maps barcode digit length to the specific schema.org GTIN property name.
_GTIN_FIELD = {8: 'gtin8', 12: 'gtin12', 13: 'gtin13', 14: 'gtin14'}

# Attribute names (lowercase) that map to dedicated schema.org properties.
_COLOR_ATTRS = frozenset({'color', 'colour', 'צבע'})
_SIZE_ATTRS = frozenset({'size', 'גודל', 'מידה'})

# Odoo product.template.type → human-readable label.
_PRODUCT_TYPE_LABELS = {
    'product': 'storable',
    'consu': 'consumable',
    'service': 'service',
}


def _strip_html(html_text):
    """Strip HTML tags from an Odoo Html field, returning plain text."""
    if not html_text:
        return ''
    text = re.sub(r'<[^>]+>', ' ', html_text)
    return re.sub(r'\s+', ' ', text).strip()


def _get_brand_name(tmpl):
    """Return brand name from brand_id or product_brand_id if present."""
    for field_name in ('brand_id', 'product_brand_id'):
        if field_name in tmpl._fields:
            brand = getattr(tmpl, field_name)
            if brand:
                return brand.name
    return None


def _build_category_node(cat, base_url, parent_id, sub_category_ids, product_ids):
    """Build a flat, fully-detailed category info dict."""
    node = {
        'id': cat.id,
        'name': cat.name,
        'parentId': parent_id,
        'subCategoryIds': sub_category_ids,
        'productIds': product_ids,
    }
    if 'website_url' in cat._fields and cat.website_url:
        node['url'] = f'{base_url}{cat.website_url}'
    if cat.image_1920:
        node['image'] = (
            f'{base_url}/web/image/product.public.category/{cat.id}/image_1920'
        )
    # Category description — try ecommerce HTML first, then website description.
    for field in ('description_ecommerce', 'website_description'):
        if field in cat._fields:
            val = getattr(cat, field)
            if val:
                stripped = _strip_html(val)
                if stripped:
                    node['description'] = stripped
                    break
    return node


def _build_variant_node(variant, base_url):
    """Build a detailed dict for one product.product variant record."""
    v = variant
    vnode = {
        'id': v.id,
        'image': f'{base_url}/web/image/product.product/{v.id}/image_1920',
    }
    display_name = v.with_context(display_default_code=False).display_name
    if display_name != v.product_tmpl_id.name:
        vnode['name'] = display_name
    if v.default_code:
        vnode['sku'] = v.default_code
    if v.sale_ok:
        vnode['price'] = round(v.lst_price, 2)
    if v.type == 'product':  # storable — inventory is actually tracked
        qty = max(0, v.qty_available)
        vnode['availability'] = 'InStock' if qty > 0 else 'OutOfStock'
        vnode['quantityAvailable'] = qty
    if v.barcode:
        barcode = v.barcode.strip()
        gtin_key = _GTIN_FIELD.get(len(barcode), 'barcode')
        vnode[gtin_key] = barcode
    if v.weight:
        vnode['weight'] = {'value': v.weight, 'unitCode': 'KGM'}
    if v.volume:
        vnode['volume'] = {'value': v.volume, 'unitCode': 'LTR'}
    attrs = {}
    for val in v.product_template_attribute_value_ids:
        attrs[val.attribute_id.name] = val.name
        attr_lower = val.attribute_id.name.lower()
        if attr_lower in _COLOR_ATTRS:
            vnode['color'] = val.name
        elif attr_lower in _SIZE_ATTRS:
            vnode['size'] = val.name
    if attrs:
        vnode['attributes'] = attrs
    return vnode


def _build_product_node(tmpl, base_url, cat_ids):
    """Build a rich dict for product.template exposing all available info."""
    node = {
        'id': tmpl.id,
        'name': tmpl.name,
        'categoryIds': cat_ids,
        'images': _get_images(tmpl, base_url),
    }

    # URL
    if 'website_url' in tmpl._fields and tmpl.website_url:
        node['url'] = f'{base_url}{tmpl.website_url}'

    # Description
    desc = _get_description(tmpl)
    if desc:
        node['description'] = desc

    # Currency (ISO 4217)
    if tmpl.currency_id:
        node['priceCurrency'] = tmpl.currency_id.name

    # Unit of measure
    if tmpl.uom_id:
        node['unitOfMeasure'] = tmpl.uom_id.name

    # Brand
    brand = _get_brand_name(tmpl)
    if brand:
        node['brand'] = brand

    # Keywords / tags
    if 'tag_ids' in tmpl._fields and tmpl.tag_ids:
        node['keywords'] = tmpl.tag_ids.mapped('name')

    # Aggregate rating
    if 'rating_count' in tmpl._fields and tmpl.rating_count:
        node['rating'] = {
            'average': round(tmpl.sudo().rating_avg, 1),
            'count': tmpl.rating_count,
            'bestRating': 5,
            'worstRating': 1,
        }

    # Cross-sell / up-sell (lightweight id+name references)
    if 'accessory_product_ids' in tmpl._fields and tmpl.accessory_product_ids:
        node['relatedProducts'] = [
            {'id': a.id, 'name': a.name} for a in tmpl.accessory_product_ids
        ]
    if 'optional_product_ids' in tmpl._fields and tmpl.optional_product_ids:
        node['similarProducts'] = [
            {'id': a.id, 'name': a.name} for a in tmpl.optional_product_ids
        ]

    # ── Product type & inventory ─────────────────────────────────────────────
    # productType: storable products maintain a real stock count; consumables
    # and services do not — the LLM must know this to interpret pricing/stock.
    node['productType'] = _PRODUCT_TYPE_LABELS.get(tmpl.type, tmpl.type)
    node['inventoryTracked'] = tmpl.type == 'product'

    # Lot / serial-number tracking mode (storable products only).
    if tmpl.type == 'product' and 'tracking' in tmpl._fields and tmpl.tracking != 'none':
        node['lotTracking'] = tmpl.tracking  # 'lot' | 'serial'

    # Sales taxes applied to this product (names only, for price context).
    if tmpl.taxes_id:
        node['taxes'] = tmpl.taxes_id.mapped('name')

    # Website badge/ribbon set by the merchant (e.g. "New", "Sale", "Hot").
    if 'website_ribbon_id' in tmpl._fields and tmpl.website_ribbon_id:
        node['ribbon'] = tmpl.website_ribbon_id.name

    # Explicit not-for-sale flag — rare on a published product but possible.
    if not tmpl.sale_ok:
        node['canBeSold'] = False

    # ── Variant info ────────────────────────────────────────────────────────
    variants = tmpl.product_variant_ids
    if tmpl.product_variant_count == 1:
        # Single variant — expose all variant-level fields at the product level.
        v = variants[0]
        if v.sale_ok:
            node['price'] = round(v.lst_price, 2)
        if v.type == 'product':  # storable — inventory is actually tracked
            qty = max(0, v.qty_available)
            node['availability'] = 'InStock' if qty > 0 else 'OutOfStock'
            node['quantityAvailable'] = qty
        if v.default_code:
            node['sku'] = v.default_code
        if tmpl.default_code:
            node['mpn'] = tmpl.default_code
        if v.barcode:
            barcode = v.barcode.strip()
            gtin_key = _GTIN_FIELD.get(len(barcode), 'barcode')
            node[gtin_key] = barcode
        if v.weight:
            node['weight'] = {'value': v.weight, 'unitCode': 'KGM'}
        if v.volume:
            node['volume'] = {'value': v.volume, 'unitCode': 'LTR'}
        for val in v.product_template_attribute_value_ids:
            attr_lower = val.attribute_id.name.lower()
            if attr_lower in _COLOR_ATTRS:
                node['color'] = val.name
            elif attr_lower in _SIZE_ATTRS:
                node['size'] = val.name
        # Attribute lines with create_variant='no_variant' are product options
        # (add-ons / customizations) — still valuable info for an AI agent.
        if tmpl.attribute_line_ids:
            node['productOptions'] = [
                {
                    'name': line.attribute_id.name,
                    'createVariant': line.attribute_id.create_variant,
                    'values': [
                        {
                            'name': ptav.name,
                            'priceExtra': round(ptav.price_extra, 2),
                        }
                        for ptav in line.product_template_value_ids
                    ],
                }
                for line in tmpl.attribute_line_ids
            ]
    else:
        # Multi-variant — price range, attribute axes summary, and full variant list.
        prices = [round(v.lst_price, 2) for v in variants if v.sale_ok]
        if prices:
            if min(prices) == max(prices):
                node['price'] = min(prices)
            else:
                node['priceRange'] = {'min': min(prices), 'max': max(prices)}
        if tmpl.default_code:
            node['sku'] = tmpl.default_code
            node['mpn'] = tmpl.default_code
        if tmpl.attribute_line_ids:
            node['attributeOptions'] = [
                {
                    'name': line.attribute_id.name,
                    'createVariant': line.attribute_id.create_variant,
                    'values': [
                        {
                            'name': ptav.name,
                            'priceExtra': round(ptav.price_extra, 2),
                        }
                        for ptav in line.product_template_value_ids
                    ],
                }
                for line in tmpl.attribute_line_ids
            ]
        node['variants'] = [_build_variant_node(v, base_url) for v in variants]

    return node


def _get_description(tmpl):
    """Return the best available product description.

    Mirrors Odoo's own website_sale markup_data logic exactly:
      - description_ecommerce  → the eCommerce HTML body shown on the product
                                  page (fields.Html, stripped of tags).
      - website_meta_description → SEO meta description (Char, used by Odoo
                                  for single-variant Product nodes).
      - description_sale       → plain-text copy for quotes / invoices.
      - description            → internal notes (Html, stripped).
    """
    if 'description_ecommerce' in tmpl._fields and tmpl.description_ecommerce:
        stripped = _strip_html(tmpl.description_ecommerce)
        if stripped:
            return stripped
    if 'website_meta_description' in tmpl._fields and tmpl.website_meta_description:
        return tmpl.website_meta_description
    if tmpl.description_sale:
        return tmpl.description_sale
    if tmpl.description:
        return _strip_html(tmpl.description)
    return ''


def _get_images(tmpl, base_url, variant=None):
    """Return image URL (str) or list of URLs when extra gallery images exist.

    Primary image: the variant's image (falls back to template on the server)
    or the template main image for ProductGroup nodes.
    Extra images come from product_image_ids (ecommerce gallery slides).
    """
    primary = (
        f'{base_url}/web/image/product.product/{variant.id}/image_1920'
        if variant
        else f'{base_url}/web/image/product.template/{tmpl.id}/image_1920'
    )
    extras = []
    if 'product_image_ids' in tmpl._fields and tmpl.product_image_ids:
        extras = [
            f'{base_url}/web/image/product.image/{img.id}/image_1920'
            for img in tmpl.product_image_ids
            if img.image_1920
        ]
    return [primary] + extras


class ProductCategory(models.Model):
    _inherit = 'product.public.category'

    def action_download_jsonld(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/jsonld/category/{self.id}',
            'target': 'new',
        }

    def action_download_jsonl(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/jsonl/category/{self.id}',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def _to_markup_data(self):
        """Build a rich cross-referenced catalog for this category's subtree.

        Returns a dict with:
          - categories: flat list of every category in the subtree, each with
                        parentId, subCategoryIds[], productIds[], and all
                        available metadata (name, url, image, description).
          - products:   flat list of every published product in any of those
                        categories, each with categoryIds[] and all available
                        product fields (price, description, images, brand,
                        attributes, variants, ratings, cross-sells, etc.).

        Both arrays are keyed by 'id' and fully cross-referenced so an AI agent
        can traverse the graph in any direction without nested lookups.
        """
        self.ensure_one()
        base_url = (
            self.env['ir.config_parameter']
            .sudo()
            .get_param('web.base.url', '')
            .rstrip('/')
        )
        return self._build_catalog(base_url)

    # ------------------------------------------------------------------
    # Catalog builders
    # ------------------------------------------------------------------

    def _build_catalog(self, base_url):
        """Cross-referenced catalog for the subtree rooted at self."""

        # ── Phase 1: collect every category in the subtree ─────────────
        cat_records = {}   # id → record
        cat_parent = {}    # id → parent_id (None if root or parent outside scope)
        cat_children = {}  # id → [child_ids]

        def _gather(cat, parent_id):
            cat_records[cat.id] = cat
            cat_parent[cat.id] = parent_id
            cat_children[cat.id] = []
            children = self.env['product.public.category'].search(
                [('parent_id', '=', cat.id)], order='name'
            )
            for ch in children:
                cat_children[cat.id].append(ch.id)
                _gather(ch, cat.id)

        _gather(self, self.parent_id.id if self.parent_id else None)
        all_cat_ids = list(cat_records.keys())

        # ── Phase 2: collect all published products in any of those cats ─
        tmpl_model = self.env['product.template']
        domain = [('public_categ_ids', 'in', all_cat_ids), ('active', '=', True)]
        if 'is_published' in tmpl_model._fields:
            domain.append(('is_published', '=', True))
        elif 'website_published' in tmpl_model._fields:
            domain.append(('website_published', '=', True))
        templates = tmpl_model.search(domain, order='name')

        # ── Phase 3: build bidirectional cross-reference maps ───────────
        cat_product_ids = {cid: [] for cid in all_cat_ids}
        tmpl_cat_ids = {}
        for tmpl in templates:
            cats_in_scope = [
                cid for cid in tmpl.public_categ_ids.ids if cid in cat_records
            ]
            tmpl_cat_ids[tmpl.id] = cats_in_scope
            for cid in cats_in_scope:
                cat_product_ids[cid].append(tmpl.id)

        # ── Phase 4: assemble output ────────────────────────────────────
        categories = [
            _build_category_node(
                cat_records[cid], base_url,
                cat_parent[cid], cat_children[cid], cat_product_ids[cid],
            )
            for cid in sorted(cat_records, key=lambda i: cat_records[i].name)
        ]

        products = []
        for tmpl in templates:
            try:
                products.append(
                    _build_product_node(tmpl, base_url, tmpl_cat_ids[tmpl.id])
                )
            except Exception:
                _logger.warning(
                    'jsonld_catalog: skipping template id=%d', tmpl.id,
                    exc_info=True,
                )

        return {
            'generatedAt': datetime.now(timezone.utc).isoformat(),
            'baseUrl': base_url,
            'rootCategoryId': self.id,
            'categories': categories,
            'products': products,
        }

    def _build_full_catalog(self, base_url):
        """Cross-referenced catalog covering ALL public categories and products."""

        # ── Collect every public category ───────────────────────────────
        all_cats = self.env['product.public.category'].search([], order='name')
        cat_parent = {}
        cat_children = {cat.id: [] for cat in all_cats}
        for cat in all_cats:
            pid = cat.parent_id.id if cat.parent_id else None
            cat_parent[cat.id] = pid
            if pid and pid in cat_children:
                cat_children[pid].append(cat.id)

        # ── Collect all published products ──────────────────────────────
        all_cat_ids = [cat.id for cat in all_cats]
        tmpl_model = self.env['product.template']
        domain = [('public_categ_ids', 'in', all_cat_ids), ('active', '=', True)]
        if 'is_published' in tmpl_model._fields:
            domain.append(('is_published', '=', True))
        elif 'website_published' in tmpl_model._fields:
            domain.append(('website_published', '=', True))
        templates = tmpl_model.search(domain, order='name')

        # ── Bidirectional cross-reference maps ──────────────────────────
        cat_product_ids = {cat.id: [] for cat in all_cats}
        tmpl_cat_ids = {}
        for tmpl in templates:
            cats = tmpl.public_categ_ids.ids
            tmpl_cat_ids[tmpl.id] = cats
            for cid in cats:
                if cid in cat_product_ids:
                    cat_product_ids[cid].append(tmpl.id)

        # ── Assemble output ─────────────────────────────────────────────
        categories = [
            _build_category_node(
                cat, base_url,
                cat_parent[cat.id], cat_children[cat.id], cat_product_ids[cat.id],
            )
            for cat in all_cats
        ]

        products = []
        for tmpl in templates:
            try:
                products.append(
                    _build_product_node(tmpl, base_url, tmpl_cat_ids[tmpl.id])
                )
            except Exception:
                _logger.warning(
                    'jsonld_catalog: skipping template id=%d', tmpl.id,
                    exc_info=True,
                )

        return {
            'generatedAt': datetime.now(timezone.utc).isoformat(),
            'baseUrl': base_url,
            'categories': categories,
            'products': products,
        }
