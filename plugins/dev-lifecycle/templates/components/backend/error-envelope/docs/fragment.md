<!-- fragment: block:components/backend/error-envelope -->

## Setup
Copy `errors.py` into `app/core/errors.py`. Raise the concrete `AppError`
subclass matching the failure (`NotFoundError`, `ConflictError`, ...)
anywhere in a service/route; register a framework exception handler
(FastAPI's `add_exception_handler(AppError, ...)`, or a Django/DRF
`exception_handler`) that catches `AppError` and renders
`exc.to_envelope().model_dump()` with `exc.status_code` — that handler is
wired in Step 2, not this file.

## Maintenance
Framework-neutral by design: no FastAPI import in this file. This is THE
error contract both the FastAPI (Stage 3) and Django/DRF (Stage 4) tracks
conform to.
