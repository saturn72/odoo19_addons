# -*- coding: utf-8 -*-
{
    'name': 'SEO Website Slugs',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'summary': 'Removes database IDs from category URLs and adds editable slug validation.',
    'depends': ['website_sale', 'product'],
    'data': [
        'views/product_category_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'seo_slug/static/src/js/slug_auto_compute.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}