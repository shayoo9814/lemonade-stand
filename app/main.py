"""
Lemonade Stand Game — FastAPI Application

A small business simulation where players buy ingredients, track capital,
and run a lemonade stand.
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import game as game_service
from app.routes import router

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


async def _intra_day_clock() -> None:
    """Advance all running game sessions by one hour every few real seconds."""
    while True:
        await asyncio.sleep(game_service.SECONDS_PER_GAME_HOUR)
        game_service.tick_all()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_intra_day_clock())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Lemonade Stand Game",
    description="Buy ingredients, manage capital, and run your lemonade stand.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    """Serve the rules landing page."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/play")
def play():
    """Serve the interactive game UI."""
    return FileResponse(STATIC_DIR / "play.html")


@app.get("/health")
def health():
    return {"status": "ok"}
