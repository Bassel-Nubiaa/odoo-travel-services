"""Tests for VAT on the margin: orders, invoices and the tax switch."""
from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import TravelCommon
from .test_application_line import FLIGHT_DETAILS


@tagged("post_install", "-at_install")
class TestMarginVat(TravelCommon):
    """A 5% tax on margin applies to (price - cost), never below zero."""

    @classmethod
    def setUpClass(cls):
        """Create a 5% tax on margin and a normal 5% tax; the services use the margin one."""
        super().setUpClass()
        Tax = cls.env["account.tax"]
        cls.margin_tax = Tax.create({
            "name": "VAT 5% on margin",
            "amount": 5.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "travel_margin_tax": True,
        })
        cls.normal_tax = Tax.create({
            "name": "VAT 5%",
            "amount": 5.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
        })
        (cls.flight | cls.transfer).taxes_id = cls.margin_tax

    def _order(self, **line_vals):
        """Create the sales order of an application with a flight and a transfer."""
        application = self._application()
        self._line(application, self.flight, **FLIGHT_DETAILS, **line_vals).state = "done"
        self._line(application, self.transfer).state = "done"
        application.stage_id = self.stage_in_progress
        application.action_create_sale_order()
        return application.sale_order_id

    def test_cost_copied_to_order(self):
        """Each order line carries its application line's purchase price."""
        order = self._order()
        self.assertEqual(order.order_line.mapped("travel_cost"), [900.0, 100.0])

    def test_order_taxed_on_margin(self):
        """5% of (1,200 - 900) plus 5% of (150 - 100): 15 + 2.5."""
        order = self._order()
        self.assertEqual(order.order_line.mapped("price_tax"), [15.0, 2.5])
        self.assertEqual(order.order_line.mapped("price_subtotal"), [1200.0, 150.0])
        self.assertEqual(order.amount_untaxed, 1350.0)
        self.assertEqual(order.amount_tax, 17.5)
        self.assertEqual(order.amount_total, 1367.5)

    def test_margin_never_below_zero(self):
        """Selling below cost gives no tax, not a negative one."""
        order = self._order(price_unit=800.0)
        self.assertEqual(order.order_line[0].price_tax, 0.0)

    def test_normal_tax_unchanged(self):
        """A tax without the switch still applies to the full price."""
        order = self._order()
        order.order_line[0].tax_id = self.normal_tax
        self.assertEqual(order.order_line[0].price_tax, 60.0)

    def test_line_without_cost_taxed_in_full(self):
        """A margin tax on a line without cost applies to the full price."""
        order = self._order()
        order.order_line[0].travel_cost = 0.0
        self.assertEqual(order.order_line[0].price_tax, 60.0)

    def test_invoice_taxed_on_margin(self):
        """The invoice carries the costs, and its tax line has the margin as base."""
        order = self._order()
        order.action_confirm()
        invoice = order._create_invoices()
        self.assertEqual(invoice.invoice_line_ids.mapped("travel_cost"), [900.0, 100.0])
        self.assertEqual(invoice.invoice_line_ids.mapped("price_subtotal"), [1200.0, 150.0])
        self.assertEqual(invoice.amount_tax, 17.5)
        invoice.action_post()
        tax_line = invoice.line_ids.filtered(lambda line: line.tax_line_id == self.margin_tax)
        self.assertEqual(tax_line.tax_base_amount, 350.0)
        self.assertEqual(abs(tax_line.balance), 17.5)
        self.assertEqual(invoice.amount_total, 1367.5)

    def test_foreign_cost_converted(self):
        """A purchase price in another currency is converted to the order currency."""
        today = fields.Date.today()
        company_currency = self.env.company.currency_id
        company_rate = company_currency._get_rates(self.env.company, today)[company_currency.id]
        # 2 units of this currency for 1 unit of the company currency.
        foreign = self.env["res.currency"].create({
            "name": "TST",
            "symbol": "T$",
            "rate_ids": [Command.create({
                "name": today,
                "rate": 2.0 * company_rate,
                "company_id": self.env.company.id,
            })],
        })
        order = self._order(vendor_id=self.vendor.id, purchase_currency_id=foreign.id, cost=1800.0)
        self.assertEqual(order.order_line[0].travel_cost, 900.0)
        self.assertEqual(order.order_line[0].price_tax, 15.0)

    def test_margin_tax_must_be_percent_excluded(self):
        """A tax on margin cannot be a fixed amount or included in the price."""
        with self.assertRaises(ValidationError):
            self.env["account.tax"].create({
                "name": "Fixed on margin",
                "amount": 10.0,
                "amount_type": "fixed",
                "type_tax_use": "sale",
                "travel_margin_tax": True,
            })
        with self.assertRaises(ValidationError):
            self.margin_tax.price_include_override = "tax_included"
