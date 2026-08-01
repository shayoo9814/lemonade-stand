"""
Unit tests for the game simulation layer.
"""

from decimal import Decimal

import pytest

from app import game as game_service
from app import ingredients as ingredients_service
from app import inventory as inventory_service
from app import lemonades as lemonades_service
from app.database import get_inventory, reset_db, set_user
from app.ledger import get_ledger, list_entries
from app.models import GamePhase, LedgerAction, User

USER_ID = "u1"
USER_ID_2 = "u2"
CLASSIC_PRICE = Decimal("2.00")


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
        assert not inventory_service.can_make_lemonade(USER_ID)
        assert inventory_service.list_all(USER_ID) == []

    def test_first_start_seeds_opening_without_reset(self):
        session = game_service.start_game(USER_ID)
        assert session is not None
        entries = list_entries(USER_ID)
        assert len(entries) == 1
        assert entries[0].action == LedgerAction.OPENING_BALANCE
        assert entries[0].amount == Decimal("30.00")
        assert entries[0].current_capital == Decimal("30.00")
        assert get_ledger(USER_ID).current_capital == Decimal("30.00")

    def test_start_appends_reset_then_opening_without_erasing_history(self):
        game_service.start_game(USER_ID)
        assert ingredients_service.buy(USER_ID, "lemons", unit_count=Decimal("1")) is True
        # reset skipped (no prior) + opening + purchase
        assert len(list_entries(USER_ID)) == 2
        capital_before_reset = get_ledger(USER_ID).current_capital
        assert capital_before_reset == Decimal("29.40")

        game_service.start_game(USER_ID)
        entries = list_entries(USER_ID)
        # opening + purchase + reset-ledger + opening
        assert len(entries) == 4
        assert entries[0].action == LedgerAction.OPENING_BALANCE
        assert entries[1].action == LedgerAction.PURCHASE
        assert entries[2].action == LedgerAction.RESET_LEDGER
        assert entries[2].item_id == "reset-ledger"
        assert entries[2].amount == capital_before_reset
        assert entries[2].current_capital == Decimal("0")
        assert entries[2].expenses_incurred == Decimal("0")
        assert entries[3].action == LedgerAction.OPENING_BALANCE
        assert entries[3].amount == Decimal("30.00")
        assert entries[3].current_capital == Decimal("30.00")
        assert get_ledger(USER_ID).current_capital == Decimal("30.00")

    def test_start_unknown_user_returns_none(self):
        assert game_service.start_game("missing") is None

    def test_start_does_not_clear_other_players(self):
        set_user(User(id=USER_ID_2, name="Other", email="other@example.com"))
        game_service.start_game(USER_ID)
        ingredients_service.buy(USER_ID, "lemons", Decimal("5"))
        lemonades_service.set_price(USER_ID, "classic", Decimal("3.00"))

        game_service.start_game(USER_ID_2)

        assert game_service.get_session(USER_ID) is not None
        assert game_service.get_session(USER_ID).phase == GamePhase.DAY_START
        assert get_inventory(USER_ID, "lemons").amount == Decimal("5")
        assert lemonades_service.get(USER_ID, "classic").price == Decimal("3.00")
        assert inventory_service.list_all(USER_ID_2) == []
        assert get_ledger(USER_ID_2).current_capital == Decimal("30.00")


class TestDayStartActions:
    def test_buy_and_set_price_allowed_at_day_start(self):
        game_service.start_game(USER_ID)
        assert ingredients_service.buy(USER_ID, "lemons", Decimal("10")) is True
        assert lemonades_service.set_price(USER_ID, "classic", Decimal("2.50")) is True
        assert get_inventory(USER_ID, "lemons").amount == Decimal("10")
        assert lemonades_service.get(USER_ID, "classic").price == Decimal("2.50")

    def test_buy_and_set_price_blocked_while_running(self):
        game_service.start_game(USER_ID)
        ingredients_service.buy(USER_ID, "lemons", Decimal("12"))
        ingredients_service.buy(USER_ID, "sugar", Decimal("1"))
        ingredients_service.buy(USER_ID, "cups", Decimal("12"))
        ingredients_service.buy(USER_ID, "ice", Decimal("12"))
        game_service.continue_day(USER_ID)

        assert ingredients_service.buy(USER_ID, "lemons", Decimal("1")) is False
        assert lemonades_service.set_price(USER_ID, "classic", Decimal("3.00")) is False
        assert lemonades_service.get(USER_ID, "classic").price == Decimal("2.00")

    def test_set_price_allows_zero_and_below_recipe_cost(self):
        game_service.start_game(USER_ID)
        # classic recipe cost is 0.8275 — below-cost and free pricing are allowed
        assert lemonades_service.set_price(USER_ID, "classic", Decimal("0.50")) is True
        assert lemonades_service.get(USER_ID, "classic").price == Decimal("0.50")
        assert lemonades_service.set_price(USER_ID, "classic", Decimal("0")) is True
        assert lemonades_service.get(USER_ID, "classic").price == Decimal("0")

    def test_set_price_is_per_player(self):
        set_user(User(id=USER_ID_2, name="Other", email="other@example.com"))
        game_service.start_game(USER_ID)
        game_service.start_game(USER_ID_2)
        assert lemonades_service.set_price(USER_ID, "classic", Decimal("4.00")) is True
        assert lemonades_service.get(USER_ID, "classic").price == Decimal("4.00")
        assert lemonades_service.get(USER_ID_2, "classic").price == Decimal("2.00")


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
        assert get_inventory(USER_ID, "lemons").amount == Decimal("11")
        assert get_ledger(USER_ID).current_capital == capital_after_buy + CLASSIC_PRICE

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
        assert get_inventory(USER_ID, "ice").amount == Decimal("5")
        assert get_inventory(USER_ID, "lemons").amount == Decimal("0")

        session = game_service.tick(USER_ID)
        assert session.phase == GamePhase.DAY_START
        assert session.day == 2
        assert get_inventory(USER_ID, "ice").amount == Decimal("0")

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
        assert get_inventory(USER_ID, "ice").amount == Decimal("0")
        assert get_inventory(USER_ID, "lemons").amount == Decimal("6")
        assert get_inventory(USER_ID, "cups").amount == Decimal("6")

    def test_bankruptcy_when_no_capital_and_cannot_make_lemonade(self):
        game_service.start_game(USER_ID)
        # Spend all capital on cups only — cannot make classic lemonade
        assert ingredients_service.buy(USER_ID, "cups", Decimal("375")) is True
        assert get_ledger(USER_ID).current_capital == Decimal("0")
        assert get_inventory(USER_ID, "cups").amount == Decimal("375")
        assert not inventory_service.can_make_lemonade(USER_ID)

        game_service.continue_day(USER_ID)
        session = game_service.tick(USER_ID)
        assert session.phase == GamePhase.GAME_OVER

    def test_bankruptcy_when_only_ice_remains(self):
        game_service.start_game(USER_ID)
        assert ingredients_service.buy(USER_ID, "ice", Decimal("300")) is True
        assert get_ledger(USER_ID).current_capital == Decimal("0")
        assert get_inventory(USER_ID, "ice").amount == Decimal("300")

        game_service.continue_day(USER_ID)
        session = game_service.tick(USER_ID)
        assert session.phase == GamePhase.GAME_OVER
        assert get_inventory(USER_ID, "ice").amount == Decimal("0")
