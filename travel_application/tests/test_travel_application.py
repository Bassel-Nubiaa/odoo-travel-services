"""Tests for applications, their references, stages and access."""
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestTravelApplication(TransactionCase):
    """References, default values, stage columns and access levels."""

    @classmethod
    def setUpClass(cls):
        """Create a paying client and an agent user."""
        super().setUpClass()
        cls.client = cls.env["res.partner"].create({"name": "Travel Client"})
        cls.agent = new_test_user(
            cls.env, login="travel_agent", groups="travel_application.group_travel_agent",
        )
        cls.Application = cls.env["travel.application"]

    def test_reference_from_sequence(self):
        """Each new application gets the next APP/ reference."""
        first = self.Application.create({"partner_id": self.client.id})
        second = self.Application.create({"partner_id": self.client.id})
        self.assertTrue(first.name.startswith("APP/"))
        self.assertNotEqual(first.name, second.name)

    def test_defaults(self):
        """A new application starts in the first stage, with its agent and the company currency."""
        application = self.Application.with_user(self.agent).create({"partner_id": self.client.id})
        first_stage = self.env["travel.application.stage"].search([], limit=1)
        self.assertEqual(application.stage_id, first_stage)
        self.assertEqual(application.user_id, self.agent)
        self.assertEqual(application.currency_id, self.env.company.currency_id)

    def test_every_stage_shown_in_kanban(self):
        """Grouping by stage returns every stage, including empty ones."""
        self.Application.create({"partner_id": self.client.id})
        groups = self.Application.read_group([], ["stage_id"], ["stage_id"])
        all_stages = self.env["travel.application.stage"].search([])
        self.assertEqual(len(groups), len(all_stages))

    def test_agent_cannot_delete(self):
        """Agents create and edit applications but cannot delete them."""
        application = self.Application.with_user(self.agent).create({"partner_id": self.client.id})
        with self.assertRaises(AccessError):
            application.with_user(self.agent).unlink()

    def test_agent_cannot_edit_stages(self):
        """Only administrators change the stages."""
        stage = self.env["travel.application.stage"].search([], limit=1)
        with self.assertRaises(AccessError):
            stage.with_user(self.agent).name = "Renamed"
