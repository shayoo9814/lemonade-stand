"""
Unit tests for the stub auth layer.
"""

import pytest
from fastapi import HTTPException

from app.auth import get_current_user, resolve_current_user_id
from app.database import reset_db


@pytest.fixture(autouse=True)
def fresh_db():
    reset_db()
    yield


class TestResolveCurrentUser:
    def test_resolves_sole_seeded_player_without_header(self):
        assert resolve_current_user_id() == "u1"

    def test_header_overrides_seed_fallback(self):
        assert resolve_current_user_id("u1") == "u1"

    def test_get_current_user_returns_seeded_player(self):
        user = get_current_user()
        assert user.id == "u1"
        assert user.name == "Sungho Yoo"

    def test_get_current_user_from_header(self):
        user = get_current_user(x_user_id="u1")
        assert user.id == "u1"

    def test_unknown_header_user_unauthorized(self):
        with pytest.raises(HTTPException) as exc:
            get_current_user(x_user_id="missing")
        assert exc.value.status_code == 401
