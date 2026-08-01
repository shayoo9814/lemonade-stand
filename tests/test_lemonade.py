"""
Unit tests for lemonade recipe pricing consistency.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import Ingredient, IngredientUnit, Lemonade

SEED_TS = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _catalog() -> dict[str, Ingredient]:
    return {
        "lemons": Ingredient(
            id="ingredient-lemons",
            name="lemons",
            unit_price=Decimal("0.60"),
            unit=IngredientUnit.EACH,
            timestamp=SEED_TS,
        ),
        "sugar": Ingredient(
            id="ingredient-sugar",
            name="sugar",
            unit_price=Decimal("0.95"),
            unit=IngredientUnit.LB,
            timestamp=SEED_TS,
        ),
        "cups": Ingredient(
            id="ingredient-cups",
            name="cups",
            unit_price=Decimal("0.08"),
            unit=IngredientUnit.EACH,
            timestamp=SEED_TS,
        ),
        "ice": Ingredient(
            id="ingredient-ice",
            name="ice",
            unit_price=Decimal("0.10"),
            unit=IngredientUnit.CUP,
            timestamp=SEED_TS,
        ),
    }


class TestLemonadeRecipe:
    def test_recipe_cost_matches_ingredients(self):
        lemonade = Lemonade(
            id="lemonade-classic",
            name="classic",
            price=Decimal("2.00"),
            recipe={
                "lemons": Decimal("1"),
                "sugar": Decimal("0.05"),
                "cups": Decimal("1"),
                "ice": Decimal("1"),
            },
        )
        # 0.60 + 0.05*0.95 + 0.08 + 0.10 = 0.8275
        assert lemonade.recipe_cost(_catalog()) == Decimal("0.8275")

    def test_price_covering_recipe_passes(self):
        lemonade = Lemonade(
            id="lemonade-classic",
            name="classic",
            price=Decimal("2.00"),
            recipe={"lemons": Decimal("1"), "cups": Decimal("1")},
        )
        lemonade.ensure_price_covers_recipe(_catalog())

    def test_price_below_recipe_cost_raises(self):
        lemonade = Lemonade(
            id="lemonade-cheap",
            name="cheap",
            price=Decimal("0.50"),
            recipe={"lemons": Decimal("1"), "cups": Decimal("1")},
        )
        with pytest.raises(ValueError, match="below recipe cost"):
            lemonade.ensure_price_covers_recipe(_catalog())

    def test_unknown_ingredient_raises(self):
        lemonade = Lemonade(
            id="lemonade-mystery",
            name="mystery",
            price=Decimal("5.00"),
            recipe={"salt": Decimal("1")},
        )
        with pytest.raises(ValueError, match="unknown ingredient"):
            lemonade.recipe_cost(_catalog())

    def test_empty_recipe_rejected(self):
        with pytest.raises(ValidationError):
            Lemonade(id="lemonade-empty", name="empty", price=Decimal("1.00"), recipe={})

    def test_non_positive_recipe_amount_rejected(self):
        with pytest.raises(ValidationError):
            Lemonade(
                id="lemonade-bad",
                name="bad",
                price=Decimal("1.00"),
                recipe={"lemons": Decimal("0")},
            )
