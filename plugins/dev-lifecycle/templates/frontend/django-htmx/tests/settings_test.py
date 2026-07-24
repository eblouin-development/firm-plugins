"""Hermetic test settings for THIS block's own standalone test run.

Extends `backend/django`'s own hermetic `config.settings_test` (sqlite,
placeholder `SECRET_KEY`/`DATABASE_URL`/`JWT_SIGNING_KEY` — see that
module's own docstring) with this block's own `webapp` app wiring:
`INSTALLED_APPS` (+ sessions/messages/staticfiles/webapp),
`MIDDLEWARE` (+ Session/Message/SilentRefresh, appended innermost —
mirroring the "Wiring into apps/api" ordering the block README
documents for a real project's `config/settings.py`), `TEMPLATES[0][
"DIRS"]` (this block's own `templates/`), `STATIC_URL`, and
`ROOT_URLCONF` pointed at `tests.urls` (a tiny test-only URLconf wiring
BOTH `core.urls` and `webapp.urls` — see that module's own docstring).

`tests/conftest.py`'s `sys.path` wiring is what makes `from
config.settings_test import *` resolve at all in a standalone run of this
block — see that file's own module docstring for the "why" this is
unusual. `DJANGO_SETTINGS_MODULE=tests.settings_test`
(`pyproject.toml`'s `[tool.pytest.ini_options]`) is what selects this
module."""

from __future__ import annotations

from pathlib import Path

from config.settings_test import *  # noqa: E402,F401,F403

_THIS_BLOCK_ROOT = Path(__file__).resolve().parent.parent

INSTALLED_APPS = [  # noqa: F821 -- brought in by the star-import above
    *INSTALLED_APPS,
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "webapp",
]

# Session/Message middleware placed INNERMOST (right before Django's own
# SecurityMiddleware/CommonMiddleware, which config.settings.py's own
# MIDDLEWARE list already puts innermost of the security-composition
# stack) -- Django requires SessionMiddleware before AuthenticationMiddleware/
# anything using request.session, and this ordering must not disturb the
# existing security-composition stack's own outermost-to-innermost order
# (see backend/django/config/settings.py's own MIDDLEWARE comment) --
# see the block README's "Wiring into apps/api" section for the exact
# same placement documented for a real project.
MIDDLEWARE = [  # noqa: F821
    *MIDDLEWARE,
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "webapp.middleware.SilentRefreshMiddleware",
]

TEMPLATES[0]["DIRS"] = [str(_THIS_BLOCK_ROOT / "templates")]  # noqa: F821
TEMPLATES[0]["OPTIONS"]["context_processors"] = [  # noqa: F821
    *TEMPLATES[0]["OPTIONS"]["context_processors"],  # noqa: F821
    "django.contrib.messages.context_processors.messages",
    "webapp.context_processors.webapp_context",
]

STATIC_URL = "/static/"
STATICFILES_DIRS: list = []

ROOT_URLCONF = "tests.urls"

# Simplifies this block's own test fixtures -- login/lockout ARE already
# proven against real HTTP by backend/django's own tests/test_auth.py
# (Stage 5c, #45); this block's tests exercise the webapp-specific
# COOKIE/CSRF/fragment/redirect behavior on top of a login that succeeds,
# not the verification/lockout state machine a second time.
AUTH_REQUIRE_EMAIL_VERIFICATION = False  # noqa: F821 -- override of the star-imported default
AUTH_LOCKOUT_ENABLED = False  # noqa: F821
