"""Cookie-based principal-resolution adapter for `webapp`'s server-rendered
views — a thin wrapper over the vendored `core.security.auth` component's
`AuthService`/`AccessClaims`, reading the access token from the
`access_token` cookie this block's `LoginView` sets (see the block
README's "Auth & CSRF" section for why that cookie is this block's own,
NEW extension to the existing cookie set) instead of the `Authorization:
Bearer` header `core/security/auth/django.py`'s own `resolve_principal`
expects.

Not a reimplementation of anything in the vendored component: this module
never touches JWT verification/minting itself — it only extracts the raw
token string from a different transport (a cookie instead of a header)
and hands it to the SAME `AuthService.resolve_access` the bearer-token/API
path already uses, exactly the "thin adapter, not a reimplementation"
instruction this block was authored under."""

from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync

from core.security.auth import AccessClaims, AuthError, InvalidToken
from core.security.auth.stores import AuthNotConfiguredError, build_auth_service

ACCESS_COOKIE_NAME = "access_token"
"""This block's ONE deliberate extension to `backend/django`'s existing
cookie set — see the block README's "Judgment calls" section for the full
rationale (HttpOnly, `Path=/`, TTL matched to `JWT_ACCESS_TTL_SECONDS`,
never exposed to JS)."""


async def resolve_principal_from_cookie(request: Any, auth_service: Any) -> AccessClaims:
    """Reads the `access_token` cookie off `request.COOKIES` and resolves
    it into `AccessClaims` via `auth_service.resolve_access(token)` — the
    identical resolution `core/security/auth/django.py`'s
    `resolve_principal` performs for a bearer header, just sourced from a
    cookie. Raises `InvalidToken` (part of the SAME `AuthError` hierarchy
    `core/security/auth/django.py`'s `AUTH_ERROR_HTTP` table maps) when
    the cookie is missing or the token itself is invalid/expired — a
    caller (a view, `SilentRefreshMiddleware`, or `get_current_principal`
    below) decides what to do next; this function never redirects or
    swallows the error itself."""
    token = request.COOKIES.get(ACCESS_COOKIE_NAME)
    if not token:
        raise InvalidToken("No access token cookie was presented.")
    return await auth_service.resolve_access(token)


def get_current_principal(request: Any) -> AccessClaims | None:
    """Sync, best-effort helper a webapp view (or the `webapp_context`
    context processor) calls to get the resolved principal for the
    current request — `None` if unauthenticated, the access token is
    missing/expired/invalid, or auth isn't configured at all
    (`AuthNotConfiguredError` — an unset `JWT_SIGNING_KEY`). Bridges into
    the async `resolve_principal_from_cookie` above via
    `asgiref.sync.async_to_sync`, mirroring `core/views.py`'s own
    sync-view/async-service posture exactly.

    Deliberately returns `None` rather than raising for EVERY failure
    mode, including a genuinely expired token — an anonymous or
    session-expired visitor is the normal case for a server-rendered page
    (the nav simply shows "Log in" instead of "Log out"), not an error a
    caller needs to handle specially. `webapp/decorators.py`'s
    `login_required` is the seam that turns "no principal" into a
    redirect for the routes that actually require one."""
    try:
        auth_service = build_auth_service()
    except AuthNotConfiguredError:
        return None
    try:
        return async_to_sync(resolve_principal_from_cookie)(request, auth_service)
    except AuthError:
        return None


def enforce_csrf_header_or_form(request: Any) -> None:
    """The mutating-request CSRF gate every webapp POST (login excluded —
    see `webapp/views.py`'s `LoginView` docstring on why login itself
    needs no CSRF check) and every `hx-post`/`hx-delete` call must pass.

    Reuses `core.security.auth`'s existing double-submit-cookie machinery
    verbatim (`verify_double_submit`, `CSRF_COOKIE_NAME`) — this is NOT a
    second CSRF mechanism, it is the identical check
    `core/security/auth/django.py`'s `enforce_csrf` performs, just able to
    read the token from TWO places instead of one:

    1. The `X-CSRF-Token` request header — set on every non-GET htmx
       request by `templates/webapp/base.html`'s `htmx:configRequest`
       listener, reading the value from the `<meta name="csrf-token">`
       tag `webapp_context` (the context processor) renders into every
       page.
    2. A hidden `<input type="hidden" name="csrf_token">` form field —
       rendered into every progressively-enhanced `<form method="post">`
       (see `templates/webapp/partials/_login_form.html`'s sibling forms
       and the item-create/delete forms) for the JS-disabled case, per
       `htmx.md`'s "Progressive enhancement" section: a plain form POST
       cannot set a custom request header at all, so there is no way for
       a JS-disabled submission to carry the token any other way.

    Whichever is present is used (the header takes precedence when both
    are, which only happens for an htmx-issued request against a form
    that also carries the hidden field — harmless, since a real htmx
    request always sets the header to the SAME value the hidden field
    would have carried anyway). `core/security/auth`'s own
    `verify_double_submit` still performs the actual constant-time
    comparison against the `csrf_token` cookie — this function adds no
    comparison logic of its own, only a second place to read the
    candidate token from."""
    from core.security.auth import CSRF_COOKIE_NAME, verify_double_submit

    header_token = request.headers.get("X-CSRF-Token")
    form_token = request.POST.get("csrf_token")
    verify_double_submit(
        csrf_cookie=request.COOKIES.get(CSRF_COOKIE_NAME),
        csrf_header=header_token or form_token,
    )
