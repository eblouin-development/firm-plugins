"""`webapp`'s page views — the server-rendered, HTMX-enhanced demo surface
this block ships (see the block README's "What this demonstrates").
Plain function-based Django views throughout (no DRF `APIView` anywhere in
this app — this is the server-rendered/HTML track, not the JSON API
track); the auth views bridge into the vendored, async `AuthService` via
`asgiref.sync.async_to_sync`, mirroring `core/views.py`'s own
sync-view/async-service posture exactly. `HX-Request` detection and the
full-page-vs-fragment branch follow `htmx.md`'s "Fragments / partial
responses" pattern throughout."""

from __future__ import annotations

import math
import uuid

from asgiref.sync import async_to_sync
from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from core.contract.pagination import PageParams
from core.models import Item
from core.security.auth import AuthError, CsrfValidationError, generate_csrf_token
from core.security.auth.stores import AuthNotConfiguredError, build_auth_service
from webapp.auth import ACCESS_COOKIE_NAME, enforce_csrf_header_or_form, get_current_principal
from webapp.cookies import clear_webapp_auth_cookies, set_webapp_auth_cookies
from webapp.decorators import login_required
from webapp.forms import ItemForm, LoginForm

PAGE_SIZE = 10


def _is_htmx(request: HttpRequest) -> bool:
    """`htmx.md`'s exact "detect the HTMX request server-side (e.g. the
    `HX-Request` header)" pattern — never a query param or a second URL;
    the SAME template renders both the full page and the standalone
    fragment (`htmx.md`'s "a partial that's also a valid standalone HTMX
    response is ideal")."""
    return request.headers.get("HX-Request") == "true"


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "webapp/home.html", {})


# ---------------------------------------------------------------------------
# Auth: login / logout
# ---------------------------------------------------------------------------


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    """`GET`/`POST /login` — an HTML form (email+password), per the block
    README's "Auth & CSRF" section. Mirrors `core/views.py`'s `LoginView`
    cookie-mode branch handler-for-handler, minus the `X-Auth-Mode` header
    switch (this route is ALWAYS cookie mode — there is no bearer-token
    caller for a server-rendered page) and with a NEW `access_token`
    cookie set alongside the existing `refresh_token`/`csrf_token` pair
    (see the block README's "Judgment calls" — the one deliberate
    extension to the existing cookie set this block introduces).

    No CSRF check on this view, on either the GET or POST — same rationale
    `core/views.py`'s `LoginView` docstring gives: login is
    credential-authenticated (email+password), and there is no cookie yet
    for a CSRF check to protect."""
    if request.method == "GET":
        if get_current_principal(request) is not None:
            return redirect("webapp-home")
        return render(request, "webapp/login.html", {"form": LoginForm(), "auth_error": None})

    form = LoginForm(request.POST)
    if not form.is_valid():
        return _render_login_form(request, form, auth_error=None, status=400)

    try:
        auth_service = build_auth_service()
    except AuthNotConfiguredError:
        return _render_login_form(
            request,
            form,
            auth_error="Sign-in is not available right now. Please try again later.",
            status=503,
        )

    try:
        pair = async_to_sync(auth_service.login)(form.cleaned_data["email"], form.cleaned_data["password"])
    except AuthError:
        # Per htmx.md's "Forms & validation": re-render the form partial
        # with an inline error, never a redirect/500 -- and per
        # core/exceptions.py's own FIX-B posture, ONE generic message
        # regardless of the real reason (unknown email, wrong password,
        # locked account, unverified email are all indistinguishable at
        # the wire on the API track too — see AuthService.login's own
        # docstring on the anti-enumeration defense this preserves).
        return _render_login_form(request, form, auth_error="Invalid email or password.", status=401)

    next_url = request.POST.get("next") or request.GET.get("next") or "/"
    if not next_url.startswith("/") or next_url.startswith("//"):
        # Never redirect off-site — a "next" param is caller-supplied
        # (typically from login_required's own ?next= redirect, but
        # nothing stops a crafted link from setting it to anything).
        next_url = "/"
    response = redirect(next_url)
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=pair.access,
        max_age=settings.JWT_ACCESS_TTL_SECONDS,
        path="/",
        httponly=True,
        secure=True,
        samesite="lax",
    )
    set_webapp_auth_cookies(
        response,
        refresh_value=pair.refresh,
        csrf_value=generate_csrf_token(),
        max_age=settings.JWT_REFRESH_TTL_SECONDS,
    )
    return response


def _render_login_form(request: HttpRequest, form: LoginForm, *, auth_error: str | None, status: int) -> HttpResponse:
    """Shared by every `login_view` failure branch. The login form is a
    PLAIN, progressively-enhanced `<form method="post">` in this block's
    own templates — no `hx-post` — per `htmx.md`'s "Progressive
    enhancement" guidance: a credential-bearing, redirect-on-success form
    is exactly the case a real form (working with no JS at all) handles
    better than an `hx-post` needing `HX-Redirect` wiring. This still
    honors `htmx.md`'s "Fragments / partial responses" pattern faithfully
    (detect `HX-Request`, branch to the partial) for any caller that DOES
    drive this route via htmx (e.g. a project that later adds an
    `hx-boost`ed login link) — `webapp/login.html` (the full-page
    response) `{% include %}`s the SAME `_login_form.html` partial this
    branch returns standalone, so both responses render byte-identical
    form markup."""
    context = {"form": form, "auth_error": auth_error}
    template = "webapp/partials/_login_form.html" if _is_htmx(request) else "webapp/login.html"
    return render(request, template, context, status=status)


@require_http_methods(["POST"])
def logout_view(request: HttpRequest) -> HttpResponse:
    """`POST /logout` — POST-only, CSRF-checked (state-changing: revokes
    the presented refresh token's entire family via `AuthService.logout`),
    clears all three cookies via `clear_webapp_auth_cookies` (the
    existing refresh/csrf pair, at this block's own `Path=/` — see
    `webapp/cookies.py`) plus this block's own `access_token` cookie. A
    missing/invalid CSRF token gets a PLAIN 403 (not the JSON
    `ErrorEnvelope` the API track uses) — see the block README's "Auth &
    CSRF" section for why a plain response, not the envelope, is the
    right shape for an HTML-route failure."""
    try:
        enforce_csrf_header_or_form(request)
    except CsrfValidationError:
        return HttpResponseForbidden("CSRF validation failed.")

    refresh_token = request.COOKIES.get("refresh_token")
    if refresh_token:
        try:
            auth_service = build_auth_service()
            async_to_sync(auth_service.logout)(refresh_token)
        except (AuthNotConfiguredError, AuthError):
            # AuthService.logout is best-effort/idempotent by design (see
            # core/views.py's LogoutView docstring) -- an already-invalid
            # token, or auth being unconfigured, still results in the
            # user's browser-side session ending (cookies cleared below).
            pass

    response = redirect("webapp-home")
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
    clear_webapp_auth_cookies(response)
    return response


# ---------------------------------------------------------------------------
# Items demo surface
# ---------------------------------------------------------------------------


def items_list(request: HttpRequest) -> HttpResponse:
    """`GET /browse/items` — server-rendered pagination + an `hx-get`
    search/filter input with debounce (`templates/webapp/items/list.html`
    wires `hx-trigger="keyup changed delay:300ms, search"`, `htmx.md`'s
    exact pattern). Detects `HX-Request` and renders ONLY
    `_item_list.html` (also `{% include %}`d by the full page) instead of
    the full page — `htmx.md`'s "Fragments / partial responses" pattern."""
    query = request.GET.get("q", "").strip()
    try:
        requested_page = int(request.GET.get("page", "1"))
    except ValueError:
        requested_page = 1
    # PageParams (core.contract.pagination, the SAME vendored contract
    # source the JSON API track validates page/size through) clamps an
    # out-of-range page/size rather than accepting it — reused here for a
    # single, already-proven bounds policy instead of re-deriving one.
    params = PageParams(page=max(requested_page, 1), size=PAGE_SIZE)

    queryset = Item.objects.all().order_by("created_at", "id")
    if query:
        queryset = queryset.filter(name__icontains=query)

    total = queryset.count()
    pages = max(1, math.ceil(total / params.size))
    page = min(params.page, pages)
    offset = (page - 1) * params.size
    items = list(queryset[offset : offset + params.size])

    context = {
        "items": items,
        "query": query,
        "page": page,
        "pages": pages,
        "total": total,
        "create_form": ItemForm(),
    }
    template = "webapp/partials/_item_list.html" if _is_htmx(request) else "webapp/items/list.html"
    return render(request, template, context)


@login_required
@require_http_methods(["POST"])
def item_create(request: HttpRequest) -> HttpResponse:
    """`POST /browse/items/create` — gated behind `login_required` so the auth
    story is actually exercised, not just present (block README, "What
    this demonstrates"). Returns just the new `<li>` fragment on success
    (`hx-post` on the create form swaps it into the list via
    `hx-swap="afterbegin"` targeting the list container — see
    `templates/webapp/items/list.html`) or re-renders the create-form
    partial with inline errors on failure — `htmx.md`'s "Forms &
    validation" pattern, the same shape `_render_login_form` above uses
    for the login form."""
    try:
        enforce_csrf_header_or_form(request)
    except CsrfValidationError:
        return HttpResponseForbidden("CSRF validation failed.")

    form = ItemForm(request.POST)
    if not form.is_valid():
        # The create form's own hx-post targets #item-list (hx-swap
        # "afterbegin") for the SUCCESS case -- the new row's natural
        # home. A validation failure needs to land back in the form
        # itself instead: HX-Retarget/HX-Reswap (htmx.md's "use response
        # headers ... to drive client behavior from the server when
        # needed") override the form's own hx-target/hx-swap for just
        # this response, so the SAME create-form partial (now carrying
        # inline errors, per htmx.md's "Forms & validation") replaces the
        # form in place instead of being inserted into the item list.
        response = render(request, "webapp/partials/_item_create_form.html", {"create_form": form}, status=400)
        response["HX-Retarget"] = "#item-create-form"
        response["HX-Reswap"] = "outerHTML"
        return response

    item = Item.objects.create(
        name=form.cleaned_data["name"],
        description=form.cleaned_data.get("description") or None,
    )
    return render(request, "webapp/partials/_item_row.html", {"item": item})


@login_required
@require_http_methods(["POST"])
def item_delete(request: HttpRequest, item_id: uuid.UUID) -> HttpResponse:
    """`POST /browse/items/<item_id>/delete` — gated behind `login_required`, the
    demo surface's second mutating, auth-exercising route. Soft-deletes
    via `Item.mark_deleted()` (the SAME soft-delete convention
    `core/models.py`'s `Item` already establishes for the JSON API track —
    this view does not hard-delete). Returns an EMPTY 200 body; the
    triggering element uses `hx-target="closest li"`
    `hx-swap="outerHTML"` (see `templates/webapp/partials/_item_row.html`)
    so swapping in an empty response removes the row from the DOM —
    `htmx.md`'s smallest-swap-that-does-the-job guidance."""
    try:
        enforce_csrf_header_or_form(request)
    except CsrfValidationError:
        return HttpResponseForbidden("CSRF validation failed.")

    item = Item.objects.filter(id=item_id).first()
    if item is not None:
        item.mark_deleted()
        item.save(update_fields=["deleted_at"])
    return HttpResponse(status=200)
