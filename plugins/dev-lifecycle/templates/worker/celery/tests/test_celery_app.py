"""Proves the Celery app is wired the way celery_app.py's docstring/README
claim: JSON-only serialization, broker/result-backend from settings, and
name-based routing of `io_*` tasks onto the dedicated IO queue."""

from __future__ import annotations

from app.celery_app import app, settings


def test_json_only_serialization():
    assert app.conf.task_serializer == "json"
    assert app.conf.result_serializer == "json"
    assert app.conf.accept_content == ["json"]


def test_broker_url_from_settings():
    assert app.conf.broker_url == settings.celery_broker_url


def test_default_queue_from_settings():
    assert app.conf.task_default_queue == settings.celery_default_queue


def test_worker_prefetch_multiplier_default_is_one():
    # celery.md's "Workers & concurrency": long-running tasks should not
    # default to Celery's own default of 4.
    assert app.conf.worker_prefetch_multiplier == 1


def test_io_prefixed_task_routes_to_io_queue():
    route = app.amqp.router.route({}, "app.tasks.example.io_send_notification")
    assert route["queue"].name == settings.celery_io_queue


def test_non_io_task_stays_on_default_queue():
    route = app.amqp.router.route({}, "app.tasks.example.record_event")
    assert route["queue"].name == settings.celery_default_queue


def test_example_tasks_autodiscovered():
    assert "app.tasks.example.record_event" in app.tasks
    assert "app.tasks.example.io_send_notification" in app.tasks
