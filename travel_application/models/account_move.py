"""Invoices: margin taxes use the cost carried by each invoice line."""
from odoo import models


class AccountMove(models.Model):
    """Feed each invoice line's cost to the taxes computation."""

    _inherit = "account.move"

    def _prepare_product_base_line_for_taxes_computation(self, product_line):
        """Tax invoice lines on their margin when their taxes say so."""
        base_line = super()._prepare_product_base_line_for_taxes_computation(product_line)
        if self.is_invoice(include_receipts=True) and product_line.travel_cost:
            self.env["account.tax"]._travel_apply_margin(base_line, product_line.travel_cost)
        return base_line
