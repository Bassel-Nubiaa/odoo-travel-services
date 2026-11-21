"""Tests for the partners' running balances on journal items."""
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .common import TravelCommon


@tagged("post_install", "-at_install")
class TestRunningBalance(TravelCommon):
    """Balance = opening - sum(debit - credit) of the counted items; Cr when negative."""

    @classmethod
    def setUpClass(cls):
        """Create an opening balance account and journal; find the other journals and accounts."""
        super().setUpClass()
        company = cls.env.company
        Journal = cls.env["account.journal"]
        Account = cls.env["account.account"]
        cls.opening_account = Account.create({
            "name": "Opening Balance",
            "code": "TRVOPEN01",
            "account_type": "equity",
        })
        cls.opening_journal = Journal.create({
            "name": "Opening Balances",
            "code": "TOPB",
            "type": "general",
        })
        cls.bank_journal = Journal.search(
            [("type", "=", "bank"), ("company_id", "=", company.id)], limit=1,
        )
        cls.sale_journal = Journal.search(
            [("type", "=", "sale"), ("company_id", "=", company.id)], limit=1,
        )
        cls.purchase_journal = Journal.search(
            [("type", "=", "purchase"), ("company_id", "=", company.id)], limit=1,
        )
        cls.bank_account = cls.bank_journal.default_account_id
        cls.income_account = Account.search(
            [("account_type", "=", "income"), ("company_ids", "in", company.id)], limit=1,
        )
        cls.expense_account = Account.search(
            [("account_type", "=", "expense"), ("company_ids", "in", company.id)], limit=1,
        )
        cls.receivable = cls.client.with_company(company).property_account_receivable_id
        cls.payable = cls.vendor.with_company(company).property_account_payable_id

    def _entry(self, journal, partner, lines, post=True):
        """Create a journal entry for a partner; lines are (account, debit, credit) tuples."""
        move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": journal.id,
            "line_ids": [
                Command.create({
                    "account_id": account.id,
                    "partner_id": partner.id,
                    "debit": debit,
                    "credit": credit,
                })
                for account, debit, credit in lines
            ],
        })
        if post:
            move.action_post()
        return move

    def _balance(self, partner):
        """Return the partner's latest running balance."""
        last = self.env["account.move.line"].search(
            [("partner_id", "=", partner.id), ("travel_in_balance", "=", True)],
            order="id desc",
            limit=1,
        )
        return last.travel_balance

    def _client_opening(self, amount):
        """The client starts with money held by us: Opening Balance Dr / Receivable Cr."""
        return self._entry(self.opening_journal, self.client, [
            (self.opening_account, amount, 0.0),
            (self.receivable, 0.0, amount),
        ])

    def _vendor_opening(self, amount):
        """We start with money held by the vendor: Payable Dr / Opening Balance Cr."""
        return self._entry(self.opening_journal, self.vendor, [
            (self.payable, amount, 0.0),
            (self.opening_account, 0.0, amount),
        ])

    def test_client_example(self):
        """Opening 50 (50 Cr), sale 21 (29 Cr), payment 21 (50 Cr)."""
        self._client_opening(50.0)
        self.assertEqual(self._balance(self.client), -50.0)
        self._entry(self.sale_journal, self.client, [
            (self.receivable, 21.0, 0.0),
            (self.income_account, 0.0, 21.0),
        ])
        self.assertEqual(self._balance(self.client), -29.0)
        self._entry(self.bank_journal, self.client, [
            (self.bank_account, 21.0, 0.0),
            (self.receivable, 0.0, 21.0),
        ])
        self.assertEqual(self._balance(self.client), -50.0)

    def test_vendor_example(self):
        """Opening 100 (100 Dr), purchase 10 (90 Dr), payment 10 (100 Dr)."""
        self._vendor_opening(100.0)
        self.assertEqual(self._balance(self.vendor), 100.0)
        self._entry(self.purchase_journal, self.vendor, [
            (self.expense_account, 10.0, 0.0),
            (self.payable, 0.0, 10.0),
        ])
        self.assertEqual(self._balance(self.vendor), 90.0)
        self._entry(self.bank_journal, self.vendor, [
            (self.payable, 10.0, 0.0),
            (self.bank_account, 0.0, 10.0),
        ])
        self.assertEqual(self._balance(self.vendor), 100.0)

    def test_vat_counts(self):
        """An invoice of 20 + 5% VAT moves the balance by 21."""
        tax = self.env["account.tax"].create({
            "name": "VAT 5%", "amount": 5.0, "amount_type": "percent", "type_tax_use": "sale",
        })
        self._client_opening(50.0)
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.client.id,
            "invoice_line_ids": [Command.create({
                "name": "Visa service",
                "price_unit": 20.0,
                "account_id": self.income_account.id,
                "tax_ids": [Command.set(tax.ids)],
            })],
        })
        invoice.action_post()
        self.assertEqual(self._balance(self.client), -29.0)

    def test_excluded_items(self):
        """Receivable, payable, partnerless and draft items do not count."""
        opening = self._client_opening(50.0)
        receivable_line = opening.line_ids.filtered(lambda line: line.account_id == self.receivable)
        self.assertFalse(receivable_line.travel_in_balance)
        payable_line = self._vendor_opening(100.0).line_ids.filtered(
            lambda line: line.account_id == self.payable
        )
        self.assertFalse(payable_line.travel_in_balance)
        bank_opening = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": self.opening_journal.id,
            "line_ids": [
                Command.create({"account_id": self.bank_account.id, "debit": 500.0}),
                Command.create({"account_id": self.opening_account.id, "credit": 500.0}),
            ],
        })
        bank_opening.action_post()
        self.assertFalse(bank_opening.line_ids.filtered("travel_in_balance"))
        sale = self._entry(self.sale_journal, self.client, [
            (self.receivable, 21.0, 0.0),
            (self.income_account, 0.0, 21.0),
        ], post=False)
        self.assertFalse(sale.line_ids.filtered("travel_in_balance"))
        self.assertEqual(self._balance(self.client), -50.0)

    def test_late_posting_slots_in_by_id(self):
        """An entry registered earlier but posted later recomputes the items after it."""
        self._client_opening(50.0)
        early_sale = self._entry(self.sale_journal, self.client, [
            (self.receivable, 21.0, 0.0),
            (self.income_account, 0.0, 21.0),
        ], post=False)
        payment = self._entry(self.bank_journal, self.client, [
            (self.bank_account, 10.0, 0.0),
            (self.receivable, 0.0, 10.0),
        ])
        payment_line = payment.line_ids.filtered("travel_in_balance")
        self.assertEqual(payment_line.travel_balance, -60.0)
        early_sale.action_post()
        self.assertEqual(payment_line.travel_balance, -39.0)

    def test_reset_to_draft_recomputes(self):
        """Resetting an entry takes it out of the balance and corrects the items after it."""
        self._client_opening(50.0)
        sale = self._entry(self.sale_journal, self.client, [
            (self.receivable, 21.0, 0.0),
            (self.income_account, 0.0, 21.0),
        ])
        self._entry(self.bank_journal, self.client, [
            (self.bank_account, 5.0, 0.0),
            (self.receivable, 0.0, 5.0),
        ])
        self.assertEqual(self._balance(self.client), -34.0)
        sale.button_draft()
        self.assertEqual(self._balance(self.client), -55.0)
        self.assertFalse(sale.line_ids.filtered("travel_balance"))

    def test_only_system_admin_resets(self):
        """An accountant cannot reset an entry that counts in a running balance."""
        accountant = new_test_user(
            self.env, login="travel_accountant", groups="account.group_account_manager",
        )
        sale = self._entry(self.sale_journal, self.client, [
            (self.receivable, 21.0, 0.0),
            (self.income_account, 0.0, 21.0),
        ])
        with self.assertRaises(UserError):
            sale.with_user(accountant).button_draft()

    def test_opening_side_counts(self):
        """In an opening, the Opening Balance item is the side that counts."""
        opening = self._client_opening(50.0)
        counted = opening.line_ids.filtered("travel_in_balance")
        self.assertEqual(counted.account_id, self.opening_account)
        self.assertEqual(counted.travel_balance, -50.0)
