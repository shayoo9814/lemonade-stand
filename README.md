# Lemonade Stand Game

A small business simulation built with FastAPI. Players buy ingredients, track capital on a general ledger, and run a lemonade stand.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the server

```bash
fastapi dev
```

Or:

```bash
python -m uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/** for the rules page; **http://127.0.0.1:8000/play** for the game UI; **http://127.0.0.1:8000/ledger** for the general ledger.
API docs remain at `/docs`.

## Running tests

```bash
pytest -v
```

## Assumptions
* There's an infinite supply of ingredients (i.e. the supermarket doesn't run out of ingredients)
* 1 hour in the game takes 1 second in real life to pass
* Lemonade creation is as fast as the computer can perform the necessary logic 
* Lemons are not perishable

## API endpoints

Player-scoped routes identify the actor with the ``X-User-Id`` header. 
When the header is omitted and exactly one user
is seeded, that player is used (so ``GET /auth/me`` can bootstrap the UI).

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| GET | /auth/me | Current user (from ``X-User-Id``, or seeded player) |
| GET | /ingredients | Shared supermarket ingredient catalog |
| GET | /inventory | Current user's on-hand inventory stock |
| GET | /users/capital | Current user's capital |
| GET | /users/ledger | Current user's general ledger entries |
| DELETE | /users/ledger | Wipe the current user's general ledger |
| POST | /users/opening-balance | Create opening balance if missing (idempotent) |
| POST | /ingredients/buy | Buy ingredients (day-start only when a game is active) |
| GET | /lemonades | Current user's menu (id, name, price, recipe) |
| POST | /lemonades/sell | Sell lemonade servings (stock + revenue) |
| POST | /lemonades/price | Set lemonade sell price (day-start only when a game is active) |
| POST | /game/start | Start a game ($30 seed capital, empty inventory for this player) |
| GET | /game | Current game session (day, hour, phase) |
| POST | /game/continue | Leave day-start prep and start the intra-day clock |

## Things to keep an eye out for
* **Ledger safety via decoupling.**
   * Capital changes live in `app/ledger`, which only accepts a user id plus a cost or revenue.
   * `GeneralLedger` rows are frozen (immutable); changes always produce a new entry.
   * Pure helpers (`apply_purchase` / `apply_sale`) compute the next row without
     mutating prior entries or module state; only successful results are appended.
   * Buy/sell flows own domain rules (inventory stock, pricing), then call the ledger
     so money math stays isolated, append-only, and easy to unit-test without the
     rest of the stack.
* **Auth stub for later swap-in.** 
   * There is no real login yet. 
   * Routes take `CurrentUser` via a FastAPI dependency that today resolves identity from
     ``X-User-Id`` (or the single seeded user). 
   * Replacing `resolve_current_user_id()` with session/JWT logic
     should not require rewriting route handlers.
* **In-memory DB as a thin store.** 
   * `app/database` holds dict-backed entities with get/set/list only — no business rules. 
   * Ingredient prices are a shared append-only supermarket catalog; inventory and lemonade
     menus are keyed by player; capital history lives only in ``app.ledger``.
   * Seed data loads from JSON on import; `reset_db` clears everything for tests.
   * A real database can replace this layer without rewriting domain services.
* **Ledger timestamps are wall-clock for now.**
   * Entries simply log ``datetime.now(UTC)`` when written.
   * That sits awkwardly next to the game clock (1 game-hour = 1 real second):
     many sale rows can share nearly the same real timestamp while spanning
     many in-game hours. A better display (e.g. game day/hour on the ledger)
     is left for later.

## Game loop

1. `POST /game/start` → opening-balance seeds **$30** (if capital already exists, a reset-ledger row zeros it first); phase `day_start` with empty stock
2. Buy ingredients and/or set lemonade prices
3. `POST /game/continue` → phase `running`
4. Background clock advances **1 game-hour every 1 real second**, auto-selling 1× `classic` per hour
5. Day ends when stock cannot cover a sale **or** hour reaches 24 → leftover **ice is discarded**, then back to `day_start` (or `game_over` if capital is empty and inventory cannot make a lemonade)

## Potential Extensions
* Create easy mode / medium mode / hard mode based on hourly demand 
    * Create more accurate simulation of user behavior
* Add proper multi-tenancy support (e.g. race conditions, deadlocks)
* Add ability to add an item to the menu
* Add proper auth layer with proper log-in page 
* Add ability to stream live prices into db for fluctuating ingredient pricing 
* Add a search functionality on the ledger page 