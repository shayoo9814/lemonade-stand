"""
Data models for the lemonade stand game.
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IngredientUnit(str, Enum):
    EACH = "each"
    CUP = "cup"
    LB = "lb"


class LedgerAction(str, Enum):
    """Kinds of append-only general ledger entries."""
    OPENING_BALANCE = "opening_balance"
    PURCHASE = "purchase"
    SALE = "sale"
    RESET_LEDGER = "reset-ledger"


# Sentinel ``item_id`` for opening-balance rows (no catalog item).
OPENING_BALANCE_ITEM_ID = "opening-balance"
# Sentinel ``item_id`` for game-reset rows that zero capital.
RESET_LEDGER_ITEM_ID = "reset-ledger"


class GamePhase(str, Enum):
    """Lifecycle phase of a lemonade stand game session."""
    DAY_START = "day_start"
    RUNNING = "running"
    GAME_OVER = "game_over"


class GameSession(BaseModel):
    """Per-player game clock and phase for the stand simulation."""
    user_id: str
    day: int = Field(ge=1)
    hour: int = Field(ge=0, le=24)
    phase: GamePhase


class GeneralLedger(BaseModel):
    """One append-only ledger row logging a capital action for a player.

    ``user_id`` identifies the owning player so the log is self-describing
    as a flat table. Running balances after the action are stored on the
    row; the player's current position is their latest entry. Rows are
    immutable once written.

    ``item_id`` always references a related item:
    - purchase → ``Ingredient.id``
    - sale → ``Lemonade.id``
    - opening balance → ``OPENING_BALANCE_ITEM_ID``
    - reset-ledger (game reset) → ``RESET_LEDGER_ITEM_ID``
    """
    model_config = ConfigDict(frozen=True)

    user_id: str
    timestamp: datetime
    action: LedgerAction
    amount: Decimal = Field(
        description=(
            "Magnitude of the action (opening capital credited, purchase cost, "
            "sale revenue, or capital cleared on reset)"
        ),
    )
    current_capital: Decimal
    expenses_incurred: Decimal = Decimal("0")
    item_id: str = Field(
        description=(
            "Related Ingredient.id (purchase), Lemonade.id (sale), "
            "OPENING_BALANCE_ITEM_ID (opening balance), or RESET_LEDGER_ITEM_ID (game reset)"
        ),
    )


class User(BaseModel):
    """A player who owns a lemonade stand and its general ledger."""
    id: str
    name: str
    email: str
    general_ledger: list[GeneralLedger] = Field(
        default_factory=list,
        description="Append-only capital log owned by this player; empty until play begins",
    )


class Ingredient(BaseModel):
    """A buyable ingredient catalog entry with bulk pricing.

    ``price`` is the cost for ``amount`` units (e.g. $4.75 for a 5 lb bag).
    Unit cost is ``price / amount``. Rows are append-only and immutable: a
    new ``timestamp`` records a price (or pack-size) change over time.
    """
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    amount: Decimal = Field(gt=0, description="Quantity covered by the listed price")
    price: Decimal = Field(gt=0)
    unit: IngredientUnit
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this price became effective",
    )

    @property
    def unit_price(self) -> Decimal:
        """Cost per single unit of this ingredient."""
        return self.price / self.amount


class Inventory(BaseModel):
    """On-hand stock for a single ingredient."""
    ingredient_name: str
    amount: Decimal = Field(ge=0)


class Lemonade(BaseModel):
    """A drink recipe: sell price should cover the cost of required ingredients."""
    id: str
    name: str
    price: Decimal = Field(ge=0)
    recipe: dict[str, Decimal] = Field(
        description="Ingredient name → amount required per serving",
    )

    @field_validator("recipe")
    @classmethod
    def recipe_must_be_nonempty_with_positive_amounts(
        cls, value: dict[str, Decimal]
    ) -> dict[str, Decimal]:
        if not value:
            raise ValueError("lemonade recipe must include at least one ingredient")
        for name, amount in value.items():
            if amount <= 0:
                raise ValueError(f"ingredient '{name}' amount must be positive")
        return value

    def recipe_cost(self, catalog: dict[str, Ingredient]) -> Decimal:
        """Total ingredient cost for one serving given a price catalog."""
        total = Decimal("0")
        for name, amount in self.recipe.items():
            ingredient = catalog.get(name)
            if ingredient is None:
                raise ValueError(f"unknown ingredient in recipe: {name}")
            total += ingredient.unit_price * amount
        return total

    def ensure_price_covers_recipe(self, catalog: dict[str, Ingredient]) -> None:
        """Raise if sell price is below the recipe's ingredient cost."""
        cost = self.recipe_cost(catalog)
        if self.price < cost:
            raise ValueError(
                f"lemonade price {self.price} is below recipe cost {cost}"
            )
