# Copyright 2020 Tecnativa - David Vidal
# Copyright 2023 Michael Tietz (MT Software) <mtietz@mt-software.de>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, SavepointCase, tagged


@tagged("post_install", "-at_install")
class TestRmaSaleMrp(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.res_partner = cls.env["res.partner"]
        cls.product_product = cls.env["product.product"]
        cls.product_kit = cls.product_product.create(
            {"name": "Product test 1", "type": "consu"}
        )
        cls.product_kit_comp_1 = cls.product_product.create(
            {"name": "Product Component 1", "type": "product"}
        )
        cls.product_kit_comp_2 = cls.product_product.create(
            {"name": "Product Component 2", "type": "product"}
        )
        cls.bom = cls.env["mrp.bom"].create(
            {
                "product_id": cls.product_kit.id,
                "product_tmpl_id": cls.product_kit.product_tmpl_id.id,
                "type": "phantom",
                "bom_line_ids": [
                    (
                        0,
                        0,
                        {"product_id": cls.product_kit_comp_1.id, "product_qty": 2},
                    ),
                    (
                        0,
                        0,
                        {"product_id": cls.product_kit_comp_2.id, "product_qty": 4},
                    ),
                ],
            }
        )
        cls.product_2 = cls.product_product.create(
            {"name": "Product test 2", "type": "product"}
        )
        cls.partner = cls.res_partner.create({"name": "Partner test"})
        cls.sale_order = cls._create_sale_order(5)
        cls.sale_order.action_confirm()
        # Maybe other modules create additional lines in the create
        # method in sale.order model, so let's find the correct line.
        cls.order_line = cls.sale_order.order_line.filtered(
            lambda r: r.product_id == cls.product_kit
        )
        cls.order_out_picking = cls.sale_order.picking_ids
        # Confirm but leave a backorder to split moves so we can test that
        # the wizard correctly creates the RMAs with the proper quantities
        for line in cls.order_out_picking.move_lines:
            line.quantity_done = line.product_uom_qty - 7
        wiz_act = cls.order_out_picking.button_validate()
        wiz = Form(
            cls.env[wiz_act["res_model"]].with_context(wiz_act["context"])
        ).save()
        wiz.process()
        cls.backorder = cls.sale_order.picking_ids - cls.order_out_picking
        for line in cls.backorder.move_lines:
            line.quantity_done = line.product_uom_qty
        cls.backorder.button_validate()

    @classmethod
    def _create_sale_order(cls, qty):
        order_form = Form(cls.env["sale.order"])
        order_form.partner_id = cls.partner
        with order_form.order_line.new() as line_form:
            line_form.product_id = cls.product_kit
            line_form.product_uom_qty = qty
        return order_form.save()

    def _do_rma_test(self, wizard):
        order = self.sale_order
        out_pickings = self.order_out_picking + self.backorder
        res = wizard.create_and_open_rma()
        rmas = self.env["rma"].search(res["domain"])
        for rma in rmas:
            self.assertEqual(rma.partner_id, order.partner_id)
            self.assertEqual(rma.order_id, order)
            self.assertTrue(rma.picking_id in out_pickings)
        self.assertEqual(rmas.mapped("phantom_bom_product"), self.product_kit)
        self.assertEqual(
            rmas.mapped("product_id"), self.product_kit_comp_1 + self.product_kit_comp_2
        )
        rma_1 = rmas.filtered(lambda x: x.product_id == self.product_kit_comp_1)
        rma_2 = rmas.filtered(lambda x: x.product_id == self.product_kit_comp_2)
        move_1 = out_pickings.mapped("move_lines").filtered(
            lambda x: x.product_id == self.product_kit_comp_1
        )
        move_2 = out_pickings.mapped("move_lines").filtered(
            lambda x: x.product_id == self.product_kit_comp_2
        )
        self.assertEqual(sum(rma_1.mapped("product_uom_qty")), 8)
        self.assertEqual(rma_1.mapped("product_uom"), move_1.mapped("product_uom"))
        self.assertEqual(sum(rma_2.mapped("product_uom_qty")), 16)
        self.assertEqual(rma_2.mapped("product_uom"), move_2.mapped("product_uom"))
        self.assertEqual(rma.state, "confirmed")
        self.assertEqual(
            rma_1.mapped("reception_move_ids.origin_returned_move_id"),
            move_1,
        )
        self.assertEqual(
            rma_2.mapped("reception_move_ids.origin_returned_move_id"),
            move_2,
        )
        self.assertEqual(
            rmas.mapped("reception_move_ids.picking_id")
            + self.order_out_picking
            + self.backorder,
            order.picking_ids,
        )
        # Refund the RMA
        user = self.env["res.users"].create(
            {"login": "test_refund_with_so", "name": "Test"}
        )
        order.user_id = user.id
        rma.reception_move_ids.quantity_done = rma.product_uom_qty
        rma.reception_move_ids.picking_id._action_done()
        # All the component RMAs must be received if we want to make a refund
        with self.assertRaises(UserError):
            rma.action_refund()
        rmas_left = rmas - rma
        for additional_rma in rmas_left:
            additional_rma.reception_move_ids.quantity_done = (
                additional_rma.product_uom_qty
            )
            additional_rma.reception_move_ids.picking_id._action_done()
        rma.action_refund()
        self.assertEqual(rma.refund_id.user_id, user)
        # The component RMAs get automatically refunded
        self.assertEqual(rma.refund_id, rmas_left.mapped("refund_id"))
        # The refund product is the kit, not the components
        self.assertEqual(rma.refund_id.invoice_line_ids.product_id, self.product_kit)
        rma.refund_id.action_post()

    def _do_rma_test_remaining(self):
        order = self.sale_order
        # We can still return another kit
        wizard_id = order.action_create_rma()["res_id"]
        wizard = self.env["sale.order.rma.wizard"].browse(wizard_id)
        self.assertEqual(wizard.line_ids.quantity, 1)
        wizard.create_and_open_rma()
        # Now we open the wizard again and try to force the RMA qty wich should
        # be 0 at this time
        wizard_id = order.action_create_rma()["res_id"]
        wizard = self.env["sale.order.rma.wizard"].browse(wizard_id)
        self.assertEqual(wizard.line_ids.quantity, 0)
        wizard.line_ids.quantity = 1
        with self.assertRaises(ValidationError):
            wizard.create_and_open_rma()

    def test_create_rma_from_so(self):
        order = self.sale_order
        wizard_id = order.action_create_rma()["res_id"]
        wizard = self.env["sale.order.rma.wizard"].browse(wizard_id)
        self.assertEqual(len(wizard.line_ids), 1)
        self.assertEqual(len(wizard.component_line_ids), 4)
        wizard.line_ids.quantity = 4
        self._do_rma_test(wizard)
        self._do_rma_test_remaining()

    def test_create_rma_from_so_detailed(self):
        self.product_kit.rma_kit_show_detailed = True
        order = self.sale_order
        wizard_id = order.action_create_rma()["res_id"]
        wizard = self.env["sale.order.rma.wizard"].browse(wizard_id)
        self.assertEqual(len(wizard.line_ids), 4)
        self.assertEqual(len(wizard.component_line_ids), 0)

        kit_comp_1_lines = wizard.line_ids.filtered(
            lambda line: line.product_id == self.product_kit_comp_1
        ).sorted(lambda l: l.move_id.id)
        kit_comp_2_lines = wizard.line_ids - kit_comp_1_lines
        kit_comp_2_lines = kit_comp_2_lines.sorted(lambda l: l.move_id.id)

        # set quantities like test_create_rma_from_so
        kit_comp_1_lines[0].quantity = 3.0
        kit_comp_1_lines[1].quantity = 5.0
        kit_comp_2_lines[0].quantity = 13.0
        kit_comp_2_lines[1].quantity = 3.0

        self._do_rma_test(wizard)

    def _do_picking(self, picking, set_qty_done=True, qty=False):
        if set_qty_done:
            for line in picking.move_lines:
                line.quantity_done = qty or line.product_uom_qty

        wiz = picking.button_validate()
        if wiz is True:
            return wiz
        wiz = Form(self.env[wiz["res_model"]].with_context(wiz["context"])).save()
        wiz.process()
        return picking.backorder_ids

    def test_qty_delivered(self):
        order = self._create_sale_order(1)
        order.action_confirm()
        self._do_picking(order.picking_ids)
        self.assertEqual(order.order_line.qty_delivered, 1)

        wizard_id = order.action_create_rma()["res_id"]
        wizard = self.env["sale.order.rma.wizard"].browse(wizard_id)

        rmas = wizard.create_rma()
        rmas.write({"operation_id": self.env.ref("rma.rma_operation_replace").id})
        rmas.operation_id.write(
            {
                "create_refund_timing": "update_sale_delivered_qty",
                "create_receipt_timing": "on_confirm",
                "create_return_timing": "on_confirm",
            }
        )
        rmas.action_confirm()
        rmas[0].delivery_move_ids.quantity_done = rmas[
            0
        ].delivery_move_ids.product_uom_qty
        backorder = self._do_picking(rmas[0].delivery_move_ids.picking_id, False)
        self.assertEqual(order.order_line.qty_delivered, 1)
        self.assertEqual(backorder.move_lines, rmas[1].delivery_move_ids)
        self._do_picking(backorder)
        self.assertEqual(order.order_line.qty_delivered, 2)
        rmas[0].reception_move_ids.quantity_done = rmas[
            0
        ].reception_move_ids.product_uom_qty
        self._do_picking(rmas[0].reception_move_ids.picking_id, False)
        self.assertEqual(order.order_line.qty_delivered, 1)
        order.order_line._compute_qty_delivered()
        self._do_picking(rmas[1].reception_move_ids.picking_id)
        self.assertEqual(order.order_line.qty_delivered, 1)
