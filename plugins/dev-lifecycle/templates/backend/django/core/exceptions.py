"""Custom DRF `EXCEPTION_HANDLER` — Stage 4 Step 2 (#27) — mapping every
exception DRF's view dispatch can raise onto `core.contract.errors.
ErrorEnvelope`, handler-for-handler mirroring backend/fastapi's
`app/main.py` (`_validation_exception_handler` + `_app_error_handler` +
`_make_unhandled_exception_handler`):

| Exception                                   | ErrorCode            | status |
|----------------------------------------------|----------------------|--------|
| `core.contract.errors.AppError` subclass      | `exc.code`           | `exc.status_code` |
| `rest_framework.exceptions.ValidationError`   | `validation_failed`  | 422    |
| `NotFound` / `django.http.Http404`            | `not_found`          | 404    |
| `NotAuthenticated`                            | `unauthenticated`    | 401    |
| `PermissionDenied` (DRF or Django's own)      | `permission_denied`  | 403    |
| `Throttled`                                   | `rate_limited`       | 429    |
| anything else (other `APIException`s, a bare  | `internal_error`     | 500    |
| bug)                                           |                      |        |

**422, not DRF's default 400**: DRF's own `ValidationError` defaults to
`status_code = 400`; FastAPI's `RequestValidationError` remap
(app/main.py) uses 422 — reproducing 422 here, NOT DRF's default, is what
this handler's `ValidationError` branch does (constructs the `Response`
itself rather than reusing DRF's default handler's status).

**NEVER leak `str(exc)`**: the catch-all branch never includes the
original exception's message in the client-facing envelope — same promise
`error-envelope/errors.py`'s own module docstring makes ("an unhandled
bug ... the framework's generic 500 handler still catches, mapping to
this same base's `to_envelope()`") and `app/main.py`'s
`_unhandled_exception_handler` keeps literally true on the FastAPI side.

Wired via `REST_FRAMEWORK["EXCEPTION_HANDLER"]` = `"core.exceptions.
exception_handler"` (config/settings.py)."""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response

from core.contract.errors import AppError, ErrorBody, ErrorCode, ErrorDetail, ErrorEnvelope

logger = logging.getLogger(__name__)

_VALIDATION_MESSAGE = "Request validation failed."


def _flatten_validation_errors(detail: Any, field_path: str = "") -> list[ErrorDetail]:
    """Flattens DRF's field-keyed `ValidationError.detail` (a `dict`/`list`
    tree of `rest_framework.exceptions.ErrorDetail` string subclasses) into
    `core.contract.errors.ErrorDetail` entries — the DRF-side counterpart
    to `app/main.py`'s `".".join(str(p) for p in err["loc"])` flattening of
    FastAPI's `RequestValidationError.errors()`. A top-level, non-field
    error (`raise ValidationError("message")`, `non_field_errors`) yields
    `field=None`/`field="non_field_errors"` respectively — same
    `field: str | None` shape `ErrorDetail` (core/contract/errors.py)
    declares."""
    details: list[ErrorDetail] = []
    if isinstance(detail, dict):
        for key, value in detail.items():
            sub_path = f"{field_path}.{key}" if field_path else str(key)
            details.extend(_flatten_validation_errors(value, sub_path))
    elif isinstance(detail, list):
        for item in detail:
            if isinstance(item, (dict, list)):
                details.extend(_flatten_validation_errors(item, field_path))
            else:
                details.append(ErrorDetail(field=field_path or None, message=str(item)))
    else:
        details.append(ErrorDetail(field=field_path or None, message=str(detail)))
    return details


def exception_handler(exc: Exception, context: dict) -> Response:
    """DRF's `EXCEPTION_HANDLER` contract: `(exc, context) -> Response |
    None`. This implementation always returns a `Response` — even the
    final catch-all branch — so an exception raised inside a DRF view
    dispatch NEVER falls through to DRF's own default handler or Django's
    generic error page; every error response this app sends is
    `ErrorEnvelope`-shaped, no exceptions (see this module's docstring
    table)."""

    if isinstance(exc, AppError):
        envelope = exc.to_envelope()
        return Response(envelope.model_dump(mode="json"), status=exc.status_code)

    if isinstance(exc, drf_exceptions.ValidationError):
        envelope = ErrorEnvelope(
            error=ErrorBody(
                code=ErrorCode.VALIDATION_FAILED,
                message=_VALIDATION_MESSAGE,
                details=_flatten_validation_errors(exc.detail) or None,
            )
        )
        return Response(envelope.model_dump(mode="json"), status=422)

    if isinstance(exc, (drf_exceptions.NotFound, Http404)):
        envelope = ErrorEnvelope(
            error=ErrorBody(code=ErrorCode.NOT_FOUND, message=str(exc) or "Not found.", details=None)
        )
        return Response(envelope.model_dump(mode="json"), status=404)

    if isinstance(exc, drf_exceptions.NotAuthenticated):
        envelope = ErrorEnvelope(
            error=ErrorBody(
                code=ErrorCode.UNAUTHENTICATED,
                message=str(exc) or "Authentication is required.",
                details=None,
            )
        )
        return Response(envelope.model_dump(mode="json"), status=401)

    if isinstance(exc, (drf_exceptions.PermissionDenied, DjangoPermissionDenied)):
        envelope = ErrorEnvelope(
            error=ErrorBody(
                code=ErrorCode.PERMISSION_DENIED,
                message=str(exc) or "You do not have permission to perform this action.",
                details=None,
            )
        )
        return Response(envelope.model_dump(mode="json"), status=403)

    if isinstance(exc, drf_exceptions.Throttled):
        envelope = ErrorEnvelope(
            error=ErrorBody(
                code=ErrorCode.RATE_LIMITED,
                message="Too many requests. Please try again later.",
                details=None,
            )
        )
        return Response(envelope.model_dump(mode="json"), status=429)

    # Anything else: DRF's other APIException subclasses (MethodNotAllowed,
    # UnsupportedMediaType, ParseError, AuthenticationFailed, ...) and any
    # genuinely unhandled bug -- collapsed to the same internal_error/500
    # this catalog's error contract uses for "an unhandled bug" (error-
    # envelope/errors.py's own module docstring), per this step's own
    # instructions ("unhandled/APIException -> 500 internal_error"). Logged
    # server-side (with the real traceback) for operability -- NEVER in the
    # client-facing envelope, which only ever gets AppError's own generic
    # default_message.
    logger.exception("Unhandled exception in DRF view", exc_info=exc)
    envelope = AppError().to_envelope()
    return Response(envelope.model_dump(mode="json"), status=500)
