"""Test harness for this block's OWN standalone test run.

**Why this is unusual, read before touching it again.** This block
overlays `backend/django` — `webapp/`, `templates/`, `static_src/` are
meant to be copied into the SAME `apps/api/` directory `backend/django`
already materializes into (see the block README's "Placement &
composition rule"). A real scaffolded project's `webapp/views.py` doing
`from core.models import Item` resolves naturally there, because `core/`
physically sits right next to `webapp/` in one `apps/api/` directory.

This block's OWN standalone test run (this directory, run in isolation —
`template-author`'s acceptance bar requires every block's test suite to
actually run on its own) has no such co-located `core/`: it lives in a
SIBLING template directory,
`plugins/dev-lifecycle/templates/backend/django/`. Copying or symlinking
`core/` into this directory is not an option — that would be exactly the
kind of hand-duplication the freshness-audit vendoring discipline exists
to avoid, and it would stop this test run from exercising the code the
way it will actually be laid out post-scaffolding. Instead, this file
inserts `../../../backend/django` onto `sys.path` (pinned to a
`pytest.ini`-configured `pythonpath` entry too — see `pyproject.toml`) so
`import core` / `import config` resolve the SAME way they will once a
real scaffolded project has copied both blocks into one `apps/api/`
directory — the closest a standalone test run of ONE block can get to
modeling the real, co-located layout, without a second copy of `core/` to
drift out of sync."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_THIS_BLOCK_ROOT = Path(__file__).resolve().parent.parent
_DJANGO_BLOCK_ROOT = (_THIS_BLOCK_ROOT.parent.parent / "backend" / "django").resolve()

for _root in (_DJANGO_BLOCK_ROOT, _THIS_BLOCK_ROOT):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))


@pytest.fixture(autouse=True)
def _reset_rate_limit_store():
    """Same test-isolation rationale as backend/django's own
    tests/conftest.py fixture of the same name — `core.security.
    rate_limiting.django.RateLimitMiddleware` is NOT wired into this
    block's own MIDDLEWARE (see tests/settings_test.py), so this is a
    defensive no-op today, kept for parity in case a future change adds
    it to this block's test settings too."""
    import core.security.rate_limiting.django as rate_limiting_django

    rate_limiting_django._default_store = None


@pytest.fixture()
def user_credentials() -> dict:
    """A known email/password pair a test can log in with — NOT yet
    persisted; use the `verified_user` fixture (below) to actually create
    the row. Kept separate so a test that wants a WRONG password can
    still reference the right email."""
    return {"email": "webapp-test-user@example.com", "password": "correct-horse-battery-staple"}


@pytest.fixture()
def verified_user(db, user_credentials: dict):  # noqa: ARG001 -- `db` enables DB access for this fixture
    """Creates a `core.models.User` row directly (bypassing
    `AuthService.register`/email verification entirely — this block's
    `tests/settings_test.py` sets `AUTH_REQUIRE_EMAIL_VERIFICATION=False`
    precisely so this fixture doesn't need to drive a verify-email round
    trip just to get a logged-in-able user) with an Argon2id-hashed
    password via the SAME process-wide `PasswordService`
    `build_auth_service()` itself uses, so `AuthService.login` verifies it
    exactly as it would a normally-registered user's password."""
    from core.models import User
    from core.security.auth.stores import get_password_service

    password_hash = get_password_service().hash(user_credentials["password"])
    return User.objects.create(
        email=user_credentials["email"],
        password_hash=password_hash,
        roles=[],
        email_verified=True,
    )
