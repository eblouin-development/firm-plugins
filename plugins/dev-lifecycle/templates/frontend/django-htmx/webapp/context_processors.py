"""Template context processor injecting `principal` (the current
visitor's resolved `AccessClaims`, or `None`) and `csrf_token_value` (the
raw `csrf_token` cookie value) into EVERY template render — so
`templates/webapp/base.html`'s nav (Log in vs. Log out) and CSRF `<meta>`
tag work without every view repeating the same two context keys by hand.

Wire into `config/settings.py`'s
`TEMPLATES[0]["OPTIONS"]["context_processors"]` — see the block README's
"Wiring into apps/api" section for the exact line to add."""

from __future__ import annotations

from typing import Any

from core.security.auth import CSRF_COOKIE_NAME, generate_csrf_token
from webapp.auth import get_current_principal


def webapp_context(request: Any) -> dict[str, Any]:
    # An anonymous visitor who has never logged in has no csrf_token
    # cookie yet -- generating one ad hoc here (never set as a cookie)
    # keeps `{{ csrf_token_value }}` always renderable without an
    # `if`/`default` in every template, but it does NOT double as a real
    # CSRF token for that request: it won't match any cookie
    # `verify_double_submit` compares against. This is harmless because
    # every mutating route this block ships either doesn't need CSRF
    # (login: credential-authenticated, no cookie yet) or is behind
    # `login_required` (item create/delete, logout) — a visitor who
    # reaches one of those already HAS a real `csrf_token` cookie from
    # login, which is what this line then reads back out instead.
    csrf_value = request.COOKIES.get(CSRF_COOKIE_NAME) or generate_csrf_token()
    return {
        "principal": get_current_principal(request),
        "csrf_token_value": csrf_value,
    }
