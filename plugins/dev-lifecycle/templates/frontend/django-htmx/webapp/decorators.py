"""The HTML-route auth gate — the `login_required`-equivalent for
`webapp`'s server-rendered views. Unlike DRF's `IsAuthenticated` (which
401s with a JSON `ErrorEnvelope`), an HTML route redirects an
unauthenticated visitor to the login page with a `?next=` back-link — see
the block README's "Auth & CSRF" section. Gates item creation/deletion
(`webapp/views.py`) so the auth story is actually exercised, not just
present."""

from __future__ import annotations

import functools
from urllib.parse import urlencode

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from webapp.auth import get_current_principal


def login_required(view_func):
    """Wraps a plain Django view function. Resolves the current principal
    via `webapp.auth.get_current_principal` (the cookie-based adapter,
    NOT Django's own `django.contrib.auth.decorators.login_required` —
    this app has no `AUTH_USER_MODEL`/session-auth surface for that
    decorator to check against, see `backend/django/core/models.py`'s
    `User` docstring on why). On success, stashes the resolved
    `AccessClaims` on `request.principal` so the wrapped view (and any
    template it renders) can use it without re-resolving; on failure,
    redirects to `/login?next=<original path>` rather than rendering an
    error page."""

    @functools.wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        principal = get_current_principal(request)
        if principal is None:
            login_url = "/login?" + urlencode({"next": request.get_full_path()})
            return redirect(login_url)
        request.principal = principal
        return view_func(request, *args, **kwargs)

    return wrapper
