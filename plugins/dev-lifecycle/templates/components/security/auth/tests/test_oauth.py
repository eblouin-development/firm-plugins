"""Tests for `_oauth.py`: state/nonce/PKCE generation and verification,
authorization-URL building, and `OAuthAccountService`'s account-linking
rules -- especially the unverified-email account-takeover defense that is
this module's most security-critical behavior, mirroring `test_core.py`'s
own emphasis on `AuthService.refresh`'s reuse-detection state machine."""

from __future__ import annotations

import base64
import hashlib

import pytest


# ---------------------------------------------------------------------------
# State / nonce
# ---------------------------------------------------------------------------


def test_generate_state_and_nonce_are_high_entropy_and_unique(oauth_mod):
    values = {oauth_mod.generate_state() for _ in range(50)}
    assert len(values) == 50
    assert all(len(v) >= 32 for v in values)


def test_verify_state_accepts_matching_pair(oauth_mod):
    state = oauth_mod.generate_state()
    oauth_mod.verify_state(expected=state, received=state)  # does not raise


@pytest.mark.parametrize(
    "expected,received",
    [
        (None, "abc"),
        ("abc", None),
        (None, None),
        ("", "abc"),
        ("abc", ""),
        ("abc", "xyz"),
    ],
)
def test_verify_state_rejects_every_failure_mode(oauth_mod, expected, received):
    with pytest.raises(oauth_mod.OAuthStateMismatch):
        oauth_mod.verify_state(expected=expected, received=received)


def test_verify_nonce_rejects_mismatch_as_distinct_exception_type(oauth_mod):
    with pytest.raises(oauth_mod.OAuthNonceMismatch):
        oauth_mod.verify_nonce(expected="one", received="two")


def test_state_and_nonce_mismatch_are_distinct_exception_types(oauth_mod):
    assert not issubclass(oauth_mod.OAuthStateMismatch, oauth_mod.OAuthNonceMismatch)
    assert not issubclass(oauth_mod.OAuthNonceMismatch, oauth_mod.OAuthStateMismatch)


# ---------------------------------------------------------------------------
# PKCE
# ---------------------------------------------------------------------------


def test_generate_pkce_pair_uses_s256_and_matches_rfc7636_transform(oauth_mod):
    pair = oauth_mod.generate_pkce_pair()
    assert pair.method == "S256"
    expected_challenge = base64.urlsafe_b64encode(hashlib.sha256(pair.verifier.encode("ascii")).digest())
    expected_challenge = expected_challenge.rstrip(b"=").decode("ascii")
    assert pair.challenge == expected_challenge
    assert "=" not in pair.challenge  # padding stripped
    assert len(pair.challenge) == 43  # base64url(SHA-256 digest), no padding, is always 43 chars


def test_generate_pkce_pair_is_unique_per_call(oauth_mod):
    pairs = {oauth_mod.generate_pkce_pair().verifier for _ in range(20)}
    assert len(pairs) == 20


# ---------------------------------------------------------------------------
# Authorization URL building
# ---------------------------------------------------------------------------


def _google_config(oauth_mod):
    return oauth_mod.OAuthProviderConfig(
        name="google",
        client_id="test-client-id",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        scopes=("openid", "email", "profile"),
    )


def test_build_authorization_url_includes_pkce_and_no_client_secret(oauth_mod):
    config = _google_config(oauth_mod)
    pkce = oauth_mod.generate_pkce_pair()
    url = oauth_mod.build_authorization_url(
        config,
        redirect_uri="https://app.example.com/auth/oauth/google/callback",
        state="s1",
        nonce="n1",
        pkce=pkce,
    )
    assert f"code_challenge={pkce.challenge}" in url or "code_challenge=" in url
    assert "code_challenge_method=S256" in url
    assert "response_type=code" in url
    assert "client_secret" not in url
    assert "state=s1" in url
    assert "nonce=n1" in url


def test_build_authorization_url_includes_apple_form_post_and_extra_params(oauth_mod):
    config = oauth_mod.OAuthProviderConfig(
        name="apple",
        client_id="apple-client-id",
        authorize_url="https://appleid.apple.com/auth/authorize",
        scopes=("name", "email"),
        response_mode="form_post",
        extra_authorize_params={"response_type": "code id_token"},
    )
    pkce = oauth_mod.generate_pkce_pair()
    url = oauth_mod.build_authorization_url(
        config,
        redirect_uri="https://app.example.com/auth/oauth/apple/callback",
        state="s1",
        nonce="n1",
        pkce=pkce,
    )
    assert "response_mode=form_post" in url
    # extra_authorize_params overrides the default response_type=code.
    assert "response_type=code" not in url or "id_token" in url


def test_start_authorization_returns_matching_request_and_url(oauth_mod):
    config = _google_config(oauth_mod)
    request = oauth_mod.start_authorization(config, redirect_uri="https://app.example.com/cb")
    assert request.state in request.authorization_url
    assert request.nonce in request.authorization_url
    assert request.pkce.challenge in request.authorization_url
    assert request.pkce.verifier not in request.authorization_url  # verifier never leaves this app


# ---------------------------------------------------------------------------
# OAuthAccountService: account-linking rules
# ---------------------------------------------------------------------------


def _identity(oauth_mod, *, provider="google", subject="sub-1", email="user@example.com", verified=True, name=None):
    return oauth_mod.OAuthIdentity(
        provider=provider,
        subject=subject,
        email=email,
        email_verified=verified,
        name=name,
    )


@pytest.mark.asyncio
async def test_new_identity_no_existing_account_creates_and_links(oauth_mod, oauth_service, user_store, oauth_account_store):
    identity = _identity(oauth_mod, email="brandnew@example.com", verified=True)
    user = await oauth_service.resolve_or_link(identity)
    assert user.email == "brandnew@example.com"
    assert user.email_verified is True
    assert user.roles == ()
    link = await oauth_account_store.get_by_provider_subject("google", "sub-1")
    assert link is not None
    assert link.user_id == user.id


@pytest.mark.asyncio
async def test_new_identity_with_unverified_provider_email_creates_unverified_account(oauth_mod, oauth_service):
    identity = _identity(oauth_mod, email="unverified@example.com", verified=False)
    user = await oauth_service.resolve_or_link(identity)
    assert user.email_verified is False


@pytest.mark.asyncio
async def test_new_account_password_hash_is_unusable_random_argon2(oauth_mod, oauth_service, password_service):
    identity = _identity(oauth_mod, email="pwtest@example.com")
    user = await oauth_service.resolve_or_link(identity)
    # A hash of a random, never-persisted value can never verify true
    # against anything a real client could submit.
    assert password_service.verify(user.password_hash, "") is False
    assert password_service.verify(user.password_hash, "password123") is False


@pytest.mark.asyncio
async def test_known_link_returns_same_user_without_re_checking_email(oauth_mod, oauth_service, user_store):
    identity = _identity(oauth_mod, provider="google", subject="sub-2", email="first@example.com", verified=True)
    first = await oauth_service.resolve_or_link(identity)

    # Same provider+subject, DIFFERENT email claimed this time -- the
    # known-link fast path must not re-derive identity from email at all.
    changed_email_identity = _identity(
        oauth_mod, provider="google", subject="sub-2", email="changed@example.com", verified=True
    )
    second = await oauth_service.resolve_or_link(changed_email_identity)
    assert second.id == first.id


@pytest.mark.asyncio
async def test_verified_identity_links_onto_verified_existing_account(oauth_mod, oauth_service, user_store, clock):
    existing = await user_store.create("shared@example.com", "irrelevant-hash", ())
    await user_store.mark_email_verified(existing.id, clock())

    identity = _identity(oauth_mod, provider="github", subject="gh-1", email="shared@example.com", verified=True)
    linked_user = await oauth_service.resolve_or_link(identity)
    assert linked_user.id == existing.id


@pytest.mark.asyncio
async def test_unverified_new_identity_against_verified_existing_account_is_refused(oauth_mod, oauth_service, user_store, clock):
    """Attack shape 1 (see UnverifiedEmailAccountConflict docstring): an
    attacker's OAuth identity claims a victim's email but the PROVIDER has
    not verified it -- must never auto-link onto the victim's real account."""
    victim = await user_store.create("victim@example.com", "irrelevant-hash", ())
    await user_store.mark_email_verified(victim.id, clock())

    attacker_identity = _identity(oauth_mod, provider="shady-idp", subject="atk-1", email="victim@example.com", verified=False)
    with pytest.raises(oauth_mod.UnverifiedEmailAccountConflict):
        await oauth_service.resolve_or_link(attacker_identity)


@pytest.mark.asyncio
async def test_verified_identity_against_unverified_existing_account_is_refused(oauth_mod, oauth_service, user_store):
    """Attack shape 2: an attacker pre-registered the victim's email
    locally but never verified it; the victim's later, genuinely-verified
    OAuth login must not be auto-linked onto that unverified, attacker-
    controlled row."""
    await user_store.create("victim2@example.com", "attacker-set-hash", ())  # never verified

    victim_identity = _identity(oauth_mod, provider="google", subject="victim-sub", email="victim2@example.com", verified=True)
    with pytest.raises(oauth_mod.UnverifiedEmailAccountConflict):
        await oauth_service.resolve_or_link(victim_identity)


@pytest.mark.asyncio
async def test_unverified_identity_against_unverified_existing_account_is_also_refused(oauth_mod, oauth_service, user_store):
    await user_store.create("bothunverified@example.com", "hash", ())
    identity = _identity(oauth_mod, email="bothunverified@example.com", verified=False)
    with pytest.raises(oauth_mod.UnverifiedEmailAccountConflict):
        await oauth_service.resolve_or_link(identity)


@pytest.mark.asyncio
async def test_stale_link_falls_back_to_email_resolution(oauth_mod, oauth_service, oauth_account_store, user_store, clock):
    """A link row whose target user no longer exists (deleted since
    linking) must not permanently strand that identity -- it re-resolves
    by email exactly like a first-time login."""
    stale = oauth_mod.OAuthLinkedAccountRecord(
        provider="google", subject="ghost-sub", user_id="does-not-exist", email_at_link="ghost@example.com", linked_at=clock()
    )
    await oauth_account_store.link(stale)

    identity = _identity(oauth_mod, provider="google", subject="ghost-sub", email="ghost@example.com", verified=True)
    user = await oauth_service.resolve_or_link(identity)
    assert user.email == "ghost@example.com"
    assert user.id != "does-not-exist"


@pytest.mark.asyncio
async def test_complete_login_issues_a_real_token_pair(oauth_mod, oauth_service, refresh_store):
    identity = _identity(oauth_mod, email="loginflow@example.com", verified=True)
    pair = await oauth_service.complete_login(identity)
    assert pair.access
    assert pair.refresh
    assert len(refresh_store.all_records()) == 1


@pytest.mark.asyncio
async def test_complete_login_emits_login_event_tagged_oauth(oauth_mod, user_store, oauth_account_store, password_service, clock, token_service, refresh_store, event_sink):
    import importlib
    import sys

    core = sys.modules["_core"]
    auth_service = core.AuthService(user_store, refresh_store, password_service, token_service, clock, events=event_sink)
    service = oauth_mod.OAuthAccountService(user_store, oauth_account_store, password_service, auth_service, clock)

    identity = _identity(oauth_mod, email="audited@example.com", verified=True)
    await service.complete_login(identity)

    assert any(action == "auth.login" and extra.get("method") == "oauth" for action, extra in event_sink.events)
