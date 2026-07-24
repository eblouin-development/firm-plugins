"""`webapp`-local cookie-setting helpers — a thin, `Path=/`-scoped sibling
of `core.security.auth.django.set_auth_cookies`/`clear_auth_cookies`.

**Why this file exists at all.** The vendored `_cookies.py`'s
`build_refresh_cookie_kwargs`/`build_csrf_cookie_kwargs` (and their
`clear_*` counterparts) hardcode `path="/auth"` — correct and deliberate
for the JSON API track, whose ONLY cookie-mode routes live under
`/auth/*` (`core/urls.py`'s `/auth/login`, `/auth/refresh`, `/auth/logout`
— see that file's own comment). `webapp`'s routes do NOT live under
`/auth/*` — they're mounted at the site root (`webapp/urls.py`: `/`,
`/login`, `/logout`, `/browse/items`, `/browse/items/create`,
`/browse/items/<id>/delete`). A browser only attaches a cookie to a
request whose path is under (or equal to) the cookie's own `Path`
attribute — a `Path=/auth` cookie is NEVER sent to `/logout` or
`/browse/items/create`, no matter how valid it is. Calling
`core.security.auth.django.set_auth_cookies`/`clear_auth_cookies`
directly from `webapp` (as an earlier version of this block did) sets
`refresh_token`/`csrf_token` at `Path=/auth` while `webapp`'s own
`access_token` cookie (below and in `webapp/views.py`/`webapp/
middleware.py`) is correctly set at `Path=/` — a mismatch invisible to
Django's test `Client` (which ignores `Path` entirely when matching
cookies back to requests) but fatal in a real browser: every CSRF-checked
`webapp` POST (`/logout`, `/browse/items/create`, `/browse/items/<id>/
delete`) would find the `csrf_token` cookie simply absent from the
request, and `SilentRefreshMiddleware` would never see a `refresh_token`
cookie on any `webapp` page to refresh from. This is a FUNCTIONAL bug,
not a security bypass — the double-submit CSRF check itself still fails
CLOSED (403) when the cookie is missing; it just fails closed on every
single request instead of only on a forged one.

**The fix.** `webapp` never calls `core.security.auth.django.
set_auth_cookies`/`clear_auth_cookies` — it calls
`set_webapp_auth_cookies`/`clear_webapp_auth_cookies` below instead,
which reuse the SAME vendored `_cookies.py` kwargs builders (so every
other flag — `httponly`, `secure`, `samesite="lax"`, `max_age` — stays
byte-identical to the API track's own cookies) and override only `path`
to `"/"`, matching the `access_token` cookie `webapp` already sets at
`Path=/`. The API track's own `core/views.py` (`LoginView`/`RefreshView`/
`LogoutView`) is UNCHANGED — it still calls `core.security.auth.django.
set_auth_cookies`/`clear_auth_cookies` directly, still at `Path=/auth`;
this file adds a second, `webapp`-scoped call path, it does not modify
the shared one."""

from __future__ import annotations

from typing import Any

from core.security.auth import _cookies


def set_webapp_auth_cookies(response: Any, *, refresh_value: str, csrf_value: str, max_age: int) -> None:
    """`webapp`'s own `set_auth_cookies` — identical to `core.security.
    auth.django.set_auth_cookies` except both cookies are set at
    `path="/"` instead of the vendored builders' own `path="/auth"`
    default, matching every other `webapp` cookie (`access_token`,
    `webapp/views.py`/`webapp/middleware.py`). See this module's own
    docstring for why `path="/auth"` would silently break every
    CSRF-checked `webapp` POST in a real browser."""
    refresh_kwargs = {**_cookies.build_refresh_cookie_kwargs(refresh_value, max_age), "path": "/"}
    csrf_kwargs = {**_cookies.build_csrf_cookie_kwargs(csrf_value, max_age), "path": "/"}
    response.set_cookie(**refresh_kwargs)
    response.set_cookie(**csrf_kwargs)


def clear_webapp_auth_cookies(response: Any) -> None:
    """`webapp`'s own `clear_auth_cookies` — same `path="/"` override as
    `set_webapp_auth_cookies` above, for the same reason: a browser only
    matches a cookie-clear instruction against a cookie set with the SAME
    `path`, so clearing at `path="/auth"` would silently fail to remove
    the `path="/"` cookies `set_webapp_auth_cookies` actually set."""
    refresh_kwargs = {**_cookies.clear_refresh_cookie_kwargs(), "path": "/"}
    csrf_kwargs = {**_cookies.clear_csrf_cookie_kwargs(), "path": "/"}
    response.set_cookie(**refresh_kwargs)
    response.set_cookie(**csrf_kwargs)
