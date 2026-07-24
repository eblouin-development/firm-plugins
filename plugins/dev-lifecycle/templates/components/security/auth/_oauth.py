"""Framework-neutral OAuth 2.0 / OIDC authorization-code + PKCE core:
state/nonce/PKCE generation and verification, provider-agnostic
authorization-URL building, and `OAuthAccountService` -- the account-
linking orchestrator implementing the SAME "collapse every rejection
reason into one generic error" and "never trust a claim the store itself
doesn't confirm" posture `_core.py`'s `AuthService`/`AccountService`
already establish, applied here to the **unverified-email account-
takeover attack** (see `OAuthAccountService.resolve_or_link`'s docstring).
Canon: `references/security/secure-baseline.md`'s "Authentication &
authorization" section, and the OWASP OAuth 2.0 / OIDC guidance this
module's `sources` cite.

Drop-in: copy this file into `app/core/security/auth/_oauth.py` (Django:
`core/security/auth/_oauth.py`), alongside `_core.py` and (if the cookie
transport is used) `_cookies.py` from the same directory -- this component
ships the framework-neutral core only; wiring `/auth/oauth/{provider}/
authorize` + `/auth/oauth/{provider}/callback` routes into a FastAPI or
Django backend block is the `social-login` recipe's job (`references/
recipes/social-login.md`), not this file's.

**What this file does NOT do, deliberately, matching every other file in
this component's "framework-neutral core, app-level network/route
wiring" split (see `_core.py`'s own module docstring on `UserStore`/
`RefreshTokenStore`; `EmailSender`/`ConsoleEmailSender` for the identical
pattern applied to email delivery):**
- It never makes an HTTP request. Exchanging an authorization `code` for
  tokens at a provider's token endpoint, and fetching/verifying an OIDC
  `id_token`'s signature against the provider's JWKS, are both APP code
  (they need a real HTTP client and, for Google/Apple's `id_token`, PyJWT's
  `PyJWKClient` -- already a dependency of this component via `_core.py`'s
  own `TokenService`, so no new library is introduced). The recipe's own
  wire-up steps show the concrete calls; this module starts one step
  later, at an already-resolved `OAuthIdentity`.
- It never imports FastAPI, Django, or SQLAlchemy -- stdlib only, same
  "zero framework/app import" posture `_core.py`/`_cookies.py` hold.
- It never mints or verifies this app's own access/refresh JWTs itself --
  `OAuthAccountService.complete_login` calls `AuthService.issue_session`
  (added to `_core.py` alongside this file) to do that, so a federated
  login issues the EXACT SAME session/token shape (same claims, same
  cookie/bearer transport, same refresh-rotation state machine) a
  password login does. This module's entire job is resolving "which
  `UserRecord`, if any, does this federated identity correspond to" --
  never "how do we tell the client they're logged in."

**PKCE is REQUIRED, not optional, for every provider this module talks
to** -- `build_authorization_request` always returns a `code_challenge`;
there is no code path that omits it. RFC 7636 was written for public
clients that can't hold a client secret (native/mobile apps); this
component treats it as mandatory for every client type per current OAuth
2.0 Security Best Current Practice (RFC 9700) guidance, which recommends
PKCE for ALL authorization-code clients, confidential or not -- it costs
nothing for a confidential (backend) client and closes the authorization-
code-interception class of attack outright.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from urllib.parse import urlencode

from _core import AuthError, AuthService, PasswordService, UserRecord, UserStore

# ---------------------------------------------------------------------------
# Exceptions -- extend _core.AuthError, same closed-ErrorCode-mapping posture
# ---------------------------------------------------------------------------


class OAuthStateMismatch(AuthError):
    """The `state` value returned on the callback did not match the one
    this app generated for that authorization request (missing, expired,
    or simply wrong). Maps to `ErrorCode.UNAUTHENTICATED` (401) -- the
    exact CSRF-on-the-OAuth-flow defense `state` exists for; a callback
    that arrives without a matching state could be the attacker's own
    authorization flow being completed inside the victim's authenticated
    browser session (login CSRF), not the user's own flow returning."""


class OAuthNonceMismatch(AuthError):
    """The OIDC `id_token`'s `nonce` claim did not match the one this app
    generated for that authorization request. Maps to `ErrorCode.
    UNAUTHENTICATED` (401) -- `nonce` is the `id_token`-specific analogue
    of `state`, defending against a replayed/substituted `id_token` being
    accepted as a fresh login rather than one bound to this exact
    authorization request."""


class UnverifiedEmailAccountConflict(AuthError):
    """Raised by `OAuthAccountService.resolve_or_link` when a federated
    identity's email matches an EXISTING account, but the link cannot be
    made safely because either side's email is not provably verified.
    Maps to `ErrorCode.CONFLICT` (409) -- an account with this email
    already exists, and this module deliberately refuses to guess whether
    the caller IS that account's owner.

    **This is the unverified-email account-takeover defense.** Two
    distinct attack shapes this single refusal closes, symmetric to each
    other:
    1. *Attacker links their own OAuth account onto a victim's local
       account.* A provider that lets a user register or claim an
       unverified email (some do) would let an attacker authenticate
       via OAuth with `identity.email = victim@example.com,
       email_verified=False`. If this module auto-linked purely on email
       match, the attacker would gain a valid session AS the victim's
       existing (password) account. Refused here: linking to an existing
       account requires `identity.email_verified is True`.
    2. *Attacker pre-registers a victim's email locally, unverified, then
       the victim later arrives via a real, verified OAuth login.* If
       this module auto-linked the victim's OAuth identity onto that
       existing-but-unverified local row, the attacker (who still knows
       that local account's password, since they set it) would retain
       access to what the victim now believes is *their* account.
       Refused here: linking to an existing account ALSO requires
       `existing_user.email_verified is True` -- an existing account
       whose own email was never confirmed is not a safe link target
       regardless of how well-verified the NEW identity is.

    Both conditions must hold (`identity.email_verified AND
    existing_user.email_verified`) before this module links automatically.
    When either is false, this exception is raised instead of silently
    creating a second, disconnected account OR silently linking an
    unproven pair -- the app-level route handler decides the recovery UX
    (e.g. "an account with this email already exists; log in with your
    password first, then connect this provider from account settings" --
    an explicit, authenticated linking flow this module does not itself
    implement, since it requires a signed-in session to drive, which is
    exactly the app-layer concern this framework-neutral core stays out
    of)."""


# ---------------------------------------------------------------------------
# State / nonce / PKCE
# ---------------------------------------------------------------------------


def generate_state() -> str:
    """A fresh, high-entropy CSRF-on-the-OAuth-flow token
    (`secrets.token_urlsafe(32)`, ~256 bits) -- the caller persists it
    (short-lived server-side store, or a signed/`HttpOnly` cookie scoped
    to the auth flow) and compares it against the callback's `state`
    query parameter via `verify_state` below."""
    return secrets.token_urlsafe(32)


def generate_nonce() -> str:
    """A fresh, high-entropy OIDC nonce (`secrets.token_urlsafe(32)`) --
    embedded in the authorization request, later asserted to match the
    `nonce` claim inside the provider's `id_token` (Google, Apple).
    GitHub's plain-OAuth2 flow has no `id_token` and never consults this;
    it is still generated uniformly for every provider so a caller doesn't
    need provider-specific branching to know whether to call this."""
    return secrets.token_urlsafe(32)


def verify_state(*, expected: str | None, received: str | None) -> None:
    """Raises `OAuthStateMismatch` unless both `expected` (what this app
    persisted when it started the flow) and `received` (the callback's
    `state` query parameter) are present, non-empty, and equal under a
    CONSTANT-TIME comparison (`hmac`-free here since both operands are
    ordinary tokens this app itself generated, not a shared secret with a
    keyed-MAC available -- `secrets.compare_digest` is the stdlib
    constant-time primitive for two token strings, the same timing-safety
    goal `_cookies.verify_double_submit`'s `hmac.compare_digest` serves
    for its own cookie/header pair). Every failure mode (missing expected,
    missing received, mismatch) collapses to the SAME exception -- the
    "don't leak which specific reason" posture every other comparison in
    this component follows."""
    if not expected or not received or not secrets.compare_digest(expected, received):
        raise OAuthStateMismatch("The OAuth state parameter is missing or does not match.")


def verify_nonce(*, expected: str | None, received: str | None) -> None:
    """The identical check `verify_state` performs, against the `id_token`'s
    `nonce` claim instead of the callback's `state` parameter. Kept as a
    separate function (rather than a shared helper both call) so each
    call site's exception type stays exactly what it claims to be --
    matching `_core.py`'s "distinct exception TYPES even where the check
    is mechanically identical" posture (see `InvalidToken`/`TokenReused`)."""
    if not expected or not received or not secrets.compare_digest(expected, received):
        raise OAuthNonceMismatch("The OIDC nonce is missing or does not match the authorization request.")


@dataclass(frozen=True)
class PKCEPair:
    """A PKCE verifier/challenge pair, RFC 7636. `verifier` is the secret
    the client (this backend) holds onto for the lifetime of the flow and
    sends ONLY on the final token-exchange request (never in the
    authorization redirect); `challenge` is the value sent in the
    authorization URL, derived from `verifier` in a way the provider can
    check against the verifier presented at token-exchange time without
    ever having seen the verifier itself in transit until that final,
    TLS-protected, server-to-server call."""

    verifier: str
    challenge: str
    method: str = "S256"


def generate_pkce_pair() -> PKCEPair:
    """Generates a fresh RFC 7636 verifier/challenge pair using the
    `S256` method exclusively -- the `plain` method (verifier ==
    challenge) is deliberately never produced here; it exists in the RFC
    only for clients that cannot compute SHA-256, which is not a
    constraint any of this kit's backend blocks have. `verifier` is
    `secrets.token_urlsafe(96)` (96 raw bytes, ~728 bits before
    URL-safe-base64 encoding -- comfortably inside RFC 7636's 43-128
    character allowed length after encoding, and far above its 256-bit
    entropy floor). `challenge` is `BASE64URL-ENCODE(SHA256(verifier))`
    with padding stripped, exactly RFC 7636 §4.2's transform."""
    verifier = secrets.token_urlsafe(96)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return PKCEPair(verifier=verifier, challenge=challenge)


# ---------------------------------------------------------------------------
# Provider config + authorization-URL building
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OAuthProviderConfig:
    """The static, non-secret shape of one provider's authorization-code
    flow -- everything `build_authorization_request` needs to build the
    redirect URL. `client_id` is NOT secret (it appears in the redirect
    URL, visible to the browser); `client_secret` never appears anywhere
    in this file -- it is used only at token-exchange time, an app-level,
    server-to-server HTTP call this module never makes (see this file's
    module docstring)."""

    name: str
    """A short slug (`"google"`, `"github"`, `"apple"`) -- also the value
    persisted on `OAuthLinkedAccountRecord.provider` below, so a stored
    link is always resolvable back to a config without ambiguity."""

    client_id: str
    authorize_url: str
    scopes: tuple[str, ...]
    response_mode: str | None = None
    """`None` for Google/GitHub (the default `query` response mode -- the
    callback arrives as a GET with `code`/`state` query parameters).
    `"form_post"` for **Apple**, which POSTs the callback body instead of
    redirecting with a query string -- Apple's own documented quirk (see
    this file's module docstring and the `social-login` recipe's own
    "Apple quirks" section); a route wiring Apple's callback must accept
    a POSTed form body, not a query string, or the flow silently breaks."""

    extra_authorize_params: Mapping[str, str] = field(default_factory=dict)
    """Provider-specific authorization-request parameters this module has
    no generic opinion on -- e.g. Apple's `response_type=code%20id_token`
    (Apple returns an `id_token` directly on the form_post callback,
    alongside the code) or a `prompt=consent`/`access_type=offline` a
    project wants from Google. Merged into the built URL verbatim; this
    module does not validate provider-specific parameter names."""


def build_authorization_url(
    config: OAuthProviderConfig,
    *,
    redirect_uri: str,
    state: str,
    nonce: str,
    pkce: PKCEPair,
) -> str:
    """Pure URL construction -- no I/O. Builds `config.authorize_url` with
    the standard authorization-code + PKCE query parameters
    (`response_type=code`, `client_id`, `redirect_uri`, `scope`, `state`,
    `nonce`, `code_challenge`, `code_challenge_method`) plus
    `config.extra_authorize_params`, all `urlencode`d. `nonce` is included
    unconditionally (see `generate_nonce`'s own docstring on why it's
    generated uniformly across providers even though GitHub's flow never
    reads it back)."""
    params = {
        "response_type": "code",
        "client_id": config.client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(config.scopes),
        "state": state,
        "nonce": nonce,
        "code_challenge": pkce.challenge,
        "code_challenge_method": pkce.method,
        **config.extra_authorize_params,
    }
    if config.response_mode is not None:
        params["response_mode"] = config.response_mode
    separator = "&" if "?" in config.authorize_url else "?"
    return f"{config.authorize_url}{separator}{urlencode(params)}"


@dataclass(frozen=True)
class OAuthAuthorizationRequest:
    """Everything a route handler needs to start a flow AND to verify its
    own callback later: the URL to redirect the user-agent to, plus the
    three values (`state`, `nonce`, `pkce.verifier`) that must be
    persisted server-side (short-lived store, or `HttpOnly`-cookie-scoped
    to the auth flow -- never a `localStorage`/client-readable value,
    same posture the refresh cookie already holds) for the lifetime of
    the flow and handed back to `verify_state`/`verify_nonce`/the
    token-exchange call on the callback."""

    authorization_url: str
    state: str
    nonce: str
    pkce: PKCEPair


def start_authorization(config: OAuthProviderConfig, *, redirect_uri: str) -> OAuthAuthorizationRequest:
    """Generates a fresh `state`/`nonce`/PKCE pair and builds the
    authorization URL in one call -- the entry point a route's
    `GET /auth/oauth/{provider}/authorize` handler uses. The caller is
    responsible for persisting the returned `state`/`nonce`/
    `pkce.verifier` (this module has no storage of its own -- app-level,
    same as every store `Protocol` in `_core.py`) and for redirecting the
    user-agent to `authorization_url`."""
    pkce = generate_pkce_pair()
    return OAuthAuthorizationRequest(
        authorization_url=build_authorization_url(
            config,
            redirect_uri=redirect_uri,
            state=(state := generate_state()),
            nonce=(nonce := generate_nonce()),
            pkce=pkce,
        ),
        state=state,
        nonce=nonce,
        pkce=pkce,
    )


# ---------------------------------------------------------------------------
# Resolved identity + linked-account storage seam
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OAuthIdentity:
    """The already-verified result of a completed provider round-trip --
    what an app-level callback handler builds AFTER exchanging the code
    for tokens and (for Google/Apple) verifying the `id_token`'s
    signature/issuer/audience/nonce against the provider's JWKS. This
    module never constructs one itself; `OAuthAccountService.
    complete_login` only ever consumes one.

    `email_verified` MUST reflect the PROVIDER's own claim, never be
    defaulted to `True` by the app-level caller for convenience --
    `resolve_or_link`'s entire unverified-email defense (see
    `UnverifiedEmailAccountConflict`) depends on this being an honest
    signal. Concretely: Google's `email_verified` claim is authoritative
    (Google will not issue `id_token`s for unverified email otherwise, but
    the claim is still asserted rather than assumed); Apple always
    verifies email before issuing an `id_token` (`email_verified` is
    always `"true"` on Apple's own token, but is still asserted from the
    claim, not hardcoded); GitHub has no OIDC claim at all -- the app-level
    caller derives it from `GET /user/emails`, taking ONLY an entry with
    both `primary: true` AND `verified: true` (see the `social-login`
    recipe's GitHub wiring step) -- a GitHub email that is present but
    unverified must be surfaced here as `email_verified=False`, never
    silently upgraded."""

    provider: str
    subject: str
    """The provider's own stable user identifier (`sub` on an OIDC
    `id_token`; GitHub's numeric `id` from `GET /user`, stringified) --
    the identity `resolve_or_link` looks up FIRST (`OAuthAccountStore.
    get_by_provider_subject`), before ever falling back to email
    matching, since a provider's `subject` cannot be reassigned to a
    different real-world person the way an email address technically
    could (mailbox reassignment) -- it is the stronger of the two
    identifiers this module has available."""

    email: str
    email_verified: bool
    name: str | None = None
    """`None` when the provider did not return a display name on THIS
    grant. **Apple's documented quirk:** Apple includes the user's name
    in its response ONLY on the very first authorization a user ever
    grants a given app -- every subsequent login omits it entirely, even
    if the user's Apple ID name is later changed. A caller must persist
    the name captured on that first grant itself (on the `UserRecord`, or
    wherever the app keeps a display name); this module does not do that
    persistence itself (`UserStore.create`'s existing shape has no name
    field -- see this file's module docstring on the app-level `UserStore`
    extension the `social-login` recipe describes) but `resolve_or_link`
    never overwrites an already-known name with a later `None`."""


@dataclass(frozen=True)
class OAuthLinkedAccountRecord:
    """One persisted provider-identity-to-local-account link.
    `provider`+`subject` together are the natural key (a `UNIQUE(provider,
    subject)` constraint in a real schema); `user_id` is the local
    `UserRecord.id` it resolves to. One local account MAY have multiple
    linked providers (Google AND GitHub on the same account) -- this
    module places no limit on that; a provider MAY NOT be linked to more
    than one local account (the natural key already prevents that at the
    storage layer)."""

    provider: str
    subject: str
    user_id: str
    email_at_link: str
    linked_at: datetime


class OAuthAccountStore(Protocol):
    """The storage seam `OAuthAccountService` runs against -- a framework
    adapter implements this against its own ORM/session, the identical
    "app implements the `Protocol`, this module never touches a database"
    posture `UserStore`/`RefreshTokenStore` already establish in
    `_core.py`. `async` for the same reason every storage `Protocol` in
    this component is."""

    async def get_by_provider_subject(self, provider: str, subject: str) -> OAuthLinkedAccountRecord | None: ...

    async def link(self, record: OAuthLinkedAccountRecord) -> None:
        """**Upserts** `record`, keyed by the `(provider, subject)` natural
        key -- e.g. a SQL `INSERT ... ON CONFLICT (provider, subject) DO
        UPDATE SET user_id = excluded.user_id, email_at_link =
        excluded.email_at_link, linked_at = excluded.linked_at`, never a
        plain rejecting `INSERT`. Implementations MUST make the write
        durable (committed) before returning -- the same durable-commit
        contract `RefreshTokenStore.add` documents, for the identical
        reason: `resolve_or_link` relies on a just-linked record being
        immediately visible to a concurrent lookup of the same
        `(provider, subject)` pair.

        **Upsert, not a rejecting insert, is a deliberate part of this
        contract** -- `resolve_or_link`'s stale-link fallback (see that
        method's own docstring/body) re-calls `link()` for a
        `(provider, subject)` pair that ALREADY has a row on file (whose
        target user was deleted) once it re-resolves the identity to a
        (possibly different) user. A plain `UNIQUE`-enforcing `INSERT`
        would raise on that second call; `resolve_or_link` depends on
        this method silently replacing the stale row instead. The
        `(provider, subject)` key therefore still behaves as unique
        storage-wide (at most one row per pair, ever) -- it is just
        maintained via upsert semantics rather than insert-and-reject."""
        ...


# ---------------------------------------------------------------------------
# OAuthAccountService: identity resolution + account linking
# ---------------------------------------------------------------------------


class OAuthAccountService:
    """Resolves an `OAuthIdentity` (already fully verified by the caller —
    signature, issuer, audience, nonce all checked before this class ever
    sees it) to a local `UserRecord`, applying the account-linking rules,
    then hands off to `AuthService.issue_session` to mint the SAME
    session/token shape a password login produces. Composed ALONGSIDE
    `AuthService`/`AccountService` -- constructed independently against
    the same underlying `UserStore`, never a subclass of either.

    `passwords` (a `PasswordService`) is used ONLY to mint an unusable,
    never-communicated password hash for a brand-new OAuth-only account
    (see `resolve_or_link`'s "new account" branch) -- never to check a
    password; an OAuth-only account has none. Using a REAL Argon2id hash
    of a random, immediately-discarded, never-returned value (rather than
    a magic sentinel string like `"!oauth-account!"`) is the deliberate
    choice: a sentinel string is a value someone could accidentally end up
    checking a submitted password against (a future refactor, a copy-paste
    bug) and get a false positive on; a real Argon2id hash of 256 bits of
    CSPRNG output that was never persisted or returned anywhere can NEVER
    verify true against anything a client could ever submit, which is a
    strictly stronger guarantee than "don't compare against this specific
    string."""

    def __init__(
        self,
        users: UserStore,
        oauth_accounts: OAuthAccountStore,
        passwords: PasswordService,
        auth: AuthService,
        now: Callable[[], datetime],
    ) -> None:
        self._users = users
        self._oauth_accounts = oauth_accounts
        self._passwords = passwords
        self._auth = auth
        self._now = now

    @staticmethod
    def _normalize_email(email: str) -> str:
        """The identical `.strip().lower()` normalization `_core.py`'s
        `AuthService._normalize_email`/`_normalize_email_for_account`
        apply, duplicated here for the same "zero coupling to
        `AuthService`'s internals" reason `AccountService`'s own
        docstring gives -- this class calls `AuthService.issue_session`
        (a small, intentional seam), never anything private."""
        return email.strip().lower()

    async def resolve_or_link(self, identity: OAuthIdentity) -> UserRecord:
        """Implements the account-linking rules, in this exact order:

        1. **Known link.** `OAuthAccountStore.get_by_provider_subject`
           finds an existing `(provider, subject)` row -> load and return
           that `UserRecord` directly (`UserStore.get_by_id`). This is
           the fast, common path for every login after the first for a
           given provider+account pair, and it is NOT re-checked against
           email at all -- once linked, the provider's own stable
           `subject` is authoritative, even if the user's email at that
           provider has since changed.
        2. **No known link -> look up by email.** `UserStore.get_by_email`
           on `_normalize_email(identity.email)`.
           - **No existing account** -> create one: `UserStore.create`
             with a freshly Argon2id-hashed random password (see this
             class's own docstring), `roles=()` (same empty-by-default
             posture `AuthService.register` already enforces -- roles are
             never grantable over a federated login any more than over
             `POST /auth/register`), then IMMEDIATELY `UserStore.
             mark_email_verified(user.id, now())` if `identity.
             email_verified` is `True` (an OAuth provider that has
             already verified this email is exactly the same proof of
             inbox control `AccountService.verify_email`'s single-use
             token flow establishes -- no reason to make a brand-new
             OAuth user click a SEPARATE verification email for the
             address the provider already vouched for). Then link.
           - **Existing account found** -> raises
             `UnverifiedEmailAccountConflict` UNLESS BOTH `identity.
             email_verified` AND the existing user's `email_verified`
             are `True` -- see that exception's own docstring for the
             two attack shapes this refusal closes. When both hold, links
             the identity onto the existing account (no new `UserRecord`
             created) and returns it.
        3. Either way (steps 2's two success sub-branches), persists the
           new link via `OAuthAccountStore.link` before returning.

        This method does NOT mint tokens -- see `complete_login` below,
        which wraps this plus `AuthService.issue_session`."""
        existing_link = await self._oauth_accounts.get_by_provider_subject(identity.provider, identity.subject)
        if existing_link is not None:
            user = await self._users.get_by_id(existing_link.user_id)
            if user is not None:
                return user
            # The link survives but its target user is gone (deleted
            # since linking) -- fall through and re-resolve by email
            # exactly as if this were a first-time login, rather than
            # raising: a stale link row is a data-hygiene concern for the
            # app to clean up, not a reason to lock this identity out of
            # the account-resolution flow entirely. The re-link below
            # OVERWRITES this same (provider, subject) row via
            # OAuthAccountStore.link's upsert contract (see that
            # Protocol method's own docstring) -- it does not attempt a
            # fresh insert that a rejecting UNIQUE constraint would
            # reject.

        normalized_email = self._normalize_email(identity.email)
        existing_user = await self._users.get_by_email(normalized_email)

        if existing_user is None:
            random_password = secrets.token_urlsafe(32)
            unusable_hash = self._passwords.hash(random_password)
            user = await self._users.create(normalized_email, unusable_hash, ())
            if identity.email_verified:
                await self._users.mark_email_verified(user.id, self._now())
                user = await self._users.get_by_id(user.id) or user
        else:
            if not (identity.email_verified and existing_user.email_verified):
                raise UnverifiedEmailAccountConflict(
                    "An account with this email already exists and cannot be linked automatically "
                    "until both the existing account's and the new provider's email are verified."
                )
            user = existing_user

        await self._oauth_accounts.link(
            OAuthLinkedAccountRecord(
                provider=identity.provider,
                subject=identity.subject,
                user_id=user.id,
                email_at_link=normalized_email,
                linked_at=self._now(),
            )
        )
        return user

    async def complete_login(self, identity: OAuthIdentity):
        """`resolve_or_link(identity)` followed by `AuthService.
        issue_session(user)` -- the single call a callback route handler
        needs to go from a verified `OAuthIdentity` straight to a
        `_core.TokenPair`, issuing the exact same session/token shape
        (cookie-mode or bearer-mode, whichever the route wires) a
        password login produces. Kept as a separate method from
        `resolve_or_link` (rather than folding token-minting into it) so
        a caller that only needs identity resolution (e.g. an explicit,
        already-authenticated "connect this provider to my account" flow,
        which must NOT mint a fresh session -- the user is already logged
        in) can call `resolve_or_link` alone.

        **Does NOT honor `AuthService`'s `require_verification` policy**
        the way password `login` does -- a resolved `OAuthIdentity` can
        reach `issue_session` even when the linked/created `UserRecord`'s
        `email_verified` is `False` (the "new account, provider did not
        verify the email" branch of `resolve_or_link`). This is
        deliberately NOT an account-takeover gap: that branch only ever
        creates a BRAND-NEW account (an existing, verified account can
        never be silently downgraded -- see `UnverifiedEmailAccountConflict`),
        so the worst case is a fresh account proceeding without email
        verification, the same outcome `require_verification=False`
        already produces for `AuthService.login`. A project that wants
        federated logins to also honor `require_verification` checks
        `user.email_verified` itself after this call and denies/redirects
        accordingly -- `_oauth.py` does not gate on it internally."""
        user = await self.resolve_or_link(identity)
        return await self._auth.issue_session(user)
