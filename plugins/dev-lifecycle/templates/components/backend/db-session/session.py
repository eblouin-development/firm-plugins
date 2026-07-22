"""Framework-neutral-within-SQLAlchemy async session management: an async
engine factory from a DATABASE_URL, an async_sessionmaker, and a `get_db`
FastAPI-shaped dependency with commit/rollback/close discipline. SQLAlchemy
2.0 async (`AsyncEngine`/`AsyncSession`), pinned per
references/compatibility-matrix.md's Backend — Python row. Canon:
references/backend/sqlalchemy.md ("Sessions & transactions" — one session
per request via a dependency with guaranteed cleanup, explicit commit/
rollback boundaries, never block the event loop with sync DB calls).

Drop-in: copy this file into app/core/db/session.py, alongside mixins.py
and repository.py (also SQLAlchemy-specific). Call `configure_engine
(DATABASE_URL)` once at app startup (FastAPI lifespan/on_startup); every
route then depends on `get_db` directly (`Depends(get_db)`) with no
per-route wiring:

    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession

    @router.get("/widgets")
    async def list_widgets(db: AsyncSession = Depends(get_db)):
        ...

SQLAlchemy-specific — Django's ORM has its own connection/transaction
model (autocommit-per-request or explicit `transaction.atomic()`) with no
`AsyncSession`/`async_sessionmaker` equivalent; Stage 4's Django track does
not reuse this file.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def configure_engine(database_url: str, *, echo: bool = False, **engine_kwargs: Any) -> AsyncEngine:
    """Builds (and caches, module-level) the async engine and its
    sessionmaker from a DATABASE_URL. Call exactly once at app startup —
    e.g. a FastAPI lifespan handler reading `settings.DATABASE_URL` (see
    settings/). `pool_pre_ping=True` is the default unless overridden via
    `engine_kwargs` — it recycles a connection dropped by the DB server
    (idle timeout, failover) instead of surfacing a stale-connection error
    to a request. `**engine_kwargs` passes through to
    `create_async_engine` untouched — a test suite uses it to inject
    `poolclass=StaticPool` for a shared in-memory sqlite engine (see
    tests/test_session.py); a prod deployment might use it to tune
    `pool_size`/`max_overflow`."""
    global _engine, _sessionmaker
    engine_kwargs.setdefault("pool_pre_ping", True)
    _engine = create_async_engine(database_url, echo=echo, **engine_kwargs)
    _sessionmaker = async_sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def get_engine() -> AsyncEngine:
    """Returns the engine configured by `configure_engine()`. Raises
    RuntimeError with an actionable message if startup never called it —
    fails loudly at first use rather than a confusing AttributeError deep
    inside a request."""
    if _engine is None:
        raise RuntimeError(
            "no engine configured; call configure_engine(DATABASE_URL) at app startup "
            "before serving requests (or before running tests)."
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Returns the async_sessionmaker configured by `configure_engine()`.
    Same fail-fast contract as `get_engine()`."""
    if _sessionmaker is None:
        raise RuntimeError(
            "no sessionmaker configured; call configure_engine(DATABASE_URL) at app "
            "startup before serving requests (or before running tests)."
        )
    return _sessionmaker


async def get_db() -> AsyncIterator[AsyncSession]:
    """The FastAPI dependency: yields one `AsyncSession` per request, with
    explicit commit/rollback/close discipline per
    references/backend/sqlalchemy.md's "Sessions & transactions" —

    - Success (no exception raised by the route/service code that ran with
      this session): commit.
    - Any exception: roll back, then re-raise (never swallowed) so the
      route's own error handling — or the error-envelope/ exception
      handler in Step 2 — still sees it.
    - Either way: close the session, guaranteed via `finally`, so a
      connection is never leaked back to the pool half-used.

    Takes no arguments deliberately — FastAPI's dependency injection calls
    it as `Depends(get_db)` with zero per-route wiring; the engine/
    sessionmaker it uses come from the module-level state `configure_engine()`
    set at startup, not from a parameter threaded through every route."""
    session_factory = get_sessionmaker()
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def _reset_engine_for_tests() -> None:
    """Test-only hook: clears the cached engine/sessionmaker between
    tests, so one test's `configure_engine()` call never leaks into the
    next. Not part of this module's public contract — mirrors
    secrets-loading's `_reset_asm_client_cache_for_tests()` pattern."""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
