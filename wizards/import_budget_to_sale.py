from odoo import fields, models, api
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_import_budget(self):
        self.ensure_one()
        budgets = self.env['orca.budget'].search([('importado_vendas', '=', False)])
        wizard = self.env['wizard.import.budget.to.sale'].create({
            'sale_order_id': self.id,
            'line_ids': [(0, 0, {'budget_id': b.id}) for b in budgets],
        })
        return {
            'name': 'Importar Orçamento',
            'type': 'ir.actions.act_window',
            'res_model': 'wizard.import.budget.to.sale',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }


class ImportBudgetToSaleLine(models.TransientModel):
    _name = 'wizard.import.budget.to.sale.line'
    _description = 'Linha do Assistente de Importar Orçamento'

    wizard_id = fields.Many2one('wizard.import.budget.to.sale', string='Wizard', required=True, ondelete='cascade')
    budget_id = fields.Many2one('orca.budget', string='Orçamento', required=True)
    select = fields.Boolean(string='Selecionar', default=False)
    name = fields.Char(string='Orçamento', related='budget_id.name', readonly=True, store=False)
    partner_id = fields.Many2one('res.partner', string='Cliente', related='budget_id.partner_id', readonly=True)
    meio = fields.Selection(related='budget_id.meio', string='Meio', readonly=True)
    client_number = fields.Char(string='Número do Cliente', related='budget_id.client_number', readonly=True)
    date_order = fields.Datetime(string='Data', related='budget_id.date_order', readonly=True)
    total_materiais = fields.Monetary(string='Total Materiais', related='budget_id.total_materiais', readonly=True,
        currency_field='currency_id')
    custo_horas_total = fields.Monetary(string='Custo Horas', related='budget_id.custo_horas_total', readonly=True,
        currency_field='currency_id')
    total_horas = fields.Float(string='Total Horas', related='budget_id.total_horas', readonly=True)
    total_terceiros = fields.Monetary(string='Total Terceiros', related='budget_id.total_terceiros', readonly=True,
        currency_field='currency_id')
    total_geral = fields.Monetary(string='Total Geral', related='budget_id.total_geral', readonly=True,
        currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='budget_id.currency_id', readonly=True)

    def action_toggle_select(self):
        self.select = not self.select


class ImportBudgetToSale(models.TransientModel):
    _name = 'wizard.import.budget.to.sale'
    _description = 'Importar Orçamento para Pedido de Venda'

    sale_order_id = fields.Many2one('sale.order', string='Pedido de Venda')
    line_ids = fields.One2many('wizard.import.budget.to.sale.line', 'wizard_id', string='Orçamentos')

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        active_id = self.env.context.get('active_id')
        if active_id:
            res['sale_order_id'] = active_id
        budgets = self.env['orca.budget'].search([('importado_vendas', '=', False)])
        res['line_ids'] = [(0, 0, {'budget_id': b.id}) for b in budgets]
        return res

    def action_import(self):
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError('Pedido de venda não encontrado.')
        lines = self.line_ids.filtered(lambda l: l.select and l.budget_id)
        if not lines:
            raise UserError('Selecione ao menos um orçamento para importar.')
        order = self.sale_order_id
        for line in lines:
            budget = line.budget_id
            for material_line in budget.material_line_ids:
                mo_valor = material_line.custo_horas
                mo = int(material_line.total_horas) if material_line.total_horas else 0
                vals = {
                    'order_id': order.id,
                    'product_id': material_line.product_id.id,
                    'name': material_line.product_id.display_name,
                    'product_uom_qty': material_line.quantity,
                    'product_uom': material_line.product_id.uom_id.id,
                    'mp': material_line.custo_mp_comercial_total,
                    'mo_valor': mo_valor,
                    'mo': mo,
                    'mo_total': mo * mo_valor,
                    'terc': material_line.custo_terceiros,
                }
                self.env['sale.order.line'].create(vals)
            budget.importado_vendas = True
        return {'type': 'ir.actions.act_window_close'}
