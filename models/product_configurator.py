from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class OrcaBomLineConfigurator(models.TransientModel):
    _name = 'orca.bom.line.configurator'
    _description = 'Configurador de Produto para Orçamento'

    bom_line_id = fields.Many2one('mrp.bom.line', 'Linha')
    product_tmpl_id = fields.Many2one('product.template', 'Produto', required=True)
    product_id = fields.Many2one('product.product', 'Variante')
    product_template_attribute_value_ids = fields.Many2many(
        'product.template.attribute.value',
        'orca_bom_line_config_ptav_rel',
        'configurator_id', 'ptav_id',
        string='Atributos',
        domain="[('product_tmpl_id', '=', product_tmpl_id)]")

    @api.onchange('product_tmpl_id')
    def _onchange_product_tmpl_id(self):
        if self.product_tmpl_id:
            return {'domain': {
                'product_template_attribute_value_ids': [
                    ('product_tmpl_id', '=', self.product_tmpl_id.id),
                    ('attribute_id.create_variant', '!=', 'no_variant'),
                ]
            }}
        return {'domain': {'product_template_attribute_value_ids': []}}

    def _set_bom_line_fields(self, bom_line, variant, tmpl):
        bom_line.product_id = variant
        bom_line.product_uom_id = variant.uom_id
        seller = self.env['product.supplierinfo'].search([
            '|',
            ('product_id', '=', variant.id),
            '&',
            ('product_tmpl_id', '=', tmpl.id),
            ('product_id', '=', False),
        ], order='sequence, price', limit=1)
        if seller:
            bom_line.ultimo_fornecedor_id = seller.partner_id
        else:
            bom_line.ultimo_fornecedor_id = False
        if 'purchase.order.line' in self.env:
            last_po = self.env['purchase.order.line'].search([
                ('product_id', '=', variant.id),
                ('state', '=', 'purchase'),
            ], order='date_order desc', limit=1)
            if last_po:
                bom_line.ultima_compra = last_po.order_id.date_order.date()
                bom_line.ultimo_fornecedor_id = last_po.order_id.partner_id

    def action_confirm(self):
        self.ensure_one()
        if not self.bom_line_id:
            raise ValidationError(_("Nenhuma linha selecionada."))
        tmpl = self.product_tmpl_id
        combination = self.product_template_attribute_value_ids
        variant = tmpl._get_variant_for_combination(combination)
        if not variant:
            variant = tmpl._create_product_variant(combination)
        if not variant:
            raise ValidationError(_("Nenhuma variante encontrada para a combinação selecionada."))
        self._set_bom_line_fields(self.bom_line_id, variant, tmpl)
        return {'type': 'ir.actions.act_window_close'}
