# Copyright 2020 Tecnativa - Ernesto Tejeda
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

TIMING_ON_CONFIRM = "on_confirm"
TIMING_AFTER_RECEIPT = "after_receipt"
TIMING_NO = "no"
TIMING_REFUND_SO = "update_sale_delivered_qty"


class RmaOperation(models.Model):
    _name = "rma.operation"
    _description = "RMA requested operation"

    active = fields.Boolean(default=True)
    name = fields.Char(required=True, translate=True)

    create_receipt_timing = fields.Selection(
        [
            (TIMING_ON_CONFIRM, "On confirm"),
            (TIMING_NO, "No"),
        ],
        "Receipt timing",
        default=TIMING_ON_CONFIRM,
    )

    create_return_timing = fields.Selection(
        [
            (TIMING_ON_CONFIRM, "On confirm"),
            (TIMING_AFTER_RECEIPT, "After receipt"),
            (TIMING_NO, "No"),
        ],
        "Return timing",
        default=TIMING_AFTER_RECEIPT,
    )

    create_chained_pickings = fields.Boolean(
        "Create chained pickings",
        default=True,
        help="If this is checked, the incoming and outgoing pickings will be chained",
    )

    create_refund_timing = fields.Selection(
        [
            (TIMING_ON_CONFIRM, "On confirm"),
            (TIMING_AFTER_RECEIPT, "After receipt"),
            (TIMING_REFUND_SO, "Update SO delivered qty"),
            (TIMING_NO, "No refund"),
        ],
        "Refund timing",
        default=TIMING_AFTER_RECEIPT,
    )

    refund_invoicing = fields.Selection(
        [
            ("full", "Full"),
            ("partial", "Partial"),
        ]
    )

    can_create_refund = fields.Boolean(
        "Create a refund", compute="_compute_create_refund"
    )

    _sql_constraints = [
        ("name_uniq", "unique (name)", "That operation name already exists !"),
    ]

    @api.onchange("create_refund_timing")
    def _onchange_create_refund_timing(self):
        if not self.can_create_refund:
            self.refund_invoicing = False

    @api.depends("create_refund_timing")
    def _compute_create_refund(self):
        for rec in self:
            rec.can_create_refund = rec.create_refund_timing not in [
                TIMING_NO,
                TIMING_REFUND_SO,
            ]
