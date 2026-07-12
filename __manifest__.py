# Copyright 2022 Madureira Ind. e Com.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    'name': 'Orçamento',
    'description': """
        Orçamento""",
    'version': '14.0.1.0.0',
    'license': 'AGPL-3',
    'author': 'Madureira Ind. e Com.',
    'website': 'www.madureira.ind.br',
    'depends': [
        'sale',
        'mail',
        'mrp',
        'purchase',
    ],
    'data': [
        'security/orcamento.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/res_config_settings_view.xml',
        'views/orcamento.xml',
        'wizards/create_purchase_order_views.xml',
        'wizards/import_budget_to_sale_views.xml',
        'views/purchase_list_views.xml',
        'views/sale.xml',
        'views/mrp_bom_views.xml',
        'views/product_configurator_views.xml',
        'views/product_configurator_templates.xml',
        'views/menus.xml',
    ],
    'demo': [
    ],
    'assets': {
        'web.assets_backend': [
            'sale/static/src/js/variant_mixin.js',
            'orcamento/static/src/js/bom_line_configurator.js',
        ],
    },
    "installable": True,
}
