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
