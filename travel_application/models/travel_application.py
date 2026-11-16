"""Travel applications: one customer request, made of one or more services."""
from odoo import _, api, fields, models


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

    line_ids = fields.One2many(
        "travel.application.line", "application_id", string="Details", copy=True,
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
