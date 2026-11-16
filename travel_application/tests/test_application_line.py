"""Tests for application lines: prices, required details and the Done lock."""
import base64

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

# A 1x1 PNG, enough to fill an image field.
PIXEL = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c49444154785e63502ac8020001b400fd69dba8530000000049454e44ae426082"
))


@tagged("post_install", "-at_install")
class TestApplicationLine(TransactionCase):
    """Lines take their prices from the service and lock once Done."""

    @classmethod
    def setUpClass(cls):
        """Create a flight service, a visa service, a vendor and an application."""
        super().setUpClass()
        Category = cls.env["product.category"]
        Product = cls.env["product.product"]
        cls.flight = Product.create({
            "name": "Flight Ticket",
            "type": "service",
            "list_price": 1200.0,
            "standard_price": 900.0,
            "categ_id": Category.create({
                "name": "Flights",
                "travel_requires_passport": True,
                "travel_flight_details": True,
            }).id,
        })
        cls.transfer = Product.create({
            "name": "Airport Transfer",
            "type": "service",
            "list_price": 150.0,
            "standard_price": 100.0,
            "categ_id": Category.create({"name": "Transfers"}).id,
        })
        cls.vendor = cls.env["res.partner"].create({"name": "Partner Travel Office"})
        cls.agent = new_test_user(
            cls.env, login="line_agent", groups="travel_application.group_travel_agent",
        )
        cls.application = cls.env["travel.application"].create({
            "partner_id": cls.env["res.partner"].create({"name": "Paying Client"}).id,
        })

    def _line(self, product, **vals):
        """Create a line of the test application."""
        return self.env["travel.application.line"].create({
            "application_id": self.application.id,
            "passenger_name": "Sara Haddad",
            "product_id": product.id,
            **vals,
        })

    def _flight_details(self):
        """Return every detail a flight line needs before it is Done."""
        return {
            "passport_number": "N1234567",
            "passport_photo": PIXEL,
            "flight_number": "EK 912",
            "seat_number": "14C",
            "ticket_number": "176-2412345678",
            "pnr": "K7XQ2M",
            "departure_datetime": "2026-12-01 08:00:00",
            "arrival_datetime": "2026-12-01 11:30:00",
        }

    def test_prices_from_service(self):
        """The sales price and purchase price come from the service."""
        line = self._line(self.flight)
        self.assertEqual(line.price_unit, 1200.0)
        self.assertEqual(line.cost, 900.0)

    def test_prices_editable(self):
        """Both prices stay editable after they are filled."""
        line = self._line(self.flight)
        line.write({"price_unit": 1350.0, "cost": 950.0})
        self.assertEqual(line.price_unit, 1350.0)
        self.assertEqual(line.cost, 950.0)

    def test_vendor_needs_purchase_currency(self):
        """A vendor without a purchase currency is refused."""
        with self.assertRaises(ValidationError):
            self._line(self.transfer, vendor_id=self.vendor.id)

    def test_done_requires_category_details(self):
        """A flight cannot be Done without its passport and flight details."""
        line = self._line(self.flight)
        with self.assertRaises(ValidationError):
            line.state = "done"

    def test_done_with_all_details(self):
        """With every detail filled, the flight line can be Done."""
        line = self._line(self.flight, **self._flight_details())
        line.state = "done"
        self.assertEqual(line.state, "done")

    def test_service_without_requirements(self):
        """A service whose category has no switches can be Done at once."""
        line = self._line(self.transfer)
        line.state = "done"
        self.assertEqual(line.state, "done")

    def test_arrival_before_departure_refused(self):
        """Arrival cannot be before departure."""
        with self.assertRaises(ValidationError):
            self._line(
                self.flight,
                departure_datetime="2026-12-01 08:00:00",
                arrival_datetime="2026-12-01 07:00:00",
            )

    def test_done_line_locked_for_agent(self):
        """An agent cannot change a Done line."""
        line = self._line(self.transfer)
        line.state = "done"
        with self.assertRaises(UserError):
            line.with_user(self.agent).price_unit = 100.0

    def test_admin_can_reopen_done_line(self):
        """An administrator can set a Done line back, but not change its values."""
        line = self._line(self.transfer)
        line.state = "done"
        with self.assertRaises(UserError):
            line.price_unit = 100.0
        line.state = "gathering"
        self.assertEqual(line.state, "gathering")

    def test_done_line_not_deleted(self):
        """Done lines cannot be deleted."""
        line = self._line(self.transfer)
        line.state = "done"
        with self.assertRaises(UserError):
            line.unlink()
