"""Application lines: one service for one passenger."""
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Fields each category switch makes required before a line can be Done.
PASSPORT_FIELDS = ("passport_number", "passport_photo")
FLIGHT_FIELDS = (
    "flight_number", "seat_number", "ticket_number", "pnr",
    "departure_datetime", "arrival_datetime",
)
STAY_FIELDS = ("check_in", "check_out")

# Fields that set the prices and their order; locked outside stages where lines are editable.
PRICE_FIELDS = {
    "product_id", "price_unit", "vendor_id", "purchase_currency_id", "cost", "sequence",
}


class TravelApplicationLine(models.Model):
    """One service of an application, edited in its own form."""

    _name = "travel.application.line"
    _description = "Application Line"
    _order = "application_id, sequence, id"
    _rec_name = "passenger_name"

    application_id = fields.Many2one(
        "travel.application", required=True, ondelete="cascade", index=True,
    )
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(related="application_id.company_id", store=True)
    application_editable = fields.Boolean(related="application_id.stage_id.lines_editable")
    purchase_line_ids = fields.One2many(
        "purchase.order.line", "travel_line_id", string="Purchase Order Lines", readonly=True,
    )
    company_currency_id = fields.Many2one(related="company_id.currency_id")
    currency_id = fields.Many2one(related="application_id.currency_id", string="Sales Currency")
    state = fields.Selection(
        [("draft", "Draft"), ("gathering", "Gathering Info"), ("done", "Done")],
        string="Status",
        required=True,
        default="draft",
        copy=False,
    )

    # Service and passenger
    passenger_name = fields.Char(string="Customer / Passenger", required=True)
    product_id = fields.Many2one(
        "product.product",
        string="Service",
        required=True,
        domain="[('sale_ok', '=', True)]",
    )
    requires_passport = fields.Boolean(related="product_id.categ_id.travel_requires_passport")
    flight_details = fields.Boolean(related="product_id.categ_id.travel_flight_details")
    stay_dates = fields.Boolean(related="product_id.categ_id.travel_stay_dates")
    notes = fields.Text(string="Agent Notes")

    # Prices: filled from the service once, then editable
    price_unit = fields.Monetary(
        string="Sales Price",
        currency_field="currency_id",
        compute="_compute_price_unit",
        store=True,
        readonly=False,
        precompute=True,
    )
    vendor_id = fields.Many2one(
        "res.partner",
        string="Vendor",
        help="Leave empty when the agency provides the service itself.",
    )
    purchase_currency_id = fields.Many2one("res.currency", string="Purchase Currency")
    cost_currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_cost_currency_id",
        help="The purchase currency, or the company currency when there is no vendor.",
    )
    cost = fields.Monetary(
        string="Purchase Price",
        currency_field="cost_currency_id",
        compute="_compute_cost",
        store=True,
        readonly=False,
        precompute=True,
    )

    # Both prices in the company currency, converted when a price or currency changes
    price_company = fields.Monetary(
        string="Sales Price (Company Currency)",
        currency_field="company_currency_id",
        compute="_compute_company_amounts",
        store=True,
    )
    cost_company = fields.Monetary(
        string="Purchase Price (Company Currency)",
        currency_field="company_currency_id",
        compute="_compute_company_amounts",
        store=True,
    )

    # Passport
    passport_number = fields.Char()
    passport_photo = fields.Image(max_width=1024, max_height=1024)

    # Flight
    flight_number = fields.Char()
    seat_number = fields.Char()
    ticket_number = fields.Char()
    pnr = fields.Char(string="PNR", help="Passenger Name Record: the airline booking reference.")
    departure_from = fields.Char(string="From")
    arrival_to = fields.Char(string="To")
    departure_datetime = fields.Datetime(string="Departure")
    arrival_datetime = fields.Datetime(string="Arrival")

    # Stay
    check_in = fields.Date()
    check_out = fields.Date()

    # Any other service
    service_date = fields.Date()

    # ------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------

    @api.depends("product_id")
    def _compute_price_unit(self):
        """Fill the sales price from the service, in the application's sales currency."""
        for line in self:
            line.price_unit = line._from_company_currency(
                line.product_id.lst_price, line.currency_id,
            )

    @api.depends("purchase_currency_id", "company_id")
    def _compute_cost_currency_id(self):
        """Use the purchase currency, or the company currency without a vendor."""
        for line in self:
            line.cost_currency_id = line.purchase_currency_id or line.company_id.currency_id

    @api.depends("product_id", "purchase_currency_id")
    def _compute_cost(self):
        """Fill the purchase price from the service cost, in the cost currency."""
        for line in self:
            line.cost = line._from_company_currency(
                line.product_id.standard_price, line.cost_currency_id,
            )

    def _from_company_currency(self, amount, currency):
        """Convert an amount from the company currency at today's rate."""
        self.ensure_one()
        company = self.company_id or self.env.company
        if not currency or currency == company.currency_id:
            return amount
        return company.currency_id._convert(
            amount, currency, company, fields.Date.context_today(self),
        )


    @api.depends("price_unit", "cost", "currency_id", "purchase_currency_id")
    def _compute_company_amounts(self):
        """Convert both prices to the company currency at today's rate."""
        for line in self:
            line.price_company = line._to_company_currency(line.price_unit, line.currency_id)
            line.cost_company = line._to_company_currency(line.cost, line.cost_currency_id)

    def _to_company_currency(self, amount, currency):
        """Convert an amount to the company currency at today's rate."""
        self.ensure_one()
        company = self.company_id or self.env.company
        if not currency or currency == company.currency_id:
            return amount
        return currency._convert(
            amount, company.currency_id, company, fields.Date.context_today(self),
        )

    # ------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------

    @api.constrains("vendor_id", "purchase_currency_id")
    def _check_purchase_currency(self):
        """A line bought from a vendor needs its purchase currency."""
        for line in self:
            if line.vendor_id and not line.purchase_currency_id:
                raise ValidationError(_(
                    "%(passenger)s: set the purchase currency for vendor %(vendor)s.",
                    passenger=line.passenger_name,
                    vendor=line.vendor_id.display_name,
                ))

    @api.constrains("departure_datetime", "arrival_datetime", "check_in", "check_out")
    def _check_date_order(self):
        """Arrival comes after departure, check-out after check-in."""
        for line in self:
            if (line.departure_datetime and line.arrival_datetime
                    and line.arrival_datetime < line.departure_datetime):
                raise ValidationError(_("%s: arrival is before departure.", line.passenger_name))
            if line.check_in and line.check_out and line.check_out < line.check_in:
                raise ValidationError(_("%s: check-out is before check-in.", line.passenger_name))

    @api.constrains("state", *PASSPORT_FIELDS, *FLIGHT_FIELDS, *STAY_FIELDS)
    def _check_done_requirements(self):
        """A Done line has every detail its service category requires."""
        for line in self.filtered(lambda line: line.state == "done"):
            missing = [
                line._fields[name].string
                for name in line._get_required_fields()
                if not line[name]
            ]
            if missing:
                raise ValidationError(_(
                    "%(passenger)s cannot be Done. Missing: %(fields)s.",
                    passenger=line.passenger_name,
                    fields=", ".join(missing),
                ))

    def _get_required_fields(self):
        """Return the field names this line's service category requires."""
        self.ensure_one()
        required = []
        if self.requires_passport:
            required += PASSPORT_FIELDS
        if self.flight_details:
            required += FLIGHT_FIELDS
        if self.stay_dates:
            required += STAY_FIELDS
        return required

    # ------------------------------------------------------------
    # Sales order
    # ------------------------------------------------------------

    def _prepare_sale_order_line_vals(self):
        """Return the values of this line's sales order line."""
        self.ensure_one()
        return {
            "product_id": self.product_id.id,
            "name": self._get_sale_description(),
            "product_uom_qty": 1.0,
            "price_unit": self.price_unit,
            "discount": 0.0,
            "travel_line_id": self.id,
            "travel_cost": self._get_cost_in_sales_currency(),
        }

    def _get_cost_in_sales_currency(self):
        """Return the purchase price converted to the sales currency at today's rate."""
        self.ensure_one()
        if self.cost_currency_id == self.currency_id:
            return self.cost
        return self.cost_currency_id._convert(
            self.cost,
            self.currency_id,
            self.company_id or self.env.company,
            fields.Date.context_today(self),
        )

    def _prepare_purchase_order_line_vals(self):
        """Return the values of this line's purchase order line: its cost, without taxes."""
        self.ensure_one()
        return {
            "product_id": self.product_id.id,
            "name": self._get_sale_description(),
            "product_qty": 1.0,
            "price_unit": self.cost,
            "taxes_id": [Command.set([])],
            "travel_line_id": self.id,
        }

    def _is_purchased(self):
        """Return True when the line is on a purchase order that is not cancelled."""
        self.ensure_one()
        return any(
            purchase_line.order_id.state != "cancel" for purchase_line in self.purchase_line_ids
        )

    def _get_sale_description(self):
        """Describe the line: the service, the passenger, then every required detail."""
        self.ensure_one()
        details = [self.passenger_name] + [
            self._format_detail(name)
            for name in self._get_required_fields()
            if name != "passport_photo" and self[name]
        ]
        return "%s: %s" % (self.product_id.name, ", ".join(details))

    def _format_detail(self, field_name):
        """Return a detail as text; date-times in the user's time zone."""
        self.ensure_one()
        value = self[field_name]
        if self._fields[field_name].type == "datetime":
            return fields.Datetime.context_timestamp(self, value).strftime("%Y-%m-%d %H:%M")
        return str(value)

    # ------------------------------------------------------------
    # Locks: Done lines, and lines outside editable stages
    # ------------------------------------------------------------

    def _is_travel_admin(self):
        """Return True for application administrators."""
        return self.env.user.has_group("travel_application.group_travel_admin")

    def _check_application_editable(self):
        """Refuse when an application's stage does not allow line changes."""
        locked = self.application_id.filtered(
            lambda application: not application.stage_id.lines_editable
        )
        if locked:
            raise UserError(_(
                "%(app)s is in %(stage)s: lines can no longer be added, removed or repriced. "
                "An administrator can move it back to an editable stage.",
                app=locked[0].name,
                stage=locked[0].stage_id.name,
            ))

    @api.model_create_multi
    def create(self, vals_list):
        """New lines only in stages where lines are editable."""
        lines = super().create(vals_list)
        lines._check_application_editable()
        return lines

    def write(self, vals):
        """Done lines are read-only; prices are locked outside editable stages."""
        done_lines = self.filtered(lambda line: line.state == "done")
        if done_lines:
            reopening = set(vals) == {"state"} and vals["state"] != "done"
            if not (reopening and self._is_travel_admin()):
                raise UserError(_("Done lines cannot be changed."))
        if PRICE_FIELDS & vals.keys():
            self._check_application_editable()
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_locked(self):
        """Done lines, and lines outside editable stages, cannot be deleted."""
        if self.filtered(lambda line: line.state == "done"):
            raise UserError(_("Done lines cannot be deleted."))
        self._check_application_editable()
