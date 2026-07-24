"""Proves the liveness probe (app/health.py) is scoped to the LOCAL node
only — the fix for a false-healthy result where a dead worker replica
could see a live sibling's reply on a shared, horizontally-scaled broker
(see health.py's module docstring)."""

from __future__ import annotations

import socket

from app import health


def test_local_nodename_matches_celery_default_scheme():
    assert health._local_nodename() == f"celery@{socket.gethostname()}"


def test_check_worker_pings_only_the_local_destination(monkeypatch):
    captured = {}

    def fake_ping(destination=None, timeout=None):
        captured["destination"] = destination
        return [{destination[0]: {"ok": "pong"}}]

    monkeypatch.setattr(health.app.control, "ping", fake_ping)
    assert health._check_worker(timeout=1.0) is True
    assert captured["destination"] == [health._local_nodename()]


def test_check_worker_unhealthy_on_empty_reply(monkeypatch):
    monkeypatch.setattr(health.app.control, "ping", lambda destination=None, timeout=None: [])
    assert health._check_worker(timeout=1.0) is False


def test_check_worker_unhealthy_on_none_reply(monkeypatch):
    monkeypatch.setattr(health.app.control, "ping", lambda destination=None, timeout=None: None)
    assert health._check_worker(timeout=1.0) is False


def test_check_worker_ignores_a_sibling_replicas_reply(monkeypatch):
    """The core regression this fix addresses: a reply that names some
    OTHER node (a live sibling replica on the same broker) must never be
    read as proof THIS node is alive."""

    def fake_ping(destination=None, timeout=None):
        # A dead local node would get no reply at all in reality; this
        # simulates the old bug's failure mode directly — a reply keyed
        # under a different node's name must not count as healthy here.
        return [{"celery@some-other-container": {"ok": "pong"}}]

    monkeypatch.setattr(health.app.control, "ping", fake_ping)
    assert health._check_worker(timeout=1.0) is False


def test_check_beat_healthy_when_schedule_file_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(health, "_BEAT_SCHEDULE_FILE", tmp_path / "celerybeat-schedule")
    assert health._check_beat() is True


def test_check_beat_healthy_when_schedule_file_fresh(tmp_path, monkeypatch):
    schedule_file = tmp_path / "celerybeat-schedule"
    schedule_file.write_text("")
    monkeypatch.setattr(health, "_BEAT_SCHEDULE_FILE", schedule_file)
    assert health._check_beat() is True


def test_check_beat_unhealthy_when_schedule_file_stale(tmp_path, monkeypatch):
    import os
    import time

    schedule_file = tmp_path / "celerybeat-schedule"
    schedule_file.write_text("")
    stale_time = time.time() - (health._BEAT_STALE_AFTER_SECONDS + 60)
    os.utime(schedule_file, (stale_time, stale_time))
    monkeypatch.setattr(health, "_BEAT_SCHEDULE_FILE", schedule_file)
    assert health._check_beat() is False
