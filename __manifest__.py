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
    ],
    'data': [
        'security/orcamento.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/res_config_settings_view.xml',
        'views/menus.xml',
        'views/orcamento.xml',
        'views/sale.xml',
    ],
    'demo': [
    ],
    "installable": True,
}
