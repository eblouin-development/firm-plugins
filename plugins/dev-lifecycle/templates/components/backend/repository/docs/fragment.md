<!-- fragment: block:components/backend/repository -->

## Setup
Copy `repository.py` into `app/core/db/repository.py`, alongside
`mixins.py`, `session.py`, and pagination/'s `query.py` + `schema.py` —
all five files live together in `app/core/db/` since `repository.py`
imports the pagination pair as flat sibling modules. Construct per
request: `AsyncRepository(db_session, Widget)` where `db_session` comes
from `Depends(get_db)`.

## Maintenance
SQLAlchemy-specific — not reused by the Django track (Stage 4). Never
commits; the session-per-request dependency (`db-session/`'s `get_db()`)
owns the commit/rollback boundary.
