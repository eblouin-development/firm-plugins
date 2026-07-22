<!--
block: components/backend/error-envelope  # catalog component
needs:
  - pydantic v2 (2.13.x): the sole runtime dependency, pinned per references/compatibility-matrix.md's Backend — Python row
exposes:
  - ErrorEnvelope, ErrorBody, ErrorDetail — the {error: {code, message, details?}} shape, THE non-422 error contract
  - AppError and its concrete subclasses (UnauthenticatedError, PermissionDeniedError, NotFoundError, ValidationFailedError, ConflictError, RateLimitedError) — the exception hierarchy a framework's handler maps to the envelope
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-22
provenance: manual
-->

# error-envelope

A framework-neutral, drop-in `errors.py`: THE standard non-422 error
envelope every response in this app uses, and the exception hierarchy a
framework's own exception handler maps to it. Lives at
`templates/components/backend/error-envelope/` in this repo; Stage 3
backend blocks copy `errors.py` verbatim into `app/core/errors.py`. THE
contract Step 2's FastAPI exception handler renders, and Stage 4's Django/
DRF track's own exception handler conforms to independently.

This is a **catalog component** (`template-author`'s partial-contract
kind), not an app-layer template block. **Framework-neutral by design** —
no FastAPI import anywhere in this file; both Stage 3 and Stage 4 conform
to the shape below.

## Contents
- Composition contract
- The envelope shape (THE contract)
- Not the 422 shape
- The exception hierarchy
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **Pydantic v2, 2.13.x** — the sole runtime dependency, pinned per
  `references/compatibility-matrix.md`'s Backend — Python row.

**EXPOSES**
- `ErrorEnvelope` / `ErrorBody` / `ErrorDetail` — the envelope shape (see
  below).
- `AppError` — the exception base every domain/HTTP-shaped error the app
  raises deliberately extends. `to_envelope() -> ErrorEnvelope`.
- Six concrete subclasses: `UnauthenticatedError` (401),
  `PermissionDeniedError` (403), `NotFoundError` (404),
  `ValidationFailedError` (400), `ConflictError` (409), `RateLimitedError`
  (429) — each with its own `code`, `status_code`, and `default_message`.
- Its co-located doc fragment: `docs/fragment.md`.

**Registered separately, not by this file:** the FastAPI (or Django/DRF)
exception handler that catches `AppError` and renders `exc.to_envelope()`
with `exc.status_code` is wired in Step 2's own app assembly — this
component ships the shape and the exception types only, deliberately with
no framework import or `except`-to-HTTP-response code here.

## The envelope shape (THE contract)

```python
class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str | None = None
    message: str

class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
    details: list[ErrorDetail] | None = None

class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: ErrorBody
```

Serialized:

```json
{"error": {"code": "not_found", "message": "The requested resource was not found.", "details": null}}
```

A client switches on `code` (a short, stable, machine-matchable string),
never on `message` — `message` is for humans and can change wording
without breaking a client. `details` is a list of `{field, message}`
pairs for a failure with more than one thing to say (e.g. several business
rules violated at once); `field` is optional since not every detail ties
to a single field.

## Not the 422 shape

FastAPI/Pydantic's own automatic response for a request-body or
query-param schema validation failure — `{"detail": [{"loc": [...], "msg":
..., "type": ...}]}` — is FastAPI's built-in behavior, produced before the
app's own exception handler ever runs, and is **deliberately not**
reshaped into `ErrorEnvelope`. This component's envelope covers every
*other* error class the app raises on purpose: not-found, forbidden,
unauthenticated, conflict, rate-limited, a domain-level 400 that isn't a
schema mismatch, and the generic 500 for anything unhandled.
`references/backend/fastapi.md`'s "Validation & error handling" section
("Let schema validation reject malformed input automatically (422)... Add
exception handlers for domain exceptions") is the canon this split is
grounded in.

## The exception hierarchy

`AppError(message: str | None = None, *, details: list[ErrorDetail] |
None = None)` — subclass per error class, don't raise `AppError` directly
in application code:

| Exception | `code` | `status_code` |
| --- | --- | --- |
| `UnauthenticatedError` | `unauthenticated` | 401 |
| `PermissionDeniedError` | `permission_denied` | 403 |
| `NotFoundError` | `not_found` | 404 |
| `ValidationFailedError` | `validation_failed` | 400 |
| `ConflictError` | `conflict` | 409 |
| `RateLimitedError` | `rate_limited` | 429 |
| `AppError` (base, raised directly only for an unhandled/generic case) | `internal_error` | 500 |

`UnauthenticatedError` vs `PermissionDeniedError` matches
`references/security/secure-baseline.md`'s "Authentication &
authorization" distinction: authentication proves identity (401 — no
valid credentials at all); authorization checks whether *this* identity
may act on *this* resource (403 — authenticated, but not allowed).
`RateLimitedError` exists so the middleware/rate-limit component (Stage 2)
can raise a 429 through this same envelope shape instead of hand-rolling
its own body.

## Testing

`tests/test_errors.py` covers: the envelope's exact serialized shape
(including the `details: null` omission case), a populated `details` list,
`ErrorDetail.field` being optional, all three models rejecting an unknown
field (`extra="forbid"`), `AppError`'s default-vs-custom message and
`to_envelope()` round trip, `AppError` behaving as a real raisable
exception, `to_envelope()` carrying `details` through, every concrete
subclass's `code`/`status_code`/non-empty default message (parametrized
across all six), a concrete subclass's full serialized envelope, a
concrete subclass accepting a custom message, and every concrete subclass
being an `AppError`.

Run: `uv run --python 3.13 --with 'pydantic==2.13.*' --with pytest -- pytest templates/components/backend/error-envelope/tests/ -q`

## Judgment calls

- **Six concrete subclasses, not a generic `AppError(code=..., status_code=...)`
  constructor call site.** A named class per error class
  (`NotFoundError`, `ConflictError`, ...) makes `except NotFoundError:` and
  `raise NotFoundError(...)` both readable and greppable across the
  codebase; a single parametrized `AppError` would work but loses that at
  every call and catch site.
- **`RateLimitedError` lives here, not in the middleware/rate-limit
  component (Stage 2).** The rate-limit middleware raises it, but the
  *exception type* belongs with the rest of the hierarchy so every error
  class stays in one place with one shared `to_envelope()` mechanism,
  rather than splitting the hierarchy across two components.
- **The FastAPI/Django exception-handler registration is explicitly out of
  scope for this file.** Keeping this component importable with zero
  framework dependency is what lets Stage 4's Django/DRF track reuse the
  exact same `AppError` hierarchy and envelope shape — a hard FastAPI
  import here would break that reuse.
