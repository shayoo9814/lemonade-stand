"""
API-level tests for the lemonade stand game routes.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import ingredients as ingredients_service
from app import inventory as inventory_service
from app import users as users_service
from app.auth import USER_ID_HEADER
from app.database import get_ingredient, get_inventory, reset_db
from app.ledger import get_ledger, list_entries
from app.main import app
from app.models import IngredientUnit, LedgerAction

# classic seed price: $2.00 per serving (sale revenue; costs are on purchase rows)
CLASSIC_PRICE = Decimal("2.00")
LATER_TS = datetime(2026, 8, 15, tzinfo=timezone.utc)
USER_ID = "u1"
AUTH = {USER_ID_HEADER: USER_ID}


def _stock_classic(servings: int = 12) -> None:
    """Put enough classic-recipe ingredients on hand for ``servings`` sales."""
    inventory_service.add_stock("lemons", Decimal(servings))
    sugar = (Decimal(servings) * Decimal("0.05")).to_integral_value(rounding="ROUND_UP")
    inventory_service.add_stock("sugar", sugar)
    inventory_service.add_stock("cups", Decimal(servings))
    inventory_service.add_stock("ice", Decimal(servings))


@pytest.fixture(autouse=True)
def fresh_db():
    reset_db()
    users_service.ensure_opening_balance(USER_ID)
    yield


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthCheck:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestListIngredients:
    def test_list_ingredients(self, client):
        resp = client.get("/ingredients")
        assert resp.status_code == 200
        data = resp.json()
        by_name = {item["name"]: item for item in data}
        assert set(by_name) == {"lemons", "sugar", "cups", "ice"}
        assert by_name["lemons"]["unit"] == "each"
        assert by_name["lemons"]["amount"] == "1"
        assert by_name["lemons"]["id"] == "ingredient-lemons"
        assert by_name["lemons"]["timestamp"] == "2026-08-01T00:00:00Z"
        assert by_name["sugar"]["unit"] == "lb"
        assert by_name["sugar"]["id"] == "ingredient-sugar"
        assert by_name["cups"]["unit"] == "each"
        assert by_name["ice"]["unit"] == "cup"


class TestBuyIngredients:
    def test_buy_succeeds_and_updates_inventory_and_ledger(self, client):
        resp = client.post(
            "/ingredients/buy",
            headers=AUTH,
            json={"ingredient_name": "lemons", "unit_count": "10"},
        )
        assert resp.status_code == 200
        assert resp.json() is True

        # 10 units at $0.60/each → +10 inventory; cost $6.00
        lemons = get_inventory("lemons")
        assert lemons is not None
        assert lemons.amount == 10
        latest = get_ledger(USER_ID)
        assert latest is not None
        assert latest.current_capital == 24
        assert latest.expenses_incurred == 6
        assert latest.action == LedgerAction.PURCHASE
        assert latest.user_id == USER_ID
        assert latest.item_id == "ingredient-lemons"
        assert len(list_entries(USER_ID)) == 2
        assert len(users_service.get(USER_ID).general_ledger) == 2

    def test_buy_uses_unit_price_from_bulk_catalog(self, client):
        # Catalog: $4.75 for 5 lb → $0.95/lb; buy 2 units
        ingredients_service.record_price(
            name="sugar",
            amount=Decimal("5"),
            price=Decimal("4.75"),
            unit=IngredientUnit.LB,
            timestamp=LATER_TS,
        )

        resp = client.post(
            "/ingredients/buy",
            headers=AUTH,
            json={"ingredient_name": "sugar", "unit_count": "2"},
        )
        assert resp.status_code == 200
        assert resp.json() is True
        assert get_inventory("sugar").amount == 2
        assert get_ledger(USER_ID).current_capital == Decimal("28.10")
        assert get_ledger(USER_ID).expenses_incurred == Decimal("1.90")
        assert get_ingredient("sugar").amount == Decimal("5")
        assert get_ingredient("sugar").timestamp == LATER_TS

    def test_buy_unknown_ingredient_fails(self, client):
        resp = client.post(
            "/ingredients/buy",
            headers=AUTH,
            json={"ingredient_name": "salt", "unit_count": "1"},
        )
        assert resp.status_code == 200
        assert resp.json() is False

    def test_buy_unknown_user_unauthorized(self, client):
        resp = client.post(
            "/ingredients/buy",
            headers={USER_ID_HEADER: "missing"},
            json={"ingredient_name": "lemons", "unit_count": "1"},
        )
        assert resp.status_code == 401

    def test_buy_with_insufficient_capital_fails(self, client):
        before_len = len(list_entries(USER_ID))
        resp = client.post(
            "/ingredients/buy",
            headers=AUTH,
            json={"ingredient_name": "sugar", "unit_count": "200"},
        )
        assert resp.status_code == 200
        assert resp.json() is False
        assert get_ledger(USER_ID).current_capital == 30
        assert get_inventory("sugar") is None
        assert len(list_entries(USER_ID)) == before_len


class TestSellLemonade:
    def test_sell_succeeds_and_updates_inventory_and_ledger(self, client):
        _stock_classic(12)
        resp = client.post(
            "/lemonades/sell",
            headers=AUTH,
            json={"name": "classic", "amount": "1"},
        )
        assert resp.status_code == 200
        assert resp.json() is True

        assert get_inventory("lemons").amount == 11
        assert get_inventory("sugar").amount == Decimal("0.95")
        assert get_inventory("cups").amount == 11
        assert get_inventory("ice").amount == 11

        latest = get_ledger(USER_ID)
        assert latest is not None
        assert latest.current_capital == Decimal("30") + CLASSIC_PRICE
        assert latest.expenses_incurred == 0
        assert latest.action == LedgerAction.SALE
        assert latest.user_id == USER_ID
        assert latest.amount == CLASSIC_PRICE
        assert latest.item_id == "lemonade-classic"
        assert len(list_entries(USER_ID)) == 2
        assert users_service.get(USER_ID).general_ledger[-1].action == LedgerAction.SALE

    def test_sell_multiple_servings(self, client):
        _stock_classic(12)
        resp = client.post(
            "/lemonades/sell",
            headers=AUTH,
            json={"name": "classic", "amount": "3"},
        )
        assert resp.status_code == 200
        assert resp.json() is True

        assert get_inventory("lemons").amount == 9
        assert get_inventory("sugar").amount == Decimal("0.85")
        assert get_inventory("cups").amount == 9
        assert get_inventory("ice").amount == 9
        assert get_ledger(USER_ID).current_capital == Decimal("30") + CLASSIC_PRICE * 3
        assert get_ledger(USER_ID).amount == CLASSIC_PRICE * 3
        assert len(list_entries(USER_ID)) == 2

    def test_sell_unknown_lemonade_fails(self, client):
        resp = client.post(
            "/lemonades/sell",
            headers=AUTH,
            json={"name": "mango", "amount": "1"},
        )
        assert resp.status_code == 200
        assert resp.json() is False
        assert get_ledger(USER_ID).current_capital == 30

    def test_sell_with_insufficient_stock_fails(self, client):
        _stock_classic(12)
        # Drain all 12 lemons in one sale, then another sale must fail
        assert client.post(
            "/lemonades/sell",
            headers=AUTH,
            json={"name": "classic", "amount": "12"},
        ).json() is True

        resp = client.post(
            "/lemonades/sell",
            headers=AUTH,
            json={"name": "classic", "amount": "1"},
        )
        assert resp.status_code == 200
        assert resp.json() is False
        assert get_inventory("lemons").amount == 0
        assert get_ledger(USER_ID).current_capital == Decimal("30") + CLASSIC_PRICE * 12
        # opening + one bulk sale
        assert len(list_entries(USER_ID)) == 2


class TestGameRoutes:
    def test_start_and_get_game(self, client):
        # Pre-stock so we can prove start clears inventory
        _stock_classic(3)
        resp = client.post("/game/start", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == USER_ID
        assert data["day"] == 1
        assert data["hour"] == 0
        assert data["phase"] == "day_start"
        assert get_ledger(USER_ID).current_capital == Decimal("30.00")
        assert client.get("/inventory").json() == []

        got = client.get("/game", headers=AUTH)
        assert got.status_code == 200
        assert got.json()["phase"] == "day_start"

    def test_continue_day(self, client):
        client.post("/game/start", headers=AUTH)
        client.post(
            "/ingredients/buy",
            headers=AUTH,
            json={"ingredient_name": "lemons", "unit_count": "1"},
        )
        resp = client.post("/game/continue", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["phase"] == "running"

    def test_set_lemonade_price(self, client):
        client.post("/game/start", headers=AUTH)
        resp = client.post(
            "/lemonades/price",
            headers=AUTH,
            json={"name": "classic", "price": "2.50"},
        )
        assert resp.status_code == 200
        assert resp.json() is True


class TestInventoryAndCapital:
    def test_list_inventory(self, client):
        resp = client.get("/inventory")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_auth_me(self, client):
        resp = client.get("/auth/me", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == {
            "id": USER_ID,
            "name": "Sungho Yoo",
            "email": "shayoo9814@gmail.com",
        }

    def test_auth_me_without_header_uses_seeded_player(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 200
        assert resp.json()["id"] == USER_ID

    def test_get_capital(self, client):
        resp = client.get("/users/capital", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == {"user_id": USER_ID, "current_capital": "30.00"}

    def test_list_ledger(self, client):
        resp = client.get("/users/ledger", headers=AUTH)
        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) == 1
        assert entries[0]["user_id"] == USER_ID
        assert entries[0]["action"] == "opening_balance"
        assert entries[0]["amount"] == "30.00"
        assert entries[0]["current_capital"] == "30.00"
        assert entries[0]["expenses_incurred"] == "0"
        assert entries[0]["item_id"] == "opening-balance"

        client.post(
            "/ingredients/buy",
            headers=AUTH,
            json={"ingredient_name": "lemons", "unit_count": "1"},
        )
        entries = client.get("/users/ledger", headers=AUTH).json()
        assert len(entries) == 2
        assert entries[1]["action"] == "purchase"
        assert entries[1]["amount"] == "0.60"
        assert entries[1]["current_capital"] == "29.40"
        assert entries[1]["expenses_incurred"] == "0.60"
        assert entries[1]["item_id"] == "ingredient-lemons"

    def test_clear_ledger(self, client):
        client.post(
            "/ingredients/buy",
            headers=AUTH,
            json={"ingredient_name": "lemons", "unit_count": "1"},
        )
        assert len(client.get("/users/ledger", headers=AUTH).json()) == 2

        resp = client.delete("/users/ledger", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == []
        assert client.get("/users/ledger", headers=AUTH).json() == []
        assert client.get("/users/capital", headers=AUTH).status_code == 404
        assert users_service.get(USER_ID).general_ledger == []

    def test_list_ledger_empty_without_opening(self, client):
        from app.ledger import clear_all

        clear_all()
        resp = client.get("/users/ledger", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_capital_without_ledger(self, client):
        from app.ledger import clear_all

        clear_all()
        resp = client.get("/users/capital", headers=AUTH)
        assert resp.status_code == 404

    def test_ensure_opening_balance(self, client):
        from app.ledger import clear_all, get_ledger

        clear_all()
        resp = client.post("/users/opening-balance", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == {"user_id": USER_ID, "current_capital": "30.00"}
        assert get_ledger(USER_ID).current_capital == Decimal("30.00")

        # Idempotent — does not reset an existing ledger
        client.post(
            "/ingredients/buy",
            headers=AUTH,
            json={"ingredient_name": "lemons", "unit_count": "1"},
        )
        resp = client.post("/users/opening-balance", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["current_capital"] == "29.40"

    def test_ui_index(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Lemonade Stand" in resp.text
        assert "How a day works" in resp.text
        assert 'href="/play"' in resp.text
        assert 'id="player-line"' not in resp.text

    def test_ui_play(self, client):
        resp = client.get("/play")
        assert resp.status_code == 200
        assert "Lemonade Stand" in resp.text
        assert 'id="player-line"' in resp.text
        assert 'href="/ledger"' in resp.text

    def test_ui_ledger(self, client):
        resp = client.get("/ledger")
        assert resp.status_code == 200
        assert "General ledger" in resp.text
        assert 'id="ledger-body"' in resp.text
        assert 'id="btn-clear-ledger"' in resp.text
        assert 'href="/play"' in resp.text
