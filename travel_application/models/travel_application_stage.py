"""Stages of travel applications."""
from odoo import fields, models


class TravelApplicationStage(models.Model):
    """A step of the application workflow; administrators rename, reorder and add them."""

    _name = "travel.application.stage"
    _description = "Application Stage"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(
        string="Folded in Kanban",
        help="Show this stage as a narrow column in the kanban view.",
    )
    lines_editable = fields.Boolean(
        help="In this stage, lines can be added or removed, and their prices, services, "
             "vendors and currencies changed.",
    )
    lines_must_be_done = fields.Boolean(
        string="Lines Must Be Done",
        help="Entering this stage, or moving past it, requires every line to be Done.",
    )
    is_cancel = fields.Boolean(
        string="Cancellation",
        help="Applications can always be moved to this stage, even with open lines.",
    )
