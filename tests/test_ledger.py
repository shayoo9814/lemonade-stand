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
    apply_reset_ledger,
    apply_sale,
    clear_all,
    get_ledger,
    list_entries,
    record_opening_balance,
    record_purchase,
    record_reset_ledger,
    record_sale,
)
from app.models import (
    GeneralLedger,
    LedgerAction,
    OPENING_BALANCE_ITEM_ID,
    RESET_LEDGER_ITEM_ID,
)

FIXED_TS = datetime(2026, 8, 1, tzinfo=timezone.utc)
USER_ID = "u1"
ING_ID = "ingredient-lemons"
LEM_ID = "lemonade-classic"


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
            item_id=OPENING_BALANCE_ITEM_ID,
        )
        result = apply_purchase(
            previous, Decimal("25.00"), ING_ID, timestamp=FIXED_TS
        )

        assert result is not None
        assert result.user_id == USER_ID
        assert result.action == LedgerAction.PURCHASE
        assert result.amount == Decimal("25.00")
        assert result.current_capital == Decimal("75.00")
        assert result.expenses_incurred == Decimal("35.00")
        assert result.timestamp == FIXED_TS
        assert result.item_id == ING_ID

    def test_does_not_mutate_input_ledger(self):
        previous = GeneralLedger(
            user_id=USER_ID,
            timestamp=FIXED_TS,
            action=LedgerAction.OPENING_BALANCE,
            amount=Decimal("100.00"),
            current_capital=Decimal("100.00"),
            expenses_incurred=Decimal("0"),
            item_id=OPENING_BALANCE_ITEM_ID,
        )
        apply_purchase(previous, Decimal("10.00"), ING_ID, timestamp=FIXED_TS)

        assert previous.current_capital == Decimal("100.00")
        assert previous.expenses_incurred == Decimal("0")

    def test_rejects_insufficient_capital(self):
        previous = get_ledger(USER_ID)
        assert previous is not None
        previous = previous.model_copy(update={"current_capital": Decimal("5.00")})
        assert apply_purchase(previous, Decimal("5.01"), ING_ID) is None

    def test_allows_exact_capital_spend(self):
        previous = GeneralLedger(
            user_id=USER_ID,
            timestamp=FIXED_TS,
            action=LedgerAction.OPENING_BALANCE,
            amount=Decimal("5.00"),
            current_capital=Decimal("5.00"),
            expenses_incurred=Decimal("0"),
            item_id=OPENING_BALANCE_ITEM_ID,
        )
        result = apply_purchase(previous, Decimal("5.00"), ING_ID, timestamp=FIXED_TS)

        assert result is not None
        assert result.current_capital == Decimal("0")
        assert result.expenses_incurred == Decimal("5.00")
        assert result.item_id == ING_ID

    def test_rejects_zero_cost(self):
        assert apply_purchase(get_ledger(USER_ID), Decimal("0"), ING_ID) is None

    def test_rejects_negative_cost(self):
        assert apply_purchase(get_ledger(USER_ID), Decimal("-1.00"), ING_ID) is None


class TestRecordPurchase:
    """Stateful append-only per-player ledger API."""

    def test_appends_entry_on_success(self):
        assert (
            record_purchase(USER_ID, Decimal("40.00"), ING_ID, timestamp=FIXED_TS)
            is True
        )

        entries = list_entries(USER_ID)
        assert len(entries) == 2
        assert entries[0].action == LedgerAction.OPENING_BALANCE
        assert entries[0].item_id == OPENING_BALANCE_ITEM_ID
        assert entries[1].action == LedgerAction.PURCHASE
        assert entries[1].user_id == USER_ID
        assert entries[1].amount == Decimal("40.00")
        assert entries[1].item_id == ING_ID

        latest = get_ledger(USER_ID)
        assert latest is not None
        assert latest.current_capital == Decimal("60.00")
        assert latest.expenses_incurred == Decimal("40.00")

    def test_leaves_ledger_unchanged_on_failure(self):
        assert record_purchase(USER_ID, Decimal("150.00"), ING_ID) is False

        entries = list_entries(USER_ID)
        assert len(entries) == 1
        latest = get_ledger(USER_ID)
        assert latest is not None
        assert latest.current_capital == Decimal("100.00")
        assert latest.expenses_incurred == Decimal("0")

    def test_accumulates_multiple_purchases(self):
        assert (
            record_purchase(USER_ID, Decimal("10.00"), ING_ID, timestamp=FIXED_TS)
            is True
        )
        assert (
            record_purchase(USER_ID, Decimal("15.50"), "ingredient-sugar", timestamp=FIXED_TS)
            is True
        )

        assert len(list_entries(USER_ID)) == 3
        latest = get_ledger(USER_ID)
        assert latest is not None
        assert latest.current_capital == Decimal("74.50")
        assert latest.expenses_incurred == Decimal("25.50")
        assert latest.item_id == "ingredient-sugar"

    def test_unknown_user_fails(self):
        assert record_purchase("missing", Decimal("1.00"), ING_ID) is False


class TestApplySale:
    """Pure accounting helper — no module state."""

    def test_credits_capital_with_revenue(self):
        previous = GeneralLedger(
            user_id=USER_ID,
            timestamp=FIXED_TS,
            action=LedgerAction.OPENING_BALANCE,
            amount=Decimal("100.00"),
            current_capital=Decimal("100.00"),
            expenses_incurred=Decimal("10.00"),
            item_id=OPENING_BALANCE_ITEM_ID,
        )
        result = apply_sale(previous, Decimal("2.00"), LEM_ID, timestamp=FIXED_TS)

        assert result is not None
        assert result.user_id == USER_ID
        assert result.action == LedgerAction.SALE
        assert result.amount == Decimal("2.00")
        assert result.current_capital == Decimal("102.00")
        assert result.expenses_incurred == Decimal("10.00")
        assert result.item_id == LEM_ID

    def test_does_not_mutate_input_ledger(self):
        previous = get_ledger(USER_ID)
        assert previous is not None
        apply_sale(previous, Decimal("2.00"), LEM_ID, timestamp=FIXED_TS)

        assert previous.current_capital == Decimal("100.00")
        assert previous.expenses_incurred == Decimal("0")

    def test_allows_zero_revenue(self):
        previous = GeneralLedger(
            user_id=USER_ID,
            timestamp=FIXED_TS,
            action=LedgerAction.OPENING_BALANCE,
            amount=Decimal("50.00"),
            current_capital=Decimal("50.00"),
            expenses_incurred=Decimal("0"),
            item_id=OPENING_BALANCE_ITEM_ID,
        )
        result = apply_sale(previous, Decimal("0"), LEM_ID, timestamp=FIXED_TS)

        assert result is not None
        assert result.current_capital == Decimal("50.00")
        assert result.item_id == LEM_ID


class TestRecordSale:
    """Stateful append-only API for sales."""

    def test_appends_entry_on_success(self):
        assert record_sale(USER_ID, Decimal("2.00"), LEM_ID, timestamp=FIXED_TS) is True

        entries = list_entries(USER_ID)
        assert len(entries) == 2
        assert entries[1].action == LedgerAction.SALE
        latest = get_ledger(USER_ID)
        assert latest is not None
        assert latest.current_capital == Decimal("102.00")
        assert latest.expenses_incurred == Decimal("0")
        assert latest.amount == Decimal("2.00")
        assert latest.item_id == LEM_ID

    def test_leaves_ledger_unchanged_on_failure(self):
        assert record_sale("unknown-user", Decimal("1.00"), LEM_ID) is False

        assert len(list_entries(USER_ID)) == 1
        latest = get_ledger(USER_ID)
        assert latest is not None
        assert latest.current_capital == Decimal("100.00")
        assert latest.expenses_incurred == Decimal("0")


class TestLedgerStateHelpers:
    def test_record_reset_ledger_zeros_balance_without_erasing_history(self):
        record_purchase(USER_ID, Decimal("30.00"), ING_ID, timestamp=FIXED_TS)
        assert get_ledger(USER_ID).current_capital == Decimal("70.00")

        reset = record_reset_ledger(user_id=USER_ID, timestamp=FIXED_TS)
        assert reset is not None

        entries = list_entries(USER_ID)
        assert len(entries) == 3
        assert entries[0].action == LedgerAction.OPENING_BALANCE
        assert entries[1].action == LedgerAction.PURCHASE
        assert entries[1].item_id == ING_ID
        assert entries[2].action == LedgerAction.RESET_LEDGER
        assert entries[2].item_id == RESET_LEDGER_ITEM_ID
        assert entries[2].amount == Decimal("70.00")
        assert entries[2].current_capital == Decimal("0")
        assert entries[2].expenses_incurred == Decimal("0")
        latest = get_ledger(USER_ID)
        assert latest is not None
        assert latest.current_capital == Decimal("0")

    def test_apply_reset_ledger_subtracts_previous_balance_to_zero(self):
        previous = GeneralLedger(
            user_id=USER_ID,
            timestamp=FIXED_TS,
            action=LedgerAction.OPENING_BALANCE,
            amount=Decimal("100.00"),
            current_capital=Decimal("100.00"),
            expenses_incurred=Decimal("25.00"),
            item_id=OPENING_BALANCE_ITEM_ID,
        )
        entry = apply_reset_ledger(previous, timestamp=FIXED_TS)
        assert entry.action == LedgerAction.RESET_LEDGER
        assert entry.item_id == RESET_LEDGER_ITEM_ID
        assert entry.amount == Decimal("100.00")
        assert entry.current_capital == Decimal("0")
        assert entry.expenses_incurred == Decimal("0")

    def test_record_reset_ledger_noop_without_prior_ledger(self):
        clear_all()
        assert record_reset_ledger(user_id=USER_ID) is None
        assert list_entries(USER_ID) == []

    def test_record_opening_balance_appends_without_erasing_history(self):
        record_purchase(USER_ID, Decimal("30.00"), ING_ID, timestamp=FIXED_TS)
        record_opening_balance(user_id=USER_ID, timestamp=FIXED_TS)

        entries = list_entries(USER_ID)
        assert len(entries) == 3
        assert entries[0].action == LedgerAction.OPENING_BALANCE
        assert entries[1].action == LedgerAction.PURCHASE
        assert entries[1].item_id == ING_ID
        assert entries[2].action == LedgerAction.OPENING_BALANCE
        assert entries[2].item_id == OPENING_BALANCE_ITEM_ID
        latest = get_ledger(USER_ID)
        assert latest is not None
        assert latest.current_capital == Decimal("30.00")
        assert latest.expenses_incurred == Decimal("0")

    def test_players_have_isolated_ledgers(self):
        record_opening_balance(
            user_id="u2", current_capital=Decimal("100.00"), timestamp=FIXED_TS
        )
        assert (
            record_purchase(USER_ID, Decimal("40.00"), ING_ID, timestamp=FIXED_TS)
            is True
        )

        assert get_ledger(USER_ID).current_capital == Decimal("60.00")
        assert get_ledger("u2").current_capital == Decimal("100.00")
        assert len(list_entries(USER_ID)) == 2
        assert len(list_entries("u2")) == 1
