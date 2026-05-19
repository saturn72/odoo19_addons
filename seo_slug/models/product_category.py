# -*- coding: utf-8 -*-
import re
from odoo import models, fields, api

class ProductPublicCategory(models.Model):
    _inherit = 'product.public.category'

    s72_seo_name = fields.Char(
        string="Website Slug", 
        copy=False, 
        index=True,
        help="Custom URL slug used for website navigation instead of the database ID."
    )

    def _clean_and_verify_slug(self, requested_slug, current_id=False):
        if not requested_slug:
            return ''
            
        base_slug = requested_slug.lower()
        base_slug = re.sub(r'[^a-z0-9_-]', '-', base_slug)
        base_slug = re.sub(r'-+', '-', base_slug)
        base_slug = base_slug.strip('-')

        if not base_slug:
            base_slug = 'category'

        candidate_slug = base_slug
        counter = 1

        while True:
            # Look for collisions using the new property name
            domain = [('s72_seo_name', '=', candidate_slug)]
            if current_id:
                domain.append(('id', '!=', current_id))
            
            collision = self.search(domain, limit=1)
            if not collision:
                return candidate_slug
            
            candidate_slug = f"{base_slug}-{counter}"
            counter += 1

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            requested = vals.get('s72_seo_name') or vals.get('name') or 'category'
            vals['s72_seo_name'] = self._clean_and_verify_slug(requested)
        return super().create(vals_list)

    def write(self, vals):
        if 's72_seo_name' in vals:
            for record in self:
                if vals['s72_seo_name'] == record.s72_seo_name:
                    continue
                vals['s72_seo_name'] = record._clean_and_verify_slug(vals['s72_seo_name'], current_id=record.id)
        return super().write(vals)

    def _compute_website_url(self):
        super()._compute_website_url()
        for category in self:
            if category.s72_seo_name:
                category.website_url = f"/shop/category/{category.s72_seo_name}"