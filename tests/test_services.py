"""
Unit tests for inventory and ingredient application layers.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app import ingredients as ingredients_service
from app import inventory as inventory_service
from app import users as users_service
from app.database import get_ingredient_history, reset_db
from app.ledger import get_ledger, list_entries
from app.models import IngredientUnit, LedgerAction

SEED_TS = datetime(2026, 8, 1, tzinfo=timezone.utc)
LATER_TS = datetime(2026, 8, 15, tzinfo=timezone.utc)
USER_ID = "u1"


@pytest.fixture(autouse=True)
def fresh_state():
    reset_db()
    users_service.ensure_opening_balance(USER_ID)
    yield


class TestInventoryService:
    def test_add_stock_increases_on_hand(self):
        entry = inventory_service.add_stock("lemons", Decimal("3"))
        assert entry.amount == Decimal("3")
        assert inventory_service.get("lemons").amount == Decimal("3")

    def test_has_sufficient_and_deduct(self):
        inventory_service.add_stock("lemons", Decimal("12"))
        inventory_service.add_stock("cups", Decimal("50"))
        assert inventory_service.has_sufficient({"lemons": Decimal("2"), "cups": Decimal("1")})
        assert inventory_service.deduct({"lemons": Decimal("2"), "cups": Decimal("1")})
        assert inventory_service.get("lemons").amount == Decimal("10")
        assert inventory_service.get("cups").amount == Decimal("49")

    def test_deduct_fails_when_short(self):
        inventory_service.add_stock("lemons", Decimal("12"))
        assert inventory_service.deduct({"lemons": Decimal("100")}) is False
        assert inventory_service.get("lemons").amount == Decimal("12")


class TestIngredientsService:
    def test_buy_updates_inventory_and_player_ledger(self):
        assert ingredients_service.buy(USER_ID, "lemons", unit_count=Decimal("10")) is True
        assert inventory_service.get("lemons").amount == Decimal("10")
        latest = get_ledger(USER_ID)
        assert latest is not None
        assert latest.current_capital == Decimal("24")
        assert latest.expenses_incurred == Decimal("6")
        assert latest.action == LedgerAction.PURCHASE
        assert latest.user_id == USER_ID
        assert latest.item_id == "ingredient-lemons"
        assert len(list_entries(USER_ID)) == 2

        user = users_service.get(USER_ID)
        assert user is not None
        assert len(user.general_ledger) == 2
        assert user.general_ledger[-1].current_capital == Decimal("24")

    def test_buy_uses_unit_price_from_bulk_catalog(self):
        ingredients_service.record_price(
            name="sugar",
            amount=Decimal("5"),
            price=Decimal("4.75"),
            unit=IngredientUnit.LB,
            timestamp=LATER_TS,
        )
        assert ingredients_service.buy(USER_ID, "sugar", unit_count=Decimal("2")) is True
        # 2 units × ($4.75 / 5) = $1.90; inventory +2
        assert inventory_service.get("sugar").amount == Decimal("2")
        assert get_ledger(USER_ID).current_capital == Decimal("28.10")

    def test_buy_unknown_ingredient_fails(self):
        assert ingredients_service.buy(USER_ID, "salt", unit_count=Decimal("1")) is False

    def test_buy_unknown_user_fails(self):
        assert ingredients_service.buy("missing", "lemons", unit_count=Decimal("1")) is False

    def test_record_price_appends_history(self):
        ingredients_service.record_price(
            name="lemons",
            amount=Decimal("1"),
            price=Decimal("0.75"),
            unit=IngredientUnit.EACH,
            timestamp=LATER_TS,
        )
        history = get_ingredient_history("lemons")
        assert len(history) == 2
        assert history[0].price == Decimal("0.60")
        assert history[1].price == Decimal("0.75")
        assert ingredients_service.get("lemons").price == Decimal("0.75")
