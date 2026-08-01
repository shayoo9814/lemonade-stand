"""
Unit tests for the game simulation layer.
"""

from decimal import Decimal

import pytest

from app import game as game_service
from app import ingredients as ingredients_service
from app import inventory as inventory_service
from app import lemonades as lemonades_service
from app.database import get_inventory, reset_db
from app.ledger import get_ledger, list_entries
from app.models import GamePhase, LedgerAction

USER_ID = "u1"
CLASSIC_PROFIT = Decimal("1.1725")


@pytest.fixture(autouse=True)
def fresh_state():
    reset_db()
    yield


class TestStartGame:
    def test_start_sets_seed_capital_empty_stock_and_day_start(self):
        session = game_service.start_game(USER_ID)
        assert session is not None
        assert session.day == 1
        assert session.hour == 0
        assert session.phase == GamePhase.DAY_START
        assert get_ledger(USER_ID).current_capital == Decimal("30.00")
        assert not inventory_service.can_make_lemonade()
        assert inventory_service.list_all() == []

    def test_start_appends_opening_balance_without_erasing_history(self):
        game_service.start_game(USER_ID)
        assert ingredients_service.buy(USER_ID, "lemons", unit_count=Decimal("1")) is True
        assert len(list_entries(USER_ID)) == 2

        game_service.start_game(USER_ID)
        entries = list_entries(USER_ID)
        assert len(entries) == 3
        assert entries[0].action == LedgerAction.OPENING_BALANCE
        assert entries[1].action == LedgerAction.PURCHASE
        assert entries[2].action == LedgerAction.OPENING_BALANCE
        assert entries[2].current_capital == Decimal("30.00")
        assert get_ledger(USER_ID).current_capital == Decimal("30.00")

    def test_start_unknown_user_returns_none(self):
        assert game_service.start_game("missing") is None


class TestDayStartActions:
    def test_buy_and_set_price_allowed_at_day_start(self):
        game_service.start_game(USER_ID)
        assert ingredients_service.buy(USER_ID, "lemons", Decimal("10")) is True
        assert lemonades_service.set_price(USER_ID, "classic", Decimal("2.50")) is True
        assert get_inventory("lemons").amount == Decimal("10")
        assert lemonades_service.get("classic").price == Decimal("2.50")

    def test_buy_and_set_price_blocked_while_running(self):
        game_service.start_game(USER_ID)
        ingredients_service.buy(USER_ID, "lemons", Decimal("12"))
        ingredients_service.buy(USER_ID, "sugar", Decimal("1"))
        ingredients_service.buy(USER_ID, "cups", Decimal("12"))
        ingredients_service.buy(USER_ID, "ice", Decimal("12"))
        game_service.continue_day(USER_ID)

        assert ingredients_service.buy(USER_ID, "lemons", Decimal("1")) is False
        assert lemonades_service.set_price(USER_ID, "classic", Decimal("3.00")) is False
        assert lemonades_service.get("classic").price == Decimal("2.00")

    def test_set_price_allows_zero_and_below_recipe_cost(self):
        game_service.start_game(USER_ID)
        # classic recipe cost is 0.8275 — below-cost and free pricing are allowed
        assert lemonades_service.set_price(USER_ID, "classic", Decimal("0.50")) is True
        assert lemonades_service.get("classic").price == Decimal("0.50")
        assert lemonades_service.set_price(USER_ID, "classic", Decimal("0")) is True
        assert lemonades_service.get("classic").price == Decimal("0")


class TestContinueAndTick:
    def _stock_for_sales(self, servings: int = 12) -> None:
        ingredients_service.buy(USER_ID, "lemons", Decimal(servings))
        # classic uses 0.05 lb sugar per serving
        sugar_units = (Decimal(servings) * Decimal("0.05")).to_integral_value(
            rounding="ROUND_UP"
        )
        ingredients_service.buy(USER_ID, "sugar", sugar_units)
        ingredients_service.buy(USER_ID, "cups", Decimal(servings))
        ingredients_service.buy(USER_ID, "ice", Decimal(servings))

    def test_continue_starts_running_day(self):
        game_service.start_game(USER_ID)
        self._stock_for_sales()
        session = game_service.continue_day(USER_ID)
        assert session is not None
        assert session.phase == GamePhase.RUNNING
        assert session.day == 1
        assert session.hour == 0

    def test_tick_noops_during_day_start(self):
        game_service.start_game(USER_ID)
        session = game_service.tick(USER_ID)
        assert session is not None
        assert session.phase == GamePhase.DAY_START
        assert session.hour == 0

    def test_tick_autosells_and_advances_hour(self):
        game_service.start_game(USER_ID)
        self._stock_for_sales()
        capital_after_buy = get_ledger(USER_ID).current_capital
        game_service.continue_day(USER_ID)

        session = game_service.tick(USER_ID)
        assert session is not None
        assert session.hour == 1
        assert session.phase == GamePhase.RUNNING
        assert get_inventory("lemons").amount == Decimal("11")
        assert get_ledger(USER_ID).current_capital == capital_after_buy + CLASSIC_PROFIT

    def test_stock_exhaustion_ends_day(self):
        game_service.start_game(USER_ID)
        self._stock_for_sales(servings=1)
        game_service.continue_day(USER_ID)

        # First tick sells the only serving; second cannot sell → EOD
        assert game_service.tick(USER_ID).phase == GamePhase.RUNNING
        session = game_service.tick(USER_ID)
        assert session.phase == GamePhase.DAY_START
        assert session.day == 2

    def test_hour_24_ends_day(self):
        game_service.start_game(USER_ID)
        self._stock_for_sales(servings=24)
        game_service.continue_day(USER_ID)

        for _ in range(23):
            session = game_service.tick(USER_ID)
            assert session.phase == GamePhase.RUNNING

        session = game_service.tick(USER_ID)
        assert session.hour == 0
        assert session.phase == GamePhase.DAY_START
        assert session.day == 2

    def test_ice_does_not_carry_to_next_day(self):
        game_service.start_game(USER_ID)
        self._stock_for_sales(servings=1)
        # Extra ice beyond what the day's sale will use
        ingredients_service.buy(USER_ID, "ice", Decimal("5"))
        game_service.continue_day(USER_ID)

        # Sell the only possible serving; leftover ice remains until EOD
        assert game_service.tick(USER_ID).phase == GamePhase.RUNNING
        assert get_inventory("ice").amount == Decimal("5")
        assert get_inventory("lemons").amount == Decimal("0")

        session = game_service.tick(USER_ID)
        assert session.phase == GamePhase.DAY_START
        assert session.day == 2
        assert get_inventory("ice").amount == Decimal("0")

    def test_non_perishables_carry_when_day_ends_at_hour_24(self):
        game_service.start_game(USER_ID)
        self._stock_for_sales(servings=30)
        game_service.continue_day(USER_ID)

        for _ in range(24):
            game_service.tick(USER_ID)

        session = game_service.get_session(USER_ID)
        assert session is not None
        assert session.phase == GamePhase.DAY_START
        assert session.day == 2
        assert get_inventory("ice").amount == Decimal("0")
        assert get_inventory("lemons").amount == Decimal("6")
        assert get_inventory("cups").amount == Decimal("6")

    def test_bankruptcy_when_no_capital_and_cannot_make_lemonade(self):
        game_service.start_game(USER_ID)
        # Spend all capital on cups only — cannot make classic lemonade
        assert ingredients_service.buy(USER_ID, "cups", Decimal("375")) is True
        assert get_ledger(USER_ID).current_capital == Decimal("0")
        assert get_inventory("cups").amount == Decimal("375")
        assert not inventory_service.can_make_lemonade()

        game_service.continue_day(USER_ID)
        session = game_service.tick(USER_ID)
        assert session.phase == GamePhase.GAME_OVER

    def test_bankruptcy_when_only_ice_remains(self):
        game_service.start_game(USER_ID)
        assert ingredients_service.buy(USER_ID, "ice", Decimal("300")) is True
        assert get_ledger(USER_ID).current_capital == Decimal("0")
        assert get_inventory("ice").amount == Decimal("300")

        game_service.continue_day(USER_ID)
        session = game_service.tick(USER_ID)
        assert session.phase == GamePhase.GAME_OVER
        assert get_inventory("ice").amount == Decimal("0")
