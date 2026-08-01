"""
Ingredient application layer.

Catalog reads and purchase orchestration. Persistence is delegated to
``app.database``; capital changes go through ``app.ledger`` (per player);
stock changes go through ``app.inventory``. Price changes append a new
timestamped row.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from app import database as db
from app import inventory as inventory_service
from app import ledger as ledger_store
from app import users as users_service
from app.models import Ingredient, IngredientUnit


def get(name: str) -> Optional[Ingredient]:
    """Return the latest catalog price for an ingredient, or None if missing."""
    return db.get_ingredient(name)


def list_all() -> list[Ingredient]:
    """Return the latest price version for every catalog ingredient."""
    return db.get_all_ingredients()


def record_price(
    name: str,
    amount: Decimal,
    price: Decimal,
    unit: IngredientUnit,
    timestamp: Optional[datetime] = None,
    id: Optional[str] = None,
) -> Ingredient:
    """Append a new price version for an ingredient (append-only history)."""
    kwargs: dict = {
        "id": id or str(uuid4()),
        "name": name,
        "amount": amount,
        "price": price,
        "unit": unit,
    }
    if timestamp is not None:
        kwargs["timestamp"] = timestamp
    entry = Ingredient(**kwargs)
    db.append_ingredient(entry)
    return entry


def buy(user_id: str, ingredient_name: str, unit_count: Decimal) -> bool:
    """Purchase ingredient units for a player if capital allows.

    ``unit_count`` is the number of units to buy. Cost is always
    ``ingredient.unit_price × unit_count`` (derived from bulk catalog pricing).
    On success, adds ``unit_count`` units to inventory and records the purchase
    on the player's general ledger (``item_id`` = ``Ingredient.id``).

    When a game session exists, purchases are only allowed during ``DAY_START``.

    Returns True on success, False if the user/ingredient is unknown,
    ``unit_count`` is invalid, capital is insufficient, or the game phase
    blocks purchases.
    """
    if unit_count <= 0:
        return False
    if db.get_user(user_id) is None:
        return False

    # Lazy import avoids a circular dependency with app.game.
    from app import game as game_service

    if not game_service.day_start_actions_allowed(user_id):
        return False

    ingredient = db.get_ingredient(ingredient_name)
    if ingredient is None:
        return False

    cost = ingredient.unit_price * unit_count
    if not ledger_store.record_purchase(user_id, cost, ingredient.id):
        return False

    users_service.sync_ledger(user_id)
    inventory_service.add_stock(ingredient_name, unit_count)
    return True
