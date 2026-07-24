"""`SilentRefreshMiddleware` — best-effort silent refresh for
`webapp`'s cookie-authenticated pages: a MISSING or expired `access_token`
cookie, paired with a present, valid `refresh_token` cookie, transparently
mints a fresh access token (and rotates the refresh/csrf pair, via the
SAME `AuthService.refresh` rotation-with-reuse-detection state machine
`core/views.py`'s `RefreshView` uses) instead of bouncing the visitor to
the login page on every `JWT_ACCESS_TTL_SECONDS` expiry (default 900s).

**Deliberately simple — a documented known simplification, not a bug.**
This middleware does NOT lock or coordinate across concurrent requests
from the same browser. Two tabs (or two near-simultaneous requests from
one tab) racing an expired access token can each independently call
`AuthService.refresh` with the same still-valid refresh token; both calls
succeed (refresh tokens aren't single-use until they're rotated OUT from
under a valid presentation — see `_core.AuthService.refresh`'s own
docstring), each mints its own new pair, and whichever response's
`Set-Cookie` header the browser applies LAST wins. This is safe — neither
race outcome ever lets a wrong credential through, and the "loser" of the
race isn't locked out, just slightly wasteful (one extra rotation
happened) — see the block README's "Judgment calls" for the fuller
rationale on why a locking/single-flight implementation was deliberately
not built for this demo-scoped block.

Never raises past this middleware: any failure during the silent-refresh
attempt (network/DB error, an already-invalid or reused refresh token,
`JWT_SIGNING_KEY` unset) is caught and the request proceeds exactly as if
no cookies were present at all — the visitor simply reads as
unauthenticated for this request (and, if the failure is durable, will be
redirected to login the next time a `login_required` route is hit)."""

from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from django.conf import settings

from core.security.auth import AuthError, generate_csrf_token
from core.security.auth.django import read_refresh_cookie, set_auth_cookies
from core.security.auth.stores import AuthNotConfiguredError, build_auth_service
from webapp.auth import ACCESS_COOKIE_NAME


class SilentRefreshMiddleware:
    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> Any:
        pending = self._maybe_silent_refresh(request)
        response = self.get_response(request)
        if pending is not None:
            self._apply_refresh(response, pending)
        return response

    def _maybe_silent_refresh(self, request: Any) -> dict[str, str] | None:
        access_token = request.COOKIES.get(ACCESS_COOKIE_NAME)
        refresh_token = read_refresh_cookie(request)
        if access_token or not refresh_token:
            # Either an access token is already present (this middleware
            # only fires when it's MISSING — it never proactively
            # re-validates a present-but-possibly-expired token; that's
            # webapp.auth.get_current_principal's job, which simply treats
            # an invalid/expired token as "no principal"), or there is no
            # refresh cookie to silently refresh from at all.
            return None
        try:
            auth_service = build_auth_service()
        except AuthNotConfiguredError:
            return None
        try:
            pair = async_to_sync(auth_service.refresh)(refresh_token)
        except AuthError:
            # Expired, revoked, reused, or otherwise invalid refresh
            # token -- fail closed, proceed unauthenticated. Never raise
            # out of middleware for a client-caused auth failure.
            return None
        # So THIS request's own view/context-processor also sees the
        # freshly minted access token immediately, not only the next
        # request after the Set-Cookie round-trips through the browser.
        request.COOKIES[ACCESS_COOKIE_NAME] = pair.access
        return {
            "access_token": pair.access,
            "refresh_token": pair.refresh,
            "csrf_token": generate_csrf_token(),
        }

    def _apply_refresh(self, response: Any, pending: dict[str, str]) -> None:
        response.set_cookie(
            key=ACCESS_COOKIE_NAME,
            value=pending["access_token"],
            max_age=settings.JWT_ACCESS_TTL_SECONDS,
            path="/",
            httponly=True,
            secure=True,
            samesite="lax",
        )
        set_auth_cookies(
            response,
            refresh_value=pending["refresh_token"],
            csrf_value=pending["csrf_token"],
            max_age=settings.JWT_REFRESH_TTL_SECONDS,
        )
