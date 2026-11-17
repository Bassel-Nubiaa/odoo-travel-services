"""Tests for the sales order created from an application."""
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import TravelCommon
from .test_application_line import FLIGHT_DETAILS


@tagged("post_install", "-at_install")
class TestSaleOrder(TravelCommon):
    """One quotation per application, one order line per application line."""

    def _ready_application(self, stage=None, **vals):
        """Return an application with a Done flight and a Done transfer, in In Progress."""
        application = self._application(**vals)
        self._line(application, self.flight, **FLIGHT_DETAILS).state = "done"
        self._line(application, self.transfer).state = "done"
        application.stage_id = stage or self.stage_in_progress
        return application

    def test_order_from_application(self):
        """The quotation is for the paying client, with one line per application line."""
        application = self._ready_application()
        application.action_create_sale_order()
        order = application.sale_order_id
        self.assertEqual(order.partner_id, self.client)
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.origin, application.name)
        self.assertEqual(order.travel_application_id, application)
        self.assertEqual(order.order_line.travel_line_id, application.line_ids)
        self.assertEqual(order.order_line.mapped("price_unit"), [1200.0, 150.0])
        self.assertEqual(order.order_line.mapped("product_uom_qty"), [1.0, 1.0])

    def test_description_lists_required_details(self):
        """The order line describes the service, the passenger and the required details."""
        application = self._ready_application()
        application.action_create_sale_order()
        flight_line = application.sale_order_id.order_line[0]
        self.assertTrue(flight_line.name.startswith("Flight Ticket: Sara Haddad, "))
        for detail in ("N1234567", "EK 912", "14C", "176-2412345678", "K7XQ2M"):
            self.assertIn(detail, flight_line.name)

    def test_one_order_per_application(self):
        """A second order for the same application is refused."""
        application = self._ready_application()
        application.action_create_sale_order()
        with self.assertRaises(UserError):
            application.action_create_sale_order()

    def test_deleted_quotation_can_be_recreated(self):
        """Deleting the quotation frees the application for a new one."""
        application = self._ready_application()
        application.action_create_sale_order()
        application.sale_order_id.unlink()
        self.assertFalse(application.sale_order_id)
        application.action_create_sale_order()
        self.assertTrue(application.sale_order_id)

    def test_not_before_in_progress(self):
        """Before In Progress, orders cannot be created, even with every line Done."""
        application = self._ready_application(stage=self.stage_gathering)
        self.assertFalse(application.can_create_orders)
        with self.assertRaises(UserError):
            application.action_create_sale_order()

    def test_allowed_after_in_progress(self):
        """Stages after In Progress, such as Done, still allow orders."""
        application = self._ready_application(stage=self.stage_done)
        self.assertTrue(application.can_create_orders)

    def test_not_when_cancelled(self):
        """Cancelled applications cannot create orders."""
        application = self._ready_application(stage=self.stage_canceled)
        self.assertFalse(application.can_create_orders)
        with self.assertRaises(UserError):
            application.action_create_sale_order()

    def test_reopened_line_blocks_order(self):
        """A line set back from Done blocks the order."""
        application = self._ready_application()
        application.line_ids[1].with_user(self.admin).state = "gathering"
        with self.assertRaises(UserError):
            application.action_create_sale_order()

    def test_order_in_sales_currency(self):
        """The order uses a pricelist in the application's sales currency."""
        currency = self.env["res.currency"].create({"name": "TST", "symbol": "T$"})
        self.env["product.pricelist"].create({"name": "TST Prices", "currency_id": currency.id})
        application = self._ready_application(currency_id=currency.id)
        application.action_create_sale_order()
        order = application.sale_order_id
        self.assertEqual(order.currency_id, currency)
        self.assertEqual(
            order.order_line.mapped("price_unit"), application.line_ids.mapped("price_unit"),
        )

    def test_missing_pricelist_reported(self):
        """Without a pricelist in the sales currency, the order is refused clearly."""
        currency = self.env["res.currency"].create({"name": "TST", "symbol": "T$"})
        application = self._ready_application(currency_id=currency.id)
        with self.assertRaises(UserError):
            application.action_create_sale_order()

    def test_agent_creates_order(self):
        """An agent creates the order of their own application, as its salesperson."""
        application = self._ready_application(user_id=self.agent.id)
        application.with_user(self.agent).action_create_sale_order()
        self.assertEqual(application.sale_order_id.user_id, self.agent)
