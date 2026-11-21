"""Invoice lines carry the cost of the service they invoice."""
from odoo import api, fields, models


class AccountMoveLine(models.Model):
    """The cost of an invoice line, for taxes on the margin."""

    _inherit = "account.move.line"

    travel_cost = fields.Monetary(
        string="Cost",
        currency_field="currency_id",
        copy=True,
        help="Cost of one unit, in the invoice currency, copied from the sales order line. "
             "Taxes on margin apply to the price minus this cost.",
    )

    @api.depends("travel_cost")
    def _compute_totals(self):
        """Recompute the line totals when the cost changes."""
        return super()._compute_totals()
