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
            name="lemons",
            amount=Decimal("1"),
            price=Decimal("0.60"),
            unit=IngredientUnit.EACH,
            timestamp=SEED_TS,
        ),
        "sugar": Ingredient(
            name="sugar",
            amount=Decimal("1"),
            price=Decimal("0.95"),
            unit=IngredientUnit.LB,
            timestamp=SEED_TS,
        ),
        "cups": Ingredient(
            name="cups",
            amount=Decimal("1"),
            price=Decimal("0.08"),
            unit=IngredientUnit.EACH,
            timestamp=SEED_TS,
        ),
        "ice": Ingredient(
            name="ice",
            amount=Decimal("1"),
            price=Decimal("0.10"),
            unit=IngredientUnit.CUP,
            timestamp=SEED_TS,
        ),
    }


class TestIngredientBulkPricing:
    def test_unit_price_divides_bulk_pack(self):
        sugar = Ingredient(
            name="sugar",
            amount=Decimal("5"),
            price=Decimal("4.75"),
            unit=IngredientUnit.LB,
            timestamp=SEED_TS,
        )
        assert sugar.unit_price == Decimal("0.95")

    def test_recipe_cost_uses_unit_price(self):
        catalog = {
            "sugar": Ingredient(
                name="sugar",
                amount=Decimal("5"),
                price=Decimal("4.75"),
                unit=IngredientUnit.LB,
                timestamp=SEED_TS,
            ),
        }
        lemonade = Lemonade(
            name="sweet",
            price=Decimal("2.00"),
            recipe={"sugar": Decimal("0.05")},
        )
        # 0.05 lb * ($4.75 / 5 lb) = 0.0475
        assert lemonade.recipe_cost(catalog) == Decimal("0.0475")


class TestLemonadeRecipe:
    def test_recipe_cost_matches_ingredients(self):
        lemonade = Lemonade(
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
            name="classic",
            price=Decimal("2.00"),
            recipe={"lemons": Decimal("1"), "cups": Decimal("1")},
        )
        lemonade.ensure_price_covers_recipe(_catalog())

    def test_price_below_recipe_cost_raises(self):
        lemonade = Lemonade(
            name="cheap",
            price=Decimal("0.50"),
            recipe={"lemons": Decimal("1"), "cups": Decimal("1")},
        )
        with pytest.raises(ValueError, match="below recipe cost"):
            lemonade.ensure_price_covers_recipe(_catalog())

    def test_unknown_ingredient_raises(self):
        lemonade = Lemonade(
            name="mystery",
            price=Decimal("5.00"),
            recipe={"salt": Decimal("1")},
        )
        with pytest.raises(ValueError, match="unknown ingredient"):
            lemonade.recipe_cost(_catalog())

    def test_empty_recipe_rejected(self):
        with pytest.raises(ValidationError):
            Lemonade(name="empty", price=Decimal("1.00"), recipe={})

    def test_non_positive_recipe_amount_rejected(self):
        with pytest.raises(ValidationError):
            Lemonade(
                name="bad",
                price=Decimal("1.00"),
                recipe={"lemons": Decimal("0")},
            )
