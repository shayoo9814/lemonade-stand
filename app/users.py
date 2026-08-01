"""
User application layer.

Player lookups and syncing the append-only general ledger onto ``User``.
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
    return sync_ledger(user_id)


def sync_ledger(user_id: str) -> Optional[User]:
    """Copy the player's ledger log onto ``User.general_ledger`` and persist."""
    user = db.get_user(user_id)
    if user is None:
        return None
    entries = ledger_store.list_entries(user_id)
    updated = user.model_copy(update={"general_ledger": entries})
    db.set_user(updated)
    return updated


def clear_ledger(user_id: str) -> Optional[User]:
    """Wipe the player's ledger history and sync the empty log onto ``User``."""
    user = db.get_user(user_id)
    if user is None:
        return None
    ledger_store.clear_user(user_id)
    return sync_ledger(user_id)
