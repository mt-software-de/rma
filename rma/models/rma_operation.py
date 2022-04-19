# Copyright 2020 Tecnativa - Ernesto Tejeda
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models, api


class RmaOperation(models.Model):
    _name = "rma.operation"
    _description = "RMA requested operation"

    active = fields.Boolean(default=True)
    name = fields.Char(required=True, translate=True)

    create_receipt = fields.Boolean('Create Receipt', default=True)
    create_delivery = fields.Boolean('Create delivery', default=True)
    
    refund_type = fields.Selection([
        ('refund', 'Refund'),
        ('update_sale_delivered_qty', 'Update SO delivered qty'),
        ('no_refund', 'No refund'),
    ], 'Refund timing', default='refund')

    refund_invoicing = fields.Selection([
        ('full', 'Full'),
        ('partial', 'Partial'),
    ])
    
    create_refund = fields.Boolean('Create a refund', compute="_compute_create_refund")

    _sql_constraints = [
        ("name_uniq", "unique (name)", "That operation name already exists !"),
    ]

    @api.onchange('refund_timing')
    def _onchange_refund_timing(self):
        if not self.create_refund:
            self.refund_invoicing = False

    @api.depends('refund_timing')
    def _compute_create_refund(self):
        for rec in self:
            rec.create_refund = rec.refund_type == 'refund'
