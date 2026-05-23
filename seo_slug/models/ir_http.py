# -*- coding: utf-8 -*-
from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _slug(cls, value):
        try:
            if (
                getattr(value, '_name', None) == 'product.public.category'
                and value.id
                and value.s72_seo_name
            ):
                return value.s72_seo_name
        except AttributeError:
            pass
        return super()._slug(value)
