"""Shared setup for the Travel Applications tests."""
from odoo.tests import TransactionCase, new_test_user


class TravelCommon(TransactionCase):
    """Default stages with their switches, two services, a vendor, users and a client."""

    @classmethod
    def setUpClass(cls):
        """Create the records every test needs."""
        super().setUpClass()
        cls.stage_new = cls.env.ref("travel_application.stage_new")
        cls.stage_gathering = cls.env.ref("travel_application.stage_data_gathering")
        cls.stage_in_progress = cls.env.ref("travel_application.stage_in_progress")
        cls.stage_done = cls.env.ref("travel_application.stage_done")
        cls.stage_canceled = cls.env.ref("travel_application.stage_canceled")
        # Stage switches, set explicitly so the tests do not depend on the database's settings.
        cls.stage_new.lines_editable = True
        cls.stage_in_progress.lines_must_be_done = True
        cls.stage_canceled.is_cancel = True

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
        cls.client = cls.env["res.partner"].create({"name": "Paying Client"})
        cls.agent = new_test_user(
            cls.env, login="travel_agent", groups="travel_application.group_travel_agent",
        )
        cls.admin = new_test_user(
            cls.env, login="travel_admin", groups="travel_application.group_travel_admin",
        )

    def _application(self, **vals):
        """Create an application for the test client, in the first stage."""
        return self.env["travel.application"].create({"partner_id": self.client.id, **vals})

    def _line(self, application, product, **vals):
        """Create a line on an application."""
        return self.env["travel.application.line"].create({
            "application_id": application.id,
            "passenger_name": "Sara Haddad",
            "product_id": product.id,
            **vals,
        })
