<!--
wiring: frontend-backend-contract
covers: CORS/cookie posture <-> public env conventions <-> the ErrorEnvelope/ErrorCode contract <-> Page[T] pagination, across apps/web, apps/admin, and the backend
last-verified: 2026-07-23
provenance: manual
versions-pinned-to: references/compatibility-matrix.md
sources:
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie/SameSite
  - references/security/secure-baseline.md
  - references/security/secrets-management.md
-->

# Frontend/backend contract conventions

**The cross-cutting rules every frontend consumer and the backend both conform to, regardless of which app or which backend framework** — CORS posture, which env vars are public, the one error shape, and the one pagination shape. These aren't any single block's canon; they're the seams a fresh backend + web/admin app has to agree on before requests work at all. Subordinate to a project's existing conventions where one already exists.

## Contents
- CORS: credentialed vs edge-routed same-origin
- Public env vars: `NEXT_PUBLIC_*` / `VITE_*` / `EXPO_PUBLIC_*`
- The error envelope
- Pagination: `Page[T]`
- Wiring checklist
- Related canon

## CORS: credentialed vs edge-routed same-origin
Cookie-mode auth (`apps/web`, `apps/admin`) keeps the refresh token in an `HttpOnly; Secure; SameSite=Lax; Path=/auth` cookie (`references/wiring/auth-end-to-end.md`). `SameSite=Lax` only rides on **same-site** requests, which forces a choice between two postures — never a third, wildcard-CORS-with-credentials option, which browsers refuse outright (`credentials: "include"` is incompatible with `Access-Control-Allow-Origin: *`):

- **Edge-routed same-origin (the default, simplest posture).** Serve the frontend and route the API paths (`/auth`, `/admin`, `/items`, `/health`, `/readyz`) to the backend from the *same* origin at the edge — a CDN behavior (e.g. CloudFront) in production, and the dev server's own proxy locally. The browser only ever talks to one origin, so the cookie always rides and there's no CORS to configure at all. Leave the base-URL env var (`VITE_API_BASE_URL` / `NEXT_PUBLIC_API_BASE_URL`) **empty** for this posture — an empty `baseUrl` makes `@repo/api-client` issue same-origin relative URLs.
- **Credentialed cross-origin.** Set the base-URL env var to the API's real origin and configure the backend's CORS to name the frontend's **exact** origin with `Access-Control-Allow-Credentials: true` — never a `*` wildcard — via the `cors-lockdown` component (`templates/components/security/cors-lockdown/`). The auth cookies also need `Secure` set in this posture (implied off `localhost`, required otherwise).

**Dev rewrites are the local instance of the same fix.** `templates/frontend/vite-spa/vite.config.ts`'s `server.proxy` and `templates/frontend/nextjs/next.config.ts`'s `async rewrites()` (also used verbatim by `templates/frontend/nextjs-admin/`) both forward the same API path list (`/auth`, `/admin`, `/items`, `/health`, `/readyz`) to the local backend (`http://localhost:8000` by default, overridable via `VITE_DEV_API_PROXY` / `NEXT_DEV_API_PROXY`) — without this, a cross-origin `5173 -> 8000` (or `3000 -> 8000`) dev setup would silently drop the `SameSite=Lax` refresh cookie and refresh would never work locally. The Next rewrite is hard-gated off under `NODE_ENV=production` so the dev shortcut can never proxy to `localhost` from a real deployment.

## Public env vars: `NEXT_PUBLIC_*` / `VITE_*` / `EXPO_PUBLIC_*`
Each frontend framework inlines a differently-prefixed subset of env vars into the shipped client bundle at **build time** — `VITE_*` (Vite), `NEXT_PUBLIC_*` (Next.js), `EXPO_PUBLIC_*` (Expo) — and **only** those prefixes. Two consequences, stated plainly in every consuming app's own `.env.example` (`templates/frontend/vite-spa/.env.example`, `templates/frontend/nextjs/.env.example`, `templates/frontend/nextjs-admin/.env.example`, `templates/mobile/expo/.env.example`):

- **These vars are PUBLIC, not secrets.** Anything with the framework's prefix ships inside the built bundle/binary to every visitor/device — a URL is fine (`VITE_API_BASE_URL`, `NEXT_PUBLIC_API_BASE_URL`, `EXPO_PUBLIC_API_BASE_URL`), an API key, token, or password is never fine.
- **An un-prefixed var silently doesn't exist client-side.** `@repo/api-client`'s mutator deliberately never reads a bare `process.env.API_BASE_URL` at module load — Vite ships no `process` global in the browser bundle at all (`ReferenceError`), and Next/Expo only statically inline the prefixed names, so a bare var read there resolves to `""` even when it's set in the shell/CI environment. Every consumer instead calls `configureApiClient({ baseUrl })` once at startup with the prefixed var read explicitly (see `references/wiring/api-client-generation.md`'s "The custom fetch mutator and `configureApiClient`").

Real secrets (`DATABASE_URL`, `JWT_SIGNING_KEY`, `SMTP_*`) never carry these prefixes and never reach a frontend bundle at all — they're backend-only, per `references/security/secrets-management.md` and `references/wiring/infra-app.md`'s `secret_store` section.

## The error envelope
Every non-2xx response from either backend framework carries the **same** shape — `ErrorEnvelope` (`templates/backend/fastapi/app/core/errors.py`, byte-identical on the wire from `templates/backend/django/core/contract/errors.py`):

```json
{ "error": { "code": "not_found", "message": "...", "details": null } }
```

`code` is a member of the **locked** `ErrorCode` enum — a closed, versioned set a client switches on, never on `message` (message is for humans and can reword without breaking a client):

| `code` | HTTP status | Raised by |
| --- | --- | --- |
| `internal_error` | 500 | `AppError`'s own default (an unhandled bug) |
| `unauthenticated` | 401 | `UnauthenticatedError` |
| `permission_denied` | 403 | `PermissionDeniedError` |
| `not_found` | 404 | `NotFoundError` |
| `validation_failed` | 422 | `ValidationFailedError` (and FastAPI's remapped `RequestValidationError` / DRF's remapped `ValidationError` — request-boundary and app-raised validation failures render identically) |
| `conflict` | 409 | `ConflictError` |
| `rate_limited` | 429 | `RateLimitedError` |

**This set is never extended casually.** `templates/backend/fastapi/app/core/errors.py`'s own docstring calls adding, renaming, or removing a member a contract change requiring the same coordination as any other wire-shape edit — regenerate `@repo/api-client` (`references/wiring/api-client-generation.md`) and keep Django's exception handler's code set aligned, since a generated client that exhaustively switches over the enum breaks on an unrecognized member.

`@repo/web-shared` (`templates/components/frontend/src/`) is the seam that turns this envelope into something a frontend actually uses:
- **`unwrap`** (`src/errors/unwrap.ts`) — orval's `fetch` mode resolves a documented non-2xx as a *fulfilled* promise (`{ data, status }`), which looks like success to react-query. Wrapping a generated call in `unwrap(await someHook())` makes a non-2xx **throw** an `ApiError` (carrying `status`, the parsed `ErrorCode`, and the raw envelope) instead, so react-query's error handling (and the 401 → refresh flow) actually fires.
- **`applyEnvelopeToForm`** (`src/forms/applyEnvelopeToForm.ts`) — maps a `validation_failed` envelope's `details[]` onto `react-hook-form` field errors (`setError` per `detail.field`, falling back to a form-level `root` error), so a 422 from the backend surfaces on the right input without hand-written mapping per form.

Both only ever switch on `code`; `errorCodeToMessage` (`src/errors/errorEnvelope.ts`) is the one place `ErrorCode -> user-facing string` is maintained, with a mandatory `default` branch for any code (or non-envelope 5xx/502/503) the frontend doesn't recognize.

## Pagination: `Page[T]`
Every paginated list endpoint returns the same envelope — `Page[T]` (`templates/backend/fastapi/app/core/db/schema.py`, mirrored by `templates/backend/django/core/contract/pagination.py`):

```json
{ "items": [...], "total": 0, "page": 1, "size": 20, "pages": 0 }
```

Request-side, `PageParams` accepts `page` (1-indexed, default 1) and `size` (default 20, max 200) as query params — `extra="forbid"`, so an unrecognized param (a stale `offset=`/`limit=` caller) is a hard 422 rather than silently ignored. A generated hook for a list endpoint types its response as `Page[<ItemOut>]`, so a frontend consuming it gets `items`/`total`/`page`/`size`/`pages` typed from the same OpenAPI schema the error envelope comes from — no hand-written pagination interface to keep in sync.

## Wiring checklist
1. **Pick the CORS posture** before writing any frontend env config — edge-routed same-origin (leave the base-URL var empty) unless there's a concrete reason for a separate API origin.
2. **Never put a secret in a `NEXT_PUBLIC_*`/`VITE_*`/`EXPO_PUBLIC_*` var** — grep for the prefix before adding a new env var to any frontend `.env.example`.
3. **Switch on `ErrorCode`, never on `message`**, in every error-handling branch a frontend writes; run 422s through `applyEnvelopeToForm`, everything else through `errorCodeToMessage`'s default-safe mapping.
4. **Treat `Page[T]`'s shape as fixed** — `items`/`total`/`page`/`size`/`pages`, `page` 1-indexed — rather than inventing a per-endpoint list shape.

## Related canon
- `references/wiring/auth-end-to-end.md` — the full CORS/cookie/CSRF posture this doc's CORS section summarizes.
- `references/wiring/api-client-generation.md` — how the generated client's types (including `ErrorEnvelope`/`Page[T]`) reach the frontend in the first place.
- `templates/components/frontend/README.md` — `@repo/web-shared`'s full composition contract (`unwrap`, `applyEnvelopeToForm`, `AuthProvider`).
- `templates/components/security/cors-lockdown/README.md` — the explicit-allowlist CORS policy component.
- `references/security/secrets-management.md` — the local/CI/prod secrets posture the public-env split sits alongside.
- `references/frontend/typescript.md` — "Types from a single source of truth."
