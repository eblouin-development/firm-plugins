<!--
block: frontend/django-htmx
needs:
  - backend/django materialized into the same apps/api/ (Python 3.13 + uv, its DATABASE_URL/SECRET_KEY) — see "Composition contract"
  - the vendored core.security.auth component backend/django already vendors — imported directly, not re-vendored
  - django.contrib.sessions/messages/staticfiles added to INSTALLED_APPS by this block's wiring
  - no new required env var — JWT_SIGNING_KEY (already optional) must be set for login to succeed
exposes:
  - the webapp/ Django app: server-rendered routes (/, /login, /logout, /browse/items, ...)
  - templates/ + static_src/ — an overlay onto apps/api/, not a second app
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-24
provenance: manual
-->

# frontend/django-htmx

The Django "server-rendered + HTMX" block: an **overlay** of a `webapp`
Django app, templates, and Tailwind (standalone CLI) styling that composes
into the SAME `apps/api/` directory `backend/django` already materializes
— closing the gap issue #102 identified (`references/frontend/htmx.md`
and `references/backend/django.md` describe this path in depth, but no
block shipped it). Lives at `templates/frontend/django-htmx/` in this
repo. Everything here is **subordinate to a project's existing
conventions** — when a scaffolded project has diverged, the project wins.

## Contents
- Placement & composition rule
- Composition contract
- Auth & CSRF
- Wiring into apps/api
- Tailwind (standalone CLI)
- App layout
- What this demonstrates
- Where this fits
- Testing
- Judgment calls

## Placement & composition rule

**This is the key architectural decision — read this before anything
else.** `frontend/django-htmx` is **NOT** a standalone deployable and does
**NOT** materialize into a separate `apps/web`. Django template rendering
has to run in the SAME WSGI/ASGI process as `backend/django` — there is no
separate Node server here to serve HTML, and no independent Python process
either. So this block ships an **overlay**: extra files meant to be copied
into the SAME `apps/api/` directory `backend/django` already materializes
into —

- a new Django app `webapp/` (views, urls, forms, auth adapter,
  middleware, decorators) sitting **alongside** `core/`, never inside it;
- a project-root `templates/` directory (base layout + page templates +
  partials);
- a `static_src/` directory (Tailwind input CSS) plus `bin/` download
  scripts (Tailwind standalone CLI, htmx's static build) — no Node
  toolchain anywhere in this block;
- explicit, copy-pasteable instructions (below, "Wiring into apps/api")
  for the handful of `config/settings.py` / `config/urls.py` edits a
  scaffolded project applies once, by hand or via an agent following this
  README.

Since `scaffolding` in this kit is a documentation-driven composition
process, not code that mutates files (see the `scaffolding` skill), the
"Wiring into apps/api" section below **is** the actual mechanism — it has
to be precise enough that a human or agent following it gets the wiring
right by reading it alone.

**Composition rule with the SPA blocks — an acceptance criterion of
#102, stated plainly:** `frontend/django-htmx` is an **EITHER/OR
alternative to `frontend/vite-spa` / `frontend/nextjs`** for a project's
main, human-facing web surface. A project picks ONE way to serve its
site: either a separate `apps/web` SPA/Next.js app consuming the JSON API,
or this block's server-rendered templates living inside `apps/api` itself.
**Never both** — there is no sense running two different UIs for the same
site, and both blocks would fight over the same "the human-facing site"
role.

- **It composes FINE alongside `frontend/nextjs-admin`** (`apps/admin`) —
  that block is already a separate deployable, gated on the `admin` role,
  talking to the backend purely over the JSON API / `@repo/api-client`.
  Nothing about `django-htmx` changes that contract; the admin app doesn't
  care whether the main site is server-rendered or an SPA.
- **It composes FINE alongside `backend/django`'s existing JSON API
  surface itself** — `/items`, `/auth/*` (bearer mode) stay live,
  unchanged. This block ADDS server-rendered routes at **different
  paths** (see "Wiring into apps/api" and the routing-collision judgment
  call below); it never removes or replaces the JSON ones. A mobile app or
  a future SPA-consuming client can keep hitting the JSON API exactly as
  before.
- **It requires `backend/django`**, not `backend/fastapi` — there is no
  Python template-rendering equivalent for the FastAPI track in this kit
  yet.
- **It is incompatible with `frontend/vite-spa` / `frontend/nextjs` in
  the same project's `apps/web` slot** — pick one.

## Composition contract

**NEEDS**
- **`backend/django` materialized into the SAME `apps/api/` directory**
  this block overlays — `core/models.py` (the `Item`/`User` models),
  `core/contract/pagination.py` (`PageParams`, reused for this block's own
  pagination bounds), and `core/security/auth/` (the vendored
  `AuthService`/`PasswordService`/cookie-CSRF machinery) all resolve as
  plain Python imports (`from core.models import Item`, `from
  core.security.auth import ...`) once `webapp/` sits next to `core/` in
  one directory. This block ships NO Python dependencies of its own beyond
  what `backend/django` already pins (see `pyproject.toml`'s own note).
- **`backend/django`'s existing `DATABASE_URL`/`SECRET_KEY`** — unchanged,
  no new required env var.
- **`JWT_SIGNING_KEY`** (already optional on `backend/django` — unset
  fails every `/auth/*` route AND this block's `/login` closed, per
  `AuthNotConfiguredError`'s existing fail-closed posture) must be set for
  login to actually work. No new interaction beyond what `backend/django`
  already documents.
- **`AUTH_COOKIE_MODE_ENABLED`** — **no interaction**. That flag only
  gates whether `backend/django`'s CORS policy allows credentials/extra
  headers for a CROSS-ORIGIN SPA caller (see that block's
  `config/settings.py`). This block's requests are always same-origin
  (server-rendered pages served by the same process that reads the
  cookies) — CORS is not in the request path at all for `webapp`'s own
  routes, so `AUTH_COOKIE_MODE_ENABLED` can stay `False` (its secure
  default) even in a project that ships this block.
- **Django's `django.contrib.sessions` / `django.contrib.messages` /
  `django.contrib.staticfiles`** — added to `INSTALLED_APPS` by the wiring
  below. `sessions`/`messages` are added because Django's template engine
  and a few of its own middlewares expect them present even though this
  block's OWN auth never uses `request.session` (see "Auth & CSRF" — this
  block's session/CSRF story is entirely the vendored cookie/JWT scheme,
  not Django's session framework). `staticfiles` serves the compiled
  Tailwind CSS and the vendored `htmx.min.js`.

**EXPOSES**
- **Server-rendered routes**: `GET /`, `GET`/`POST /login`, `POST
  /logout`, `GET /browse/items`, `POST /browse/items/create`, `POST
  /browse/items/<uuid:item_id>/delete` — see "What this demonstrates".
- **The `webapp/` Django app** (`INSTALLED_APPS` label: `"webapp"`) —
  views, forms, the cookie-based auth adapter (`webapp/auth.py`), the
  silent-refresh middleware (`webapp/middleware.py`), and the
  `login_required` decorator (`webapp/decorators.py`).
- **`templates/`** — `base.html` + page templates + reusable partials
  (`templates/webapp/partials/`), meant to land at the project root
  `templates/` directory backend/django's `config/settings.py`
  `TEMPLATES[0]["DIRS"]` is wired to (see below).
- **`static_src/`** (Tailwind v4 CSS-first input) + `bin/
  download-tailwind.sh` / `bin/download-htmx.sh` (dev-machine setup
  scripts, never touched by `tests/`).
- **Its co-located doc fragment**: `docs/fragment.md`.

## Auth & CSRF

**Reuses the EXISTING vendored `core.security.auth` component verbatim —
no second copy, no `django.contrib.auth`.** `webapp/` imports from
`core.security.auth`/`core.security.auth.stores` exactly like
`backend/django`'s own `core/views.py` already does
(`build_auth_service()`, `AuthService`, `PasswordService`,
`DjangoUserStore`). This block never introduces Django's own
`AUTH_USER_MODEL`/authentication backends — `core/models.py`'s `User` is
deliberately a plain `models.Model`, not `AbstractBaseUser` (see that
model's own docstring), and this block's auth story stays exactly the JWT
+ cookie scheme the JSON API already uses.

**Login** (`webapp/views.py`'s `login_view`): an HTML form (email +
password) POSTs to `/login`. The view builds an `AuthService` via
`build_auth_service()` (mirroring `core/views.py`'s `LoginView`
cookie-mode branch) and bridges into it with
`asgiref.sync.async_to_sync(...)`, matching the existing
sync-view/async-service posture. On success it sets THREE cookies:

- `access_token` — **this block's ONE deliberate, NEW extension to the
  existing cookie set** (`HttpOnly; Secure; SameSite=Lax; Path=/`, TTL =
  `JWT_ACCESS_TTL_SECONDS`). See "Judgment calls" for why this is safe.
- `refresh_token` / `csrf_token` — the EXISTING pair `set_auth_cookies`
  already sets, reused verbatim, unchanged flags/`Path=/auth`.

**Principal resolution** (`webapp/auth.py`): every page that needs the
current user reads the `access_token` cookie and resolves it via
`resolve_principal_from_cookie` — a thin adapter over the SAME
`AuthService.resolve_access` the bearer-token/API path uses, just sourced
from a cookie instead of an `Authorization` header (never a
reimplementation of JWT verification). `get_current_principal` is the
sync, best-effort wrapper every view and the `webapp_context` context
processor call; it returns `None` for every failure mode (missing cookie,
expired/invalid token, `JWT_SIGNING_KEY` unset) rather than raising — an
anonymous or session-expired visitor is the normal case for a
server-rendered page.

**Silent refresh** (`webapp/middleware.py`'s `SilentRefreshMiddleware`):
an expired/missing `access_token` cookie, paired with a present, valid
`refresh_token` cookie, transparently refreshes (via `AuthService.refresh`
— the SAME rotation-with-reuse-detection state machine `RefreshView`
uses) instead of bouncing the visitor to `/login` on every
`JWT_ACCESS_TTL_SECONDS` expiry. Deliberately simple — see "Judgment
calls" for the documented known simplification (no cross-request
locking/single-flight).

**`login_required`** (`webapp/decorators.py`): the HTML-route auth gate.
Unlike DRF's `IsAuthenticated` (401 JSON envelope), it redirects an
unauthenticated visitor to `/login?next=<path>`. Gates item
creation/deletion so the auth story is actually exercised, not just
present.

**CSRF: reuses the EXISTING double-submit-cookie scheme verbatim —
Django's own `CsrfViewMiddleware`/`{% csrf_token %}` tag are DELIBERATELY NOT added.** Adding
them would be a second, parallel, uncoordinated CSRF mechanism alongside
the one this whole kit already standardizes on for cookie-mode auth (see
`references/security/secure-baseline.md`'s cookie-session CSRF guidance,
which this design already satisfies via the double-submit scheme). Every
HTMX mutating request and every plain `<form method="post">` carries the
SAME `csrf_token`:

- `templates/webapp/base.html` renders `<meta name="csrf-token"
  content="...">` (the raw `csrf_token` cookie value, from
  `webapp_context`) and wires an `htmx:configRequest` listener that sets
  `X-CSRF-Token` on every non-GET htmx request — the standard documented
  htmx+CSRF pattern, 100% reuse of the existing double-submit machinery.
- Every progressively-enhanced `<form method="post">` also renders a
  hidden `<input type="hidden" name="csrf_token" value="...">` — a
  JS-disabled form cannot set a custom header at all, so the value has to
  travel some other way for that case.
- `webapp/auth.py`'s `enforce_csrf_header_or_form` accepts the token from
  **either** the `X-CSRF-Token` header **or** the `csrf_token` POST field
  — whichever is present — then hands both to the SAME
  `core.security.auth.verify_double_submit` constant-time comparison
  `enforce_csrf` (the JSON-API adapter) already uses. This is a thin
  "read from two places" adapter, not a second CSRF implementation.
- A missing/invalid CSRF token on a webapp mutating route (logout, item
  create/delete) returns a **plain 403** (`HttpResponseForbidden`), not
  the JSON `ErrorEnvelope` the API track uses — an HTML route has no JSON
  envelope to render consistently with; see "Judgment calls".
- Login itself needs no CSRF check — same rationale `core/views.py`'s
  `LoginView` documents: it's credential-authenticated, and there is no
  cookie yet for a CSRF check to protect.

## Wiring into apps/api

Once both blocks are materialized into the SAME `apps/api/` directory,
apply these edits to `backend/django`'s `config/settings.py` and
`config/urls.py` (this is a documentation-driven recipe — `scaffolding`
has no automated file-patching step in this kit, see "Placement &
composition rule" above):

**`config/settings.py`**

```python
# INSTALLED_APPS -- add these four (order within the list doesn't matter;
# shown here as the tail of the existing list):
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "core",
    # --- added by frontend/django-htmx ---
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "webapp",
]

# MIDDLEWARE -- add SessionMiddleware/MessageMiddleware INNERMOST, i.e.
# immediately BEFORE Django's own SecurityMiddleware/CommonMiddleware
# (which backend/django's own MIDDLEWARE list already places innermost of
# the security-composition stack -- see that file's own big MIDDLEWARE
# comment). Django REQUIRES SessionMiddleware before AuthenticationMiddleware/
# anything touching request.session; placing both new entries here does
# NOT disturb the existing security-composition order (CORS -> security-
# headers -> request-id -> rate-limiting stay outermost, exactly as
# backend/django's own README documents) -- it only adds two entries at
# the boundary already closest to the view. Also add
# webapp.middleware.SilentRefreshMiddleware right after them (silent
# refresh needs to run before the view, and has no ordering requirement
# relative to Django's own Security/CommonMiddleware).
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "core.security.security_headers.django.SecurityHeadersMiddleware",
    "core.security.audit_logging.middleware.RequestIDMiddleware",
    "core.security.rate_limiting.django.RateLimitMiddleware",
    # --- added by frontend/django-htmx ---
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "webapp.middleware.SilentRefreshMiddleware",
    # --- end added ---
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

# TEMPLATES[0] -- point DIRS at the project-root templates/ dir this block
# ships, and add the webapp context processor (+ Django's own messages
# processor, since django.contrib.messages is now installed):
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # was: []
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",  # added
                "webapp.context_processors.webapp_context",              # added
            ],
        },
    },
]

# Static files -- new (backend/django's own settings.py has neither today):
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "webapp" / "static"]
```

**`config/urls.py`**

```python
urlpatterns: list = [
    path("api/schema", SpectacularAPIView.as_view(), name="schema"),
    path("", include("core.urls")),
    path("", include("webapp.urls")),  # added by frontend/django-htmx
]
```

**Judgment call: the item-browsing page lives at `/browse/items`, not
`/items`.** `core/urls.py` already binds `GET`/`POST /items` to
`ItemViewSet` (the JSON API) — a literal `/items` HTML page would collide.
This block's server-rendered item list therefore lives at `/browse/items`
(and `/browse/items/create`, `/browse/items/<uuid>/delete`) — additive,
never colliding with the JSON surface, matching the "Placement &
composition rule" promise that this block never removes or replaces the
JSON routes. `webapp/urls.py`'s own header comment documents this in
place too.

## Tailwind (standalone CLI)

Pinned to **Tailwind CSS 4.x (4.3.3)**, kept in lockstep with the
Vite/Next.js blocks' own `tailwindcss` npm pin (same 4.3.3 release train —
see `references/compatibility-matrix.md`'s "Frontend — server-rendered
(Django + HTMX)" section) — a different DISTRIBUTION mechanism, not a
different version. No Node toolchain, no `package.json`, no
`tailwind.config.js` (Tailwind v4 is CSS-first) anywhere in this block:

1. `./bin/download-tailwind.sh` downloads the pinned standalone CLI binary
   for the host platform to `./bin/tailwindcss` (GitHub releases, `v4.3.3`
   tag). Dev-machine/CI use only — `tests/` never touches the network.
2. `static_src/input.css` is the CSS-first entry point: `@import
   "tailwindcss";` plus a small `.htmx-indicator` utility (`htmx.md`'s
   "Show feedback during requests" guidance — hidden by default, visible
   while the nearest `htmx-request`-classed ancestor has an in-flight
   request). No `@source`/content list to maintain by hand — Tailwind v4's
   standalone CLI scans the directory tree automatically.
3. Build: `./bin/tailwindcss -i static_src/input.css -o
   webapp/static/css/output.css --minify` — the output lands under
   `webapp/static/css/`, inside Django's `STATICFILES_DIRS` (see "Wiring
   into apps/api"), which `templates/webapp/base.html`'s
   `{% static 'css/output.css' %}` reads back.
4. `./bin/download-htmx.sh` downloads the pinned **htmx 2.x (2.0.10)**
   static build to `webapp/static/htmx/htmx.min.js` — a single vendored
   file, not an npm package, matching the same no-Node posture (see the
   compatibility matrix's own htmx row).

## App layout

```
webapp/                    # the Django app this block ships (INSTALLED_APPS label: "webapp")
  __init__.py
  apps.py                    # WebappConfig
  urls.py                      # /, /login, /logout, /browse/items, /browse/items/create, /browse/items/<uuid>/delete
  views.py                       # home, login_view, logout_view, items_list, item_create, item_delete
  forms.py                         # LoginForm, ItemForm -- shape-only validation, see "Auth & CSRF"
  auth.py                            # cookie-based principal resolution + enforce_csrf_header_or_form
  middleware.py                        # SilentRefreshMiddleware
  decorators.py                          # login_required (redirects, not a 401 envelope)
  context_processors.py                    # webapp_context -- principal + csrf_token_value on every render
templates/
  webapp/
    base.html                 # named blocks, nav, CSRF meta tag + htmx:configRequest script, htmx.min.js
    home.html
    login.html                  # {% include %}s partials/_login_form.html
    items/
      list.html                   # search input (debounced hx-get) + {% include %}s the create form + item list
    partials/
      _login_form.html              # standalone-safe: included by login.html AND returned directly on HX-Request
      _item_create_form.html          # standalone-safe: included by items/list.html AND returned on validation failure
      _item_list.html                   # standalone-safe: included by items/list.html AND returned on HX-Request
      _item_row.html                      # standalone-safe: included per-item AND returned on hx-post create success
static_src/
  input.css                 # @import "tailwindcss"; + .htmx-indicator
bin/
  download-tailwind.sh        # fetches the pinned 4.3.3 standalone CLI (dev/CI only, no network in tests)
  download-htmx.sh              # fetches the pinned htmx 2.0.10 static build (dev/CI only, no network in tests)
tests/
  conftest.py                # sys.path wiring onto backend/django's core/config (see that file's own docstring)
  settings_test.py             # hermetic sqlite settings, extending backend/django's own config.settings_test
  urls.py                        # test-only URLconf wiring core.urls + webapp.urls together
  test_auth_views.py               # login/logout/CSRF/login-required
  test_items_views.py                # HX-Request fragment/full-page, create/delete, validation
docs/
  fragment.md              # this block's doc fragment (documentation-standard.md)
```

## What this demonstrates

- **`GET /`** — a home page reading `principal` from the context
  processor (nav shows Log in vs. Log out).
- **`GET`/`POST /login`** — a progressively-enhanced plain `<form>` (see
  "Judgment calls" on why this route deliberately doesn't use `hx-post`),
  re-rendering the SAME `_login_form.html` partial with an inline error on
  failure (`htmx.md`'s "Forms & validation").
- **`POST /logout`** — POST-only, CSRF-checked, clears all three cookies
  via `clear_auth_cookies` plus this block's own `access_token` cookie.
- **`GET /browse/items`** — server-rendered pagination (`PageParams`,
  reused from `core.contract.pagination`) + an `hx-get` search input with
  `hx-trigger="keyup changed delay:300ms, search"` — `htmx.md`'s exact
  debounce pattern — detecting `HX-Request` server-side and branching
  between the full page and `_item_list.html` alone (`htmx.md`'s
  "Fragments / partial responses").
- **`POST /browse/items/create`** (`login_required`) — an `hx-post` form
  returning just the new `<li>` on success (swapped in via
  `hx-swap="afterbegin"`), or re-rendering the create-form partial with
  inline errors on failure — using `HX-Retarget`/`HX-Reswap` response
  headers to redirect where the error response lands, since the form's own
  `hx-target` points at the success destination (the list), not itself
  (`htmx.md`'s "use response headers ... to drive client behavior from
  the server when needed").
- **`POST /browse/items/<uuid>/delete`** (`login_required`) — soft-deletes
  via `Item.mark_deleted()` (the existing convention `core/models.py`
  already establishes) and returns an empty 200, swapped via
  `hx-target="closest li" hx-swap="outerHTML"` to remove the row.

## Where this fits

Content sites, admin-lite internal tools, and SEO-friendly server-rendered
pages where most interactivity is request/response (forms, filtering,
pagination, inline edits) — `htmx.md`'s own "When this path fits"
section. It is **not** a fit for rich, persistent client-side state or
app-like interactions (drag-and-drop canvases, real-time collaborative
editing) — that's the `frontend/vite-spa`/`frontend/nextjs` blocks'
territory, and per "Placement & composition rule" above, a project picks
one or the other, not both.

No `seo` recipe exists yet in `references/recipes/` as of this writing
(checked before writing this section) — this section deliberately does
not cross-link one. A project wanting explicit SEO tooling (sitemaps,
structured data, meta-tag conventions) beyond what server-rendered HTML
already gets for free should treat that as a gap to fill with a future
recipe, not something this block already wires.

## Testing

`pytest` (via `pytest-django`) — see `tests/conftest.py`'s own module
docstring for the unusual `sys.path` wiring this block's STANDALONE test
run needs (this block overlays `backend/django`; a real scaffolded project
has both blocks' code physically co-located in one `apps/api/`, but this
repo keeps them in sibling template directories). Run from this
directory:

```sh
uv venv && uv pip install -e . --group dev  # or: pip install the deps pyproject.toml lists
pytest
```

Covers: login success sets all three cookies with correct flags (asserted
off the rendered `Set-Cookie` text, not booleans read off the cookie
object — the one representation that reliably distinguishes "absent" from
"explicitly false", matching `backend/django`'s own
`tests/test_cookie_auth.py` posture); login failure re-renders the form
partial with an inline error (never a redirect/500); a plain vs.
`HX-Request` login failure returns the full page vs. the partial alone;
logout clears all three cookies and requires CSRF (missing CSRF → plain
403); CSRF accepted from either the header or the hidden form field; an
`HX-Request` on the items list returns ONLY the fragment (no `<html>`/
`<nav>`) while a plain GET returns the full page; search filters by name;
item creation via `hx-post` returns the new row fragment; a validation
failure re-renders the create form with `HX-Retarget`/`HX-Reswap`; item
deletion soft-deletes and empties the response; both create and delete
redirect an anonymous visitor to `/login?next=...` instead of acting.

## Judgment calls

- **The `access_token` cookie is this block's ONE deliberate extension to
  `backend/django`'s existing cookie set.** The JSON API's cookie mode
  only ever returns the access token in the response BODY (for the SPA to
  hold in memory, per `frontend/vite-spa`'s own design) — a
  server-rendered page has no JS holding any state at all, so the access
  token itself needs to live in a cookie too, or every page load would
  need to re-authenticate some other way. This is still safe: `HttpOnly`
  (never exposed to JS, so an XSS bug on this origin can't read it any
  more than it could read the refresh cookie), `Secure`, `SameSite=Lax`,
  scoped `Path=/` (broader than the refresh/csrf pair's `Path=/auth`,
  deliberately — every page route needs to read it, not just `/auth/*`),
  and a short TTL matching `JWT_ACCESS_TTL_SECONDS` (900s default) — an
  access token is already a short-lived, low-blast-radius credential by
  design (see `core/security/auth/_core.py`'s own docstrings), and this
  cookie carries no MORE exposure than the identical token a bearer client
  already holds in memory for the same duration.
- **`SilentRefreshMiddleware` is a documented known simplification, not a
  production-grade single-flight implementation.** No cross-request
  locking/coordination — two concurrent requests racing an expired access
  token can each independently refresh; both succeed, the "loser" isn't
  locked out, just one extra rotation happens. See that module's own
  docstring for the full rationale on why this is safe (never lets a
  wrong credential through) even though it isn't optimally efficient.
  Building a locking/single-flight version was deliberately out of scope
  for a block sized to demonstrate the pattern, not to ship a
  production-hardened session layer.
- **Django's own `CsrfViewMiddleware`/`{% csrf_token %}` are deliberately
  NOT added** — see "Auth & CSRF" above. Adding them would be a second, parallel,
  uncoordinated CSRF mechanism running alongside the one this whole kit
  already standardizes on for cookie-mode auth.
- **CSRF/auth failures on webapp routes return a plain `HttpResponseForbidden`
  (or a redirect for `login_required`), never the JSON `ErrorEnvelope`.**
  An HTML route has no JSON contract to stay consistent with; a plain
  `403`/redirect is the right shape for a browser-navigated page, matching
  how any other server-rendered Django view fails.
- **The item-browsing page is `/browse/items`, not `/items`** — see
  "Wiring into apps/api" for the routing-collision rationale.
- **`django.contrib.sessions`/`django.contrib.messages` are added to
  `INSTALLED_APPS` even though this block's own auth never touches
  `request.session`.** Django's template engine and admin-adjacent
  machinery expect them present; this block's session/CSRF story stays
  entirely the vendored JWT/cookie scheme — `request.session` itself is
  simply unused surface area, not a second auth mechanism.
- **`webapp_context` (the context processor) resolves the current
  principal on EVERY request**, including anonymous/static-content pages
  — one extra JWT decode per request when a valid `access_token` cookie is
  present. Acceptable for a block sized to demonstrate the pattern; a
  project with real performance requirements could cache the resolution
  per-request (e.g. via `request` object memoization) — not built here to
  keep the adapter simple and obviously correct.
- **`bin/download-tailwind.sh`/`bin/download-htmx.sh` are NOT run by
  `tests/`** — this block's test suite is fully hermetic (sqlite,
  no network), matching every other block's own testing posture in this
  kit; the compiled CSS/vendored JS these scripts produce are dev/CI-time
  artifacts, not something the test suite needs to render a template
  (Django's template engine never actually fetches `{% static ... %}`
  URLs at render time — it just emits the URL string).
