from odoo import fields, models, api, _
from odoo.exceptions import UserError


class OrcaCreatePurchaseOrderWizard(models.TransientModel):
    _name = 'orca.create.purchase.order.wizard'
    _description = 'Criar Pedido de Compra'

    purchase_list_id = fields.Many2one('orca.purchase.list', string='Lista de Compras')
    partner_ids = fields.One2many('orca.create.purchase.order.wizard.partner', 'wizard_id', string='Fornecedores')
    partner_id = fields.Many2one('res.partner', string='Fornecedor')
    currency_id = fields.Many2one(related='purchase_list_id.company_id.currency_id')
    ultimo_fornecedor = fields.Char(string='Último Fornecedor', compute='_compute_ultima_compra')
    ultima_data_compra = fields.Datetime(string='Última Data de Compra', compute='_compute_ultima_compra')
    ultimo_preco_compra = fields.Monetary(string='Último Preço de Compra', compute='_compute_ultima_compra')

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
        no_supplier_line_ids = []

        for line in lines:
            found_supplier = False

            if line.partner_id:
                p_id = line.partner_id.id
                if p_id not in suppliers:
                    suppliers[p_id] = {'partner_id': p_id, 'line_ids': []}
                if line.id not in suppliers[p_id]['line_ids']:
                    suppliers[p_id]['line_ids'].append(line.id)
                found_supplier = True

            template = line.product_id.product_tmpl_id
            for seller in template.seller_ids:
                partner = seller.partner_id
                if not partner:
                    continue
                if partner.id not in suppliers:
                    suppliers[partner.id] = {'partner_id': partner.id, 'line_ids': []}
                if line.id not in suppliers[partner.id]['line_ids']:
                    suppliers[partner.id]['line_ids'].append(line.id)
                found_supplier = True

            if not found_supplier:
                no_supplier_line_ids.append(line.id)

        for p_id in suppliers:
            for line_id in no_supplier_line_ids:
                if line_id not in suppliers[p_id]['line_ids']:
                    suppliers[p_id]['line_ids'].append(line_id)

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

        selected_partner_id = False
        product_ids = lines.mapped('product_id').ids
        last_line = self.env['purchase.order.line'].search([
            ('product_id', 'in', product_ids),
            ('state', '=', 'purchase'),
        ], order='date_order desc, id desc', limit=1)
        if last_line and last_line.order_id.partner_id.id in suppliers:
            selected_partner_id = last_line.order_id.partner_id.id
        elif len(suppliers) == 1:
            selected_partner_id = list(suppliers.keys())[0]

        if selected_partner_id:
            res['partner_id'] = selected_partner_id

        return res

    def action_create_purchase_orders(self):
        self.ensure_one()

        all_pending = self.partner_ids.mapped('purchase_list_line_ids').filtered(
            lambda l: l.state == 'pendente')

        if not all_pending:
            raise UserError(_("Nenhum item pendente para criar o pedido."))

        order_line_vals = []
        for line in all_pending:
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
            'partner_id': self.partner_id.id if self.partner_id else False,
            'company_id': self.purchase_list_id.company_id.id,
            'order_line': order_line_vals,
        })

        for po_line in order.order_line:
            match = all_pending.filtered(lambda l: l.product_id.id == po_line.product_id.id)
            if match:
                match[:1].write({
                    'state': 'pedido_criado',
                    'partner_id': self.partner_id.id if self.partner_id else False,
                    'purchase_order_line_id': po_line.id,
                })

        purchase_list = self.purchase_list_id
        all_comprado = all(
            line.state == 'comprado' for line in purchase_list.line_ids
        )
        if all_comprado and purchase_list.budget_id:
            purchase_list.budget_id.lista_compras_importada = True

        return {
            'type': 'ir.actions.act_window',
            'name': 'Pedido de Compra',
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'res_id': order.id,
            'target': 'current',
        }


class OrcaCreatePurchaseOrderWizardPartner(models.TransientModel):
    _name = 'orca.create.purchase.order.wizard.partner'
    _description = 'Fornecedor do Wizard de Pedido de Compra'

    wizard_id = fields.Many2one('orca.create.purchase.order.wizard', string='Wizard', ondelete='cascade', required=True)
    partner_id = fields.Many2one('res.partner', string='Fornecedor', required=True)
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
        self.wizard_id.partner_id = self.partner_id.id
