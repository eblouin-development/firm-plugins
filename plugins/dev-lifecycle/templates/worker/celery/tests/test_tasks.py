"""Exercises the example tasks in eager mode (conftest's `_eager_mode`
fixture) — proves the idempotent_task decorator's config lands correctly
and that a task's async DB body actually runs against the test sqlite
engine via task_session.py's run_async/task_db_session bridge."""

from __future__ import annotations

from app.tasks.example import io_send_notification, record_event


def test_record_event_runs_and_returns_event_id():
    result = record_event.delay("evt-1", {"kind": "signup"})
    assert result.get() == "evt-1"


def test_io_send_notification_runs():
    result = io_send_notification.delay("user-1", "hello")
    assert result.successful()


def test_record_event_is_acks_late_and_retries_configured():
    assert record_event.acks_late is True
    assert record_event.reject_on_worker_lost is True
    assert record_event.max_retries == 5


def test_record_event_registered_under_expected_name():
    assert record_event.name == "app.tasks.example.record_event"


def test_io_task_registered_under_expected_name():
    assert io_send_notification.name == "app.tasks.example.io_send_notification"
