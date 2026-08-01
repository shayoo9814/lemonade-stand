"""
Unit tests for the lemonade stand general ledger module.

These tests exercise ``app.ledger`` only — no database, inventory, or HTTP.
Each player has an append-only log; ``get_ledger(user_id)`` returns their latest entry.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.ledger import (
    apply_purchase,
    apply_sale,
    clear_all,
    get_ledger,
    list_entries,
    record_opening_balance,
    record_purchase,
    record_sale,
)
from app.models import GeneralLedger, LedgerAction

FIXED_TS = datetime(2026, 8, 1, tzinfo=timezone.utc)
USER_ID = "u1"


@pytest.fixture(autouse=True)
def fresh_ledger():
    clear_all()
    record_opening_balance(
        user_id=USER_ID,
        current_capital=Decimal("100.00"),
        expenses_incurred=Decimal("0"),
        timestamp=FIXED_TS,
    )
    yield


class TestApplyPurchase:
    """Pure accounting helper — no module state."""

    def test_debits_capital_and_credits_expenses(self):
        previous = GeneralLedger(
            user_id=USER_ID,
            timestamp=FIXED_TS,
            action=LedgerAction.OPENING_BALANCE,
            amount=Decimal("100.00"),
            current_capital=Decimal("100.00"),
            expenses_incurred=Decimal("10.00"),
        )
        result = apply_purchase(previous, Decimal("25.00"), timestamp=FIXED_TS)

        assert result is not None
        assert result.user_id == USER_ID
        assert result.action == LedgerAction.PURCHASE
        assert result.amount == Decimal("25.00")
        assert result.current_capital == Decimal("75.00")
        assert result.expenses_incurred == Decimal("35.00")
        assert result.timestamp == FIXED_TS

    def test_does_not_mutate_input_ledger(self):
        previous = GeneralLedger(
            user_id=USER_ID,
            timestamp=FIXED_TS,
            action=LedgerAction.OPENING_BALANCE,
            amount=Decimal("100.00"),
            current_capital=Decimal("100.00"),
            expenses_incurred=Decimal("0"),
        )
        apply_purchase(previous, Decimal("10.00"), timestamp=FIXED_TS)

        assert previous.current_capital == Decimal("100.00")
        assert previous.expenses_incurred == Decimal("0")

    def test_rejects_insufficient_capital(self):
        previous = get_ledger(USER_ID)
        assert previous is not None
        previous = previous.model_copy(update={"current_capital": Decimal("5.00")})
        assert apply_purchase(previous, Decimal("5.01")) is None

    def test_allows_exact_capital_spend(self):
        previous = GeneralLedger(
            user_id=USER_ID,
            timestamp=FIXED_TS,
            action=LedgerAction.OPENING_BALANCE,
            amount=Decimal("5.00"),
            current_capital=Decimal("5.00"),
            expenses_incurred=Decimal("0"),
        )
        result = apply_purchase(previous, Decimal("5.00"), timestamp=FIXED_TS)

        assert result is not None
        assert result.current_capital == Decimal("0")
        assert result.expenses_incurred == Decimal("5.00")

    def test_rejects_zero_cost(self):
        assert apply_purchase(get_ledger(USER_ID), Decimal("0")) is None

    def test_rejects_negative_cost(self):
        assert apply_purchase(get_ledger(USER_ID), Decimal("-1.00")) is None


class TestRecordPurchase:
    """Stateful append-only per-player ledger API."""

    def test_appends_entry_on_success(self):
        assert record_purchase(USER_ID, Decimal("40.00"), timestamp=FIXED_TS) is True

        entries = list_entries(USER_ID)
        assert len(entries) == 2
        assert entries[0].action == LedgerAction.OPENING_BALANCE
        assert entries[1].action == LedgerAction.PURCHASE
        assert entries[1].user_id == USER_ID
        assert entries[1].amount == Decimal("40.00")

        latest = get_ledger(USER_ID)
        assert latest is not None
        assert latest.current_capital == Decimal("60.00")
        assert latest.expenses_incurred == Decimal("40.00")

    def test_leaves_ledger_unchanged_on_failure(self):
        assert record_purchase(USER_ID, Decimal("150.00")) is False

        entries = list_entries(USER_ID)
        assert len(entries) == 1
        latest = get_ledger(USER_ID)
        assert latest is not None
        assert latest.current_capital == Decimal("100.00")
        assert latest.expenses_incurred == Decimal("0")

    def test_accumulates_multiple_purchases(self):
        assert record_purchase(USER_ID, Decimal("10.00"), timestamp=FIXED_TS) is True
        assert record_purchase(USER_ID, Decimal("15.50"), timestamp=FIXED_TS) is True

        assert len(list_entries(USER_ID)) == 3
        latest = get_ledger(USER_ID)
        assert latest is not None
        assert latest.current_capital == Decimal("74.50")
        assert latest.expenses_incurred == Decimal("25.50")

    def test_unknown_user_fails(self):
        assert record_purchase("missing", Decimal("1.00")) is False


class TestApplySale:
    """Pure accounting helper — no module state."""

    def test_credits_capital_with_profit(self):
        previous = GeneralLedger(
            user_id=USER_ID,
            timestamp=FIXED_TS,
            action=LedgerAction.OPENING_BALANCE,
            amount=Decimal("100.00"),
            current_capital=Decimal("100.00"),
            expenses_incurred=Decimal("10.00"),
        )
        result = apply_sale(previous, Decimal("1.1725"), timestamp=FIXED_TS)

        assert result is not None
        assert result.user_id == USER_ID
        assert result.action == LedgerAction.SALE
        assert result.amount == Decimal("1.1725")
        assert result.current_capital == Decimal("101.1725")
        assert result.expenses_incurred == Decimal("10.00")

    def test_does_not_mutate_input_ledger(self):
        previous = get_ledger(USER_ID)
        assert previous is not None
        apply_sale(previous, Decimal("2.00"), timestamp=FIXED_TS)

        assert previous.current_capital == Decimal("100.00")
        assert previous.expenses_incurred == Decimal("0")

    def test_allows_zero_profit(self):
        previous = GeneralLedger(
            user_id=USER_ID,
            timestamp=FIXED_TS,
            action=LedgerAction.OPENING_BALANCE,
            amount=Decimal("50.00"),
            current_capital=Decimal("50.00"),
            expenses_incurred=Decimal("0"),
        )
        result = apply_sale(previous, Decimal("0"), timestamp=FIXED_TS)

        assert result is not None
        assert result.current_capital == Decimal("50.00")

    def test_allows_negative_profit(self):
        previous = get_ledger(USER_ID)
        assert previous is not None
        result = apply_sale(previous, Decimal("-0.01"), timestamp=FIXED_TS)

        assert result is not None
        assert result.amount == Decimal("-0.01")
        assert result.current_capital == Decimal("99.99")


class TestRecordSale:
    """Stateful append-only API for sales."""

    def test_appends_entry_on_success(self):
        assert record_sale(USER_ID, Decimal("1.50"), timestamp=FIXED_TS) is True

        entries = list_entries(USER_ID)
        assert len(entries) == 2
        assert entries[1].action == LedgerAction.SALE
        latest = get_ledger(USER_ID)
        assert latest is not None
        assert latest.current_capital == Decimal("101.50")
        assert latest.expenses_incurred == Decimal("0")

    def test_records_loss_on_below_cost_sale(self):
        assert record_sale(USER_ID, Decimal("-1.00"), timestamp=FIXED_TS) is True

        latest = get_ledger(USER_ID)
        assert latest is not None
        assert latest.current_capital == Decimal("99.00")
        assert latest.amount == Decimal("-1.00")

    def test_leaves_ledger_unchanged_on_failure(self):
        assert record_sale("unknown-user", Decimal("1.00")) is False

        assert len(list_entries(USER_ID)) == 1
        latest = get_ledger(USER_ID)
        assert latest is not None
        assert latest.current_capital == Decimal("100.00")
        assert latest.expenses_incurred == Decimal("0")


class TestLedgerStateHelpers:
    def test_record_opening_balance_appends_without_erasing_history(self):
        record_purchase(USER_ID, Decimal("30.00"), timestamp=FIXED_TS)
        record_opening_balance(user_id=USER_ID, timestamp=FIXED_TS)

        entries = list_entries(USER_ID)
        assert len(entries) == 3
        assert entries[0].action == LedgerAction.OPENING_BALANCE
        assert entries[1].action == LedgerAction.PURCHASE
        assert entries[2].action == LedgerAction.OPENING_BALANCE
        latest = get_ledger(USER_ID)
        assert latest is not None
        assert latest.current_capital == Decimal("30.00")
        assert latest.expenses_incurred == Decimal("0")

    def test_players_have_isolated_ledgers(self):
        record_opening_balance(
            user_id="u2", current_capital=Decimal("100.00"), timestamp=FIXED_TS
        )
        assert record_purchase(USER_ID, Decimal("40.00"), timestamp=FIXED_TS) is True

        assert get_ledger(USER_ID).current_capital == Decimal("60.00")
        assert get_ledger("u2").current_capital == Decimal("100.00")
        assert len(list_entries(USER_ID)) == 2
        assert len(list_entries("u2")) == 1
