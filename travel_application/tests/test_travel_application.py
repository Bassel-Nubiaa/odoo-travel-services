"""Tests for applications, their references, stages and access."""
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import TravelCommon


@tagged("post_install", "-at_install")
class TestTravelApplication(TravelCommon):
    """References, default values, stage columns and access levels."""

    def test_reference_from_sequence(self):
        """Each new application gets the next APP/ reference."""
        first = self._application()
        second = self._application()
        self.assertTrue(first.name.startswith("APP/"))
        self.assertNotEqual(first.name, second.name)

    def test_defaults(self):
        """A new application starts in the first stage, with its agent and the company currency."""
        application = self.env["travel.application"].with_user(self.agent).create({
            "partner_id": self.client.id,
        })
        first_stage = self.env["travel.application.stage"].search([], limit=1)
        self.assertEqual(application.stage_id, first_stage)
        self.assertEqual(application.user_id, self.agent)
        self.assertEqual(application.currency_id, self.env.company.currency_id)

    def test_every_stage_shown_in_kanban(self):
        """Grouping by stage returns every stage, including empty ones."""
        self._application()
        groups = self.env["travel.application"].read_group([], ["stage_id"], ["stage_id"])
        all_stages = self.env["travel.application.stage"].search([])
        self.assertEqual(len(groups), len(all_stages))

    def test_agent_cannot_delete(self):
        """Agents create and edit applications but cannot delete them."""
        application = self.env["travel.application"].with_user(self.agent).create({
            "partner_id": self.client.id,
        })
        with self.assertRaises(AccessError):
            application.with_user(self.agent).unlink()

    def test_agent_cannot_edit_stages(self):
        """Only administrators change the stages."""
        with self.assertRaises(AccessError):
            self.stage_new.with_user(self.agent).name = "Renamed"
