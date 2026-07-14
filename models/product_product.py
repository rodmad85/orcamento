from odoo import fields, models, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def write(self, vals):
        res = super().write(vals)
        if 'standard_price' in vals:
            boms = self.env['mrp.bom'].search([
                ('bom_line_ids.product_id', 'in', self.ids),
                ('type', '=', 'orcamento'),
            ])
            if boms:
                lines = self.env['orca.material.line'].search([
                    ('product_id', 'in', boms.mapped('product_id').ids),
                ])
                if lines:
                    lines.modified(['custo_mp', 'custo_mp_total', 'custo_total'])
                    lines.recompute()
        return res
