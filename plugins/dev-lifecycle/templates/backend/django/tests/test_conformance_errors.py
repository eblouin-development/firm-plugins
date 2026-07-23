"""Conformance-proof tests for `core.exceptions.exception_handler` — Stage 4
Step 2 (#27), the acceptance core for this step. Every assertion here checks
the response body against a shape independently constructed from
`core.contract.errors` (the vendored contract source), not just "some 4xx/
5xx status" — see each test's own docstring for exactly what's cross-checked
and against what."""

from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from core.contract.errors import AppError, ErrorEnvelope, NotFoundError

pytestmark = pytest.mark.django_db


def test_validation_error_is_422_and_matches_error_envelope_shape(api_client: APIClient) -> None:
    """`name=""` violates the frozen contract's `ItemCreate.name`
    `minLength: 1` (packages/api-client/openapi.json) — DRF's own
    `ValidationError` default status is 400; this asserts the handler
    reproduces FastAPI's 422 instead (see core/exceptions.py's module
    docstring, "422, not DRF's default 400"). The cross-check: parsing the
    raw response body through `ErrorEnvelope.model_validate` — the SAME
    vendored pydantic model `core/contract/errors.py` defines — must
    succeed (proving no extra/missing keys, correct types, a real
    `ErrorCode` member) and re-dumping it must reproduce the exact same
    JSON, byte-for-byte."""
    response = api_client.post("/items", {"name": ""}, format="json")

    assert response.status_code == 422
    body = response.json()

    envelope = ErrorEnvelope.model_validate(body)
    assert envelope.error.code.value == "validation_failed"
    assert envelope.model_dump(mode="json") == body

    assert any(d.field == "name" for d in envelope.error.details or [])


def test_not_found_error_matches_vendored_not_found_error_envelope(api_client: APIClient) -> None:
    """Builds the EXPECTED envelope directly from
    `core.contract.errors.NotFoundError` (the vendored exception class
    itself, not a re-implementation) and asserts the actual `GET
    /items/{missing_id}` response equals it exactly — the literal
    "cross-check ... against the vendored errors.py output for the same
    inputs" this step's instructions call for."""
    missing_id = uuid.uuid4()

    response = api_client.get(f"/items/{missing_id}")

    assert response.status_code == 404
    expected = NotFoundError(f"Item {missing_id} was not found.").to_envelope().model_dump(mode="json")
    assert response.json() == expected


@pytest.mark.urls("tests._conformance_urls")
def test_not_authenticated_is_401_and_matches_error_envelope_shape(api_client: APIClient) -> None:
    """No real route in this block raises `NotAuthenticated` yet (Stage 5,
    #28, is real auth) — exercised via a throwaway test-only route (see
    `tests/_conformance_urls.py`), the same pattern backend/fastapi's own
    `crashing_client` fixture uses for its 500 test."""
    response = api_client.get("/__test_only_401")

    assert response.status_code == 401
    body = response.json()
    envelope = ErrorEnvelope.model_validate(body)
    assert envelope.error.code.value == "unauthenticated"
    assert envelope.model_dump(mode="json") == body


@pytest.mark.urls("tests._conformance_urls")
def test_permission_denied_is_403_and_matches_error_envelope_shape(api_client: APIClient) -> None:
    response = api_client.get("/__test_only_403")

    assert response.status_code == 403
    body = response.json()
    envelope = ErrorEnvelope.model_validate(body)
    assert envelope.error.code.value == "permission_denied"
    assert envelope.model_dump(mode="json") == body


@pytest.mark.urls("tests._conformance_urls")
def test_unhandled_exception_returns_enveloped_500_without_leaking_message(
    crashing_client: APIClient,
) -> None:
    """Pins the SAME promise backend/fastapi's
    `test_unhandled_exception_returns_enveloped_500_without_leaking_message`
    (tests/test_error_envelope.py) pins there: a genuinely unhandled bug —
    not a deliberately-raised AppError — still renders `ErrorEnvelope` at
    500, and the exception's own message/type NEVER reaches the client."""
    response = crashing_client.get("/__test_only_crash")

    assert response.status_code == 500
    body = response.json()

    expected = AppError().to_envelope().model_dump(mode="json")
    assert body == expected
    assert "boom" not in body["error"]["message"]
    assert "RuntimeError" not in body["error"]["message"]


def test_item_response_never_includes_deleted_at(api_client: APIClient) -> None:
    created = api_client.post("/items", {"name": "Visible"}, format="json").json()
    assert "deleted_at" not in created

    fetched = api_client.get(f"/items/{created['id']}").json()
    assert "deleted_at" not in fetched

    listed = api_client.get("/items").json()
    for item in listed["items"]:
        assert "deleted_at" not in item


def test_empty_name_is_rejected_with_422(api_client: APIClient) -> None:
    response = api_client.post("/items", {"name": ""}, format="json")
    assert response.status_code == 422
