"""Set the stage switches on databases installed before they existed.

The default stages are loaded with noupdate, so an update does not rewrite them; this
migration sets the new switches once, on the stages that still exist.
"""
from odoo import SUPERUSER_ID, api

STAGE_SWITCHES = {
    "travel_application.stage_new": "lines_editable",
    "travel_application.stage_in_progress": "lines_must_be_done",
    "travel_application.stage_canceled": "is_cancel",
}


def migrate(cr, version):
    """Turn on each default stage's switch."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, field_name in STAGE_SWITCHES.items():
        stage = env.ref(xmlid, raise_if_not_found=False)
        if stage:
            stage[field_name] = True
