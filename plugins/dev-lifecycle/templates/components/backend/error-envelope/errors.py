"""Framework-neutral error envelope: the app's standard shape for every
non-422 error response, plus the exception hierarchy a framework's
exception handler maps to it. Pydantic v2 only (pinned per
references/compatibility-matrix.md's Backend — Python row to Pydantic v2,
2.13.x) — NO FastAPI import in this file (shape only). This is THE
contract Stage 3's FastAPI exception handler (Step 2) and Stage 4's Django/
DRF exception handler both map their errors to, and what any API client
conforms to when parsing an error response.

Drop-in: copy this file into app/core/errors.py. The FastAPI exception
handler that catches AppError subclasses and renders ErrorEnvelope as the
JSON body is registered separately, in Step 2's app/core/exceptions.py (or
wherever that block's own FastAPI wiring lands) — this file is the shape
and the exception types only, deliberately with no `except`-to-HTTP
mapping or FastAPI import here, so a Django/DRF exception handler (Stage 4)
can import the same AppError hierarchy without pulling in FastAPI.

Distinct from FastAPI's own automatic 422 response for a request-body/
query-param Pydantic ValidationError — that shape
(`{"detail": [{"loc": [...], "msg": ..., "type": ...}]}`) is FastAPI's
built-in behavior for schema validation failures at the request boundary
and is NOT reshaped into this envelope; ErrorEnvelope/AppError cover every
OTHER error class (404, 401, 403, 409, 500, and a domain-level 400 that
isn't a schema mismatch).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# The envelope shape (THE contract)
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    """One item in an error's optional `details` list — e.g. one field's
    domain-level problem inside a larger validation failure. `field` is
    optional: some details aren't tied to a single field (a cross-field
    business rule, a resource-level conflict note)."""

    model_config = ConfigDict(extra="forbid")

    field: str | None = None
    message: str


class ErrorBody(BaseModel):
    """The `error` object inside the envelope. `code` is a short, stable,
    machine-matchable string (`"not_found"`, `"conflict"`, ...) — a client
    should switch on `code`, never on `message` (message is for humans,
    can change wording without breaking a client, and MUST NOT be treated
    as a stable identifier)."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: list[ErrorDetail] | None = None


class ErrorEnvelope(BaseModel):
    """THE non-422 error envelope every error response in this app uses:

        {"error": {"code": "not_found", "message": "...", "details": null}}

    Every field required except `details`, which is `null` (omitted from
    the exception's own `to_envelope()` output) when there's nothing more
    specific than the top-level `code`/`message` to say."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorBody


# ---------------------------------------------------------------------------
# The exception hierarchy a framework's handler maps to the envelope
# ---------------------------------------------------------------------------


class AppError(Exception):
    """Base of every domain/HTTP-shaped exception the app raises
    deliberately (as opposed to an unhandled bug, which the framework's
    generic 500 handler still catches, mapping to this same base's
    `to_envelope()` — see `code`/`status_code`'s defaults below).

    A framework's exception handler (Step 2's FastAPI wiring, or a Django/
    DRF `exception_handler`) catches `AppError` and renders
    `exc.to_envelope()` as the JSON body with `exc.status_code`. Subclass
    per error class (see the concrete ones below) rather than raising
    `AppError` directly in application code — the concrete subclasses are
    what carry the right `code`/`status_code`/default message."""

    code: str = "internal_error"
    status_code: int = 500
    default_message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, *, details: list[ErrorDetail] | None = None) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)

    def to_envelope(self) -> ErrorEnvelope:
        return ErrorEnvelope(error=ErrorBody(code=self.code, message=self.message, details=self.details))


class UnauthenticatedError(AppError):
    """No valid credentials presented at all — distinct from
    `PermissionDeniedError` (authenticated, but not allowed). Per
    references/security/secure-baseline.md's "Authentication &
    authorization": authentication proves identity; authorization checks
    whether *this* identity may act on *this* resource."""

    code = "unauthenticated"
    status_code = 401
    default_message = "Authentication is required."


class PermissionDeniedError(AppError):
    """Authenticated, but not authorized for this action/resource — the
    IDOR-class check (`references/security/secure-baseline.md`: "Check
    ownership/scope on every ID-addressed resource")."""

    code = "permission_denied"
    status_code = 403
    default_message = "You do not have permission to perform this action."


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404
    default_message = "The requested resource was not found."


class ValidationFailedError(AppError):
    """A domain-level validation failure that is NOT a schema mismatch —
    Pydantic/FastAPI's own request-body validation already produces its
    own distinct 422 response, untouched by this hierarchy (see this
    module's docstring). Raise this for a business-rule violation a field
    constraint can't express (e.g. "end_date must be after start_date"
    caught in a service function, not at the schema layer)."""

    code = "validation_failed"
    status_code = 400
    default_message = "The request could not be validated."


class ConflictError(AppError):
    """The requested change conflicts with the resource's current state
    (a duplicate unique key, a stale optimistic-concurrency version, a
    state-machine transition that isn't valid from the current state)."""

    code = "conflict"
    status_code = 409
    default_message = "The request conflicts with the current state of the resource."


class RateLimitedError(AppError):
    """Caller has exceeded a rate limit. Per
    references/security/secure-baseline.md's "Rate limiting & lockout" —
    the middleware/rate-limit component (Stage 2) raises this rather than
    hand-rolling its own 429 body, so a rate-limited response uses the
    same envelope shape as every other error."""

    code = "rate_limited"
    status_code = 429
    default_message = "Too many requests. Please try again later."
