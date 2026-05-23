# -*- coding: utf-8 -*-
from werkzeug.exceptions import NotFound
from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale

class WebsiteSaleSlug(WebsiteSale):

    @http.route([
        '/shop/category/<string:slug_name>',
        '/shop/category/<string:slug_name>/page/<int:page>'
    ], type='http', auth="public", website=True, sitemap=False)
    def shop_category_slug(self, slug_name, page=0, **post):
        category = request.env['product.public.category'].sudo().search([
            ('s72_seo_name', '=', slug_name)
        ], limit=1)
        if not category or not category.can_access_from_current_website():
            raise NotFound()
        return self.shop(category=category, page=page, **post)