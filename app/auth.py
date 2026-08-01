"""
Authentication / current-user resolution.

There is no login yet. Callers depend on this module for "who is acting?"
so a real auth layer (sessions, JWT, OAuth, etc.) can replace the stub
implementations below without rewriting route handlers or services.

Public surface to keep stable when upgrading auth:
- ``resolve_current_user_id`` — map the request to a user id (or None)
- ``get_current_user`` / ``CurrentUser`` — FastAPI dependency returning the user

Identity is taken from the ``X-User-Id`` header (not the URL path). When the
header is omitted and exactly one player is seeded, that player is used so
``GET /auth/me`` can bootstrap the client.
"""

from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, status

from app import users as users_service
from app.models import User

USER_ID_HEADER = "X-User-Id"


def resolve_current_user_id(x_user_id: Optional[str] = None) -> Optional[str]:
    """Resolve the acting user id from the ``X-User-Id`` header value.

    Stub: if the header is omitted and exactly one user is seeded, that
    player's id is returned (bootstrap / tests). Replace this function when
    adding real auth (e.g. derive id from a session cookie or Bearer token).
    """
    if x_user_id:
        return x_user_id
    players = users_service.list_all()
    if len(players) != 1:
        return None
    return players[0].id


def get_current_user(
    x_user_id: Annotated[Optional[str], Header(alias=USER_ID_HEADER)] = None,
) -> User:
    """Return the authenticated user, or raise 401 if none is resolved."""
    user_id = resolve_current_user_id(x_user_id)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
        )
    user = users_service.get(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
