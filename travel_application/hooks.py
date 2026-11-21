"""Installation hooks of the Travel Applications module."""


def post_init_hook(env):
    """Build the running balances of the journal items that already exist."""
    env["account.move.line"]._travel_recompute_all()
