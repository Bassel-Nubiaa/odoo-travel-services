"""Purchase order lines created from application lines."""
from odoo import fields, models


class PurchaseOrderLine(models.Model):
    """A purchase line remembers the application line it was created from."""

    _inherit = "purchase.order.line"

    travel_line_id = fields.Many2one(
        "travel.application.line",
        string="Application Line",
        readonly=True,
        copy=False,
        index="btree_not_null",
    )
