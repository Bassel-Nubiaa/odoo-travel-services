"""Tests for the purchase orders created from an application."""
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import TravelCommon
from .test_application_line import FLIGHT_DETAILS


@tagged("post_install", "-at_install")
class TestPurchaseOrder(TravelCommon):
    """One request for quotation per vendor and purchase currency."""

    @classmethod
    def setUpClass(cls):
        """Create a second vendor and a second purchase currency."""
        super().setUpClass()
        cls.company_currency = cls.env.company.currency_id
        cls.other_vendor = cls.env["res.partner"].create({"name": "Second Travel Office"})
        cls.foreign = cls.env["res.currency"].create({"name": "TST", "symbol": "T$"})

    def _bought(self, vendor, currency, **vals):
        """Return the values of a line bought from a vendor in a currency."""
        return {"vendor_id": vendor.id, "purchase_currency_id": currency.id, **vals}

    def _ready_application(self, stage=None):
        """Return an application in In Progress with five Done lines.

        Vendor 1 in the company currency: a flight and a transfer.
        Vendor 2 in the company currency: a transfer.
        Vendor 1 in the foreign currency: a transfer.
        No vendor: a transfer the agency provides itself.
        """
        application = self._application()
        lines = [
            self._line(application, self.flight, **FLIGHT_DETAILS,
                       **self._bought(self.vendor, self.company_currency)),
            self._line(application, self.transfer,
                       **self._bought(self.vendor, self.company_currency)),
            self._line(application, self.transfer,
                       **self._bought(self.other_vendor, self.company_currency)),
            self._line(application, self.transfer,
                       **self._bought(self.vendor, self.foreign, cost=40.0)),
            self._line(application, self.transfer),
        ]
        for line in lines:
            line.state = "done"
        application.stage_id = stage or self.stage_in_progress
        return application

    def test_one_order_per_vendor_and_currency(self):
        """Lines are grouped by vendor, then by purchase currency."""
        application = self._ready_application()
        application.action_create_purchase_orders()
        orders = application.purchase_order_ids
        self.assertEqual(len(orders), 3)
        self.assertEqual(application.purchase_order_count, 3)
        groups = {(order.partner_id, order.currency_id): len(order.order_line) for order in orders}
        self.assertEqual(groups, {
            (self.vendor, self.company_currency): 2,
            (self.other_vendor, self.company_currency): 1,
            (self.vendor, self.foreign): 1,
        })

    def test_order_line_values(self):
        """Each purchase line has the line's cost, quantity 1 and no taxes."""
        application = self._ready_application()
        application.action_create_purchase_orders()
        flight_line = application.line_ids[0]
        purchase_line = flight_line.purchase_line_ids
        self.assertEqual(purchase_line.price_unit, 900.0)
        self.assertEqual(purchase_line.product_qty, 1.0)
        self.assertFalse(purchase_line.taxes_id)
        self.assertTrue(purchase_line.name.startswith("Flight Ticket: Sara Haddad, "))
        order = purchase_line.order_id
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.origin, application.name)
        self.assertEqual(order.travel_application_id, application)
        self.assertEqual(application.line_ids[3].purchase_line_ids.price_unit, 40.0)

    def test_lines_without_vendor_skipped(self):
        """Services the agency provides itself are not ordered."""
        application = self._ready_application()
        application.action_create_purchase_orders()
        self.assertFalse(application.line_ids[4].purchase_line_ids)

    def test_lines_ordered_once(self):
        """Once every vendor line is ordered, the button has nothing left to do."""
        application = self._ready_application()
        self.assertTrue(application.has_lines_to_purchase)
        application.action_create_purchase_orders()
        self.assertFalse(application.has_lines_to_purchase)
        with self.assertRaises(UserError):
            application.action_create_purchase_orders()

    def test_deleted_order_frees_its_lines(self):
        """Deleting a request for quotation (cancelled first) lets its lines be ordered again."""
        application = self._ready_application()
        application.action_create_purchase_orders()
        order = application.line_ids[2].purchase_line_ids.order_id
        order.button_cancel()
        order.unlink()
        self.assertTrue(application.has_lines_to_purchase)
        application.action_create_purchase_orders()
        self.assertEqual(len(application.purchase_order_ids), 3)

    def test_cancelled_order_frees_its_lines(self):
        """Cancelling a request for quotation lets its lines be ordered again."""
        application = self._ready_application()
        application.action_create_purchase_orders()
        application.line_ids[2].purchase_line_ids.order_id.button_cancel()
        self.assertTrue(application.has_lines_to_purchase)

    def test_not_before_in_progress(self):
        """Before In Progress, purchase orders cannot be created."""
        application = self._ready_application(stage=self.stage_gathering)
        with self.assertRaises(UserError):
            application.action_create_purchase_orders()

    def test_no_vendor_no_purchase(self):
        """An application without vendors has nothing to buy."""
        application = self._application()
        self._line(application, self.transfer).state = "done"
        application.stage_id = self.stage_in_progress
        self.assertFalse(application.has_lines_to_purchase)
        with self.assertRaises(UserError):
            application.action_create_purchase_orders()

    def test_agent_creates_orders(self):
        """An agent creates the purchase orders of their own application."""
        application = self._ready_application()
        application.with_user(self.agent).action_create_purchase_orders()
        self.assertEqual(len(application.purchase_order_ids), 3)
