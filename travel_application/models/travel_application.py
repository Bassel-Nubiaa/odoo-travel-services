"""Travel applications: one customer request, made of one or more services."""
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

# Header fields that change the prices or balances of the lines; locked outside editable stages.
LOCKED_HEADER_FIELDS = {"partner_id", "currency_id"}
# Only administrators see the overview figures.
ADMIN_GROUP = "travel_application.group_travel_admin"


class TravelApplication(models.Model):
    """A request from a paying client, followed through the application stages."""

    _name = "travel.application"
    _description = "Application"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(
        string="Reference",
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _("New"),
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Paying Client",
        required=True,
        tracking=True,
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Responsible Agent",
        default=lambda self: self.env.user,
        tracking=True,
        domain="[('share', '=', False)]",
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Sales Currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
        tracking=True,
    )
    stage_id = fields.Many2one(
        "travel.application.stage",
        string="Stage",
        required=True,
        tracking=True,
        index=True,
        ondelete="restrict",
        copy=False,
        default=lambda self: self._default_stage_id(),
        group_expand="_read_group_stage_ids",
    )
    lines_editable = fields.Boolean(related="stage_id.lines_editable")
    line_ids = fields.One2many(
        "travel.application.line", "application_id", string="Details", copy=True,
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        string="Sales Order",
        readonly=True,
        copy=False,
        index="btree_not_null",
        ondelete="set null",
    )
    can_create_orders = fields.Boolean(compute="_compute_can_create_orders")

    # Overview: administrators only, in the company currency
    company_currency_id = fields.Many2one(related="company_id.currency_id")
    vendor_count = fields.Integer(
        string="Number of Vendors",
        compute="_compute_overview",
        store=True,
        groups=ADMIN_GROUP,
    )
    amount_sales = fields.Monetary(
        string="Total Sales",
        currency_field="company_currency_id",
        compute="_compute_overview",
        store=True,
        groups=ADMIN_GROUP,
    )
    amount_purchases = fields.Monetary(
        string="Total Purchases",
        currency_field="company_currency_id",
        compute="_compute_overview",
        store=True,
        groups=ADMIN_GROUP,
    )
    amount_profit = fields.Monetary(
        string="Profit",
        currency_field="company_currency_id",
        compute="_compute_overview",
        store=True,
        groups=ADMIN_GROUP,
    )

    # ------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------

    @api.model
    def _default_stage_id(self):
        """Return the first stage."""
        return self.env["travel.application.stage"].search([], limit=1)

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        """Show every stage as a kanban column, even when it has no application."""
        return stages.search([])

    # ------------------------------------------------------------
    # Overview
    # ------------------------------------------------------------

    @api.depends("line_ids.vendor_id", "line_ids.price_company", "line_ids.cost_company")
    def _compute_overview(self):
        """Count the vendors and add up the lines in the company currency."""
        for application in self:
            lines = application.line_ids
            application.vendor_count = len(lines.vendor_id)
            application.amount_sales = sum(lines.mapped("price_company"))
            application.amount_purchases = sum(lines.mapped("cost_company"))
            application.amount_profit = application.amount_sales - application.amount_purchases

    # ------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Give each new application the next reference of its company's sequence."""
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                company = self.env["res.company"].browse(vals.get("company_id")) or self.env.company
                vals["name"] = (
                    self.env["ir.sequence"].with_company(company).next_by_code("travel.application")
                    or _("New")
                )
        return super().create(vals_list)

    def write(self, vals):
        """Check the stage rules and the header lock before saving."""
        if "stage_id" in vals:
            new_stage = self.env["travel.application.stage"].browse(vals["stage_id"])
            for application in self:
                application._check_stage_change(new_stage)
        if LOCKED_HEADER_FIELDS & vals.keys():
            locked = self.filtered(lambda application: not application.stage_id.lines_editable)
            if locked:
                raise UserError(_(
                    "%s: the paying client and the sales currency can only change in a stage "
                    "where lines are editable.",
                    locked[0].name,
                ))
        return super().write(vals)

    # ------------------------------------------------------------
    # Stage rules
    # ------------------------------------------------------------

    def _is_travel_admin(self):
        """Return True for application administrators."""
        return self.env.user.has_group("travel_application.group_travel_admin")

    def _check_stage_change(self, new_stage):
        """Agents only move forward; open lines block the stages that need them Done."""
        self.ensure_one()
        if new_stage == self.stage_id:
            return
        stages = self.env["travel.application.stage"].search([])
        current_position = stages.ids.index(self.stage_id.id)
        new_position = stages.ids.index(new_stage.id)
        if new_position < current_position:
            if not self._is_travel_admin():
                raise UserError(_(
                    "%s: only an administrator can move an application back.", self.name,
                ))
            return
        if new_stage.is_cancel:
            return
        # The stages this move enters or passes, the new one included.
        crossed = stages[current_position + 1:new_position + 1]
        if any(crossed.mapped("lines_must_be_done")):
            self._check_lines_done(new_stage)

    def _check_lines_done(self, new_stage):
        """Refuse the move while the application has no line or open lines."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_(
                "%(app)s cannot move to %(stage)s without any line.",
                app=self.name, stage=new_stage.name,
            ))
        open_lines = self.line_ids.filtered(lambda line: line.state != "done")
        if open_lines:
            raise UserError(_(
                "%(app)s cannot move to %(stage)s. Set these lines to Done first: %(lines)s.",
                app=self.name,
                stage=new_stage.name,
                lines=", ".join(open_lines.mapped("passenger_name")),
            ))

    # ------------------------------------------------------------
    # Sales order
    # ------------------------------------------------------------

    @api.depends("stage_id")
    def _compute_can_create_orders(self):
        """Orders are created from the first stage whose lines must be Done onwards.

        Cancellation stages never allow orders, wherever they sit in the sequence.
        """
        stages = self.env["travel.application.stage"].search([])
        first = stages.filtered("lines_must_be_done")[:1]
        first_position = stages.ids.index(first.id) if first else len(stages)
        for application in self:
            stage = application.stage_id._origin
            application.can_create_orders = bool(
                stage
                and not stage.is_cancel
                and stages.ids.index(stage.id) >= first_position
            )

    def action_create_sale_order(self):
        """Create the application's sales order, one order line per application line."""
        self.ensure_one()
        if self.sale_order_id:
            raise UserError(_("%s already has a sales order.", self.name))
        if not self.can_create_orders:
            raise UserError(_(
                "%(app)s is in %(stage)s: orders are created once every line is Done "
                "and the application has moved on.",
                app=self.name, stage=self.stage_id.name,
            ))
        self._check_lines_ready_for_orders()
        self.sale_order_id = self.env["sale.order"].create(self._prepare_sale_order_vals())
        return self.action_view_sale_order()

    def action_view_sale_order(self):
        """Open the application's sales order."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Sales Order"),
            "res_model": "sale.order",
            "res_id": self.sale_order_id.id,
            "view_mode": "form",
            "views": [(False, "form")],
        }

    def _check_lines_ready_for_orders(self):
        """Refuse orders while the application has no line or open lines."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("%s has no lines to order.", self.name))
        open_lines = self.line_ids.filtered(lambda line: line.state != "done")
        if open_lines:
            raise UserError(_(
                "%(app)s: set these lines to Done before creating orders: %(lines)s.",
                app=self.name,
                lines=", ".join(open_lines.mapped("passenger_name")),
            ))

    def _prepare_sale_order_vals(self):
        """Return the values of the sales order: the paying client, in the sales currency."""
        self.ensure_one()
        return {
            "partner_id": self.partner_id.id,
            "company_id": self.company_id.id,
            "user_id": self.user_id.id,
            "pricelist_id": self._get_sale_pricelist().id,
            "origin": self.name,
            "travel_application_id": self.id,
            "order_line": [
                Command.create(line._prepare_sale_order_line_vals()) for line in self.line_ids
            ],
        }

    def _get_sale_pricelist(self):
        """Return a pricelist in the sales currency, since it sets the order's currency.

        The client's own pricelist comes first. In the company currency an order needs
        no pricelist; in any other currency, a missing pricelist is reported.
        """
        self.ensure_one()
        client_pricelist = self.partner_id.with_company(self.company_id).property_product_pricelist
        if client_pricelist.currency_id == self.currency_id:
            return client_pricelist
        pricelist = self.env["product.pricelist"].search([
            ("currency_id", "=", self.currency_id.id),
            ("company_id", "in", [self.company_id.id, False]),
        ], limit=1)
        if not pricelist and self.currency_id != self.company_id.currency_id:
            raise UserError(_(
                "No pricelist in %(currency)s. Create one in Sales > Products > Pricelists "
                "to sell %(app)s in that currency.",
                currency=self.currency_id.name, app=self.name,
            ))
        return pricelist
