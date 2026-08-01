"""
Lemonade application layer.

Recipe catalog reads and sale orchestration. Persistence is delegated to
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


def get(name: str) -> Optional[Lemonade]:
    """Return a lemonade by name, or None if missing."""
    return db.get_lemonade(name)


def list_all() -> list[Lemonade]:
    """Return every lemonade on the menu."""
    return db.get_all_lemonades()


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

    lemonade = db.get_lemonade(name)
    if lemonade is None:
        return False

    requirements = {
        ingredient_name: required * amount
        for ingredient_name, required in lemonade.recipe.items()
    }
    if not inventory_service.has_sufficient(requirements):
        return False

    revenue = lemonade.price * amount
    if not ledger_store.record_sale(user_id, revenue, lemonade.id):
        return False

    users_service.sync_ledger(user_id)
    inventory_service.deduct(requirements)
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

    lemonade = db.get_lemonade(name)
    if lemonade is None:
        return False

    db.set_lemonade(lemonade.model_copy(update={"price": price}))
    return True
