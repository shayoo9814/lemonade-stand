"""
API routes for the lemonade stand game.

Handlers stay thin: validate request shapes, then delegate to entity modules.
Identity comes from the ``X-User-Id`` header via ``app.auth``.
"""

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.auth import CurrentUser
from app import game as game_service
from app import ingredients as ingredients_service
from app import inventory as inventory_service
from app import lemonades as lemonades_service
from app import ledger as ledger_store
from app import users as users_service
from app.models import GameSession, Ingredient, Inventory, User
from app.requests import (
    BuyIngredientsRequest,
    SellLemonadeRequest,
    SetLemonadePriceRequest,
)

router = APIRouter()


class UserIdentityResponse(BaseModel):
    id: str
    name: str
    email: str


class CapitalResponse(BaseModel):
    user_id: str
    current_capital: Decimal


def _identity(user: User) -> UserIdentityResponse:
    return UserIdentityResponse(id=user.id, name=user.name, email=user.email)


@router.get("/auth/me", response_model=UserIdentityResponse)
def auth_me(current: CurrentUser) -> UserIdentityResponse:
    """Return the current user (from ``X-User-Id``, or the seeded player)."""
    return _identity(current)


@router.get("/ingredients", response_model=list[Ingredient])
def get_ingredients():
    """List all ingredients available at the lemonade stand."""
    return ingredients_service.list_all()


@router.get("/inventory", response_model=list[Inventory])
def get_inventory():
    """List on-hand inventory stock."""
    return inventory_service.list_all()


@router.post("/users/opening-balance", response_model=CapitalResponse)
def ensure_opening_balance(current: CurrentUser) -> CapitalResponse:
    """Create the player's opening balance if they have no ledger yet."""
    user = users_service.ensure_opening_balance(current.id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    latest = ledger_store.get_ledger(current.id)
    if latest is None:
        raise HTTPException(status_code=500, detail="failed to create opening balance")
    return CapitalResponse(user_id=current.id, current_capital=latest.current_capital)


@router.get("/users/capital", response_model=CapitalResponse)
def get_capital(current: CurrentUser) -> CapitalResponse:
    """Return the player's current capital from their latest ledger entry."""
    latest = ledger_store.get_ledger(current.id)
    if latest is None:
        raise HTTPException(status_code=404, detail="user ledger not found")
    return CapitalResponse(user_id=current.id, current_capital=latest.current_capital)


@router.post("/ingredients/buy", response_model=bool)
def buy_ingredients(req: BuyIngredientsRequest, current: CurrentUser) -> bool:
    """Buy ingredient units for a player; updates inventory and their ledger."""
    return ingredients_service.buy(current.id, req.ingredient_name, req.unit_count)


@router.post("/lemonades/sell", response_model=bool)
def sell_lemonade(req: SellLemonadeRequest, current: CurrentUser) -> bool:
    """Sell lemonade servings for a player; deducts inventory and credits their ledger."""
    return lemonades_service.sell(current.id, req.name, req.amount)


@router.post("/lemonades/price", response_model=bool)
def set_lemonade_price(req: SetLemonadePriceRequest, current: CurrentUser) -> bool:
    """Set a lemonade's sell price (allowed at day-start when a game is active)."""
    return lemonades_service.set_price(current.id, req.name, req.price)


@router.post("/game/start", response_model=GameSession)
def start_game(current: CurrentUser) -> GameSession:
    """Start a new game with seed capital and empty inventory."""
    session = game_service.start_game(current.id)
    if session is None:
        raise HTTPException(status_code=404, detail="user not found")
    return session


@router.get("/game", response_model=Optional[GameSession])
def get_game(current: CurrentUser) -> Optional[GameSession]:
    """Return the player's current game session, if any."""
    return game_service.get_session(current.id)


@router.post("/game/continue", response_model=GameSession)
def continue_day(current: CurrentUser) -> GameSession:
    """Finish day-start prep and begin the intra-day clock."""
    session = game_service.continue_day(current.id)
    if session is None:
        raise HTTPException(
            status_code=400,
            detail="no day-start session to continue",
        )
    return session
