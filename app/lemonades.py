"""
Lemonade application layer.

Per-player menu reads and sale orchestration. Persistence is delegated to
``app.database``; stock changes go through ``app.inventory``; sale revenue
is recorded on the player's ledger via ``app.ledger``. Ingredient costs are
already on purchase rows, so sales credit the full sale price.
"""

from decimal import Decimal
from typing import Optional

from app import database as db
from app import inventory as inventory_service
from app import ledger as ledger_store
from app import users as users_service
from app.models import Lemonade


def get(user_id: str, name: str) -> Optional[Lemonade]:
    """Return a lemonade from the player's menu, or None if missing."""
    db.ensure_user_menu(user_id)
    return db.get_lemonade(user_id, name)


def list_all(user_id: str) -> list[Lemonade]:
    """Return every lemonade on the player's menu."""
    db.ensure_user_menu(user_id)
    return db.get_all_lemonades(user_id)


def sell(user_id: str, name: str, amount: Decimal) -> bool:
    """Sell servings for a player; deduct inventory and credit revenue.

    ``amount`` is how many servings to sell. Revenue is
    ``sale price × amount`` (ingredient costs were already booked on
    purchase). The ledger row's ``item_id`` is the lemonade's ``id``.
    Returns True on success, False if the user/lemonade is unknown,
    amount is invalid, or stock is insufficient.
    """
    if amount <= 0:
        return False
    if db.get_user(user_id) is None:
        return False

    lemonade = get(user_id, name)
    if lemonade is None:
        return False

    requirements = {
        ingredient_name: required * amount
        for ingredient_name, required in lemonade.recipe.items()
    }
    if not inventory_service.has_sufficient(user_id, requirements):
        return False

    revenue = lemonade.price * amount
    if not ledger_store.record_sale(user_id, revenue, lemonade.id):
        return False

    users_service.sync_ledger(user_id)
    inventory_service.deduct(user_id, requirements)
    return True


def set_price(user_id: str, name: str, price: Decimal) -> bool:
    """Set a lemonade's sell price (day-start only when a game is active).

    Price may be zero (free) or below recipe cost. Returns True on success.
    """
    if price < 0:
        return False
    if db.get_user(user_id) is None:
        return False

    # Lazy import avoids a circular dependency with app.game.
    from app import game as game_service

    if not game_service.day_start_actions_allowed(user_id):
        return False

    lemonade = get(user_id, name)
    if lemonade is None:
        return False

    db.set_lemonade(user_id, lemonade.model_copy(update={"price": price}))
    return True
