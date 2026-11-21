"""Journal items: invoice costs, and the partners' running balances."""
from odoo import api, fields, models

# Journals whose items count in a partner's running balance.
BALANCE_JOURNAL_TYPES = ("sale", "purchase", "bank", "cash", "general")
# Receivable and payable items are left out: the other side of each entry is counted instead,
# such as the income of an invoice, the bank of a payment or the opening balance of an opening.
EXCLUDED_ACCOUNT_TYPES = ("asset_receivable", "liability_payable")
# Changes to posted items that move a running balance.
BALANCE_FIELDS = {
    "partner_id", "account_id", "journal_id", "debit", "credit", "balance", "display_type",
}


class AccountMoveLine(models.Model):
    """The cost of an invoice line, and the partner's running balance after each item."""

    _inherit = "account.move.line"

    travel_cost = fields.Monetary(
        string="Cost",
        currency_field="currency_id",
        copy=True,
        help="Cost of one unit, in the invoice currency, copied from the sales order line. "
             "Taxes on margin apply to the price minus this cost.",
    )
    travel_in_balance = fields.Boolean(
        string="Counts in Running Balance",
        compute="_compute_travel_in_balance",
        store=True,
        index=True,
    )
    travel_balance = fields.Monetary(
        string="Running Balance",
        currency_field="company_currency_id",
        readonly=True,
        copy=False,
        aggregator=False,
        help="The partner's balance after this item, in the company currency. Positive reads "
             "Dr (the partner owes us), negative reads Cr (we hold the partner's money).",
    )

    @api.depends("travel_cost")
    def _compute_totals(self):
        """Recompute the line totals when the cost changes."""
        return super()._compute_totals()

    @api.depends(
        "parent_state",
        "partner_id",
        "display_type",
        "journal_id.type",
        "account_id.account_type",
    )
    def _compute_travel_in_balance(self):
        """Posted items of a partner, in the balance journals, outside receivable and payable."""
        for line in self:
            line.travel_in_balance = bool(
                line.parent_state == "posted"
                and line.partner_id
                and line.display_type not in ("line_section", "line_note")
                and line.journal_id.type in BALANCE_JOURNAL_TYPES
                and line.account_id.account_type not in EXCLUDED_ACCOUNT_TYPES
            )

    # ------------------------------------------------------------
    # Keeping the balances in step with posted items
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Items added to posted entries move the balances that follow them."""
        lines = super().create(vals_list)
        if not self.env.context.get("travel_skip_balance"):
            lines.filtered(lambda line: line.parent_state == "posted")._travel_recompute_from_lines()
        return lines

    def write(self, vals):
        """Changes to posted items move the balances that follow them, for old and new partners."""
        if self.env.context.get("travel_skip_balance") or not BALANCE_FIELDS & vals.keys():
            return super().write(vals)
        posted = self.filtered(lambda line: line.parent_state == "posted")
        partners_before = posted.partner_id
        result = super().write(vals)
        if posted:
            self._travel_recompute_balances(partners_before | posted.partner_id, min(posted.ids))
        return result

    def unlink(self):
        """Removing posted items moves the balances that follow them."""
        posted = self.filtered(lambda line: line.parent_state == "posted")
        partners, from_id = posted.partner_id, min(posted.ids, default=0)
        result = super().unlink()
        if posted:
            self._travel_recompute_balances(partners, from_id)
        return result

    def _travel_recompute_from_lines(self):
        """Recompute the balances of these items' partners, from the first of these items."""
        if self:
            self._travel_recompute_balances(self.partner_id, min(self.ids))

    @api.model
    def _travel_recompute_balances(self, partners, from_id=0):
        """Rebuild the running balances of these partners from the item 'from_id' onwards.

        Items count in the order they were registered (by id). Each balance is the previous
        one minus the item's debit, plus its credit, in the company currency.
        """
        if not partners:
            return
        self.flush_model()
        Line = self.with_context(travel_skip_balance=True)
        for partner in partners:
            lines = Line.search(
                [("partner_id", "=", partner.id), ("travel_in_balance", "=", True),
                 ("id", ">=", from_id)],
                order="id",
            )
            for company in lines.company_id:
                previous = Line.search(
                    [("partner_id", "=", partner.id), ("travel_in_balance", "=", True),
                     ("company_id", "=", company.id), ("id", "<", from_id)],
                    order="id desc",
                    limit=1,
                )
                running = previous.travel_balance
                for line in lines.filtered(lambda line: line.company_id == company):
                    running -= line.balance
                    if line.travel_balance != running:
                        line.travel_balance = running

    @api.model
    def _travel_recompute_all(self, company=None):
        """Rebuild every running balance, for one company or for all of them.

        Items that no longer count but still carry a balance are cleared.
        """
        domain = [("travel_in_balance", "=", True)]
        if company:
            domain.append(("company_id", "=", company.id))
        self.flush_model()
        stale_domain = [("travel_in_balance", "=", False), ("travel_balance", "!=", 0.0)]
        if company:
            stale_domain.append(("company_id", "=", company.id))
        self.with_context(travel_skip_balance=True).search(stale_domain).write(
            {"travel_balance": 0.0}
        )
        partners = self.search(domain).partner_id
        self._travel_recompute_balances(partners)
