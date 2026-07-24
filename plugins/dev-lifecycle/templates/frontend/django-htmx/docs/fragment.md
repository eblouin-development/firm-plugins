<!-- fragment: block:frontend/django-htmx -->

## Setup
Overlays `apps/api/` — the SAME directory `backend/django` materializes
into (never a separate `apps/web`; see the block README's "Placement &
composition rule"). Requires `backend/django` already wired (its own
`DATABASE_URL`/`SECRET_KEY`, Python 3.13 + uv), plus the settings/urls
edits in the block README's "Wiring into apps/api" section (`webapp` +
`django.contrib.{sessions,messages,staticfiles}` in `INSTALLED_APPS`,
`SessionMiddleware`/`MessageMiddleware`/`SilentRefreshMiddleware` added
innermost, `TEMPLATES[0]["DIRS"]`/context processors, `STATIC_URL`/
`STATICFILES_DIRS`, and `path("", include("webapp.urls"))` in
`config/urls.py`). No new migration — this block adds no new models; it
reads/writes the EXISTING `core.models.Item`/`User` and the EXISTING auth
tables `backend/django` already migrates.

Build Tailwind: `./bin/download-tailwind.sh` (pinned 4.3.3 standalone
CLI, no Node), then `./bin/tailwindcss -i static_src/input.css -o
webapp/static/css/output.css --minify`. Vendor htmx:
`./bin/download-htmx.sh` (pinned 2.0.10, into
`webapp/static/htmx/htmx.min.js`). Then `just dev` (or `uv run gunicorn
config.wsgi:application --bind 0.0.0.0:8000` / `docker compose up
--build`, same as `backend/django`'s own Setup) serves both the JSON API
and this block's server-rendered routes from the SAME process: `/`,
`/login`, `/logout`, `/browse/items`, `/browse/items/create`,
`/browse/items/<uuid>/delete`.

## Maintenance
`webapp/` is entirely NEW glue for this block — nothing in it is vendored
from a catalog component, so the weekly freshness audit does not need to
track drift against a source file the way `backend/django`'s own
`core/security/` subpackages do. It DOES import the vendored
`core.security.auth` component directly (`build_auth_service`,
`resolve_access`, `read_refresh_cookie`, `verify_double_submit`, plus
`_cookies.py`'s `build_refresh_cookie_kwargs`/`build_csrf_cookie_kwargs`/
`clear_refresh_cookie_kwargs`/`clear_csrf_cookie_kwargs` — via
`webapp/cookies.py`'s `Path=/`-overriding wrappers, NOT the `django.py`
adapter's own `set_auth_cookies`/`clear_auth_cookies`, which stay
`Path=/auth`-scoped and are only ever called by the JSON API track's
`core/views.py` — see the block README's "Judgment calls" for why
`webapp` needs its own cookie-setting path) — when that component's
freshness-audit-tracked copy inside `backend/django` changes, re-verify
`webapp/auth.py`'s `resolve_principal_from_cookie`,
`webapp/middleware.py`'s `SilentRefreshMiddleware`, and
`webapp/cookies.py` still call it the same way (no signature changes
expected, since all three call the SAME public functions `core/views.py`
already calls). Tailwind/htmx versions follow
`references/compatibility-matrix.md`'s "Frontend — server-rendered
(Django + HTMX)" section, not bumped independently of that pin.

## Secrets
No NEW secret. `JWT_SIGNING_KEY` (already optional on `backend/django`)
must be set for `/login` to succeed — unset, login fails closed to a 503
with a generic "sign-in unavailable" message (via `AuthNotConfiguredError`,
the SAME fail-closed behavior every `/auth/*` JSON route already has),
never a token signed with an empty key.
