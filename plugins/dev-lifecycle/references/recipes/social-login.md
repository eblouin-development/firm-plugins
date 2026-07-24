<!--
recipe: social-login
applies-to:
  - backend block: fastapi OR django (extends the `end-to-end-auth` recipe's same backend contract — one recipe extending another, not a fork of it)
  - frontend block: any React web block (cookie mode) — pairs with @repo/api-client, adds provider buttons to the auth surfaces `end-to-end-auth` already wires
  - mobile block: any Expo block (bearer mode) — adds `expo-auth-session` on top of the auth-context `end-to-end-auth` already wires
last-verified: 2026-07-24
provenance: manual
sources:
  - https://datatracker.ietf.org/doc/html/rfc6749
  - https://datatracker.ietf.org/doc/html/rfc7636
  - https://datatracker.ietf.org/doc/html/rfc9700
  - https://openid.net/specs/openid-connect-core-1_0.html
  - https://developers.google.com/identity/openid-connect/openid-connect
  - https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps
  - https://docs.github.com/en/rest/users/emails
  - https://developer.apple.com/documentation/sign_in_with_apple/generate_and_validate_tokens
  - https://developer.apple.com/documentation/sign_in_with_apple/sign_in_with_apple_rest_api/authenticating_users_with_sign_in_with_apple
  - https://docs.expo.dev/guides/authentication/
  - https://docs.expo.dev/versions/latest/sdk/auth-session/
  - https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html
  - references/security/secure-baseline.md
  - references/wiring/auth-end-to-end.md
  - references/recipes/end-to-end-auth.md
  - references/compatibility-matrix.md
  - templates/components/security/auth/README.md ("OAuth 2.0/OIDC social login" section)
-->

# Social/OAuth login

Adds Google, GitHub, and Apple sign-in to a project that already has `end-to-end-auth` wired: OAuth 2.0/OIDC authorization-code + PKCE, resolved through the `auth` component's new `_oauth.py`, issuing the **exact same session/token shape** — web cookie-mode, mobile bearer-mode — the password flow already produces, so nothing downstream of login changes. Everything here is **subordinate to the project's existing conventions** — when they conflict, the project wins.

## Contents
- What this wires
- Prerequisites
- Wire-up steps
- Account linking & the unverified-email attack
- Provider notes (Google, GitHub, Apple)
- Frontend and mobile
- Security checklist
- Doc fragment

## What this wires
Applying this recipe gives a project that already has `end-to-end-auth` a second, federated way to reach the SAME session: `GET /auth/oauth/{provider}/authorize` redirects to the provider with PKCE + state + nonce; `GET /auth/oauth/{provider}/callback` (Apple: a `POST`, see "Provider notes") exchanges the code, verifies the identity, resolves or links a local account, and mints tokens through the same `AuthService` a password login uses — cookie-mode on web (`Set-Cookie` on the callback response) or bearer-mode on mobile (the callback response body carries the pair for `expo-auth-session` to store).

It **composes existing pieces plus one additive component extension**, invents no new session/transport infrastructure:
- **`templates/components/security/auth/_oauth.py`** (new, `#96`) — the framework-neutral OAuth core this recipe wires: PKCE (`S256`-only), state/nonce generation and verification, `OAuthProviderConfig`/`build_authorization_url`, and `OAuthAccountService` (`resolve_or_link`/`complete_login`) — the account-linking orchestrator, including the unverified-email-account-takeover defense. See that component's README's "OAuth 2.0/OIDC social login" section for the full contract; this recipe does not restate it.
- **`templates/components/security/auth/_core.py`**'s new `AuthService.issue_session(user)` (additive, `#96`) — `OAuthAccountService.complete_login` calls this, never a bespoke OAuth-specific token minting path, so a federated login's access/refresh JWTs, refresh-rotation state machine, and cookie/bearer transport are byte-for-byte what `end-to-end-auth` already established. `login`/`refresh`/`logout`/`resolve_access` are unchanged by this addition.
- **`fastapi.py`/`django.py`** (unchanged by this recipe) — the existing bearer/cookie transport glue (`set_auth_cookies`, `read_refresh_cookie`, `enforce_csrf`, `AUTH_ERROR_HTTP`) is reused as-is for the OAuth callback's response; this recipe only adds `_oauth.py`'s three new exceptions to that same table (see "Wire-up steps").
- **The `end-to-end-auth` recipe's own prerequisites** — a backend block with `UserStore`/`RefreshTokenStore` wired, `AuthService` constructed at startup, cookie-mode (web) and bearer-mode (mobile) already working. This recipe assumes that recipe is already applied and extends it; it does not repeat its steps.
- **An app-level `OAuthAccountStore`** implementing `_oauth.py`'s `OAuthAccountStore` Protocol against the real ORM (a `provider_accounts` table, `UNIQUE(provider, subject)`) — new app code this recipe's steps describe, analogous to `UserStore`/`RefreshTokenStore` in `end-to-end-auth`.
- **An app-level HTTP client** (`httpx`, async) for the token-exchange and provider-userinfo calls, and PyJWT's `PyJWKClient` (already a `_core.py`/`TokenService` dependency — no new library) for verifying Google/Apple's `id_token` signature against each provider's published JWKS. Both are app code — `_oauth.py` deliberately makes no network call itself (see its own module docstring).
- **The frontend/mobile pieces `end-to-end-auth` already wires** — provider buttons call the SAME `/auth/oauth/{provider}/authorize` redirect (web) or the SAME callback endpoint via `expo-auth-session` (mobile); no new auth-context/token-storage code, since the session that comes back is identical in shape to a password login's.

## Prerequisites
- **`end-to-end-auth` already applied** — a working backend block (FastAPI or Django) with the `auth` component vendored, `AuthService` constructed, and at least one of cookie-mode (web) / bearer-mode (mobile) working end to end. This recipe extends that vendoring; it does not re-describe it.
- **`_oauth.py` vendored** alongside the already-vendored `_core.py` (and `_cookies.py`, if cookie mode is used) — copy it into the same `app/core/security/auth/` (FastAPI) or `core/security/auth/` (Django) directory, and re-export its public surface from that directory's `__init__.py` alongside `_core.py`'s existing exports.
- **`_core.py`'s `AuthService.issue_session` present** — this ships as part of vendoring `_core.py` from this stage forward; a project that vendored `_core.py` before `#96` re-copies the file (it is purely additive — no other method's behavior changes) to pick it up.
- **Runtime dependencies**, per `references/compatibility-matrix.md`: **PyJWT 2.13.x** (already required by `end-to-end-auth`; this recipe additionally uses its `PyJWKClient` for Google/Apple `id_token` verification — no new package). **`httpx`** — an async HTTP client for the token-exchange/userinfo calls; not yet a `references/compatibility-matrix.md` row (the same situation `stripe-payments.md`'s `stripe-python` pin documents) — pin `httpx==0.28.1` (current stable at authoring time; **re-verify against PyPI before adopting**, the matrix does not yet carry this row and the agent that wires this recipe into a project owns adding it there, the same convention `_core.py`'s own README note establishes for PyJWT/argon2-cffi's first-consumer stage).
- **Registered OAuth apps** with each provider you enable — a Google Cloud OAuth 2.0 Client ID, a GitHub OAuth App, and/or an Apple Services ID configured for Sign in with Apple — each with the backend's `/auth/oauth/{provider}/callback` URL registered as an exact-match redirect URI (never a wildcard) for every environment (dev/staging/prod get DISTINCT registered apps/redirect URIs, not one shared across environments).
- **Expo SDK 57** / `expo-auth-session` (mobile) — resolved via `npx expo install expo-auth-session`, SDK-governed the same way `expo-secure-store`/`expo-router` already are per the compatibility matrix's Mobile section; not yet its own matrix row (add it alongside `httpx` when wiring this recipe).

## Wire-up steps

1. **Vendor `_oauth.py` and re-export it.** Copy `templates/components/security/auth/_oauth.py` into the backend block's `app/core/security/auth/` (or Django's `core/security/auth/`) directory, alongside the already-vendored `_core.py`/`fastapi.py` or `django.py`. Add its public surface (`OAuthProviderConfig`, `start_authorization`, `verify_state`, `verify_nonce`, `OAuthIdentity`, `OAuthAccountService`, the three new exceptions) to that directory's `__init__.py` re-export, matching how `_cookies.py`'s surface was added when cookie mode was wired.

2. **Register `_oauth.py`'s three exceptions in the app's `AUTH_ERROR_HTTP`-consuming exception handler.** The SAME `AuthError`-base-class handler `end-to-end-auth` already registers catches these automatically (they subclass `_core.AuthError`) — no new registration is needed, only confirm the handler consults `_oauth.OAuthStateMismatch`/`OAuthNonceMismatch`/`UnverifiedEmailAccountConflict`'s mappings (401/401/409 respectively — see the `auth` component's README's exception table) the same way it already consults `fastapi.py`'s/`django.py`'s own `AUTH_ERROR_HTTP`.

3. **Build one `OAuthProviderConfig` per enabled provider**, sourced from `GOOGLE_CLIENT_ID`/`GITHUB_CLIENT_ID`/`APPLE_CLIENT_ID` (secrets-loading, never inlined — see the Security checklist), each provider's published authorize endpoint:
   - Google: `https://accounts.google.com/o/oauth2/v2/auth`, `scopes=("openid", "email", "profile")`.
   - GitHub: `https://github.com/login/oauth/authorize`, `scopes=("read:user", "user:email")` — GitHub's own OAuth apps have no `openid` scope; it is not an OIDC provider (see "Provider notes").
   - Apple: `https://appleid.apple.com/auth/authorize`, `scopes=("name", "email")`, `response_mode="form_post"`, `extra_authorize_params={"response_type": "code id_token"}` (see "Provider notes" — both quirks are load-bearing, not optional).

4. **`GET /auth/oauth/{provider}/authorize`** — look up that provider's `OAuthProviderConfig`, call `_oauth.start_authorization(config, redirect_uri=...)`, persist the returned `state`/`nonce`/`pkce.verifier` server-side keyed by a short-lived, `HttpOnly`, `Secure` cookie-scoped opaque id (or an equivalent short-TTL server-side store) — **never** in a URL query string, `localStorage`, or a non-`HttpOnly` cookie the callback could be tricked into re-supplying — then redirect (`303`) the browser to `request.authorization_url`.

5. **`GET`/`POST /auth/oauth/{provider}/callback`** (Apple uses `POST`, a form body — see "Provider notes"; Google/GitHub use `GET`, query parameters):
   a. Look up the persisted `state`/`nonce`/`pkce.verifier` from step 4's opaque id; call `_oauth.verify_state(expected=..., received=request's state)` — a mismatch raises `OAuthStateMismatch` (401), caught by the app's existing exception handler.
   b. Exchange the authorization `code` for tokens at the provider's token endpoint via `httpx.AsyncClient`, sending `code_verifier=pkce.verifier` (never the challenge) and the confidential `client_secret` (secrets-loading) — server-to-server only, this call never touches the browser.
   c. **Google/Apple (OIDC):** verify the returned `id_token`'s signature via `jwt.PyJWKClient(provider_jwks_url).get_signing_key_from_jwt(id_token)`, then `jwt.decode(id_token, signing_key.key, algorithms=["RS256"], audience=client_id, issuer=expected_issuer)` — asserting `aud`/`iss` explicitly, same posture `_core.py`'s own `TokenService` holds for this app's own tokens (never inferring the algorithm from the token's own header). Call `_oauth.verify_nonce(expected=persisted_nonce, received=decoded["nonce"])`. Build an `_oauth.OAuthIdentity(provider=..., subject=decoded["sub"], email=decoded["email"], email_verified=bool(decoded["email_verified"]), name=...)`.
   d. **GitHub (plain OAuth2, no `id_token`):** call `GET /user` (subject = the numeric `id`, stringified) and `GET /user/emails`, taking ONLY the entry with **both** `primary: true` AND `verified: true` — a present-but-unverified or non-primary email is NEVER used as `identity.email`; if no such entry exists, reject the login rather than falling back to an unverified address. Build the `OAuthIdentity` the same shape as step c, `email_verified=True` always (by construction of the filter just applied).
   e. Call `await oauth_account_service.complete_login(identity)` — returns a `TokenPair` through `AuthService.issue_session`, the same object `login`/`refresh` return.
   f. Respond exactly like `end-to-end-auth`'s own login route does for the resolved mode: cookie mode — `set_auth_cookies(response, refresh_value=pair.refresh, csrf_value=generate_csrf_token(), max_age=...)`, redirect to the SPA; bearer mode — return `{access, refresh}` in the JSON body for the mobile client (via `expo-auth-session`'s redirect capture) to store exactly as `end-to-end-auth`'s own `POST /auth/login` response does.

6. **Implement `OAuthAccountStore`** against the real ORM — a `provider_accounts` table with `UNIQUE(provider, subject)`, `user_id` foreign-keyed to the same users table `UserStore` already runs against. `get_by_provider_subject`/`link` are the only two methods; see `backend/fastapi`'s `stores.py` (once this recipe's reference wiring lands there) for a concrete SQLAlchemy implementation, mirroring `RefreshTokenStore`'s own durable-write contract.

## Account linking & the unverified-email attack
`OAuthAccountService.resolve_or_link` (in `_oauth.py`) makes the linking decision — this recipe wires it, it does not re-implement it. The rule, restated for the app-level route handler's benefit (full rationale in `_oauth.py`'s own `UnverifiedEmailAccountConflict` docstring, which is canon here): a known `(provider, subject)` link always wins outright; otherwise, an email match against an existing local account is auto-linked **only when both** the incoming provider identity's email and the existing account's own email are independently verified. Per `references/security/secure-baseline.md`'s "Authentication & authorization" section, being able to present *an* email is not proof of controlling it — this closes the two symmetric attack shapes (an unverified federated identity claiming a verified victim account; a verified federated login landing on an attacker's unverified local pre-registration of the same email) that a naive "match on email, link automatically" implementation would open. When the rule refuses (`UnverifiedEmailAccountConflict`, 409), the route returns that as an error the frontend surfaces as: *"An account with this email already exists. Log in with your password, then connect \<Provider\> from account settings."* — an explicit, already-authenticated linking flow is the safe recovery path; this recipe does not implement that flow's UI, only documents it as the required next step for a project that wants it (a `POST /auth/oauth/{provider}/link` endpoint, gated behind the existing bearer/cookie auth dependency, calling `resolve_or_link` directly without `issue_session` — the user is already logged in).

## Provider notes

**Google** — full OIDC. `email_verified` on the `id_token` is Google's own authoritative claim (still asserted, never assumed `True`). JWKS: `https://www.googleapis.com/oauth2/v3/certs`. Issuer: `https://accounts.google.com`.

**GitHub** — plain OAuth 2.0, **not** OIDC — no `id_token`, no `openid` scope, no JWKS. Identity comes from two REST calls (`GET /user`, `GET /user/emails`) per step 5d above; a GitHub account can have multiple emails, several unverified — filtering to `primary && verified` is not optional, it is this provider's entire account-takeover defense (an unverified, attacker-added email on a legitimate-looking GitHub account must never be trusted).

**Apple** — two quirks, both load-bearing, both already surfaced on `OAuthProviderConfig`/`OAuthIdentity` rather than hidden in this recipe's prose alone:
- **`response_mode=form_post`.** Apple POSTs the callback as `application/x-www-form-urlencoded` body fields, never a query-string redirect — the callback route MUST read a form body (`request.form()` in FastAPI, `request.POST` in Django), not query params, or the flow silently 404s/misparses. `extra_authorize_params={"response_type": "code id_token"}` is what makes Apple return the `id_token` directly on that same POST, alongside the code.
- **Name on first grant only.** Apple includes `user.name` in the callback body **only the very first time** a given user authorizes this app — every subsequent login omits it, even after the user changes their Apple ID name elsewhere. Capture and persist it (on the `UserRecord`, or wherever the app keeps a display name) on that first grant; `_oauth.py`'s `resolve_or_link` never overwrites an already-known name with a later `None`, but the app-level route is what actually writes it the first time — don't skip that write thinking `_oauth.py` handles it.
- JWKS: `https://appleid.apple.com/auth/keys`. Issuer: `https://appleid.apple.com`. Audience: the Services ID (not the App ID) configured for Sign in with Apple.

## Frontend and mobile
- **Web (cookie mode):** each provider is a plain `<a href="/api/auth/oauth/google/authorize">`/button-styled link (or a `window.location.assign(...)` from a click handler) into step 4's endpoint — no client-side OAuth library needed; the entire flow is a server-driven redirect dance, and the callback (step 5f) sets the SAME cookies `end-to-end-auth`'s password login already sets, so the existing `configureApiClient({ baseUrl, cookieMode: true })` wiring picks the session up with zero changes. Style provider buttons per each provider's published brand guidelines (Google/GitHub/Apple each publish button-asset guidelines — use them rather than freehanding a look-alike).
- **Mobile (bearer mode):** use `expo-auth-session`'s `useAuthRequest`/`AuthSession.startAsync`-style flow, pointed at step 4's `/authorize` endpoint with the app's own registered custom-scheme (or Expo's `AuthSession.makeRedirectUri()`) redirect URI — registered as an ADDITIONAL redirect URI on each provider's OAuth app config, distinct from the web callback URL. The redirect lands back on step 5f's bearer-mode JSON response; store `refresh` in Expo SecureStore and keep `access` in memory, identically to `end-to-end-auth`'s own mobile wiring — `expo-auth-session` only drives the browser round-trip, it never touches token storage.

## Security checklist
- [ ] PKCE (`S256`) sent on every provider's authorization request — no `plain` method, no provider skipped.
- [ ] `state` generated per flow, persisted server-side (never a query string/`localStorage`), and verified on every callback before anything else runs.
- [ ] `nonce` generated per flow and verified against Google/Apple's `id_token` claim (GitHub has none to check — see "Provider notes").
- [ ] No OAuth credential (authorization code, `id_token`, access/refresh token pair) ever appears in a URL query string past the initial provider redirect, or in `localStorage`/`sessionStorage` — inherits `end-to-end-auth`'s existing in-memory-access / `HttpOnly`-cookie-or-SecureStore-refresh posture unchanged.
- [ ] `GOOGLE_CLIENT_SECRET`/`GITHUB_CLIENT_SECRET`/`APPLE_*` (Services ID private key) resolved via secrets-loading, never inlined; distinct registered apps per environment.
- [ ] Every registered redirect URI is an exact match, never a wildcard or pattern.
- [ ] `id_token` signature verified against the provider's live JWKS (`PyJWKClient`) with `aud`/`iss` asserted explicitly — never decoded with signature verification off.
- [ ] GitHub identity uses ONLY the `primary && verified` email — never an unverified or non-primary one.
- [ ] Account linking never auto-links unless BOTH the incoming identity's and the existing account's email are verified (`UnverifiedEmailAccountConflict` on any other combination) — see "Account linking & the unverified-email attack" above.
- [ ] A federated login issues the identical session/token shape (`AuthService.issue_session`) a password login does — no parallel/weaker token path exists for OAuth.

## Doc fragment
The portable fragment this recipe contributes to the project's root README when applied:

```markdown
### Social login (Google / GitHub / Apple)
- **Setup:** `GET /auth/oauth/{provider}/authorize` redirects to the provider with PKCE (`S256`) + `state` + `nonce`; `GET`/`POST /auth/oauth/{provider}/callback` (Apple: `POST`, `form_post`) resolves the identity and mints a session through the SAME `AuthService` a password login uses — web gets cookies, mobile gets a bearer pair, identical to `end-to-end-auth`. Account linking: a known `(provider, subject)` link always wins; an email match to an existing account is auto-linked ONLY when both sides' email is verified — otherwise a `409` asks the user to log in with their password first, then connect the provider. GitHub identity uses only the `primary && verified` email; Apple's name arrives on the first grant only, and its callback is a POST, not a redirect with query params.
- **Secrets:** `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET`, `APPLE_CLIENT_ID` (Services ID) + the Sign in with Apple private key — obtained from each provider's developer console, loaded via the secrets-loading component, never inlined. Register the backend's exact `/auth/oauth/{provider}/callback` URL as the redirect URI per environment.
- **Maintenance:** Re-verify `httpx`'s pin against PyPI and add it to `references/compatibility-matrix.md` if not already present when this recipe is first wired into a project; re-run `templates/components/security/auth/tests/test_oauth.py` after any change to `_oauth.py`'s account-linking logic, especially the unverified-email-attack tests.
```

---
<!--
Recipe authored via the `recipe-author` skill (#96). Extends the `_oauth.py`
addition to `templates/components/security/auth/` (also #96) rather than
inventing a separate catalog component -- this recipe composes that
addition plus the existing `_core.py`/`fastapi.py`/`django.py` transport,
per the recipe-author rule that a recipe composes, it does not invent
infrastructure. Every version-sensitive step cites
references/compatibility-matrix.md (or documents why a dependency isn't
yet a matrix row, mirroring stripe-payments.md's stripe-python treatment);
every step defaults to the secure option per
references/security/secure-baseline.md.
-->
