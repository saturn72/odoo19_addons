import json

from odoo import http
from odoo.http import request


def _catalog_to_jsonl(catalog):
    """Serialize a catalog dict to JSON Lines format.

    Each output line is a self-contained JSON object with a '_type' field
    (either 'category' or 'product') so consumers can process the stream
    record-by-record without loading the full document into memory.
    """
    lines = []
    for cat in catalog.get('categories', []):
        lines.append(json.dumps({'_type': 'category', **cat}, ensure_ascii=False))
    for prod in catalog.get('products', []):
        lines.append(json.dumps({'_type': 'product', **prod}, ensure_ascii=False))
    return '\n'.join(lines)


class JsonLdCatalogController(http.Controller):

    @http.route(
        '/jsonld/category',
        auth='public',
        type='http',
        methods=['GET'],
        csrf=False,
    )
    def category_jsonld_all(self, **kwargs):
        """Return the full cross-referenced product catalog for all categories.

        Output: { generatedAt, baseUrl, categories[], products[] }
        """
        base_url = (
            request.env['ir.config_parameter']
            .sudo()
            .get_param('web.base.url', '')
            .rstrip('/')
        )
        env_cat = request.env['product.public.category'].sudo()
        catalog = env_cat._build_full_catalog(base_url)
        data = json.dumps(catalog, indent=2, ensure_ascii=False)
        return request.make_response(
            data,
            headers=[
                ('Content-Type', 'application/json'),
                ('Content-Disposition', 'attachment; filename="catalog.json"'),
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
        """Return catalog for the subtree rooted at the given category."""
        category = request.env['product.public.category'].sudo().browse(category_id)
        if not category.exists():
            return request.make_response(
                json.dumps({'error': 'Category not found'}),
                status=404,
                headers=[('Content-Type', 'application/json')],
            )
        catalog = category._to_markup_data()
        data = json.dumps(catalog, indent=2, ensure_ascii=False)
        filename = f"catalog_category_{category_id}.json"
        return request.make_response(
            data,
            headers=[
                ('Content-Type', 'application/json'),
                ('Content-Disposition', f'attachment; filename="{filename}"'),
            ],
        )

    # ── JSONL endpoints ────────────────────────────────────────────────────

    @http.route(
        '/jsonl/category',
        auth='public',
        type='http',
        methods=['GET'],
        csrf=False,
    )
    def category_jsonl_all(self, **kwargs):
        """Full catalog as JSON Lines — one JSON object per line.

        Each line carries a '_type' field ('category' or 'product') so
        the stream can be processed record-by-record without parsing the
        full document.
        """
        base_url = (
            request.env['ir.config_parameter']
            .sudo()
            .get_param('web.base.url', '')
            .rstrip('/')
        )
        env_cat = request.env['product.public.category'].sudo()
        catalog = env_cat._build_full_catalog(base_url)
        data = _catalog_to_jsonl(catalog)
        return request.make_response(
            data,
            headers=[
                ('Content-Type', 'application/x-ndjson'),
                ('Content-Disposition', 'attachment; filename="catalog.jsonl"'),
            ],
        )

    @http.route(
        '/jsonl/category/<int:category_id>',
        auth='public',
        type='http',
        methods=['GET'],
        csrf=False,
    )
    def category_jsonl_by_id(self, category_id, **kwargs):
        """Subtree catalog as JSON Lines for the given category."""
        category = request.env['product.public.category'].sudo().browse(category_id)
        if not category.exists():
            return request.make_response(
                json.dumps({'error': 'Category not found'}),
                status=404,
                headers=[('Content-Type', 'application/json')],
            )
        catalog = category._to_markup_data()
        data = _catalog_to_jsonl(catalog)
        filename = f"catalog_category_{category_id}.jsonl"
        return request.make_response(
            data,
            headers=[
                ('Content-Type', 'application/x-ndjson'),
                ('Content-Disposition', f'attachment; filename="{filename}"'),
            ],
        )
