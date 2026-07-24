"""Auth-view tests — login success/failure, logout, CSRF enforcement, and
the login-required redirect. Mirrors backend/django's own
`tests/test_cookie_auth.py` in spirit (same underlying `AuthService`/
cookie machinery) but drives it through `webapp`'s HTML routes instead of
the JSON `/auth/*` API."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db(transaction=True)
# transaction=True: same durability rationale backend/django's own
# tests/test_auth.py documents (DjangoUserStore/DjangoRefreshTokenStore
# rely on Django's autocommit, not a per-test rolled-back atomic() block —
# see core/security/auth/stores.py's DjangoRefreshTokenStore docstring).


def test_login_success_sets_all_three_cookies_and_redirects(client, verified_user, user_credentials):
    response = client.post(
        "/login",
        {"email": user_credentials["email"], "password": user_credentials["password"]},
    )

    assert response.status_code == 302
    assert response.url == "/"

    # Cookie flags asserted off the RENDERED Set-Cookie text, not read as
    # booleans off the Morsel directly -- Django's set_cookie only ever
    # WRITES a flag key when it's truthy, so the rendered text is the one
    # representation that reliably distinguishes "absent" from "explicitly
    # false" -- same posture backend/django's own tests/test_cookie_auth.py
    # documents and uses.
    access_header = response.cookies["access_token"].output()
    assert "HttpOnly" in access_header
    assert "Secure" in access_header
    assert "SameSite=lax" in access_header
    assert "Path=/" in access_header
    # This block's ONE deliberate cookie extension (see README "Judgment
    # calls") -- Path=/ (not /auth like the refresh/csrf pair below), so
    # every page route can read it, not just /auth/*.
    assert "Path=/auth" not in access_header

    refresh_header = response.cookies["refresh_token"].output()
    assert "HttpOnly" in refresh_header
    assert "Secure" in refresh_header
    assert "Path=/auth" in refresh_header

    csrf_header = response.cookies["csrf_token"].output()
    assert "HttpOnly" not in csrf_header


def test_login_failure_rerenders_form_partial_with_inline_error(client, verified_user, user_credentials):
    response = client.post("/login", {"email": user_credentials["email"], "password": "wrong-password"})

    assert response.status_code == 401
    body = response.content.decode()
    assert "Invalid email or password." in body
    # Re-renders the FULL page (a plain, non-htmx POST) -- never a
    # redirect, never a 500 -- but the same _login_form.html partial is
    # what's embedded either way (see login.html's own {% include %}).
    assert "<nav" in body
    assert "access_token" not in response.cookies


def test_login_failure_via_htmx_returns_only_the_form_partial(client, verified_user, user_credentials):
    response = client.post(
        "/login",
        {"email": user_credentials["email"], "password": "wrong-password"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 401
    body = response.content.decode()
    assert "Invalid email or password." in body
    assert "<nav" not in body
    assert "<html" not in body


def test_login_missing_fields_shows_field_errors_not_auth_error(client):
    response = client.post("/login", {"email": "", "password": ""})

    assert response.status_code == 400
    body = response.content.decode()
    assert "Invalid email or password." not in body
    assert "This field is required." in body


def _login(client, user_credentials) -> None:
    response = client.post(
        "/login", {"email": user_credentials["email"], "password": user_credentials["password"]}
    )
    assert response.status_code == 302


def test_logout_clears_cookies_and_requires_csrf(client, verified_user, user_credentials):
    _login(client, user_credentials)
    csrf_value = client.cookies["csrf_token"].value

    # Missing CSRF -> plain 403, not the JSON ErrorEnvelope.
    forbidden = client.post("/logout")
    assert forbidden.status_code == 403
    assert forbidden["Content-Type"].startswith("text/")

    # Valid CSRF (header) -> redirect + all cookies cleared.
    response = client.post("/logout", HTTP_X_CSRF_TOKEN=csrf_value)
    assert response.status_code == 302
    for name in ("access_token", "refresh_token", "csrf_token"):
        assert "Max-Age=0" in response.cookies[name].output()


def test_logout_accepts_csrf_token_from_hidden_form_field(client, verified_user, user_credentials):
    _login(client, user_credentials)
    csrf_value = client.cookies["csrf_token"].value

    response = client.post("/logout", {"csrf_token": csrf_value})
    assert response.status_code == 302


def test_anonymous_visitor_hitting_a_protected_page_redirects_to_login(client):
    response = client.get("/browse/items/create")
    # GET isn't even allowed on this POST-only route, but login_required
    # runs BEFORE the method check (see webapp/views.py's decorator
    # order) -- an anonymous caller is redirected to login either way,
    # never shown a raw 405.
    assert response.status_code == 302
    assert response.url.startswith("/login?next=")
