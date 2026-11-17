"""Tests for record access: agents see their own applications, administrators see all."""
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import TravelCommon


@tagged("post_install", "-at_install")
class TestAccess(TravelCommon):
    """Each agent works on their own applications only."""

    @classmethod
    def setUpClass(cls):
        """Create a second agent with an application and a line of their own."""
        super().setUpClass()
        cls.other_agent = new_test_user(
            cls.env, login="travel_agent_2", groups="travel_application.group_travel_agent",
        )
        cls.mine = cls._application_of(cls.agent)
        cls.theirs = cls._application_of(cls.other_agent)

    @classmethod
    def _application_of(cls, agent):
        """Create an application with one line, for the given agent."""
        application = cls.env["travel.application"].create({
            "partner_id": cls.client.id,
            "user_id": agent.id,
        })
        cls.env["travel.application.line"].create({
            "application_id": application.id,
            "passenger_name": "Sara Haddad",
            "product_id": cls.transfer.id,
        })
        return application

    def test_agent_sees_only_own_applications(self):
        """Searching as an agent finds their applications, never another agent's."""
        found = self.env["travel.application"].with_user(self.agent).search([])
        self.assertIn(self.mine, found)
        self.assertNotIn(self.theirs, found)

    def test_agent_cannot_open_other_application(self):
        """Reading another agent's application is refused."""
        with self.assertRaises(AccessError):
            self.theirs.with_user(self.agent).read(["name"])

    def test_agent_cannot_open_other_lines(self):
        """Another agent's lines are hidden too."""
        lines = self.env["travel.application.line"].with_user(self.agent).search([])
        self.assertIn(self.mine.line_ids, lines)
        self.assertNotIn(self.theirs.line_ids, lines)
        with self.assertRaises(AccessError):
            self.theirs.line_ids.with_user(self.agent).read(["passenger_name"])

    def test_admin_sees_all(self):
        """Administrators see every agent's applications."""
        found = self.env["travel.application"].with_user(self.admin).search([])
        self.assertIn(self.mine, found)
        self.assertIn(self.theirs, found)
