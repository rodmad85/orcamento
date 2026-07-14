from odoo import fields, models, api


class OrcaBudget(models.Model):
    _name = 'orca.budget'
    _description = 'Orçamento'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'date_order desc, id desc'

    name = fields.Char(string='Orçamento', default='/', copy=False)
    partner_id = fields.Many2one('res.partner', string='Cliente', required=True)
    meio = fields.Selection([
        ('email', 'E-mail'),
        ('telefone', 'Telefone'),
        ('whatsapp', 'Whatsapp'),
        ('presencial', 'Presencial'),
    ], string='Meio', required=True)
    client_number = fields.Char(string='Número do Cliente')
    date_order = fields.Datetime(string='Data da Cotação', default=fields.Datetime.now)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    total_materiais = fields.Monetary(string='Total de Materiais', compute='_compute_totals',
        currency_field='currency_id')
    custo_horas_total = fields.Monetary(string='Custo Horas', compute='_compute_totals',
        currency_field='currency_id')
    total_horas = fields.Float(string='Total de Horas', compute='_compute_totals')
    total_terceiros = fields.Monetary(string='Total Terceiros', compute='_compute_totals',
        currency_field='currency_id')
    total_geral = fields.Monetary(string='Custo Total', compute='_compute_totals',
        currency_field='currency_id')

    lista_compras_importada = fields.Boolean(string='Lista de Compras Importada')
    importado_vendas = fields.Boolean(string='Importado para Vendas')

    material_line_ids = fields.One2many('orca.material.line', 'budget_id', string='Lista de Materiais')

    @api.depends('material_line_ids', 'material_line_ids.custo_total')
    def _compute_totals(self):
        for rec in self:
            lines = rec.material_line_ids
            rec.total_materiais = sum(lines.mapped('custo_mp_total')) + sum(lines.mapped('custo_comercial_total'))
            rec.custo_horas_total = sum(
                line.custo_horas * line.total_horas * line.quantity for line in lines
            )
            rec.total_horas = sum(line.total_horas * line.quantity for line in lines)
            rec.total_terceiros = sum(line.custo_terceiros * line.quantity for line in lines)
            rec.total_geral = sum(lines.mapped('custo_total'))

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('orca.budget.seq') or '/'
        return super().create(vals)

    def action_open_purchase_list(self):
        self.ensure_one()
        product_ids = self.material_line_ids.product_id.ids
        if not product_ids:
            return
        boms = self.env['mrp.bom'].search([
            ('product_id', 'in', product_ids),
            ('type', '=', 'orcamento'),
        ])
        purchase_lists = boms.mapped('purchase_list_id').filtered('id')
        if not purchase_lists:
            return
        if len(purchase_lists) == 1:
            return purchase_lists.action_open_lines()
        action = self.env['ir.actions.act_window']._for_xml_id('orcamento.orca_purchase_list_act_window')
        action['domain'] = [('id', 'in', purchase_lists.ids)]
        return action


class OrcaMaterialLine(models.Model):
    _name = 'orca.material.line'
    _description = 'Lista de Materiais'
    _order = 'sequence, id'

    budget_id = fields.Many2one('orca.budget', string='Orçamento', ondelete='cascade', required=True)
    sequence = fields.Integer(string='#', default=10)

    product_id = fields.Many2one('product.product', string='Produto', required=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unidade')
    quantity = fields.Float(string='Quantidade', digits='Product Unit of Measure', default=1.0, required=True)

    custo_mp = fields.Monetary(string='Custo Matéria Prima', compute='_compute_custo_mp',
        currency_field='currency_id')
    custo_mp_total = fields.Monetary(string='Total MP', compute='_compute_custo_mp_total',
        currency_field='currency_id')
    custo_comercial = fields.Monetary(string='Custo Itens Comerciais', compute='_compute_custo_comercial',
        currency_field='currency_id')
    custo_comercial_total = fields.Monetary(string='Total Comercial', compute='_compute_custo_comercial_total',
        currency_field='currency_id')
    custo_mp_comercial_total = fields.Monetary(string='Custo MP + Comercial', compute='_compute_custo_mp_comercial_total',
        currency_field='currency_id')
    custo_materiais_total = fields.Monetary(string='Total MP + Com', compute='_compute_custo_materiais_total',
        currency_field='currency_id')
    custo_horas = fields.Monetary(string='Custo Horas', compute='_compute_bom_operation_costs',
        currency_field='currency_id')
    total_horas = fields.Float(string='Total de Horas', compute='_compute_bom_operation_costs')
    custo_terceiros = fields.Monetary(string='Custo Terceiros', compute='_compute_bom_operation_costs',
        currency_field='currency_id')
    custo_total = fields.Monetary(string='Custo Total', compute='_compute_custo_total',
        currency_field='currency_id')

    currency_id = fields.Many2one(related='budget_id.currency_id', depends=['budget_id'])

    @api.depends('product_id', 'quantity')
    def _compute_custo_mp(self):
        for rec in self:
            bom, bom_qty, all_mp, all_serv = self._get_bom_and_categories(rec)
            if bom is None:
                rec.custo_mp = 0.0
                continue
            total = 0.0
            for bom_line in bom.bom_line_ids:
                if bom_line.product_id.categ_id in all_mp:
                    total += bom_line.product_qty * bom_line.product_id.standard_price
            rec.custo_mp = total / bom_qty

    @api.depends('product_id')
    def _compute_custo_comercial(self):
        for rec in self:
            bom, bom_qty, all_mp, all_serv = self._get_bom_and_categories(rec)
            if bom is None:
                rec.custo_comercial = 0.0
                continue
            total = 0.0
            for bom_line in bom.bom_line_ids:
                cat = bom_line.product_id.categ_id
                if cat not in all_mp and cat not in all_serv:
                    total += bom_line.product_qty * bom_line.product_id.standard_price
            rec.custo_comercial = total / bom_qty

    def _get_bom_and_categories(self, rec):
        if not rec.product_id:
            return None, 1.0, self.env['product.category'], self.env['product.category']
        bom = self.env['mrp.bom'].search([
            ('product_id', '=', rec.product_id.id),
            ('type', '=', 'orcamento'),
        ], limit=1)
        if not bom:
            return None, 1.0, self.env['product.category'], self.env['product.category']
        mp_category = self.env['product.category'].search([('name', '=', 'Materia Prima')], limit=1)
        serv_category = self.env['product.category'].search([('name', '=', 'Serviços')], limit=1)
        all_mp = self.env['product.category'].search([('id', 'child_of', mp_category.id)]) if mp_category else self.env['product.category']
        all_serv = self.env['product.category'].search([('id', 'child_of', serv_category.id)]) if serv_category else self.env['product.category']
        return bom, bom.product_qty or 1.0, all_mp, all_serv

    @api.depends('product_id')
    def _compute_bom_operation_costs(self):
        for rec in self:
            rec.custo_horas = 0.0
            rec.total_horas = 0.0
            rec.custo_terceiros = 0.0
            if not rec.product_id:
                continue
            bom = self.env['mrp.bom'].search([
                ('product_id', '=', rec.product_id.id),
                ('type', '=', 'orcamento'),
            ], limit=1)
            if not bom:
                continue
            ops = bom.operation_ids
            if not ops:
                continue
            total_h = 0.0
            total_cost = 0.0
            terc_cost = 0.0
            for op in ops:
                if op.workcenter_id and op.workcenter_id.is_terceiro:
                    terc_cost += (op.custo_hora or 0.0) * (op.time_cycle_hours or 0.0)
                else:
                    total_h += op.time_cycle_hours or 0.0
                    total_cost += (op.custo_hora or 0.0) * (op.time_cycle_hours or 0.0)
            rec.custo_horas = total_cost / total_h if total_h else 0.0
            rec.total_horas = total_h
            rec.custo_terceiros = terc_cost

    @api.depends('custo_mp', 'quantity')
    def _compute_custo_mp_total(self):
        for rec in self:
            rec.custo_mp_total = rec.custo_mp * rec.quantity

    @api.depends('custo_comercial', 'quantity')
    def _compute_custo_comercial_total(self):
        for rec in self:
            rec.custo_comercial_total = rec.custo_comercial * rec.quantity

    @api.depends('custo_mp_total', 'custo_comercial_total')
    def _compute_custo_mp_comercial_total(self):
        for rec in self:
            rec.custo_mp_comercial_total = rec.custo_mp_total + rec.custo_comercial_total

    @api.depends('custo_mp_total', 'custo_comercial_total')
    def _compute_custo_materiais_total(self):
        for rec in self:
            rec.custo_materiais_total = rec.custo_mp_total + rec.custo_comercial_total

    @api.depends('custo_mp_total', 'custo_comercial_total', 'custo_horas', 'total_horas', 'custo_terceiros', 'quantity')
    def _compute_custo_total(self):
        for rec in self:
            rec.custo_total = rec.custo_mp_total + rec.custo_comercial_total + (rec.custo_horas * rec.total_horas * rec.quantity) + (rec.custo_terceiros * rec.quantity)

    def action_open_bom_list(self):
        self.ensure_one()
        if not self.product_id:
            return
        bom = self.env['mrp.bom'].search([
            ('product_id', '=', self.product_id.id),
            ('type', '=', 'orcamento'),
        ], limit=1)
        if not bom:
            bom = self.env['mrp.bom'].create({
                'product_id': self.product_id.id,
                'product_tmpl_id': self.product_id.product_tmpl_id.id,
                'type': 'orcamento',
            })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Lista de Materiais',
            'res_model': 'mrp.bom',
            'view_mode': 'form',
            'res_id': bom.id,
            'target': 'current',
        }

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id
            bom = self.env['mrp.bom'].search([
                ('product_id', '=', self.product_id.id),
                ('type', '=', 'orcamento'),
            ], limit=1)
            if bom:
                self.quantity = bom.product_qty
