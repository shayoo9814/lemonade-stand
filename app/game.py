"""
Game simulation application layer.

Owns per-player session state (day/hour/phase), day-start gating, the
intra-day tick clock, end-of-day bankruptcy checks, and auto-sales.
"""

from decimal import Decimal

from app import database as db
from app import inventory as inventory_service
from app import ledger as ledger_store
from app import lemonades as lemonades_service
from app import users as users_service
from app.models import GamePhase, GameSession

SEED_CAPITAL = Decimal("30.00")
SECONDS_PER_GAME_HOUR = 1
HOURS_PER_DAY = 24
HOURLY_DEMAND = Decimal("1")
DEFAULT_LEMONADE = "classic"

# user_id → session (only one active game is supported; start clears others)
_sessions: dict[str, GameSession] = {}


def clear_sessions() -> None:
    """Remove all game sessions (used by tests / DB reset)."""
    _sessions.clear()


def get_session(user_id: str) -> GameSession | None:
    """Return the player's game session, or None if missing."""
    return _sessions.get(user_id)


def day_start_actions_allowed(user_id: str) -> bool:
    """Return True when buys / price changes are allowed for this player.

    With no active session, actions are allowed (legacy API / tests).
    With a session, only ``DAY_START`` permits shopping and price setting.
    """
    session = get_session(user_id)
    if session is None:
        return True
    return session.phase == GamePhase.DAY_START


def is_bankrupt(user_id: str) -> bool:
    """Bankrupt when capital is exhausted and no lemonade can be made."""
    latest = ledger_store.get_ledger(user_id)
    if latest is None:
        return True
    return latest.current_capital <= 0 and not inventory_service.can_make_lemonade()


def start_game(user_id: str) -> GameSession | None:
    """Start a fresh game for ``user_id`` with seed capital and empty stock.

    Clears any existing capital with a reset-ledger row (subtracts the
    current balance to zero), then appends an opening-balance row for
    ``SEED_CAPITAL``. History is retained. Clears shared inventory and
    enters ``DAY_START``. Only one active game is kept at a time.
    Returns None if the user is unknown.
    """
    if db.get_user(user_id) is None:
        return None

    _sessions.clear()
    inventory_service.clear_all()
    ledger_store.record_reset_ledger(user_id=user_id)
    ledger_store.record_opening_balance(
        user_id=user_id, current_capital=SEED_CAPITAL
    )
    users_service.sync_ledger(user_id)

    session = GameSession(
        user_id=user_id,
        day=1,
        hour=0,
        phase=GamePhase.DAY_START,
    )
    _sessions[user_id] = session
    return session


def continue_day(user_id: str) -> GameSession | None:
    """Leave ``DAY_START`` and begin the intra-day clock (``RUNNING``).

    Returns None if there is no session or the phase is not ``DAY_START``.
    """
    session = get_session(user_id)
    if session is None or session.phase != GamePhase.DAY_START:
        return None

    updated = session.model_copy(update={"phase": GamePhase.RUNNING, "hour": 0})
    _sessions[user_id] = updated
    return updated


def _end_day(session: GameSession) -> GameSession:
    """Apply EOD: discard ice, then bankrupt → ``GAME_OVER``, else next ``DAY_START``.

    Ice cannot be carried overnight; other stock remains for the next day.
    """
    inventory_service.discard_perishables()
    if is_bankrupt(session.user_id):
        updated = session.model_copy(update={"phase": GamePhase.GAME_OVER})
    else:
        updated = session.model_copy(
            update={
                "phase": GamePhase.DAY_START,
                "day": session.day + 1,
                "hour": 0,
            }
        )
    _sessions[session.user_id] = updated
    return updated


def tick(user_id: str) -> GameSession | None:
    """Advance one game-hour for a ``RUNNING`` session.

    Auto-sells ``HOURLY_DEMAND`` servings of the default lemonade. Ends the
    day when stock cannot cover a sale or ``hour`` reaches ``HOURS_PER_DAY``.
    No-ops (returns the unchanged session) unless phase is ``RUNNING``.
    """
    session = get_session(user_id)
    if session is None:
        return None
    if session.phase != GamePhase.RUNNING:
        return session

    hour = session.hour + 1
    updated = session.model_copy(update={"hour": hour})
    _sessions[user_id] = updated

    sold = lemonades_service.sell(user_id, DEFAULT_LEMONADE, HOURLY_DEMAND)
    if not sold or hour >= HOURS_PER_DAY:
        return _end_day(updated)
    return updated


def tick_all() -> None:
    """Tick every session currently in ``RUNNING`` (background clock)."""
    for user_id, session in list(_sessions.items()):
        if session.phase == GamePhase.RUNNING:
            tick(user_id)
