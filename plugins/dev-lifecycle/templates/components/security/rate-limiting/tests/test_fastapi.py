"""Tests for rate-limiting's fastapi.py: both the dependency and middleware
variants, against a real Starlette/FastAPI app + TestClient."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from starlette.testclient import TestClient


def test_middleware_allows_then_429s_with_retry_after(fastapi_mod, core_mod):
    store = core_mod.InMemoryBucketStore()
    app = FastAPI()
    app.add_middleware(
        fastapi_mod.RateLimitMiddleware, store=store, capacity=2, refill_per_second=0.001
    )

    @app.get("/")
    def homepage():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/").status_code == 200
    third = client.get("/")
    assert third.status_code == 429
    assert "retry-after" in third.headers
    assert int(third.headers["retry-after"]) >= 0


def test_middleware_per_client_ip_isolation(fastapi_mod, core_mod):
    store = core_mod.InMemoryBucketStore()
    app = FastAPI()
    app.add_middleware(
        fastapi_mod.RateLimitMiddleware, store=store, capacity=1, refill_per_second=0.001
    )

    @app.get("/")
    def homepage():
        return {"ok": True}

    # Starlette's TestClient reports a fixed client host, so isolation here
    # is exercised via the store directly (see test_core.py's per-key
    # isolation coverage) -- this test just confirms a single TestClient's
    # requests share one bucket (the same simulated client IP).
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/").status_code == 429


def test_dependency_variant_429s_on_deny(fastapi_mod, core_mod):
    store = core_mod.InMemoryBucketStore()
    app = FastAPI()
    limiter = fastapi_mod.make_rate_limit_dependency(store, capacity=1, refill_per_second=0.001)

    @app.post("/login", dependencies=[Depends(limiter)])
    def login():
        return {"ok": True}

    client = TestClient(app)
    assert client.post("/login").status_code == 200
    second = client.post("/login")
    assert second.status_code == 429
    assert "retry-after" in second.headers


def test_dependency_variant_does_not_affect_undecorated_routes(fastapi_mod, core_mod):
    store = core_mod.InMemoryBucketStore()
    app = FastAPI()
    limiter = fastapi_mod.make_rate_limit_dependency(store, capacity=1, refill_per_second=0.001)

    @app.post("/login", dependencies=[Depends(limiter)])
    def login():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    client = TestClient(app)
    client.post("/login")
    client.post("/login")  # drains the login-only limiter
    assert client.get("/health").status_code == 200  # unaffected -- different bucket entirely


# --- MEDIUM-7: refill_per_second<=0 rejected at construction ---------------


def test_dependency_construction_rejects_zero_refill_rate(core_mod, fastapi_mod):
    import pytest

    store = core_mod.InMemoryBucketStore()
    with pytest.raises(ValueError):
        fastapi_mod.make_rate_limit_dependency(store, capacity=1, refill_per_second=0)


def test_middleware_construction_rejects_zero_refill_rate(core_mod, fastapi_mod):
    import pytest

    store = core_mod.InMemoryBucketStore()
    app = FastAPI()

    @app.get("/")
    def homepage():
        return {"ok": True}

    app.add_middleware(fastapi_mod.RateLimitMiddleware, store=store, capacity=1, refill_per_second=0)
    # Starlette builds the middleware stack (and so instantiates
    # RateLimitMiddleware) lazily, on first request -- the ValueError from
    # __init__ surfaces here.
    with pytest.raises(ValueError):
        TestClient(app).get("/")


# --- Issue #42: /health + /readyz exempt from the middleware by default ----


def test_health_and_readyz_never_429_under_burst(fastapi_mod, core_mod):
    """The regression test for issue #42: behind a TLS-terminating proxy at
    the safe default trusted_hops=0, every request shares one bucket -- an
    LB polling /health under burst must never see a 429 (which it would
    read as an unhealthy instance and pull from rotation), even though a
    non-exempt route under the exact same burst does 429 (see the sibling
    test below). capacity=1 means the SECOND request of any kind would
    normally trip the limiter."""
    store = core_mod.InMemoryBucketStore()
    app = FastAPI()
    app.add_middleware(fastapi_mod.RateLimitMiddleware, store=store, capacity=1, refill_per_second=0.001)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz():
        return {"status": "ready"}

    client = TestClient(app)
    for _ in range(10):
        assert client.get("/health").status_code == 200
    for _ in range(10):
        assert client.get("/readyz").status_code == 200


def test_non_exempt_route_still_429s_under_the_same_burst(fastapi_mod, core_mod):
    """No regression to the limiter itself: a normal route sharing the SAME
    middleware instance (and so the same default exempt_paths) as the test
    above still gets 429 once its bucket is drained -- only /health and
    /readyz bypass the limiter, not every route."""
    store = core_mod.InMemoryBucketStore()
    app = FastAPI()
    app.add_middleware(fastapi_mod.RateLimitMiddleware, store=store, capacity=1, refill_per_second=0.001)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/items")
    def items():
        return {"items": []}

    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/health").status_code == 200  # still exempt, still 200
    assert client.get("/items").status_code == 200  # first token
    assert client.get("/items").status_code == 429  # bucket now empty


def test_middleware_default_exempt_paths_is_health_and_readyz(fastapi_mod):
    assert fastapi_mod._DEFAULT_EXEMPT_PATHS == frozenset({"/health", "/readyz"})


def test_middleware_exempt_paths_disableable(fastapi_mod, core_mod):
    """Passing an explicit empty frozenset opts a project back into rate-
    limiting its own health endpoint, for the rare project that wants
    that."""
    store = core_mod.InMemoryBucketStore()
    app = FastAPI()
    app.add_middleware(
        fastapi_mod.RateLimitMiddleware,
        store=store,
        capacity=1,
        refill_per_second=0.001,
        exempt_paths=frozenset(),
    )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/health").status_code == 429
