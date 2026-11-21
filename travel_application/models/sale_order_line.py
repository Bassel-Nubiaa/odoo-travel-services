"""Sales order lines created from application lines."""
from odoo import api, fields, models


class SaleOrderLine(models.Model):
    """An order line remembers its application line and the cost of its service."""

    _inherit = "sale.order.line"

    travel_line_id = fields.Many2one(
        "travel.application.line",
        string="Application Line",
        readonly=True,
        copy=False,
        index="btree_not_null",
    )
    travel_cost = fields.Monetary(
        string="Cost",
        currency_field="currency_id",
        copy=True,
        help="Cost of one unit, in the order currency, from the application line. "
             "Taxes on margin apply to the price minus this cost.",
    )

    @api.depends("travel_cost")
    def _compute_amount(self):
        """Recompute the line amounts when the cost changes."""
        return super()._compute_amount()

    def _prepare_base_line_for_taxes_computation(self, **kwargs):
        """Tax the line on its margin when its taxes say so."""
        base_line = super()._prepare_base_line_for_taxes_computation(**kwargs)
        if self.travel_cost:
            self.env["account.tax"]._travel_apply_margin(base_line, self.travel_cost)
        return base_line

    def _prepare_invoice_line(self, **optional_values):
        """Carry the cost to the invoice line."""
        values = super()._prepare_invoice_line(**optional_values)
        if self.travel_cost and values.get("display_type", "product") == "product":
            values["travel_cost"] = self.travel_cost
        return values
