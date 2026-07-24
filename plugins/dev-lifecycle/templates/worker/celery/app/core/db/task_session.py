"""Bridges this block's vendored async `session.py` (`configure_engine`/
`get_sessionmaker`) into Celery's synchronous task execution model.

Celery tasks run synchronously by default (a worker process pulls a
message off the broker and calls the task function in-process) — there is
no running asyncio event loop the way there is inside a FastAPI request.
`session.py`'s `get_db()` is shaped as an async generator for FastAPI's
`Depends()`; a task instead uses `task_db_session()` below (an
`asynccontextmanager` with the SAME commit/rollback/close discipline) and
drives it with `run_async()`, which owns a fresh event loop for exactly
the duration of one task call (`asyncio.run` — never reuse a loop across
tasks; a worker process handles many tasks over its lifetime, prefork or
otherwise, and asyncio event loops are not safe to share across them).

    from app.core.db.session import configure_engine
    from app.core.db.task_session import run_async, task_db_session

    async def _send_reminder(order_id: str) -> None:
        async with task_db_session() as db:
            ...  # await db.execute(...), same AsyncSession API as a request

    @shared_task
    def send_reminder(order_id: str) -> None:
        run_async(_send_reminder(order_id))

`configure_engine(settings.database_url)` is called once at worker-process
startup (celery_app.py's `worker_process_init` signal handler) — same
"configure once, read many times" contract session.py's own docstring
describes for a FastAPI app's startup hook.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_sessionmaker

T = TypeVar("T")


@asynccontextmanager
async def task_db_session() -> AsyncIterator[AsyncSession]:
    """Same commit-on-success / rollback-and-reraise / always-close
    contract as `session.py`'s `get_db()`, shaped as a context manager
    instead of a FastAPI dependency generator — the two are otherwise
    identical."""
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


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Runs `coro` to completion on a fresh event loop and returns its
    result — the seam a synchronous `@shared_task` body calls to reach
    async DB (or any other asyncio) code. Uses `asyncio.run()`, which
    creates and tears down a new loop every call; this is deliberately
    NOT optimized into a long-lived per-worker loop — Celery's prefork
    pool forks worker processes, and a loop created before a fork is
    unsafe to use after one, so "fresh loop per task" is the safe default
    or with -P gevent/-P threads (celery.md's "Workers & concurrency")."""
    return asyncio.run(coro)
