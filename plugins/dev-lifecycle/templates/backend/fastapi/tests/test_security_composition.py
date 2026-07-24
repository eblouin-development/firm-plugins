"""Proves the Stage 3 Step 3b (#26) security-composition wiring in
app/main.py's create_app() — see that module's "Security composition"
docstring for the full middleware-order rationale this file's tests are
checking against real request/response behavior, not just reading the
code.

Rate-limiting and CORS tests use the `make_client` factory fixture
(tests/conftest.py) to build a bespoke `Settings()` per test (a tiny
`rate_limit_capacity`, a specific `cors_allowed_origins`) rather than the
shared `client` fixture's fixed defaults, so a burst test never has to
sleep in real time and a CORS test never depends on the default empty
allowlist.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.security.audit_logging import RequestIDMiddleware, audit_event, request_id_var

# ---------------------------------------------------------------------------
# Security headers (security_headers, outermost middleware)
# ---------------------------------------------------------------------------


def test_security_headers_present_on_a_normal_response(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in response.headers["permissions-policy"]
    csp = response.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    # Plain http (the TestClient default) — HSTS must NOT be sent (see
    # security_headers/_core.py's build_headers(): HSTS is gated on
    # is_https, on purpose, not unconditionally set).
    assert "strict-transport-security" not in response.headers


def test_hsts_present_only_over_https(client: TestClient) -> None:
    """An explicit https:// URL flips the ASGI scope's scheme (verified
    directly against Starlette's TestClient/Request behavior before writing
    this test) — this is what proves HSTS is gated on the CONNECTION's
    actual scheme, not a static config flag, matching the deployment note
    in security_headers/fastapi.py's module docstring."""
    response = client.get("https://testserver/health")
    assert response.status_code == 200
    assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


# ---------------------------------------------------------------------------
# CORS (cors_lockdown, innermost of the four security middlewares)
# ---------------------------------------------------------------------------


def test_cors_preflight_allows_a_configured_origin(make_client) -> None:
    client = make_client(cors_allowed_origins=["https://allowed.example.com"])
    response = client.options(
        "/items",
        headers={
            "Origin": "https://allowed.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://allowed.example.com"


def test_cors_preflight_rejects_a_disallowed_origin(make_client) -> None:
    client = make_client(cors_allowed_origins=["https://allowed.example.com"])
    response = client.options(
        "/items",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Starlette's own CORSMiddleware behavior for a disallowed preflight
    # origin: no Access-Control-Allow-Origin header at all -- the actual
    # mechanism a browser enforces the block on, not a particular status
    # code (this component wires Starlette's CORSMiddleware unchanged; see
    # cors_lockdown/README.md's "Testing" section for the same assertion
    # shape at the component's own test layer).
    assert "access-control-allow-origin" not in response.headers


def test_cors_not_wired_at_all_when_no_origins_configured(client: TestClient) -> None:
    """The shared `client` fixture's default Settings() has an empty
    cors_allowed_origins (AppSettings' own secure default) — create_app()
    documents this as "skip CORS middleware entirely" (deny-by-default
    without hitting CORSPolicy's empty-allowlist guard on every boot).
    Proven here by a cross-origin GET (a "simple request" a browser sends
    without a preflight) getting no Access-Control-Allow-Origin header --
    the app never sends the header without CORSMiddleware in the stack."""
    response = client.get("/health", headers={"Origin": "https://anything.example.com"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


# ---------------------------------------------------------------------------
# Rate limiting (rate_limiting, wraps CORS)
# ---------------------------------------------------------------------------


def test_rate_limit_returns_429_with_retry_after_once_burst_is_exhausted(make_client) -> None:
    # refill_per_second is deliberately tiny (not 0 -- validate_refill_rate
    # rejects that, see rate_limiting/_core.py) so the 3-request capacity is
    # effectively exhausted for the rest of this test, no real-time sleep
    # needed. Bursts against /items, not /health -- see the "Issue #42"
    # section below for why /health is now exempt from this middleware by
    # default and must never be the route this suite proves 429 against.
    client = make_client(rate_limit_capacity=3, rate_limit_refill_per_second=0.0001)

    allowed = [client.get("/items") for _ in range(3)]
    assert all(r.status_code == 200 for r in allowed)

    denied = client.get("/items")
    assert denied.status_code == 429
    assert denied.json()["detail"] == "rate limit exceeded"
    assert int(denied.headers["retry-after"]) > 0


def test_rate_limit_denial_still_carries_response_headers_from_outer_middleware(make_client) -> None:
    """A 429 built by rate_limiting's own JSONResponse still passes back
    THROUGH request-id binding and security-headers (both wrap
    rate-limiting -- see create_app()'s documented order), so it should
    carry the same X-Request-ID/security headers as any other response,
    not a bare, unadorned response that bypassed the rest of the stack.
    Bursts against /items -- see the "Issue #42" section below for why
    /health is exempt from this middleware by default."""
    client = make_client(rate_limit_capacity=1, rate_limit_refill_per_second=0.0001)
    client.get("/items")  # consumes the single token
    denied = client.get("/items")
    assert denied.status_code == 429
    assert "x-request-id" in denied.headers
    assert denied.headers["x-content-type-options"] == "nosniff"


# --- Issue #42: /health + /readyz exempt from RateLimitMiddleware by default
# ---------------------------------------------------------------------------
# Behind a TLS-terminating proxy at the safe default trusted_hops=0, every
# request shares ONE bucket keyed on the proxy's own peer address -- an LB
# polling /health under burst could 429 its own health check and mark this
# instance unhealthy, an outage the limiter itself caused. See
# rate_limiting/fastapi.py's RateLimitMiddleware.exempt_paths docstring and
# app/main.py's Call 2 of 4 comment.


def test_health_never_429s_under_a_burst_that_would_trip_a_normal_route(make_client) -> None:
    """The regression test for issue #42: capacity=1 means the SECOND
    request of any kind would normally trip the limiter -- /health stays
    200 across many more requests than that because it never touches the
    bucket at all (RateLimitMiddleware.exempt_paths' default)."""
    client = make_client(rate_limit_capacity=1, rate_limit_refill_per_second=0.0001)
    for _ in range(10):
        assert client.get("/health").status_code == 200


def test_readyz_never_429s_under_a_burst_that_would_trip_a_normal_route(make_client) -> None:
    """Same regression as above, for the readiness probe -- an orchestrator
    polling /readyz to decide whether to route traffic to this instance
    must never see a self-inflicted 429 either."""
    client = make_client(rate_limit_capacity=1, rate_limit_refill_per_second=0.0001)
    for _ in range(10):
        assert client.get("/readyz").status_code == 200


def test_health_exemption_does_not_affect_a_normal_route_sharing_the_same_bucket_capacity(
    make_client,
) -> None:
    """No regression to the limiter itself: /items (NOT exempt) still 429s
    under the same low-capacity settings that leave /health untouched --
    proves the exemption is scoped to /health + /readyz, not a global
    bypass."""
    client = make_client(rate_limit_capacity=1, rate_limit_refill_per_second=0.0001)
    for _ in range(5):
        assert client.get("/health").status_code == 200
    assert client.get("/items").status_code == 200  # /items' own first (and only) token
    assert client.get("/items").status_code == 429


# ---------------------------------------------------------------------------
# Request-id / audit binding (audit_logging.middleware.RequestIDMiddleware)
# ---------------------------------------------------------------------------


def test_response_carries_a_minted_request_id_when_none_supplied(client: TestClient) -> None:
    response = client.get("/health")
    request_id = response.headers.get("x-request-id")
    assert request_id
    # Mintable as a real uuid4 -- the documented fallback shape.
    import uuid

    assert uuid.UUID(request_id).version == 4


def test_response_reflects_a_shape_valid_inbound_request_id(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "trace-abc123"})
    assert response.headers["x-request-id"] == "trace-abc123"


def test_a_malformed_inbound_request_id_is_replaced_not_trusted(client: TestClient) -> None:
    """A control character / whitespace fails `_SAFE_REQUEST_ID_RE`
    (audit_logging/middleware.py) -- the middleware mints a fresh id
    instead of reflecting the malformed one back."""
    response = client.get("/health", headers={"X-Request-ID": "bad id\nwith-newline"})
    returned = response.headers["x-request-id"]
    assert returned != "bad id\nwith-newline"
    import uuid

    assert uuid.UUID(returned).version == 4


@pytest.mark.asyncio
async def test_audit_event_called_during_a_request_carries_the_bound_request_id() -> None:
    """Direct, hermetic proof that RequestIDMiddleware actually binds
    audit.py's contextvar for the request's duration (not just the
    response header) -- the exact composition audit-logging/README.md's
    "Request-id binding (for Step 3 middleware)" section describes.
    Exercises RequestIDMiddleware standalone against a minimal inner ASGI
    app that calls audit_event() itself, rather than going through the
    full FastAPI app (which has no route that calls audit_event() yet --
    Stage 5's login flow will be the first real caller)."""
    captured: dict[str, object] = {}

    async def inner_app(scope, receive, send) -> None:
        assert scope["type"] == "http"
        record = audit_event(action="test.probe", actor="tester", resource="probe:1", outcome="success")
        captured["record"] = record
        captured["contextvar_during_request"] = request_id_var.get()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    wrapped = RequestIDMiddleware(inner_app)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=wrapped), base_url="http://testserver"
    ) as ac:
        response = await ac.get("/probe", headers={"X-Request-ID": "req-during-test"})

    assert response.headers["x-request-id"] == "req-during-test"
    assert captured["contextvar_during_request"] == "req-during-test"
    assert captured["record"]["request_id"] == "req-during-test"

    # Unbound again once the request has ended -- the middleware's `finally`
    # reset_request_id() ran, so a later, unrelated context sees None again
    # rather than leaking this request's id.
    assert request_id_var.get() is None


# ---------------------------------------------------------------------------
# Input validation (input_validation.StrictModel, adopted by ItemCreate/
# ItemUpdate/ItemOut — app/schemas/item.py)
# ---------------------------------------------------------------------------


def test_strict_model_rejects_unknown_field_on_update_at_the_api_boundary(client: TestClient) -> None:
    """ItemUpdate now extends StrictModel (app/schemas/item.py) --
    extra="forbid" applies to PATCH too, not just the POST body
    test_items.py's test_create_item_rejects_unknown_field already covers."""
    create = client.post("/items", json={"name": "Widget"})
    assert create.status_code == 201
    item_id = create.json()["id"]

    response = client.patch(f"/items/{item_id}", json={"name": "Renamed", "bogus": "nope"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_strict_model_rejects_a_wrong_json_type_at_the_api_boundary(client: TestClient) -> None:
    """`name` must arrive as a JSON string -- a JSON number is rejected,
    not silently stringified. (Item's own fields are str-only, so this
    doesn't isolate strict-mode's numeric-coercion behavior specifically --
    see test_strict_model_rejects_numeric_string_for_an_int_field below for
    that, exercised directly against the imported StrictModel class since
    no field in this app's own schemas is int/bool-typed.)"""
    response = client.post("/items", json={"name": 12345})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_strict_model_rejects_numeric_string_for_an_int_field() -> None:
    """Component-wiring sanity, not an API-boundary test (Item has no int/
    bool field to exercise this over HTTP -- see the docstring above): this
    app's actual imported `StrictModel` (app/core/security/input_validation/
    validation.py, composed into app/schemas/item.py) rejects a JSON string
    for an int field under strict=True, unlike Pydantic's lax default,
    which would silently coerce "5" -> 5. Confirms the vendored copy this
    app imports behaves per input-validation/README.md's "StrictModel uses
    real strict mode" section, not just that the component's own separate
    test suite (templates/components/security/input-validation/tests/)
    passes in isolation."""
    from pydantic import ValidationError

    from app.core.security.input_validation import StrictModel

    class _Probe(StrictModel):
        count: int

    _Probe(count=5)  # a real int is fine

    with pytest.raises(ValidationError):
        _Probe(count="5")  # a numeric STRING is not, under strict=True
