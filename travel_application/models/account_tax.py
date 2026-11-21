"""Taxes on the margin: VAT on (sales price - cost) instead of the full price."""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountTax(models.Model):
    """A sales tax can be computed on the margin of the line it applies to."""

    _inherit = "account.tax"

    travel_margin_tax = fields.Boolean(
        string="Tax on Margin",
        help="Compute this tax on the line's margin (sales price minus cost), never below "
             "zero. The margin is also the tax base shown on documents and reports. Lines "
             "without a cost are taxed on their full price.",
    )

    @api.constrains("travel_margin_tax", "amount_type", "price_include_override")
    def _check_travel_margin_tax(self):
        """A margin tax is a percentage, added on top of the price."""
        for tax in self.filtered("travel_margin_tax"):
            if tax.amount_type != "percent" or tax.price_include:
                raise ValidationError(_(
                    "%s: a tax on margin must be a percentage, excluded from the price.",
                    tax.name,
                ))

    @api.model
    def _travel_apply_margin(self, base_line, unit_cost):
        """Make the margin the base and the taxed amount of the line's margin taxes.

        Special lines, such as down payments, keep the standard computation.

        :param base_line: a base line from '_prepare_base_line_for_taxes_computation'.
        :param unit_cost: the cost of one unit, in the line's currency.
        :return: the same base line, with 'manual_tax_amounts' set for margin taxes.
        """
        margin_taxes = base_line["tax_ids"].filtered("travel_margin_tax")
        if not margin_taxes or base_line["special_type"]:
            return base_line
        quantity = base_line["quantity"]
        sale_amount = base_line["price_unit"] * (1 - base_line["discount"] / 100.0) * quantity
        margin = max(sale_amount - unit_cost * quantity, 0.0)
        manual_tax_amounts = dict(base_line["manual_tax_amounts"] or {})
        for tax in margin_taxes:
            manual_tax_amounts[str(tax.id)] = {
                "base_amount_currency": margin,
                "tax_amount_currency": margin * tax.amount / 100.0,
            }
        base_line["manual_tax_amounts"] = manual_tax_amounts
        # Odoo takes the untaxed amount from the first tax's base: keep the real one.
        base_line["travel_untaxed_currency"] = sale_amount
        return base_line

    @api.model
    def _add_tax_details_in_base_line(self, base_line, company, rounding_method=None):
        """Keep the full price as the untaxed amount of lines taxed on their margin.

        Odoo sets a line's untaxed amount to the base of its first tax. With the margin as
        that base, the untaxed amount is set back to the line's price here, in both currencies,
        and the total with taxes follows it.
        """
        super()._add_tax_details_in_base_line(base_line, company, rounding_method=rounding_method)
        untaxed = base_line.get("travel_untaxed_currency")
        if untaxed is None:
            return
        round_per_line = (
            (rounding_method or company.tax_calculation_rounding_method) == "round_per_line"
        )
        if round_per_line:
            untaxed = base_line["currency_id"].round(untaxed)
        rate = base_line["rate"]
        untaxed_company = untaxed / rate if rate else 0.0
        if round_per_line:
            untaxed_company = company.currency_id.round(untaxed_company)
        tax_details = base_line["tax_details"]
        for suffix, amount in (("_currency", untaxed), ("", untaxed_company)):
            taxes = (
                tax_details[f"raw_total_included{suffix}"]
                - tax_details[f"raw_total_excluded{suffix}"]
            )
            tax_details[f"raw_total_excluded{suffix}"] = amount
            tax_details[f"raw_total_included{suffix}"] = amount + taxes
