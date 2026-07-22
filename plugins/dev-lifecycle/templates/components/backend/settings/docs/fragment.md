<!-- fragment: block:components/backend/settings -->

## Setup
Copy `settings.py` into `app/core/settings.py`. Subclass `AppSettings`
with the project's own fields; instantiate once at startup (e.g. a
`@lru_cache`d `get_settings()` dependency) and feed `settings.database_url`
into `db-session/`'s `configure_engine()`. Compose `secret_store.get_secret`
for a field that needs its layered env-then-AWS-Secrets-Manager
resolution — see the component README's "Composition point."

## Secrets
| `DATABASE_URL` | settings | Required, no default. The connection string `db-session/`'s `configure_engine()` consumes. |

## Maintenance
Framework-neutral — no FastAPI import. `extra="forbid"` catches a stray or
typo'd `.env` key at startup rather than silently ignoring it.
