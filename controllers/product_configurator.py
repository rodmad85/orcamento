from odoo import http
from odoo.http import request


class BomLineConfiguratorController(http.Controller):

    @http.route('/orcamento/bom_line_configurator/get_html', type='json', auth='user', methods=['POST'])
    def get_configurator_html(self, bom_line_id):
        bom_line = request.env['mrp.bom.line'].browse(bom_line_id)
        product_tmpl = bom_line.product_id.product_tmpl_id
        combination = bom_line.product_id.product_template_attribute_value_ids

        return request.env['ir.ui.view']._render_template(
            'orcamento.bom_line_configurator',
            {
                'product': product_tmpl,
                'combination': combination,
            }
        )

    @http.route('/orcamento/bom_line_configurator/save', type='json', auth='user', methods=['POST'])
    def save_configurator(self, bom_line_id, ptav_ids):
        bom_line = request.env['mrp.bom.line'].browse(bom_line_id)
        bom_line.action_confirm_variant(ptav_ids)
        return True
