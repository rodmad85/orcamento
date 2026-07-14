from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    type = fields.Selection(selection_add=[
        ('orcamento', 'Orçamento'),
    ], ondelete={'orcamento': 'set default'})

    purchase_list_id = fields.Many2one('orca.purchase.list', string='Lista de Compras', copy=False)

    def write(self, vals):
        res = super().write(vals)
        for bom in self:
            if bom.type != 'orcamento':
                continue
            purchase_list = bom.purchase_list_id
            if not purchase_list:
                purchase_list = self.env['orca.purchase.list'].create({
                    'bom_id': bom.id,
                })
                bom.write({'purchase_list_id': purchase_list.id})
            purchase_list.action_generate_lines()
        return res

    @api.model
    def create(self, vals):
        res = super().create(vals)
        if res.type == 'orcamento':
            purchase_list = self.env['orca.purchase.list'].create({
                'bom_id': res.id,
            })
            res.write({'purchase_list_id': purchase_list.id})
            purchase_list.action_generate_lines()
        return res

    def action_open_purchase_list(self):
        self.ensure_one()
        if not self.purchase_list_id:
            return
        return {
            'type': 'ir.actions.act_window',
            'name': 'Itens da Lista de Compras',
            'res_model': 'orca.purchase.list.line',
            'view_mode': 'tree',
            'domain': [('purchase_list_id', '=', self.purchase_list_id.id)],
            'target': 'current',
            'context': {'default_purchase_list_id': self.purchase_list_id.id},
        }


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if self._context.get('orcamento_template_search'):
            domain = [('product_tmpl_id.name', operator, name)]
            if args:
                domain += args
            records = self.search(domain, limit=limit)
            return records.name_get()
        return super().name_search(name, args, operator, limit)


class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'

    medidas = fields.Char(string='Medidas')
    qty_available = fields.Float(string='Qtd. Estoque Atual', related='product_id.qty_available', readonly=True)
    ultima_compra = fields.Date(string='Data da Última Compra')
    ultimo_fornecedor_id = fields.Many2one('res.partner', string='Último Fornecedor')
    ultimo_preco_compra = fields.Monetary(string='Último Preço de Compra', currency_field='currency_id')
    currency_id = fields.Many2one(related='bom_id.company_id.currency_id')
    utilizar_estoque = fields.Boolean(string='Utilizar Estoque')

    def action_open_bom_list(self):
        self.ensure_one()
        if not self.product_id:
            return
        return {
            'type': 'ir.actions.act_window',
            'name': 'Lista de Materiais',
            'res_model': 'mrp.bom',
            'view_mode': 'tree,form',
            'domain': [('product_id', '=', self.product_id.id)],
        }

    def action_open_bom_line_configurator(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'orca.bom_line_configurator',
            'params': {
                'bom_line_id': self._origin.id or self.id,
                'bom_id': self.bom_id._origin.id or self.bom_id.id,
                'bom_model': self.bom_id._name,
            },
            'target': 'new',
        }

    def action_confirm_variant(self, ptav_ids):
        self.ensure_one()
        if not self.product_id:
            raise ValidationError(_("Produto não definido na linha."))
        tmpl = self.product_id.product_tmpl_id
        combination = self.env['product.template.attribute.value'].browse(ptav_ids)
        # Try to get existing variant matching the combination
        variant = tmpl._get_variant_for_combination(combination)
        if not variant:
            # If not found, try to create (works for dynamic attributes)
            variant = tmpl._create_product_variant(combination)
        if not variant:
            # Last attempt: create the variant directly bypassing the possibility check
            # This handles cases where existing variants don't have matching combination_indices
            filtered = combination._without_no_variant_attributes()
            if filtered:
                variant = tmpl.sudo().with_context(active_test=False).product_variant_ids.filtered(
                    lambda p: p.product_template_attribute_value_ids == filtered
                )[:1]
        if not variant:
            raise ValidationError(_("Nenhuma variante encontrada para a combinação selecionada."))
        self.write({
            'product_id': variant.id,
            'product_uom_id': variant.uom_id.id,
        })
        self._update_supplier_info(variant)

    def _has_configurable_attributes(self, product):
        attr_lines = product.product_tmpl_id.attribute_line_ids.filtered(
            lambda l: l.attribute_id.create_variant != 'no_variant'
        )
        return len(attr_lines) >= 1 and any(
            len(line.value_ids) > 1 for line in attr_lines
        )

    def _update_supplier_info(self, product):
        self.product_uom_id = product.uom_id
        seller = self.env['product.supplierinfo'].search([
            '|',
            ('product_id', '=', product.id),
            '&',
            ('product_tmpl_id', '=', product.product_tmpl_id.id),
            ('product_id', '=', False),
        ], order='sequence, price', limit=1)
        if seller:
            self.ultimo_fornecedor_id = seller.partner_id
        else:
            self.ultimo_fornecedor_id = False
        if 'purchase.order.line' in self.env:
            order_ids = self.env['purchase.order'].search([
                ('order_line.product_id', '=', product.id),
                ('state', '=', 'purchase'),
            ], order='date_order desc', limit=1)
            if order_ids:
                self.ultima_compra = order_ids.date_order.date()
                self.ultimo_fornecedor_id = order_ids.partner_id
                line = self.env['purchase.order.line'].search([
                    ('order_id', '=', order_ids.id),
                    ('product_id', '=', product.id),
                ], limit=1)
                self.ultimo_preco_compra = line.price_unit if line else 0.0
            else:
                self.ultima_compra = False
                self.ultimo_preco_compra = 0.0

    @api.onchange('product_id')
    def _onchange_product_id_orcamento(self):
        if not self.product_id:
            return
        if not self.bom_id or self.bom_id.type != 'orcamento':
            return
        if self._has_configurable_attributes(self.product_id):
            return {
                'action': {
                    'type': 'ir.actions.client',
                    'tag': 'orca.bom_line_configurator',
                    'params': {
                        'bom_line_id': self._origin.id or self.id,
                        'bom_id': self.bom_id._origin.id or self.bom_id.id,
                        'bom_model': self.bom_id._name,
                    },
                    'target': 'new',
                },
            }
        self._update_supplier_info(self.product_id)


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    is_terceiro = fields.Boolean(string='Terceiros')


class MrpRoutingWorkcenter(models.Model):
    _inherit = 'mrp.routing.workcenter'

    custo_hora = fields.Float(string='Custo por Hora')
    valor_total = fields.Float(string='Valor Total', compute='_compute_valor_total', store=True)
    time_cycle_hours = fields.Float(
        string='Duração (horas)',
        compute='_compute_time_cycle_hours',
        inverse='_inverse_time_cycle_hours',
    )
    workcenter_terceiro = fields.Boolean(
        string='Terceiros',
        related='workcenter_id.is_terceiro',
        store=False,
        readonly=True,
    )

    @api.depends('custo_hora', 'time_cycle', 'time_cycle_hours')
    def _compute_valor_total(self):
        for rec in self:
            rec.valor_total = rec.custo_hora * (rec.time_cycle / 60.0) if rec.time_cycle else 0.0

    @api.depends('time_cycle')
    def _compute_time_cycle_hours(self):
        for rec in self:
            rec.time_cycle_hours = rec.time_cycle / 60.0 if rec.time_cycle else 0.0

    def _inverse_time_cycle_hours(self):
        for rec in self:
            rec.time_cycle = rec.time_cycle_hours * 60.0

    @api.onchange('workcenter_id')
    def _onchange_workcenter_id(self):
        if self.workcenter_id:
            self.custo_hora = self.workcenter_id.costs_hour
