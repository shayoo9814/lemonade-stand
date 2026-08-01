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

Open **http://127.0.0.1:8000/** for the rules page; **http://127.0.0.1:8000/play** for the game UI.
API docs remain at `/docs`.

## Running tests

```bash
pytest -v
```

## Assumptions
* There's an infinite supply of ingredients (i.e. the supermarket doesn't run out of ingredients)
* 1 hour in the game takes 3 seconds in real life to pass
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
| GET | /ingredients | List stand ingredients and stock |
| GET | /inventory | On-hand inventory stock |
| GET | /users/capital | Current user's capital |
| POST | /users/opening-balance | Create opening balance if missing (idempotent) |
| POST | /ingredients/buy | Buy ingredients (day-start only when a game is active) |
| POST | /lemonades/sell | Sell lemonade servings (stock + profit) |
| POST | /lemonades/price | Set lemonade sell price (day-start only when a game is active) |
| POST | /game/start | Start a game ($30 seed capital, empty inventory) |
| GET | /game | Current game session (day, hour, phase) |
| POST | /game/continue | Leave day-start prep and start the intra-day clock |

## Auth (stub)

There is no login yet. Identity is resolved in `app/auth.py` so a real auth
layer can plug in later without rewriting routes.

**How identity is resolved**

1. Player-scoped handlers take `current: CurrentUser`.
2. `CurrentUser` is a FastAPI dependency (`Depends(get_current_user)`).
3. `get_current_user()` reads the ``X-User-Id`` header and calls
   `resolve_current_user_id()`.
4. If the header is set, that id is used (unknown id → `401`). If it is
   omitted and exactly one user is seeded, that player is treated as signed
   in; otherwise the request is `401`.
5. The user record is loaded; routes use `current.id` (no `user_id` in the
   path or body).

The UI calls ``GET /auth/me`` once (header optional), then sends
``X-User-Id`` on subsequent requests.

**Extending later**

Replace `resolve_current_user_id()` / `get_current_user()` to derive the user
from a session cookie, Bearer JWT, or similar instead of ``X-User-Id``. Keep
`CurrentUser` as the stable surface used by routes.

## Game loop

1. `POST /game/start` → phase `day_start` with **$30** capital and empty stock
2. Buy ingredients and/or set lemonade prices
3. `POST /game/continue` → phase `running`
4. Background clock advances **1 game-hour every 3 real seconds**, auto-selling 1× `classic` per hour
5. Day ends when stock cannot cover a sale **or** hour reaches 24 → leftover **ice is discarded**, then back to `day_start` (or `game_over` if capital is empty and inventory cannot make a lemonade)