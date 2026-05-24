{
    'name': 'JSON-LD Catalog',
    'version': '19.0.1.0.0',
    'summary': 'Export product categories as JSON-LD structured data',
    'description': """
Export Product Categories as JSON-LD
=====================================
Adds a "Download JSON-LD" button to the product category admin form.

Clicking the button downloads a fully schema.org-compliant JSON-LD file
representing the complete category subtree, including:

- Recursive subcategory tree (schema:ItemList)
- Direct products per category (schema:Product / schema:ProductGroup)
- Per-variant pricing, availability, GTIN, SKU, brand, and ratings

Self-contained: no website or pricelist context required.
    """,
    'category': 'Website/eCommerce',
    'author': '',
    'depends': ['website_sale'],
    'data': [
        'views/product_category_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
