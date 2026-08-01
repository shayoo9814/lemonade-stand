"""
User application layer.

Player lookups and opening-balance / ledger-clear helpers that delegate
capital history to ``app.ledger`` (the sole source of truth).
"""

from decimal import Decimal
from typing import Optional

from app import database as db
from app import ledger as ledger_store
from app.models import User

SEED_CAPITAL = Decimal("30.00")


def get(user_id: str) -> Optional[User]:
    """Return a user by id, or None if missing."""
    return db.get_user(user_id)


def list_all() -> list[User]:
    """Return all users."""
    return db.get_all_users()


def ensure_opening_balance(user_id: str) -> Optional[User]:
    """Create a seed opening-balance entry if the player has no ledger yet.

    Idempotent: existing ledgers are left unchanged. Available for API/tests;
    the play UI waits for ``POST /game/start``, which seeds capital itself.
    """
    user = db.get_user(user_id)
    if user is None:
        return None
    if ledger_store.get_ledger(user_id) is not None:
        return user
    ledger_store.record_opening_balance(user_id=user_id, current_capital=SEED_CAPITAL)
    return user


def clear_ledger(user_id: str) -> Optional[User]:
    """Wipe the player's ledger history in ``app.ledger``."""
    user = db.get_user(user_id)
    if user is None:
        return None
    ledger_store.clear_user(user_id)
    return user
