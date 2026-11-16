"""Product categories decide which details a travel service needs."""
from odoo import fields, models


class ProductCategory(models.Model):
    """Switches that make application line fields required, per category of service."""

    _inherit = "product.category"

    travel_requires_passport = fields.Boolean(
        string="Requires Passport",
        help="Lines of this service need the passport number and photo before they are Done.",
    )
    travel_flight_details = fields.Boolean(
        string="Flight Details",
        help="Lines of this service need the flight, seat, ticket and PNR before they are Done.",
    )
    travel_stay_dates = fields.Boolean(
        string="Stay Dates",
        help="Lines of this service need check-in and check-out dates before they are Done.",
    )
