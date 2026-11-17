"""Sales orders created from travel applications."""
from odoo import fields, models


class SaleOrder(models.Model):
    """A sales order remembers the application it was created from."""

    _inherit = "sale.order"

    travel_application_id = fields.Many2one(
        "travel.application",
        string="Travel Application",
        readonly=True,
        copy=False,
        index="btree_not_null",
    )
