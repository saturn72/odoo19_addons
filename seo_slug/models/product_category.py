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

    def _slugify(self, text):
        text = (text or '').lower()
        text = re.sub(r'[\W_]', '-', text)   # keep Unicode letters and digits
        text = re.sub(r'-+', '-', text)
        return text.strip('-')

    def _clean_and_verify_slug(self, requested_slug, current_id=False):
        base_slug = self._slugify(requested_slug)
        if not base_slug:
            base_slug = 'category'

        # Pure-digit slugs (e.g. "12") collide with Odoo's model-converter
        # route which interprets the trailing integer as a record id.
        # Start the counter at 0 so the first stored slug is "12-0".
        is_numeric = bool(re.fullmatch(r'\d+', base_slug))
        counter = 0 if is_numeric else None

        while True:
            candidate = f"{base_slug}-{counter}" if counter is not None else base_slug
            domain = [('s72_seo_name', '=', candidate)]
            if current_id:
                domain.append(('id', '!=', current_id))
            if not self.search(domain, limit=1):
                return candidate
            counter = (counter + 1) if counter is not None else 1

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if not record.s72_seo_name:
                # No slug was provided; generate one from the name.
                # current_id is now known after creation, so non-ASCII names
                # fall back to cat-{id} instead of the literal 'category'.
                requested = record.name or ''
                record.s72_seo_name = record._clean_and_verify_slug(
                    requested, current_id=record.id
                )
            else:
                # Slug was provided; ensure it is slugified and unique.
                cleaned = record._clean_and_verify_slug(
                    record.s72_seo_name, current_id=record.id
                )
                if cleaned != record.s72_seo_name:
                    record.s72_seo_name = cleaned
        return records

    def write(self, vals):
        if 's72_seo_name' not in vals:
            return super().write(vals)

        # Save the original user input before any mutation.
        # Odoo sends False when a Char field is cleared in the UI.
        original_input = vals.get('s72_seo_name') or False

        for record in self:
            # Skip recomputing when the user did not actually change the slug.
            if original_input and original_input == record.s72_seo_name:
                record_slug = record.s72_seo_name
            else:
                requested = original_input or record.name or ''
                record_slug = record._clean_and_verify_slug(
                    requested, current_id=record.id
                )
            # Write per-record so each record gets its own unique slug.
            # This also avoids the shared-dict mutation bug where iterating
            # over multiple records would corrupt vals for subsequent records.
            super(ProductPublicCategory, record).write(
                dict(vals, s72_seo_name=record_slug)
            )

        return True

    def _search_render_results(self, fetch_fields, mapping, icon, limit):
        # Base (website_sale) sets url='/shop/category/{id}' (numeric only).
        # We override with the custom slug when available.
        results_data = super()._search_render_results(fetch_fields, mapping, icon, limit)
        ids = [d['id'] for d in results_data if d.get('id')]
        if ids:
            slug_by_id = {
                cat.id: cat.s72_seo_name
                for cat in self.browse(ids)
                if cat.s72_seo_name
            }
            for data in results_data:
                seo = slug_by_id.get(data.get('id'))
                if seo:
                    data['url'] = f"/shop/category/{seo}"
        return results_data