"""Build the running balances on databases installed before they existed."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Rebuild every running balance once."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["account.move.line"]._travel_recompute_all()
