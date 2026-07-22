<!--
block: components/backend/settings  # catalog component
needs:
  - pydantic v2 (2.13.x) + pydantic-settings (2.14.x): the runtime dependencies, pinned per references/compatibility-matrix.md's Backend — Python row
  - process env / .env (optional): pydantic-settings' own loader — DATABASE_URL required, no default
  - secret_store.get_secret (optional composition, not imported by this file): a subclass wires a field's default to it — see "Composition point"
exposes:
  - AppSettings — the pydantic-settings BaseSettings subclass every project's own Settings extends
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-22
provenance: manual
-->

# settings

A framework-neutral, drop-in `settings.py`: a `pydantic-settings`
`BaseSettings` base with env/`.env` loading, `extra="forbid"` fail-fast
posture, and a documented — not hard-wired — composition point for
`secret_store.get_secret` (see
`templates/components/security/secrets-loading/`). Lives at
`templates/components/backend/settings/` in this repo; Stage 3 backend
blocks copy `settings.py` verbatim into `app/core/settings.py`. Canon:
`references/backend/pydantic.md`'s "Settings & secrets" section.

This is a **catalog component** (`template-author`'s partial-contract
kind), not an app-layer template block. Framework-neutral — no FastAPI
import; usable from a Django project too (independent of Django's own
`settings.py` module).

## Contents
- Composition contract
- Fields and defaults
- Composition point: secret_store.get_secret
- extra="forbid" is safe here
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **Pydantic v2, 2.13.x, and `pydantic-settings`, 2.14.x** — both pinned
  per `references/compatibility-matrix.md`'s Backend — Python row (added
  by this build; see that matrix's own changelog note).
- **Process env / `.env` (optional)** — `pydantic-settings`' own loader,
  not bespoke code in this module (matches
  `secrets-loading/README.md`'s "Why no `.env` parsing" rationale — one
  `.env` loader per project, this component doesn't add a second).
  `DATABASE_URL` is required with no default; every other field has a
  sensible default.
- **`secret_store.get_secret` (optional, not imported here)** — a
  consuming project composes it explicitly in a subclass; see below.

**EXPOSES**
- `AppSettings` — the `BaseSettings` subclass a project's real `Settings`
  extends, adding its own fields.
- Its co-located doc fragment: `docs/fragment.md`.

## Fields and defaults

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `environment` | `Literal["development","test","staging","production"]` | `"development"` | |
| `debug` | `bool` | `False` | |
| `database_url` | `str` | *(required)* | No default — missing/unset fails `AppSettings()` construction at startup, not on the first request that touches the database. |
| `cors_allowed_origins` | `list[str]` | `[]` | Per `references/security/secure-baseline.md`'s CORS lockdown — an explicit per-environment allowlist, never `*` combined with credentials. |

`env_file=".env"` is the default `model_config`; a project overrides it
(or passes `_env_file=` at construction, as this component's own tests
do) if it needs a different path.

## Composition point: secret_store.get_secret

`settings.py` **does not import** `secret_store`
(`templates/components/security/secrets-loading/secret_store.py`)
directly — that would hard-couple every project using this settings base
to that specific component, even one that never installs it.
`pydantic-settings`' own env-file loading already covers the common case
(a field with no default reads its env var straight from the process env
or `.env`). Reach for `secret_store`'s composition only when a field needs
its *layered* env-then-AWS-Secrets-Manager resolution, which plain
`pydantic-settings` doesn't provide:

```python
from secret_store import get_secret  # app.core.security.secret_store, once copied in

class Settings(AppSettings):
    secret_key: str = Field(default_factory=lambda: get_secret("SECRET_KEY"))
```

`default_factory` (not a plain default) is what makes the composition
lazy — `get_secret()` runs at `Settings()` construction time, not at class
definition/import time, so the same fail-fast-at-startup behavior
`secret_store.validate_required()` provides applies here too: a missing
secret raises before the app starts serving traffic.

## extra="forbid" is safe here

`AppSettings.model_config` sets `extra="forbid"` — the same reject-don't-
drop posture as `input-validation`'s `StrictModel`, applied to
configuration instead of request bodies. This is safe specifically for
`pydantic-settings`: its `EnvSettingsSource` only maps process-env keys
that match a **declared field name** (respecting `env_prefix`/
`case_sensitive`) into the settings object — it does not vacuum up every
unrelated system env var (`PATH`, `HOME`, a CI runner's own variables) as
an "extra" field. So `extra="forbid"` catches a genuine misconfiguration
(a typo'd key in `.env`, a field renamed in code but not in the deployed
environment, an explicit unexpected keyword argument) without ever
tripping on the ordinary noise of a real process environment.

## Testing

`tests/test_settings.py` covers: loading a required field from the
process env, the missing-required-field `ValidationError`, default values
for every optional field, an env var overriding a default, rejection of
an invalid `Literal["environment"]` value, case-insensitive env var name
matching, `extra="forbid"` rejecting an unknown field passed directly
while an unrelated system env var does NOT trip it, `.env` file loading
via a temp file, process env taking priority over a `.env` file value,
and — the required secret-composition coverage — a subclass wiring
`secret_store.get_secret` into a field's `default_factory` resolving
correctly end to end (with the real `secret_store` module imported from
its sibling `security/secrets-loading/` component), that same composition
propagating `secret_store`'s own fail-fast error when the secret is
genuinely missing, and confirming `settings.py` itself never imports
`secret_store` (the composition is opt-in per-subclass, not baked in).

Run: `uv run --python 3.13 --with 'pydantic==2.13.*' --with 'pydantic-settings==2.14.*' --with pytest -- pytest templates/components/backend/settings/tests/ -q`

## Judgment calls

- **`extra="forbid"` on a settings class, not the more common
  `extra="ignore"`.** Verified specifically against `pydantic-settings`'
  documented env-source behavior (declared-field-only mapping, not a
  blanket environ dump) before choosing this — the usual worry with
  `extra="forbid"` on settings (a real process environment has hundreds of
  unrelated variables) doesn't apply to `pydantic-settings` the way it
  would to, say, constructing a plain `BaseModel` from `os.environ` by
  hand. Chosen for the same fail-fast-on-misconfiguration reasoning as
  `StrictModel` and `secret_store.validate_required()` elsewhere in this
  catalog.
- **`database_url` has no default; nothing else is required.** Matches
  this kit's stance that a missing DB connection is always a hard startup
  failure, while `environment`/`debug`/`cors_allowed_origins` have
  reasonable safe-by-default values a project can override per
  environment via its own `.env`/deployment config.
- **The `secret_store` composition test imports the real sibling
  component (via `sys.path`), not a stub.** The task explicitly calls out
  secrets-loading as "for the pydantic-settings composition point," so
  this component's test suite exercises the actual composition rather
  than asserting only that a `default_factory` callable is invoked.
