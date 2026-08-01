"""
Inventory application layer.

Owns stock mutation rules for a single player's stand. Persistence is
delegated to ``app.database``.
"""

from decimal import Decimal

from app import database as db
from app.models import IngredientUnit, Inventory

# Ingredients that melt / spoil overnight and cannot carry to the next day.
PERISHABLE_INGREDIENTS = frozenset({"ice"})


def get(user_id: str, ingredient_name: str) -> Inventory | None:
    """Return on-hand stock for an ingredient, or None if missing."""
    return db.get_inventory(user_id, ingredient_name)


def list_all(user_id: str) -> list[Inventory]:
    """Return all inventory entries for a player."""
    return db.get_all_inventory(user_id)


def _unit_for(ingredient_name: str, current: Inventory | None) -> IngredientUnit:
    """Resolve the display unit from the catalog, or keep an existing entry's unit."""
    ingredient = db.get_ingredient(ingredient_name)
    if ingredient is not None:
        return ingredient.unit
    if current is not None:
        return current.unit
    raise ValueError(f"unknown ingredient: {ingredient_name}")


def add_stock(user_id: str, ingredient_name: str, amount: Decimal) -> Inventory:
    """Increase on-hand stock and return the updated entry."""
    if amount <= 0:
        raise ValueError("amount to add must be positive")
    current = db.get_inventory(user_id, ingredient_name)
    on_hand = current.amount if current is not None else Decimal("0")
    entry = Inventory(
        ingredient_name=ingredient_name,
        amount=on_hand + amount,
        unit=_unit_for(ingredient_name, current),
    )
    db.set_inventory(user_id, entry)
    return entry


def has_sufficient(user_id: str, requirements: dict[str, Decimal]) -> bool:
    """Return True when every required ingredient amount is on hand."""
    for ingredient_name, required in requirements.items():
        entry = db.get_inventory(user_id, ingredient_name)
        if entry is None or entry.amount < required:
            return False
    return True


def deduct(user_id: str, requirements: dict[str, Decimal]) -> bool:
    """Deduct recipe amounts from inventory. Returns False if stock is short."""
    if not has_sufficient(user_id, requirements):
        return False
    for ingredient_name, required in requirements.items():
        entry = db.get_inventory(user_id, ingredient_name)
        assert entry is not None  # guaranteed by has_sufficient
        db.set_inventory(
            user_id,
            Inventory(
                ingredient_name=entry.ingredient_name,
                amount=entry.amount - required,
                unit=entry.unit,
            ),
        )
    return True


def clear_all(user_id: str) -> None:
    """Remove every inventory entry for a player (used when starting a new game)."""
    db.clear_inventory(user_id)


def discard_perishables(user_id: str) -> None:
    """Zero ingredients that cannot carry over to the next day (e.g. ice)."""
    for name in PERISHABLE_INGREDIENTS:
        entry = db.get_inventory(user_id, name)
        if entry is None:
            continue
        db.set_inventory(
            user_id,
            Inventory(
                ingredient_name=entry.ingredient_name,
                amount=Decimal("0"),
                unit=entry.unit,
            ),
        )


def can_make_lemonade(user_id: str) -> bool:
    """Return True when on-hand stock covers at least one lemonade recipe."""
    db.ensure_user_menu(user_id)
    for lemonade in db.get_all_lemonades(user_id):
        if has_sufficient(user_id, lemonade.recipe):
            return True
    return False
