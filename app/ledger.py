"""
General ledger application layer for the lemonade stand game.

Per-player append-only logs of capital actions. Rows are never updated or
deleted during play — only appended. Callers supply a user id plus a cost or
revenue (and, for purchases/sales, the related catalog ``id``); this module
never looks up ingredients or lemonades. Current balances for a player are
always their latest entry. Persistence of the log onto
``User.general_ledger`` is done by the users layer after successful writes.

``clear_all`` exists only for process/test bootstrap, not game operations.
"""

from datetime import datetime, timezone
from decimal import Decimal

from app.models import (
    GeneralLedger,
    LedgerAction,
    OPENING_BALANCE_ITEM_ID,
    RESET_LEDGER_ITEM_ID,
)

_DEFAULT_STARTING_CAPITAL = Decimal("30.00")
_DEFAULT_USER_ID = "u1"

# user_id → append-only entries
_ledgers: dict[str, list[GeneralLedger]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _opening_entry(
    user_id: str,
    current_capital: Decimal = _DEFAULT_STARTING_CAPITAL,
    expenses_incurred: Decimal = Decimal("0"),
    timestamp: datetime | None = None,
) -> GeneralLedger:
    return GeneralLedger(
        user_id=user_id,
        timestamp=timestamp or _now(),
        action=LedgerAction.OPENING_BALANCE,
        amount=current_capital,
        current_capital=current_capital,
        expenses_incurred=expenses_incurred,
        item_id=OPENING_BALANCE_ITEM_ID,
    )


def list_entries(user_id: str) -> list[GeneralLedger]:
    """Return all ledger entries for a player in append order."""
    return list(_ledgers.get(user_id, []))


def get_ledger(user_id: str) -> GeneralLedger | None:
    """Return the latest ledger entry for a player, or None if missing."""
    entries = _ledgers.get(user_id)
    if not entries:
        return None
    return entries[-1]


def clear_all() -> None:
    """Wipe all ledgers (process/test bootstrap only — not a game operation)."""
    _ledgers.clear()


def clear_user(user_id: str) -> None:
    """Remove all ledger entries for a single player."""
    _ledgers.pop(user_id, None)


def record_opening_balance(
    user_id: str = _DEFAULT_USER_ID,
    current_capital: Decimal = _DEFAULT_STARTING_CAPITAL,
    expenses_incurred: Decimal = Decimal("0"),
    timestamp: datetime | None = None,
) -> GeneralLedger:
    """Append an opening-balance row (e.g. first load before play).

    Prior entries are retained. The new row becomes the player's current
    capital via ``get_ledger``.
    """
    entry = _opening_entry(user_id, current_capital, expenses_incurred, timestamp)
    _ledgers.setdefault(user_id, []).append(entry)
    return entry


def apply_reset_ledger(
    previous: GeneralLedger,
    timestamp: datetime | None = None,
) -> GeneralLedger:
    """Return a reset-ledger entry that subtracts the previous balance to zero.

    ``amount`` is the capital being cleared. ``current_capital`` and
    ``expenses_incurred`` become zero. Pure: does not mutate module state.
    """
    return GeneralLedger(
        user_id=previous.user_id,
        timestamp=timestamp or _now(),
        action=LedgerAction.RESET_LEDGER,
        amount=previous.current_capital,
        current_capital=Decimal("0"),
        expenses_incurred=Decimal("0"),
        item_id=RESET_LEDGER_ITEM_ID,
    )


def record_reset_ledger(
    user_id: str,
    timestamp: datetime | None = None,
) -> GeneralLedger | None:
    """Append a reset-ledger row that zeros capital. No-op if no prior ledger."""
    previous = get_ledger(user_id)
    if previous is None:
        return None
    entry = apply_reset_ledger(previous, timestamp=timestamp)
    _ledgers[user_id].append(entry)
    return entry


def apply_purchase(
    previous: GeneralLedger,
    cost: Decimal,
    item_id: str,
    timestamp: datetime | None = None,
) -> GeneralLedger | None:
    """Return a new purchase entry, or None if invalid.

    Debits ``current_capital`` and credits ``expenses_incurred`` by ``cost``.
    ``item_id`` is the related ``Ingredient.id``. Pure: does not mutate
    ``previous`` or module state.
    """
    if cost <= 0:
        return None
    if previous.current_capital < cost:
        return None
    return GeneralLedger(
        user_id=previous.user_id,
        timestamp=timestamp or _now(),
        action=LedgerAction.PURCHASE,
        amount=cost,
        current_capital=previous.current_capital - cost,
        expenses_incurred=previous.expenses_incurred + cost,
        item_id=item_id,
    )


def record_purchase(
    user_id: str,
    cost: Decimal,
    item_id: str,
    timestamp: datetime | None = None,
) -> bool:
    """Append a purchase entry for a player. Returns True on success."""
    previous = get_ledger(user_id)
    if previous is None:
        return False
    updated = apply_purchase(previous, cost, item_id, timestamp=timestamp)
    if updated is None:
        return False
    _ledgers[user_id].append(updated)
    return True


def apply_sale(
    previous: GeneralLedger,
    revenue: Decimal,
    item_id: str,
    timestamp: datetime | None = None,
) -> GeneralLedger | None:
    """Return a new sale entry, or None if invalid.

    Credits ``current_capital`` by ``revenue`` (full sale proceeds).
    ``item_id`` is the related ``Lemonade.id``. Zero revenue is allowed.
    Pure: does not mutate ``previous`` or module state.
    """
    return GeneralLedger(
        user_id=previous.user_id,
        timestamp=timestamp or _now(),
        action=LedgerAction.SALE,
        amount=revenue,
        current_capital=previous.current_capital + revenue,
        expenses_incurred=previous.expenses_incurred,
        item_id=item_id,
    )


def record_sale(
    user_id: str,
    revenue: Decimal,
    item_id: str,
    timestamp: datetime | None = None,
) -> bool:
    """Append a sale entry for a player. Returns True on success."""
    previous = get_ledger(user_id)
    if previous is None:
        return False
    updated = apply_sale(previous, revenue, item_id, timestamp=timestamp)
    if updated is None:
        return False
    _ledgers[user_id].append(updated)
    return True
