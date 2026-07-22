"""Hermetic test fixture: boots the real `create_app()` FastAPI app against
an in-memory, shared-cache sqlite database (aiosqlite + StaticPool — the
same pattern db-session/README.md's own test suite documents) instead of a
real DATABASE_URL/Postgres.

Uses a substitute lifespan (`_test_lifespan`) rather than the app's real
one: the real lifespan (app/main.py) reads `Settings().database_url` and
calls `configure_engine(url)` with no extra `engine_kwargs`, which would
open a *fresh, empty* anonymous in-memory sqlite database per connection —
StaticPool is what makes "in-memory" mean one shared database across the
whole test. Configuring the engine here (before the app/TestClient exist)
and creating/dropping tables inside `_test_lifespan` keeps that StaticPool
detail entirely inside the test suite; app/main.py's real lifespan is
never modified to know about it.

Stage 3 Step 3b (#26): `app/main.py`'s `create_app()` now resolves
`Settings()` (directly, or via `get_settings()`) at APP-CONSTRUCTION time,
not just inside `lifespan`, to wire CORS/rate-limiting/security-header
config — see that module's "Security composition" docstring. Importing
`app.main` (below) runs its module-level `app = create_app()` immediately,
which now needs a valid `DATABASE_URL` to construct `Settings()` even
though this suite's actual engine is configured separately, directly, via
`configure_engine()` + `StaticPool` in the `client` fixture below (never
through `settings.database_url` — see `_test_lifespan` above). The
`setdefault` below supplies a placeholder that is never used to open a
real connection; it only satisfies `AppSettings.database_url`'s
required-field construction check.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")

from collections.abc import AsyncIterator, Callable, Iterator  # noqa: E402
from contextlib import ExitStack, asynccontextmanager  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.db import Base, configure_engine, get_engine  # noqa: E402
from app.core.db.session import _reset_engine_for_tests  # noqa: E402
from app.main import create_app  # noqa: E402

# Import side effect: registers every model on Base.metadata so
# Base.metadata.create_all()/drop_all() below actually create/drop each
# model's table. Goes through the app/models/__init__.py aggregator (Stage
# 3 #26, Step 3a) rather than importing `app.models.item` directly, so a
# future model added there is picked up here automatically.
import app.models  # noqa: F401,E402


@asynccontextmanager
async def _test_lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture()
def client() -> Iterator[TestClient]:
    configure_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    app = create_app(lifespan_ctx=_test_lifespan)
    with TestClient(app) as test_client:
        yield test_client
    _reset_engine_for_tests()


@pytest.fixture()
def make_client() -> Iterator[Callable[..., TestClient]]:
    """Factory fixture (Stage 3 Step 3b, #26) for tests that need a bespoke
    `Settings()` — a tiny `rate_limit_capacity` to trigger 429 without a
    real time delay, a specific `cors_allowed_origins` to test allow/deny,
    etc. — rather than the `client` fixture's fixed defaults. See
    tests/test_security_composition.py.

    `**settings_overrides` are passed straight to `Settings(...)`;
    `database_url` is always the hermetic in-memory sqlite URL (never
    overridable here — this fixture is about security config, not the DB).
    Call `_make()` at most ONCE per test: like the `client` fixture, this
    reconfigures the one process-global engine (app/core/db/session.py has
    no concept of multiple concurrent engines), so a second call within the
    same test would silently repoint the first client's already-created app
    at a fresh, empty database.
    """
    with ExitStack() as stack:

        def _make(**settings_overrides: object) -> TestClient:
            configure_engine("sqlite+aiosqlite://", poolclass=StaticPool)
            stack.callback(_reset_engine_for_tests)
            settings = Settings(database_url="sqlite+aiosqlite://", **settings_overrides)
            app = create_app(lifespan_ctx=_test_lifespan, settings=settings)
            return stack.enter_context(TestClient(app))

        yield _make
