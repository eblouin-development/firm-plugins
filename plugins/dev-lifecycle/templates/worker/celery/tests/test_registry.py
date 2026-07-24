"""Proves the enqueue seam (registry.py) — the by-name producer path a
backend block calls without importing this block's task code — behaves
per its contract: fails fast with no CELERY_BROKER_URL, builds a client
Celery app otherwise, and keeps TaskName in sync with the real registered
task names (a conformance check so the two can't silently drift)."""

from __future__ import annotations

import os

import pytest

from app.celery_app import app as worker_app
from app.registry import TaskName, _producer_app


def test_task_name_constants_match_registered_tasks():
    assert TaskName.RECORD_EVENT in worker_app.tasks
    assert TaskName.IO_SEND_NOTIFICATION in worker_app.tasks


def test_producer_app_reads_broker_url_from_env(monkeypatch):
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    _producer_app.cache_clear()
    client = _producer_app()
    assert client.conf.broker_url == "redis://localhost:6379/0"
    _producer_app.cache_clear()


def test_producer_app_fails_fast_with_no_broker_url(monkeypatch):
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    _producer_app.cache_clear()
    with pytest.raises(RuntimeError, match="CELERY_BROKER_URL"):
        _producer_app()
    _producer_app.cache_clear()
    # Restore for any test running after this one in the same session.
    monkeypatch.setenv("CELERY_BROKER_URL", os.environ.get("CELERY_BROKER_URL", "memory://"))
