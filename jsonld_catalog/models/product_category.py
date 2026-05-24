import logging
import re

from odoo import models

_logger = logging.getLogger(__name__)

# Maps barcode digit length to the specific schema.org GTIN property name.
_GTIN_FIELD = {8: 'gtin8', 12: 'gtin12', 13: 'gtin13', 14: 'gtin14'}

# Attribute names (lowercase) that map to dedicated schema.org properties.
_COLOR_ATTRS = frozenset({'color', 'colour', 'צבע'})
_SIZE_ATTRS = frozenset({'size', 'גודל', 'מידה'})


def _strip_html(html_text):
    """Strip HTML tags from an Odoo Html field, returning plain text."""
    if not html_text:
        return ''
    text = re.sub(r'<[^>]+>', ' ', html_text)
    return re.sub(r'\s+', ' ', text).strip()


def _product_refs(templates, base_url):
    """Return minimal schema.org Product reference list for related products."""
    refs = []
    for tmpl in templates:
        ref = {'@type': 'Product', 'name': tmpl.name}
        if 'website_url' in tmpl._fields and tmpl.website_url:
            ref['url'] = f'{base_url}{tmpl.website_url}'
        refs.append(ref)
    return refs


class ProductCategory(models.Model):
    _inherit = 'product.public.category'

    def action_download_jsonld(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/jsonld/category/{self.id}',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def _to_markup_data(self):
        """Return a schema:ItemList JSON-LD document for the full category tree.

        The returned document represents this category as the root ItemList.
        Each ItemList node contains:
          - itemListElement: a positional list of ListItems whose `item` is
            either a Product/ProductGroup (direct products of this category)
            or a nested ItemList (direct child categories, each also fully
            expanded with their own products and subcategories, recursively).

        Schema.org compliance notes:
          - @context appears only on the root node; nested nodes inherit it.
          - ListItem.item accepts any Thing, making ItemList a valid value for
            representing subcategories without leaving the standard vocabulary.
          - hasPart is intentionally avoided because it belongs to CreativeWork
            and ItemList does not extend CreativeWork.

        Self-contained: reads only from model fields; no HTTP request context,
        no pricelist, no fiscal position, no website_sale calls required.
        """
        self.ensure_one()
        base_url = (
            self.env['ir.config_parameter']
            .sudo()
            .get_param('web.base.url', '')
            .rstrip('/')
        )
        return self._build_category_jsonld(base_url, root=True)

    def _category_path(self):
        """Return slash-separated ancestor path, e.g. 'Food > Dairy > Cheese'."""
        parts = []
        cat = self
        while cat:
            parts.append(cat.name)
            cat = cat.parent_id
        return ' > '.join(reversed(parts))

    # ------------------------------------------------------------------
    # Category tree builder
    # ------------------------------------------------------------------

    def _build_category_jsonld(self, base_url, root=True, category_path=None):
        """Recursively build a schema:ItemList node for this category.

        Direct products of this category become ListItem > Product/ProductGroup
        entries.  Direct child categories become ListItem > ItemList entries,
        each recursively expanded.  Products come first, then subcategories,
        both numbered in a single continuous position sequence.

        :param base_url: Server base URL (no trailing slash).
        :param root: True  → include @context (root document only).
                     False → nested node; context inherited from ancestor.
        :param category_path: Pre-computed slash-separated path string, or None
                              to compute it from self.
        :return: dict representing the schema:ItemList node.
        """
        path = category_path or self._category_path()
        # Fetch direct products linked to this public category.
        # Filter to published-only when website_sale's publishing field is present.
        tmpl_model = self.env['product.template']
        domain = [('public_categ_ids', 'in', [self.id]), ('active', '=', True)]
        if 'is_published' in tmpl_model._fields:
            domain.append(('is_published', '=', True))
        elif 'website_published' in tmpl_model._fields:
            domain.append(('website_published', '=', True))
        direct_templates = tmpl_model.search(domain, order='name')
        # Fetch direct child categories.
        children = self.env['product.public.category'].search(
            [('parent_id', '=', self.id)],
            order='name',
        )

        list_elements = []
        position = 1

        # ── Direct products ────────────────────────────────────────────
        for tmpl in direct_templates:
            try:
                product_node = self._build_template_jsonld(tmpl, base_url, root=False, category_path=path)
                list_elements.append({
                    '@type': 'ListItem',
                    'position': position,
                    'item': product_node,
                })
                position += 1
            except Exception:
                _logger.warning(
                    "jsonld_catalog: skipping template id=%d in category id=%d",
                    tmpl.id, self.id,
                    exc_info=True,
                )

        # ── Child categories (each is an ItemList, nested recursively) ─
        for child in children:
            child_path = f'{path} > {child.name}'
            child_node = child._build_category_jsonld(base_url, root=False, category_path=child_path)
            list_elements.append({
                '@type': 'ListItem',
                'position': position,
                'item': child_node,
            })
            position += 1

        # ── Assemble the ItemList node ──────────────────────────────────
        data = {
            '@type': 'ItemList',
            'name': self.name,
            # numberOfItems counts direct products + direct subcategories.
            'numberOfItems': len(list_elements),
            # No meaningful ordering exists for a product catalog export.
            'itemListOrder': 'https://schema.org/ItemListUnordered',
        }

        # @context on root only — nested nodes inherit it.
        if root:
            data = {'@context': 'https://schema.org', **data}

        if 'website_url' in self._fields and self.website_url:
            cat_url = f'{base_url}{self.website_url}'
            data['@id'] = cat_url
            data['url'] = cat_url
        if self.image_1920:
            data['image'] = f'{base_url}/web/image/product.public.category/{self.id}/image_1920'

        if list_elements:
            data['itemListElement'] = list_elements

        return data

    # ------------------------------------------------------------------
    # Product node builders
    # ------------------------------------------------------------------

    def _build_template_jsonld(self, tmpl, base_url, root=True, category_path=None):
        """schema:Product for single-variant, schema:ProductGroup for multi.

        :param root: False when called as a nested ListItem.item value so that
                     @context is not repeated inside the document.
        :param category_path: Slash-separated category path to set as `category`.
        """
        if tmpl.product_variant_count == 1:
            return self._build_variant_jsonld(
                tmpl.product_variant_id, base_url, root=root, category_path=category_path
            )

        product_url = None
        if 'website_url' in tmpl._fields and tmpl.website_url:
            product_url = f'{base_url}{tmpl.website_url}'

        data = {
            '@type': 'ProductGroup',
            'name': tmpl.name,
            'image': f'{base_url}/web/image/product.template/{tmpl.id}/image_1920',
            # Stable group identifier: internal SKU or numeric id.
            'productGroupID': tmpl.default_code or str(tmpl.id),
            # hasVariant items are nested nodes — no @context on them.
            'hasVariant': [
                self._build_variant_jsonld(
                    v, base_url, root=False,
                    product_group_id=tmpl.default_code or str(tmpl.id),
                    category_path=category_path,
                )
                for v in tmpl.product_variant_ids
            ],
        }

        if root:
            data = {'@context': 'https://schema.org', **data}

        # variesBy: attribute axes that distinguish variants (e.g. Color, Size).
        varies_by = tmpl.attribute_line_ids.mapped('attribute_id.name')
        if varies_by:
            data['variesBy'] = varies_by

        if tmpl.default_code:
            data['mpn'] = tmpl.default_code

        desc = tmpl.description_sale or _strip_html(tmpl.description)
        if desc:
            data['description'] = desc
        if category_path:
            data['category'] = category_path
        if product_url:
            data['@id'] = product_url
            data['url'] = product_url

        brand_name = self._get_brand_name(tmpl)
        if brand_name:
            data['brand'] = {'@type': 'Brand', 'name': brand_name}

        # Keywords from product tags.
        if 'tag_ids' in tmpl._fields and tmpl.tag_ids:
            data['keywords'] = ', '.join(tmpl.tag_ids.mapped('name'))

        # Cross-sell / accessory products → isRelatedTo.
        if 'accessory_product_ids' in tmpl._fields and tmpl.accessory_product_ids:
            data['isRelatedTo'] = _product_refs(tmpl.accessory_product_ids, base_url)

        # Up-sell / optional products → isSimilarTo.
        if 'optional_product_ids' in tmpl._fields and tmpl.optional_product_ids:
            data['isSimilarTo'] = _product_refs(tmpl.optional_product_ids, base_url)

        # Rating at group level for multi-variant products.
        if 'rating_count' in tmpl._fields and tmpl.rating_count:
            data['aggregateRating'] = {
                '@type': 'AggregateRating',
                'ratingValue': round(tmpl.sudo().rating_avg, 1),
                'reviewCount': tmpl.rating_count,
                'bestRating': 5,
                'worstRating': 1,
            }

        return data

    def _build_variant_jsonld(self, variant, base_url, root=True, product_group_id=None, category_path=None):
        """Build a schema:Product node for one product.product record.

        :param root: True  → standalone document root; @context included.
                     False → nested inside ProductGroup.hasVariant or
                             ListItem.item; context inherited from ancestor.
        :param product_group_id: productGroupID of the parent ProductGroup when
                                 this variant is part of a multi-variant group.
        :param category_path: Slash-separated category path to set as `category`.
        """
        product_url = None
        if 'website_url' in variant._fields and variant.website_url:
            product_url = f'{base_url}{variant.website_url}'

        data = {
            '@type': 'Product',
            'name': variant.with_context(display_default_code=False).display_name,
            'image': f'{base_url}/web/image/product.product/{variant.id}/image_1920',
        }

        if variant.sale_ok:
            offer = {
                '@type': 'Offer',
                # lst_price = list_price + price_extra (correct per-variant value).
                'price': round(variant.lst_price, 2),
                'priceCurrency': variant.currency_id.name,  # ISO 4217
                'itemCondition': 'https://schema.org/NewCondition',
                'seller': {'@type': 'Organization', 'name': self.env.company.name},
            }
            if product_url:
                offer['url'] = product_url
            # Availability from stock module; guarded by field presence check.
            if 'qty_available' in variant._fields:
                offer['availability'] = (
                    'https://schema.org/InStock'
                    if variant.qty_available > 0
                    else 'https://schema.org/OutOfStock'
                )
            # Unit of measure as the eligible selling quantity.
            if variant.uom_id:
                offer['eligibleQuantity'] = {
                    '@type': 'QuantitativeValue',
                    'value': 1,
                    'unitText': variant.uom_id.name,
                }
            data['offers'] = offer

        if root:
            data = {'@context': 'https://schema.org', **data}

        if product_url:
            data['@id'] = product_url

        if product_group_id:
            data['inProductGroupWithID'] = product_group_id

        if variant.default_code:
            data['sku'] = variant.default_code
        if variant.product_tmpl_id.default_code:
            data['mpn'] = variant.product_tmpl_id.default_code

        # Variant-specific attribute values (e.g. Color: Red, Size: Large).
        # Known attributes are also written to their dedicated schema.org property.
        additional_props = []
        for val in variant.product_template_attribute_value_ids:
            attr_lower = val.attribute_id.name.lower()
            if attr_lower in _COLOR_ATTRS:
                data['color'] = val.name
            elif attr_lower in _SIZE_ATTRS:
                data['size'] = val.name
            additional_props.append({
                '@type': 'PropertyValue',
                'name': val.attribute_id.name,
                'value': val.name,
            })
        # Volume as a quantitative measurement.
        if variant.volume:
            additional_props.append({
                '@type': 'QuantitativeValue',
                'name': 'volume',
                'value': variant.volume,
                'unitCode': 'LTR',
            })
        if additional_props:
            data['additionalProperty'] = additional_props

        # Most specific GTIN key based on barcode digit count.
        if variant.barcode:
            barcode = variant.barcode.strip()
            gtin_key = _GTIN_FIELD.get(len(barcode), 'gtin')
            data[gtin_key] = barcode

        desc = variant.description_sale or _strip_html(variant.product_tmpl_id.description)
        if desc:
            data['description'] = desc
        if category_path:
            data['category'] = category_path
        if product_url:
            data['url'] = product_url

        if variant.weight:
            data['weight'] = {
                '@type': 'QuantitativeValue',
                'value': variant.weight,
                'unitCode': 'KGM',
            }

        brand_name = self._get_brand_name(variant.product_tmpl_id)
        if brand_name:
            data['brand'] = {'@type': 'Brand', 'name': brand_name}

        # Keywords from product tags.
        tmpl = variant.product_tmpl_id
        if 'tag_ids' in tmpl._fields and tmpl.tag_ids:
            data['keywords'] = ', '.join(tmpl.tag_ids.mapped('name'))

        # For standalone (non-grouped) products, add cross-sell and up-sell refs.
        if not product_group_id:
            if 'accessory_product_ids' in tmpl._fields and tmpl.accessory_product_ids:
                data['isRelatedTo'] = _product_refs(tmpl.accessory_product_ids, base_url)
            if 'optional_product_ids' in tmpl._fields and tmpl.optional_product_ids:
                data['isSimilarTo'] = _product_refs(tmpl.optional_product_ids, base_url)

        # Rating requires rating mixin (website_sale / rating module).
        if 'rating_count' in variant._fields and variant.rating_count:
            data['aggregateRating'] = {
                '@type': 'AggregateRating',
                'ratingValue': round(variant.sudo().rating_avg, 1),
                'reviewCount': variant.rating_count,
                'bestRating': 5,
                'worstRating': 1,
            }

        return data

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_brand_name(tmpl):
        """Return brand name if a brand relation exists on the template.

        Checks brand_id (Odoo OCA product_brand) and product_brand_id (other
        modules).  Returns None when no such field is installed.
        """
        for field_name in ('brand_id', 'product_brand_id'):
            if field_name in tmpl._fields:
                brand = getattr(tmpl, field_name)
                if brand:
                    return brand.name
        return None
