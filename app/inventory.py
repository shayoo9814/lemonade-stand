"""
Inventory application layer.

Owns stock mutation rules. Persistence is delegated to ``app.database``.
"""

from decimal import Decimal

from app import database as db
from app.models import IngredientUnit, Inventory

# Ingredients that melt / spoil overnight and cannot carry to the next day.
PERISHABLE_INGREDIENTS = frozenset({"ice"})


def get(ingredient_name: str) -> Inventory | None:
    """Return on-hand stock for an ingredient, or None if missing."""
    return db.get_inventory(ingredient_name)


def list_all() -> list[Inventory]:
    """Return all inventory entries."""
    return db.get_all_inventory()


def _unit_for(ingredient_name: str, current: Inventory | None) -> IngredientUnit:
    """Resolve the display unit from the catalog, or keep an existing entry's unit."""
    ingredient = db.get_ingredient(ingredient_name)
    if ingredient is not None:
        return ingredient.unit
    if current is not None:
        return current.unit
    raise ValueError(f"unknown ingredient: {ingredient_name}")


def add_stock(ingredient_name: str, amount: Decimal) -> Inventory:
    """Increase on-hand stock and return the updated entry."""
    if amount <= 0:
        raise ValueError("amount to add must be positive")
    current = db.get_inventory(ingredient_name)
    on_hand = current.amount if current is not None else Decimal("0")
    entry = Inventory(
        ingredient_name=ingredient_name,
        amount=on_hand + amount,
        unit=_unit_for(ingredient_name, current),
    )
    db.set_inventory(entry)
    return entry


def has_sufficient(requirements: dict[str, Decimal]) -> bool:
    """Return True when every required ingredient amount is on hand."""
    for ingredient_name, required in requirements.items():
        entry = db.get_inventory(ingredient_name)
        if entry is None or entry.amount < required:
            return False
    return True


def deduct(requirements: dict[str, Decimal]) -> bool:
    """Deduct recipe amounts from inventory. Returns False if stock is short."""
    if not has_sufficient(requirements):
        return False
    for ingredient_name, required in requirements.items():
        entry = db.get_inventory(ingredient_name)
        assert entry is not None  # guaranteed by has_sufficient
        db.set_inventory(
            Inventory(
                ingredient_name=entry.ingredient_name,
                amount=entry.amount - required,
                unit=entry.unit,
            )
        )
    return True


def clear_all() -> None:
    """Remove every inventory entry (used when starting a new game)."""
    db.clear_inventory()


def discard_perishables() -> None:
    """Zero ingredients that cannot carry over to the next day (e.g. ice)."""
    for name in PERISHABLE_INGREDIENTS:
        entry = db.get_inventory(name)
        if entry is None:
            continue
        db.set_inventory(
            Inventory(
                ingredient_name=entry.ingredient_name,
                amount=Decimal("0"),
                unit=entry.unit,
            )
        )


def can_make_lemonade() -> bool:
    """Return True when on-hand stock covers at least one lemonade recipe."""
    for lemonade in db.get_all_lemonades():
        if has_sufficient(lemonade.recipe):
            return True
    return False
