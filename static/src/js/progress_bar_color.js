odoo.define('ordem_servico.progress_bar_color', function (require) {
"use strict";
var core = require('web.core');
var utils = require('web.utils');
var Widget = require('web.Widget');
var FieldRegistry = require('web.field_registry');
var FieldProgressBar = require('web.basic_fields').FieldProgressBar;
FieldProgressBar.include({
    _render_value: function (v) {
        var value = this.value;
        var max_value = this.max_value;
        if (!isNaN(v)) {
            if (this.edit_max_value) {
                max_value = v;
            } else {
                value = v;
            }
        }
        value = value || 0;
        max_value = max_value || 0;
        var widthComplete;
        if (value <= max_value) {
            widthComplete = value/max_value * 100;
        } else {
            widthComplete = 100;
        }
        this.$('.o_progress').toggleClass('o_progress_overflow', value > max_value)
            .attr('aria-valuemin', '0')
            .attr('aria-valuemax', max_value)
            .attr('aria-valuenow', value);
//        this.$('.o_progressbar_complete').css('width', widthComplete + '%');
        this.$('.o_progressbar_complete').toggleClass('o_progress_red',widthComplete>101).css('width', widthComplete + '%');
        this.$('.o_progressbar_complete').toggleClass('o_progress_yellow',widthComplete>75 && widthComplete<=100).css('width', widthComplete + '%');
        this.$('.o_progressbar_complete').toggleClass('o_progress_light_green',widthComplete>41 && widthComplete<=74).css('width', widthComplete + '%');
        this.$('.o_progressbar_complete').toggleClass('o_progress_green',widthComplete>0 && widthComplete<=40).css('width', widthComplete + '%');
        if (!this.write_mode) {
            if (max_value !== 100) {
                this.$('.o_progressbar_value').text(utils.human_number(value) + " / " + utils.human_number(max_value));
            } else {
                this.$('.o_progressbar_value').text(utils.human_number(value) + "%");
            }
        } else if (isNaN(v)) {
            this.$('.o_progressbar_value').val(this.edit_max_value ? max_value : value);
            this.$('.o_progressbar_value').focus().select();
        }
    },
});
});