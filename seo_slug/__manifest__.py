# -*- coding: utf-8 -*-
{
    'name': 'SEO Website Slugs',
    'version': '19.0.1.1.0',
    'category': 'Website',
    'summary': 'Replaces pure database IDs with custom alphanumeric slugs in store URLs.',
    'author': 'Saturn72',
    'depends': [
        'website_sale',
        'product'
    ],
    'data': [
        'views/product_category_views.xml',
        'views/website_sale_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'seo_slug/static/src/js/category_slug_autofill.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'OPL-1',
}