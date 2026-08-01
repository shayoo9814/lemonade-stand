"""
Thin in-memory persistence for the lemonade stand game.

Stores entities and exposes get/set/list/clear helpers only. Business rules
live in entity modules (``app.ingredients``, ``app.inventory``, etc.).
Per-player general ledger logs are owned by ``app.ledger`` and mirrored onto
``User.general_ledger``. Ingredient rows are an append-only price history
(``append_ingredient`` only; no in-place updates). Inventory and lemonade
menus are keyed by ``user_id``. ``clear_all`` / ``reset_db`` are
process/test bootstrap only.
"""

import json
import os
from typing import Optional

from app import ledger as ledger_store
from app.models import Ingredient, Inventory, Lemonade, User

_users: dict[str, User] = {}
# Shared supermarket catalog: ingredient name → append-only price history.
# Not keyed by user — market prices are the same for every stand; per-player
# stock lives in ``_inventory``, sell prices in ``_lemonades``.
_ingredients: dict[str, list[Ingredient]] = {}
# user_id → ingredient_name → Inventory
_inventory: dict[str, dict[str, Inventory]] = {}
# user_id → lemonade_name → Lemonade
_lemonades: dict[str, dict[str, Lemonade]] = {}
# Seed menu templates cloned onto each player
_lemonade_templates: list[Lemonade] = []


def _load_seed_data() -> None:
    """Load seed data from JSON file into the in-memory stores."""
    seed_path = os.path.join(os.path.dirname(__file__), "..", "data", "seed.json")
    seed_path = os.path.normpath(seed_path)

    if not os.path.exists(seed_path):
        return

    with open(seed_path, "r") as f:
        data = json.load(f)

    for u in data.get("users", []):
        set_user(
            User(
                id=u["id"],
                name=u["name"],
                email=u["email"],
            )
        )

    for item in data.get("ingredients", []):
        append_ingredient(Ingredient(**item))

    catalog = get_ingredients_catalog()
    _lemonade_templates.clear()
    for item in data.get("lemonades", []):
        lemonade = Lemonade(**item)
        lemonade.ensure_price_covers_recipe(catalog)
        _lemonade_templates.append(lemonade)

    for user in get_all_users():
        for lemonade in _lemonade_templates:
            set_lemonade(user.id, lemonade.model_copy(deep=True))

    for item in data.get("inventory", []):
        user_id = item["user_id"]
        entry = Inventory(
            ingredient_name=item["ingredient_name"],
            amount=item["amount"],
            unit=item["unit"],
        )
        set_inventory(user_id, entry)


def clear_all() -> None:
    """Clear all entity stores (does not reset ledgers)."""
    _users.clear()
    _ingredients.clear()
    _inventory.clear()
    _lemonades.clear()
    _lemonade_templates.clear()


def reset_db() -> None:
    """Clear all data and reload from seed. Useful for tests."""
    from app import game as game_service

    clear_all()
    ledger_store.clear_all()
    game_service.clear_sessions()
    _load_seed_data()


# --- Users ---

def get_user(user_id: str) -> Optional[User]:
    return _users.get(user_id)


def get_all_users() -> list[User]:
    return list(_users.values())


def set_user(user: User) -> None:
    _users[user.id] = user


# --- Ingredients (append-only price history) ---

def get_ingredient(name: str) -> Optional[Ingredient]:
    """Return the latest price version for an ingredient."""
    versions = _ingredients.get(name)
    if not versions:
        return None
    return max(versions, key=lambda item: item.timestamp)


def get_ingredient_history(name: str) -> list[Ingredient]:
    """Return all price versions for an ingredient, oldest first."""
    versions = _ingredients.get(name, [])
    return sorted(versions, key=lambda item: item.timestamp)


def get_all_ingredients() -> list[Ingredient]:
    """Return the latest price version for every ingredient."""
    return [get_ingredient(name) for name in _ingredients if get_ingredient(name) is not None]


def append_ingredient(ingredient: Ingredient) -> None:
    """Append a new price version (does not mutate prior rows)."""
    _ingredients.setdefault(ingredient.name, []).append(ingredient)


def get_ingredients_catalog() -> dict[str, Ingredient]:
    """Return a name → latest ingredient map for pricing lookups."""
    catalog: dict[str, Ingredient] = {}
    for name in _ingredients:
        latest = get_ingredient(name)
        if latest is not None:
            catalog[name] = latest
    return catalog


# --- Inventory (per player) ---

def get_inventory(user_id: str, ingredient_name: str) -> Optional[Inventory]:
    return _inventory.get(user_id, {}).get(ingredient_name)


def get_all_inventory(user_id: str) -> list[Inventory]:
    return list(_inventory.get(user_id, {}).values())


def set_inventory(user_id: str, entry: Inventory) -> None:
    _inventory.setdefault(user_id, {})[entry.ingredient_name] = entry


def clear_inventory(user_id: str) -> None:
    """Remove all on-hand stock entries for a player."""
    _inventory.pop(user_id, None)


# --- Lemonades (per-player menu) ---

def get_lemonade(user_id: str, name: str) -> Optional[Lemonade]:
    return _lemonades.get(user_id, {}).get(name)


def get_all_lemonades(user_id: str) -> list[Lemonade]:
    return list(_lemonades.get(user_id, {}).values())


def set_lemonade(user_id: str, lemonade: Lemonade) -> None:
    _lemonades.setdefault(user_id, {})[lemonade.name] = lemonade


def ensure_user_menu(user_id: str) -> None:
    """Clone seed menu templates onto a player if they have no menu yet."""
    if _lemonades.get(user_id):
        return
    for lemonade in _lemonade_templates:
        set_lemonade(user_id, lemonade.model_copy(deep=True))


# Load seed data on module import
_load_seed_data()
