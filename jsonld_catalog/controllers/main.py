import json
from odoo import http
from odoo.http import request


class JsonLdCatalogController(http.Controller):

    @http.route(
        '/jsonld/category',
        auth='public',
        type='http',
        methods=['GET'],
        csrf=False,
    )
    def category_jsonld_all(self, **kwargs):
        """Return a schema:ItemList covering the entire product category forest.

        Each root-level category becomes a ListItem > ItemList entry, recursively
        expanded with its own products and subcategories.
        """
        base_url = (
            request.env['ir.config_parameter']
            .sudo()
            .get_param('web.base.url', '')
            .rstrip('/')
        )
        root_categories = request.env['product.public.category'].sudo().search(
            [('parent_id', '=', False)],
            order='name',
        )
        list_elements = []
        for position, cat in enumerate(root_categories, start=1):
            list_elements.append({
                '@type': 'ListItem',
                'position': position,
                'item': cat._build_category_jsonld(base_url, root=False),
            })
        catalog = {
            '@context': 'https://schema.org',
            '@type': 'ItemList',
            'name': 'Product Catalog',
            'numberOfItems': len(list_elements),
            'itemListOrder': 'https://schema.org/ItemListUnordered',
        }
        if list_elements:
            catalog['itemListElement'] = list_elements
        data = json.dumps(catalog, indent=2, ensure_ascii=False)
        return request.make_response(
            data,
            headers=[
                ('Content-Type', 'application/ld+json'),
                ('Content-Disposition', 'attachment; filename="categories.jsonld"'),
            ],
        )

    @http.route(
        '/jsonld/category/<int:category_id>',
        auth='public',
        type='http',
        methods=['GET'],
        csrf=False,
    )
    def category_jsonld_by_id(self, category_id, **kwargs):
        """Return JSON-LD items for the full subtree of the given category."""
        category = request.env['product.public.category'].sudo().browse(category_id)
        if not category.exists():
            return request.make_response(
                json.dumps({'error': 'Category not found'}),
                status=404,
                headers=[('Content-Type', 'application/ld+json')],
            )
        data = json.dumps(category._to_markup_data(), indent=2, ensure_ascii=False)
        filename = f"category_{category_id}.jsonld"
        return request.make_response(
            data,
            headers=[
                ('Content-Type', 'application/ld+json'),
                ('Content-Disposition', f'attachment; filename="{filename}"'),
            ],
        )
