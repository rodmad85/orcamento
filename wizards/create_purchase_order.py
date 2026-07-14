from odoo import fields, models, api, _
from odoo.exceptions import UserError


class OrcaCreatePurchaseOrderWizard(models.TransientModel):
    _name = 'orca.create.purchase.order.wizard'
    _description = 'Criar Pedido de Compra'

    purchase_list_id = fields.Many2one('orca.purchase.list', string='Lista de Compras')
    partner_ids = fields.One2many('orca.create.purchase.order.wizard.partner', 'wizard_id', string='Fornecedores')
    partner_id = fields.Many2one('res.partner', compute='_compute_partner_id', inverse='_inverse_partner_id', string='Fornecedor')
    currency_id = fields.Many2one(related='purchase_list_id.company_id.currency_id')
    ultimo_fornecedor = fields.Char(string='Último Fornecedor', compute='_compute_ultima_compra')
    ultima_data_compra = fields.Datetime(string='Última Data de Compra', compute='_compute_ultima_compra')
    ultimo_preco_compra = fields.Monetary(string='Último Preço de Compra', compute='_compute_ultima_compra')

    @api.depends('partner_ids.selected')
    def _compute_partner_id(self):
        for rec in self:
            selected = rec.partner_ids.filtered('selected')
            rec.partner_id = selected[:1].partner_id if selected else False

    def _inverse_partner_id(self):
        for rec in self:
            if rec.partner_id:
                rec.partner_ids.write({'selected': False})
                match = rec.partner_ids.filtered(lambda p: p.partner_id == rec.partner_id)
                if match:
                    match[:1].selected = True

    @api.depends('partner_ids', 'partner_ids.purchase_list_line_ids')
    def _compute_ultima_compra(self):
        for rec in self:
            product_ids = rec.partner_ids.mapped('purchase_list_line_ids.product_id').ids
            if not product_ids:
                rec.ultimo_fornecedor = False
                rec.ultima_data_compra = False
                rec.ultimo_preco_compra = 0.0
                continue
            last_line = self.env['purchase.order.line'].search([
                ('product_id', 'in', product_ids),
                ('state', '=', 'purchase'),
            ], order='date_order desc, id desc', limit=1)
            if last_line:
                rec.ultimo_fornecedor = last_line.order_id.partner_id.display_name
                rec.ultima_data_compra = last_line.order_id.date_order
                rec.ultimo_preco_compra = last_line.price_unit
            else:
                rec.ultimo_fornecedor = False
                rec.ultima_data_compra = False
                rec.ultimo_preco_compra = 0.0

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids')
        purchase_list_id = self.env.context.get('default_purchase_list_id')

        lines = self.env['orca.purchase.list.line']
        if active_ids:
            lines = lines.browse(active_ids).filtered(lambda l: l.state == 'pendente')
        elif purchase_list_id:
            purchase_list = self.env['orca.purchase.list'].browse(purchase_list_id)
            lines = purchase_list.line_ids.filtered(lambda l: l.state == 'pendente')

        if not lines:
            return res

        suppliers = {}
        for line in lines:
            template = line.product_id.product_tmpl_id
            for seller in template.seller_ids:
                partner = seller.partner_id
                if not partner:
                    continue
                if partner.id not in suppliers:
                    suppliers[partner.id] = {
                        'partner_id': partner.id,
                        'line_ids': [],
                    }
                if line.id not in suppliers[partner.id]['line_ids']:
                    suppliers[partner.id]['line_ids'].append(line.id)

        partner_vals = []
        for p_id, p_data in suppliers.items():
            partner_vals.append({
                'partner_id': p_data['partner_id'],
                'purchase_list_line_ids': [(6, 0, p_data['line_ids'])],
            })

        res.update({
            'purchase_list_id': lines[0].purchase_list_id.id,
            'partner_ids': [(0, 0, vals) for vals in partner_vals],
        })

        product_ids = lines.mapped('product_id').ids
        last_line = self.env['purchase.order.line'].search([
            ('product_id', 'in', product_ids),
            ('state', '=', 'purchase'),
        ], order='date_order desc, id desc', limit=1)
        if last_line and last_line.order_id.partner_id.id in suppliers:
            for vals in partner_vals:
                if vals['partner_id'] == last_line.order_id.partner_id.id:
                    vals['selected'] = True
                    break

        return res

    def action_create_purchase_orders(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Selecione um fornecedor."))

        partner = self.partner_id
        selected = self.partner_ids.filtered('selected')
        pl_lines = selected[:1].purchase_list_line_ids.filtered(lambda l: l.state == 'pendente') if selected else self.env['orca.purchase.list.line']
        if not pl_lines:
            raise UserError(_("Nenhum item pendente para este fornecedor."))

        order_line_vals = []
        for line in pl_lines:
            last_purchase = self.env['purchase.order.line'].search([
                ('product_id', '=', line.product_id.id),
                ('state', '=', 'purchase'),
            ], order='date_order desc, id desc', limit=1)
            price = last_purchase.price_unit if last_purchase else 0.0
            order_line_vals.append((0, 0, {
                'product_id': line.product_id.id,
                'product_uom': line.product_uom_id.id or line.product_id.uom_id.id,
                'product_qty': line.product_qty,
                'name': line.product_id.display_name,
                'price_unit': price,
            }))
        order = self.env['purchase.order'].create({
            'partner_id': partner.id,
            'company_id': self.purchase_list_id.company_id.id,
            'order_line': order_line_vals,
        })
        for po_line in order.order_line:
            match = pl_lines.filtered(lambda l: l.product_id.id == po_line.product_id.id)
            if match:
                match[:1].write({'state': 'pedido_criado', 'partner_id': partner.id, 'purchase_order_line_id': po_line.id})
        orders = order
        orders = order

        purchase_list = self.purchase_list_id
        all_comprado = all(
            line.state == 'comprado' for line in purchase_list.line_ids
        )
        if all_comprado and purchase_list.budget_id:
            purchase_list.budget_id.lista_compras_importada = True

        return {
            'type': 'ir.actions.act_window',
            'name': 'Pedidos de Compra',
            'res_model': 'purchase.order',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', orders.ids)],
            'target': 'current',
        }


class OrcaCreatePurchaseOrderWizardPartner(models.TransientModel):
    _name = 'orca.create.purchase.order.wizard.partner'
    _description = 'Fornecedor do Wizard de Pedido de Compra'

    wizard_id = fields.Many2one('orca.create.purchase.order.wizard', string='Wizard', ondelete='cascade', required=True)
    partner_id = fields.Many2one('res.partner', string='Fornecedor', required=True)
    selected = fields.Boolean(string='Selecionado', default=False)
    purchase_list_line_ids = fields.Many2many('orca.purchase.list.line', relation='orca_wiz_partner_line_rel', string='Itens')
    ultimo_fornecedor = fields.Char(string='Último Fornecedor', compute='_compute_purchase_info')
    ultima_data_compra = fields.Datetime(string='Última Data de Compra', compute='_compute_purchase_info')
    ultimo_preco_compra = fields.Monetary(string='Último Preço de Compra', compute='_compute_purchase_info')
    currency_id = fields.Many2one(related='wizard_id.purchase_list_id.company_id.currency_id')

    @api.depends('partner_id')
    def _compute_purchase_info(self):
        for rec in self:
            if not rec.partner_id:
                rec.ultimo_fornecedor = False
                rec.ultima_data_compra = False
                rec.ultimo_preco_compra = 0.0
                continue
            product_ids = rec.purchase_list_line_ids.product_id.ids
            domain = [('order_id.partner_id', '=', rec.partner_id.id), ('state', '=', 'purchase')]
            if product_ids:
                domain.append(('product_id', 'in', product_ids))
            last_line = self.env['purchase.order.line'].search(
                domain, order='date_order desc, id desc', limit=1)
            if last_line:
                rec.ultimo_fornecedor = last_line.order_id.partner_id.display_name
                rec.ultima_data_compra = last_line.order_id.date_order
                rec.ultimo_preco_compra = last_line.price_unit
            else:
                rec.ultimo_fornecedor = rec.partner_id.display_name
                rec.ultima_data_compra = False
                rec.ultimo_preco_compra = 0.0

    def select_partner(self):
        self.ensure_one()
        self.wizard_id.partner_ids.write({'selected': False})
        self.selected = True
