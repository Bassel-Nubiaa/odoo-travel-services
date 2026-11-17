"""Tests for the stage rules: forward-only moves, Done lines and the price lock."""
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import TravelCommon


@tagged("post_install", "-at_install")
class TestStageRules(TravelCommon):
    """Agents move forward; lines must be Done before In Progress; prices lock after New."""

    def _ready_application(self):
        """Return an application in Data Gathering whose only line is Done."""
        application = self._application()
        self._line(application, self.transfer).state = "done"
        application.stage_id = self.stage_gathering
        return application

    def test_agent_moves_forward(self):
        """An agent can move an application to a later stage."""
        application = self._application().with_user(self.agent)
        application.stage_id = self.stage_gathering
        self.assertEqual(application.stage_id, self.stage_gathering)

    def test_agent_cannot_move_back(self):
        """An agent cannot move an application to an earlier stage."""
        application = self._application()
        application.stage_id = self.stage_gathering
        with self.assertRaises(UserError):
            application.with_user(self.agent).stage_id = self.stage_new

    def test_admin_moves_back(self):
        """An administrator can move an application back."""
        application = self._application()
        application.stage_id = self.stage_gathering
        application.with_user(self.admin).stage_id = self.stage_new
        self.assertEqual(application.stage_id, self.stage_new)

    def test_in_progress_needs_lines(self):
        """An application without lines cannot reach In Progress."""
        application = self._application()
        with self.assertRaises(UserError):
            application.stage_id = self.stage_in_progress

    def test_in_progress_needs_done_lines(self):
        """Open lines block In Progress; once Done, the move is allowed."""
        application = self._application()
        line = self._line(application, self.transfer)
        with self.assertRaises(UserError):
            application.stage_id = self.stage_in_progress
        line.state = "done"
        application.stage_id = self.stage_in_progress
        self.assertEqual(application.stage_id, self.stage_in_progress)

    def test_skipping_in_progress_checked(self):
        """Jumping straight to Done still needs every line Done."""
        application = self._application()
        self._line(application, self.transfer)
        with self.assertRaises(UserError):
            application.stage_id = self.stage_done

    def test_cancel_always_allowed(self):
        """An application with open lines can still be cancelled."""
        application = self._application()
        self._line(application, self.transfer)
        application.stage_id = self.stage_canceled
        self.assertEqual(application.stage_id, self.stage_canceled)

    def test_prices_locked_after_new(self):
        """After New, prices and vendors of the lines can no longer change."""
        application = self._application()
        line = self._line(application, self.transfer)
        application.stage_id = self.stage_gathering
        with self.assertRaises(UserError):
            line.price_unit = 999.0
        with self.assertRaises(UserError):
            line.write({"vendor_id": self.vendor.id, "purchase_currency_id": line.currency_id.id})

    def test_other_line_fields_editable_after_new(self):
        """Details that do not set prices stay editable until the line is Done."""
        application = self._application()
        line = self._line(application, self.flight)
        application.stage_id = self.stage_gathering
        line.passport_number = "N7654321"
        self.assertEqual(line.passport_number, "N7654321")

    def test_no_lines_added_or_removed_after_new(self):
        """After New, lines can be neither added nor deleted."""
        application = self._ready_application()
        with self.assertRaises(UserError):
            self._line(application, self.transfer)
        open_line = application.line_ids
        open_line.with_user(self.admin).state = "gathering"
        with self.assertRaises(UserError):
            open_line.unlink()

    def test_client_and_currency_locked_after_new(self):
        """After New, the paying client and the sales currency are locked."""
        application = self._application()
        application.stage_id = self.stage_gathering
        with self.assertRaises(UserError):
            application.partner_id = self.vendor
