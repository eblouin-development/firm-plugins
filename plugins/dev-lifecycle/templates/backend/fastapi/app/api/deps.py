"""Shared FastAPI dependencies. `get_auth_service` is the Stage 5a (#41)
per-request `AuthService` provider — binds this request's DB session
(`get_db`) into fresh `SqlAlchemyUserStore`/`SqlAlchemyRefreshTokenStore`
instances, plus the process-wide `PasswordService` singleton and a
`Settings`-derived `TokenService`, into one `AuthService`. `get_current_
principal` is the vendored auth component's `build_get_current_principal(
get_auth_service)`, bound once at import time — declares the `HTTPBearer`
security scheme in OpenAPI (via the component's `bearer_scheme`) and
resolves a request's bearer token into `_core.AccessClaims` for any route
that depends on it (`app/api/routers/auth.py`'s `GET /auth/me`, and any
future protected route)."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.security.auth import AuthService, build_get_current_principal
from app.core.security.auth.stores import (
    SqlAlchemyRefreshTokenStore,
    SqlAlchemyUserStore,
    get_password_service,
    get_token_service,
    utc_now,
)


async def get_auth_service(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthService:
    """Per-request `AuthService`, bound to THIS request's `AsyncSession` —
    a fresh pair of store instances every call (they're thin wrappers
    holding only a session reference, so this is cheap), the process-wide
    `PasswordService` singleton (`get_password_service()` — see its own
    docstring on why that one IS cached), and a `TokenService` built fresh
    from the current `Settings` (`get_token_service()` — raises
    `AuthNotConfiguredError`, fail-closed, if `jwt_signing_key` is unset;
    see that function's own docstring). `now=utc_now` is the SAME callable
    `get_token_service()` passes to the `TokenService` it builds — see
    that function's own module, `utc_now`'s docstring."""
    return AuthService(
        users=SqlAlchemyUserStore(db),
        refresh_tokens=SqlAlchemyRefreshTokenStore(db),
        passwords=get_password_service(),
        tokens=get_token_service(settings),
        now=utc_now,
    )


get_current_principal = build_get_current_principal(get_auth_service)
