"""Sales order lines created from application lines."""
from odoo import fields, models


class SaleOrderLine(models.Model):
    """An order line remembers the application line it was created from."""

    _inherit = "sale.order.line"

    travel_line_id = fields.Many2one(
        "travel.application.line",
        string="Application Line",
        readonly=True,
        copy=False,
        index="btree_not_null",
    )
