"""Tests for the Overview tab: vendors, totals and profit in the company currency."""
from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import TravelCommon


@tagged("post_install", "-at_install")
class TestOverview(TravelCommon):
    """The overview adds the lines up in the company currency, for administrators only."""

    @classmethod
    def setUpClass(cls):
        """Create a second vendor and a foreign currency worth half the company currency."""
        super().setUpClass()
        cls.company_currency = cls.env.company.currency_id
        cls.other_vendor = cls.env["res.partner"].create({"name": "Second Travel Office"})
        # Rates are relative to a base currency, which need not be the company currency:
        # read the company currency's raw rate, then give the test currency twice that,
        # so 2 units of it are worth 1 unit of the company currency on any database.
        today = fields.Date.today()
        company_rate = cls.company_currency._get_rates(cls.env.company, today)[
            cls.company_currency.id
        ]
        cls.foreign = cls.env["res.currency"].create({
            "name": "TST",
            "symbol": "T$",
            "rate_ids": [Command.create({
                "name": today,
                "rate": 2.0 * company_rate,
                "company_id": cls.env.company.id,
            })],
        })

    def _bought_line(self, application, product, vendor, currency, **vals):
        """Create a line bought from a vendor in the given purchase currency."""
        return self._line(
            application, product,
            vendor_id=vendor.id, purchase_currency_id=currency.id, **vals,
        )

    def test_totals_and_profit(self):
        """Sales, purchases and profit add up the lines."""
        application = self._application()
        self._bought_line(application, self.flight, self.vendor, self.company_currency)
        self._line(application, self.transfer)
        self.assertEqual(application.amount_sales, 1350.0)
        self.assertEqual(application.amount_purchases, 1000.0)
        self.assertEqual(application.amount_profit, 350.0)

    def test_vendors_counted_once(self):
        """A vendor with several lines counts once; lines without a vendor do not count."""
        application = self._application()
        self._bought_line(application, self.flight, self.vendor, self.company_currency)
        self._bought_line(application, self.transfer, self.vendor, self.company_currency)
        self._bought_line(application, self.transfer, self.other_vendor, self.company_currency)
        self._line(application, self.transfer)
        self.assertEqual(application.vendor_count, 2)

    def test_foreign_purchase_currency(self):
        """A purchase price in another currency is converted to the company currency."""
        application = self._application()
        line = self._bought_line(
            application, self.transfer, self.vendor, self.foreign, cost=200.0,
        )
        self.assertEqual(line.cost_company, 100.0)
        self.assertEqual(application.amount_purchases, 100.0)

    def test_foreign_sales_currency(self):
        """Sales prices in another sales currency are converted back to the company currency."""
        application = self._application(currency_id=self.foreign.id)
        line = self._line(application, self.transfer)
        self.assertEqual(line.price_unit, 300.0)
        self.assertEqual(application.amount_sales, 150.0)

    def test_follows_price_changes(self):
        """Changing a price in New updates the overview."""
        application = self._application()
        line = self._line(application, self.transfer)
        line.price_unit = 400.0
        self.assertEqual(application.amount_sales, 400.0)
        self.assertEqual(application.amount_profit, 300.0)

    def test_loss_shown_as_negative_profit(self):
        """Selling below cost gives a negative profit."""
        application = self._application()
        self._line(application, self.transfer, price_unit=80.0)
        self.assertEqual(application.amount_profit, -20.0)

    def test_agents_cannot_read_overview(self):
        """The overview figures are hidden from agents."""
        application = self._application()
        with self.assertRaises(AccessError):
            application.with_user(self.agent).read(["amount_profit"])
        figures = application.with_user(self.admin).read(["amount_profit"])
        self.assertIn("amount_profit", figures[0])
