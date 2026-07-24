"""Liveness/readiness for the worker and beat processes. Celery ships no
HTTP server for either process (unlike the FastAPI/Django backend's
`/health`/`/readyz` routes) — this block's liveness story is a CLI probe
instead, wired into the Dockerfile's `HEALTHCHECK` for both the `worker`
and `beat` images (see Dockerfile).

    python -m app.health worker   # `celery -A app.celery_app inspect ping`
                                   # against THIS process — exits 0 if it
                                   # answers within the timeout, 1 otherwise.
    python -m app.health beat     # checks the beat schedule file's mtime
                                   # is recent — `inspect ping` targets
                                   # WORKER processes only; beat has no
                                   # broker-facing ping of its own.

An orchestrator without a Docker HEALTHCHECK story (e.g. the infra block's
ECS task definition) runs the same command as its own container health
check command — see this block's docs/fragment.md "Deployment" section.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from app.celery_app import app

# celerybeat-schedule is the default PersistentScheduler's on-disk shelve
# file (celery_app.py wires no explicit --schedule path, so this is
# Celery's own default, relative to beat's working directory — the
# Dockerfile's WORKDIR).
_BEAT_SCHEDULE_FILE = Path("celerybeat-schedule")
_BEAT_STALE_AFTER_SECONDS = 120  # beat's own default tick is 5s; 120s is generous


def _check_worker(timeout: float = 5.0) -> bool:
    """`inspect ping` round-trips through the broker to the LOCAL worker
    process only when `destination` is left unset and this app instance
    IS that worker (per Celery's own ping-inspects-this-process docs) —
    the standard "is this container's Celery process still alive and
    consuming" check."""
    replies = app.control.inspect(timeout=timeout).ping()
    return bool(replies)


def _check_beat() -> bool:
    if not _BEAT_SCHEDULE_FILE.exists():
        # Fresh container, beat hasn't written its first tick yet — not
        # itself a failure within the HEALTHCHECK's own start_period grace.
        return True
    age = time.time() - _BEAT_SCHEDULE_FILE.stat().st_mtime
    return age < _BEAT_STALE_AFTER_SECONDS


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "worker"
    if target == "worker":
        ok = _check_worker()
    elif target == "beat":
        ok = _check_beat()
    else:
        print(f"unknown health target {target!r} — expected 'worker' or 'beat'", file=sys.stderr)
        return 2
    if not ok:
        print(f"{target} health check failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
