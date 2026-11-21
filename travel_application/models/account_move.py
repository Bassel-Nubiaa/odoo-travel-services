"""Journal entries: margin taxes on invoices, and the partners' running balances."""
from odoo import _, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    """Feed invoice costs to the taxes, and keep running balances in step with posting."""

    _inherit = "account.move"

    def _prepare_product_base_line_for_taxes_computation(self, product_line):
        """Tax invoice lines on their margin when their taxes say so."""
        base_line = super()._prepare_product_base_line_for_taxes_computation(product_line)
        if self.is_invoice(include_receipts=True) and product_line.travel_cost:
            self.env["account.tax"]._travel_apply_margin(base_line, product_line.travel_cost)
        return base_line

    def write(self, vals):
        """Recompute the running balances when entries are posted or reset to draft."""
        result = super().write(vals)
        if "state" in vals:
            lines = self.line_ids
            lines.filtered(
                lambda line: not line.travel_in_balance and line.travel_balance
            ).with_context(travel_skip_balance=True).write({"travel_balance": 0.0})
            lines._travel_recompute_from_lines()
        return result

    def button_draft(self):
        """Only system administrators reset entries that count in a running balance."""
        if (
            not self.env.user.has_group("base.group_system")
            and self.line_ids.filtered("travel_in_balance")
        ):
            raise UserError(_(
                "These entries count in the partners' running balances. "
                "Only a system administrator can reset them to draft."
            ))
        return super().button_draft()
