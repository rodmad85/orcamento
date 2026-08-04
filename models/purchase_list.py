from odoo import fields, models, api, _
from odoo.exceptions import UserError


class OrcaPurchaseList(models.Model):
    _name = 'orca.purchase.list'
    _description = 'Lista de Compras'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'date_order desc, id desc'

    name = fields.Char(string='Lista de Compras', default='/', copy=False)
    date_order = fields.Datetime(string='Data', default=fields.Datetime.now)
    bom_id = fields.Many2one('mrp.bom', string='Lista de Materiais', ondelete='cascade', required=True)
    budget_id = fields.Many2one('orca.budget', string='Orçamento', compute='_compute_budget_id', store=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Rascunho'),
        ('done', 'Finalizado'),
    ], string='Situação', default='draft', tracking=True)
    line_ids = fields.One2many('orca.purchase.list.line', 'purchase_list_id', string='Itens')

    @api.depends('bom_id')
    def _compute_budget_id(self):
        for rec in self:
            bom = rec.bom_id
            if not bom:
                rec.budget_id = False
                continue
            material_line = self.env['orca.material.line'].search([
                ('product_id', '=', bom.product_id.id),
            ], limit=1)
            rec.budget_id = material_line.budget_id if material_line else False

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('orca.purchase.list.seq') or '/'
        return super().create(vals)

    def action_generate_lines(self):
        self.ensure_one()
        bom = self.bom_id
        lines_vals = []
        for bom_line in bom.bom_line_ids:
            if bom_line.utilizar_estoque:
                continue
            product = bom_line.product_id
            partner = bom_line.ultimo_fornecedor_id
            if not partner:
                seller = self.env['product.supplierinfo'].search([
                    '|',
                    ('product_id', '=', product.id),
                    '&',
                    ('product_tmpl_id', '=', product.product_tmpl_id.id),
                    ('product_id', '=', False),
                ], order='sequence, price', limit=1)
                if seller:
                    partner = seller.partner_id
            lines_vals.append({
                'purchase_list_id': self.id,
                'product_id': product.id,
                'product_uom_id': bom_line.product_uom_id.id or product.uom_id.id,
                'product_qty': bom_line.product_qty,
                'partner_id': partner.id if partner else False,
                'bom_line_id': bom_line.id,
            })
        if lines_vals:
            self.line_ids.unlink()
            self.env['orca.purchase.list.line'].create(lines_vals)

    def action_view_purchase_list(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Lista de Compras',
            'res_model': 'orca.purchase.list',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Itens da Lista de Compras',
            'res_model': 'orca.purchase.list.line',
            'view_mode': 'tree',
            'domain': [('purchase_list_id', '=', self.id)],
            'target': 'current',
        }


class OrcaPurchaseListLine(models.Model):
    _name = 'orca.purchase.list.line'
    _description = 'Item da Lista de Compras'
    _order = 'partner_id, product_id'

    purchase_list_id = fields.Many2one('orca.purchase.list', string='Lista de Compras', ondelete='cascade', required=True)
    product_id = fields.Many2one('product.product', string='Produto', required=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unidade')
    product_qty = fields.Float(string='Quantidade', digits='Product Unit of Measure', default=1.0, required=True)
    partner_id = fields.Many2one('res.partner', string='Fornecedor')
    bom_line_id = fields.Many2one('mrp.bom.line', string='Linha da Lista de Materiais')
    purchase_order_line_id = fields.Many2one('purchase.order.line', string='Pedido de Compra', copy=False)
    state = fields.Selection([
        ('pendente', 'Pendente'),
        ('pedido_criado', 'Pedido Criado'),
        ('comprado', 'Comprado'),
    ], string='Situação', default='pendente')
    company_id = fields.Many2one(related='purchase_list_id.company_id', store=True)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id

    def action_regenerate_from_lines(self):
        purchase_lists = self.mapped('purchase_list_id')
        for pl in purchase_lists:
            pl.action_generate_lines()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_open_create_wizard(self):
        pendente = self.filtered(lambda l: l.state == 'pendente')
        if not pendente:
            raise UserError(_("Nenhum item pendente. Selecione itens com situação 'Pendente'."))
        wizard = self.env['orca.create.purchase.order.wizard'].with_context(
            active_ids=pendente.ids,
        ).create({})
        return {
            'type': 'ir.actions.act_window',
            'name': 'Criar Pedido de Compra',
            'res_model': 'orca.create.purchase.order.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def button_confirm(self):
        res = super().button_confirm()
        self._update_purchase_list_lines()
        return res

    def button_cancel(self):
        res = super().button_cancel()
        self._reset_purchase_list_lines()
        return res

    def _update_purchase_list_lines(self):
        for order in self:
            for line in order.order_line:
                purchase_list_lines = self.env['orca.purchase.list.line'].search([
                    ('purchase_order_line_id', '=', line.id),
                ])
                if purchase_list_lines:
                    purchase_list_lines.write({'state': 'comprado'})

    def _reset_purchase_list_lines(self):
        for order in self:
            for line in order.order_line:
                purchase_list_lines = self.env['orca.purchase.list.line'].search([
                    ('purchase_order_line_id', '=', line.id),
                ])
                if purchase_list_lines:
                    purchase_list_lines.write({
                        'state': 'pendente',
                        'purchase_order_line_id': False,
                        'partner_id': False,
                    })
