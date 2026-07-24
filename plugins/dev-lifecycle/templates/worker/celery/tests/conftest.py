"""Shared test fixtures. Sets required env vars BEFORE any `app.*` import
touches `WorkerSettings()` (module-level construction in celery_app.py),
same ordering constraint backend/fastapi's own conftest documents for its
settings module. Uses `task_always_eager` (celery.md's "Pitfalls &
testing") so `.delay()` runs inline in the test process against a real
broker connection is never required, and an in-memory sqlite engine
(matching db-session's own test pattern) so DB-touching tasks don't need a
live Postgres.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")

import pytest
from sqlalchemy.pool import StaticPool

from app.celery_app import app as celery_app
from app.core.db.session import _reset_engine_for_tests, configure_engine
from app.registry import _reset_producer_for_tests


@pytest.fixture(autouse=True)
def _eager_mode():
    """Runs every task synchronously, in-process, per celery.md's testing
    guidance — no live broker needed for unit tests exercising task
    bodies. Integration coverage against a real broker is a project's own
    addition (docker-compose.yml's `worker`/`beat` services, run by hand
    or in a separate integration-test job)."""
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False


@pytest.fixture(autouse=True)
def _sqlite_engine():
    """One shared in-memory sqlite engine per test, StaticPool-backed so
    the single :memory: connection survives across the async engine's
    internal pool — matches db-session's own tests/conftest.py pattern."""
    configure_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    yield
    _reset_engine_for_tests()


@pytest.fixture(autouse=True)
def _reset_registry():
    yield
    _reset_producer_for_tests()
