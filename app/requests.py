"""
Request and response schemas for the lemonade stand game API.

Player identity is not in these bodies — it comes from the ``X-User-Id``
header via ``app.auth``.
"""

from decimal import Decimal

from pydantic import BaseModel, Field


class BuyIngredientsRequest(BaseModel):
    ingredient_name: str
    unit_count: Decimal = Field(gt=0, description="Number of units to purchase")


class SellLemonadeRequest(BaseModel):
    name: str
    amount: Decimal = Field(gt=0, description="Number of servings to sell")


class SetLemonadePriceRequest(BaseModel):
    name: str
    price: Decimal = Field(ge=0, description="Sell price per serving (0 = free)")
