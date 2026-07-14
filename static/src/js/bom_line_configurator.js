odoo.define('orcamento.BomLineConfigurator', function (require) {
'use strict';

var ajax = require('web.ajax');
var core = require('web.core');
var Dialog = require('web.Dialog');
var ServicesMixin = require('web.ServicesMixin');
var VariantMixin = require('sale.VariantMixin');

var BomLineConfiguratorDialog = Dialog.extend(ServicesMixin, VariantMixin, {
    events: _.extend({}, Dialog.prototype.events, VariantMixin.events, {}),
    init: function (parent, params) {
        this.bomLineId = params.bom_line_id;

        this._super(parent, _.extend({
            size: 'medium',
            buttons: [
                {
                    text: 'Cancelar',
                    close: true,
                    classes: 'btn-secondary',
                },
                {
                    text: 'Confirmar',
                    classes: 'btn-primary',
                    click: this._onConfirm.bind(this),
                },
            ],
            title: 'Configurar Produto',
        }, params || {}));
    },
    willStart: function () {
        var self = this;
        var getHtml = ajax.jsonRpc('/orcamento/bom_line_configurator/get_html', 'call', {
            bom_line_id: this.bomLineId,
        }).then(function (html) {
            if (html) {
                self.$content = $(html);
            }
        });
        return Promise.all([getHtml, this._super.apply(this, arguments)]);
    },
    start: function () {
        var self = this;
        var def = this._super.apply(this, arguments);
        return def.then(function () {
            self.triggerVariantChange(self.$el);
        });
    },
    _onConfirm: function () {
        var self = this;
        var $container = this.$content || this.$el;
        var ptavIds = VariantMixin.getSelectedVariantValues($container);

        ajax.jsonRpc('/orcamento/bom_line_configurator/save', 'call', {
            bom_line_id: this.bomLineId,
            ptav_ids: ptavIds,
        }).then(function () {
            self.confirmed = true;
            self.close();
            var $notification = $('<div class="o_notification o_notification--success">' +
                '<div class="o_notification__content">' +
                '<span>Produto configurado com sucesso!</span>' +
                '</div></div>');
            $('body').append($notification);
            setTimeout(function () {
                $notification.fadeOut(function () {
                    $notification.remove();
                });
            }, 3000);
        }).catch(function (error) {
            var msg = error && error.message ? error.message : 'Erro ao configurar produto.';
            var $notification = $('<div class="o_notification o_notification--danger">' +
                '<div class="o_notification__content">' +
                '<span>' + _.escape(msg) + '</span>' +
                '</div></div>');
            $('body').append($notification);
            setTimeout(function () {
                $notification.fadeOut(function () {
                    $notification.remove();
                });
            }, 5000);
        });
    },
});

function bomLineConfiguratorAction(env, action) {
    var params = action && action.params || {};
    var dialog = new BomLineConfiguratorDialog(null, params);
    dialog.open();
    return new Promise(function (resolve) {
        dialog.on('closed', null, function () {
            if (dialog.confirmed && params.bom_id && params.bom_id > 0) {
                env.services.action.doAction({
                    type: 'ir.actions.act_window',
                    res_model: params.bom_model || 'mrp.bom',
                    res_id: params.bom_id,
                    views: [[false, 'form']],
                    target: 'current',
                    flags: {mode: 'edit'},
                });
            }
            resolve();
        });
    });
}

core.action_registry.add('orca.bom_line_configurator', bomLineConfiguratorAction);

return bomLineConfiguratorAction;
});
