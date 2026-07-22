<!--
block: components/backend/pagination  # catalog component
needs:
  - pydantic v2 (2.13.x): schema.py's sole dependency, pinned per references/compatibility-matrix.md's Backend — Python row
  - SQLAlchemy 2.0.x (async extras): query.py's additional dependency — only needed by the SQLAlchemy half, not by schema.py
exposes:
  - PageParams — request-side page/size params (schema.py, neutral)
  - Page[T] — the generic {items, total, page, size, pages} response envelope (schema.py, neutral)
  - paginate_select(session, stmt, params) -> Page[Any] — applies limit/offset to a select() and fills a Page (query.py, SQLAlchemy-specific)
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-22
provenance: manual
-->

# pagination

Two files, deliberately split by reusability, living in one directory:
`schema.py` (framework-neutral, Pydantic v2 only — THE pagination contract
Stage 4's Django track reimplements against) and `query.py` (the
SQLAlchemy-specific half that applies it to a `select()`). Lives at
`templates/components/backend/pagination/` in this repo; Stage 3 backend
blocks copy both files into `app/core/db/pagination/`. A Django project
(Stage 4) copies `schema.py` alone.

This is a **catalog component** (`template-author`'s partial-contract
kind), not an app-layer template block. It's the SQLAlchemy half's
counterpart 4 and the neutral half's counterpart 6 of Stage 3's backend
catalog — one directory, two files, kept **file-distinct** by reusability
rather than split into two directories, since they're always installed
together on the SQLAlchemy side and the neutral file is trivially
copy-alone for a Django project.

## Contents
- Composition contract
- schema.py: the neutral contract (THE shape)
- query.py: applying it to a select()
- Why two round trips, not a window function
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **`schema.py`**: Pydantic v2, 2.13.x — its only dependency. **No
  SQLAlchemy import anywhere in this file** — that's the point; Stage 4's
  Django track reuses exactly this file.
- **`query.py`**: SQLAlchemy 2.0.x with the `asyncio` extra, in addition
  to Pydantic (it imports `Page`/`PageParams` from the sibling
  `schema.py`). SQLAlchemy-specific — a Django/DRF pagination class
  reimplements the `Page`/`PageParams` *shape* against a Django
  `QuerySet`, it does not import this file.

**EXPOSES**
- `PageParams` — `page` (1-indexed, `ge=1`), `size` (`ge=1, le=200`), an
  `.offset` property (`(page - 1) * size`, the one place that formula is
  computed), `extra="forbid"`.
- `Page[T]` — the generic response envelope: `items: list[T]`, `total`,
  `page`, `size`, `pages`. `Page.create(items, *, total, params)` is the
  one constructor every producer of a `Page` should go through — see
  "schema.py: the neutral contract" below for the exact shape quoted.
- `paginate_select(session, stmt, params) -> Page[Any]` — runs `stmt`
  through the `COUNT(*)` + `LIMIT`/`OFFSET` two-query pattern (see "Why two
  round trips") and returns a filled `Page`.
- Its co-located doc fragment: `docs/fragment.md`.

`repository/`'s `AsyncRepository.list()` calls `paginate_select()`
directly (`from query import paginate_select`) — see that component's
README for how the two compose.

## schema.py: the neutral contract (THE shape)

This is the pagination envelope every list endpoint in the app returns,
and the shape Stage 4's Django/DRF track reimplements against even though
it never imports this file:

```python
class PageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=200)

class Page(BaseModel, Generic[T]):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    items: list[T]
    total: int
    page: int
    size: int
    pages: int
```

Serialized: `{"items": [...], "total": 137, "page": 2, "size": 20, "pages": 7}`.
1-indexed `page`, `size` capped at 200 server-side (a client asking for
`size=100000` gets a 422, not an accidental unbounded query — per
`references/backend/fastapi.md`'s "Pagination, filtering, versioning": "don't
return unbounded collections"). `pages` is always present, computed by
`Page.create()` (`ceil(total / size)`, floored at 0 for an empty result),
so no consumer re-derives it inconsistently.

`arbitrary_types_allowed=True` on `Page` is deliberate: at the API
boundary `T` is a serializable Pydantic schema (the common, fully-typed
case), but `repository/`'s internal plumbing also returns a `Page` holding
raw SQLAlchemy ORM instances before a route handler maps them to an output
schema — see the class docstring in `schema.py` for the full rationale.

## query.py: applying it to a select()

```python
async def paginate_select(session: AsyncSession, stmt: Select[Any], params: PageParams) -> Page[Any]:
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()
    paged_stmt = stmt.limit(params.size).offset(params.offset)
    items = (await session.execute(paged_stmt)).scalars().all()
    return Page.create(items, total=total, params=params)
```

Pass in a `select()` with whatever `WHERE`/`JOIN`/`ORDER BY` the endpoint
needs already applied — `paginate_select` adds only `LIMIT`/`OFFSET` (to
the page-of-rows query) and wraps the whole statement in `COUNT(*)` (for
the total), so a filtered list's `total` reflects the filter, not the
unfiltered table.

## Why two round trips, not a window function

A single query *can* return both a windowed page and an unwindowed total
in one round trip using `COUNT(*) OVER()` — but that's PostgreSQL-specific
syntax with patchy-to-absent sqlite support, and sqlite is this catalog's
hermetic-test target (see `db-mixins/README.md`'s UUID-type rationale for
the same dual-dialect concern). `paginate_select` deliberately runs two
queries — one `COUNT(*)`, one `LIMIT`/`OFFSET` — so it works identically
on both dialects with no per-backend branch. A project on PostgreSQL only,
at a scale where the extra round trip is a measured cost, can swap in the
window-function version; that's a project-level optimization, not this
component's default.

## Testing

`tests/test_schema.py` (Pydantic only, no SQLAlchemy) covers: `PageParams`
defaults and its `.offset` math across several page/size combinations,
`page`/`size` bounds rejection (`page <= 0`, `size` out of `[1, 200]`),
`extra="forbid"` rejecting an unknown field, `Page.create()`'s pagination
math (evenly-divisible totals, a remainder, an empty result set, a
single-item result), `Page[T]` working with a plain type, a Pydantic
model, and an arbitrary non-Pydantic object (`arbitrary_types_allowed`),
and the envelope's serialized key set.

`tests/test_query.py` (SQLAlchemy, aiosqlite in-memory) covers:
`paginate_select` returning the correct items/total/pages for a first,
middle, and last (partial) page; a page requested past the end returning
empty `items` with `total` still correct; a size that evenly divides the
total; `total` reflecting a `WHERE` filter already on the passed-in
`stmt` (not the whole table); and an empty table.

Run (neutral half only): `uv run --python 3.13 --with 'pydantic==2.13.*' --with pytest -- pytest templates/components/backend/pagination/tests/test_schema.py -q`
Run (both halves together — `query.py` imports `schema.py`): `uv run --python 3.13 --with 'sqlalchemy[asyncio]==2.0.*' --with aiosqlite --with pytest --with pytest-asyncio --with 'pydantic==2.13.*' -- pytest templates/components/backend/pagination/tests/ -q`

## Judgment calls

- **One directory, two files, not two directories.** The task split
  pagination into a "SQLAlchemy half" and a "neutral half" by
  *reusability*, not by *deployment unit* — on the SQLAlchemy side the two
  files are always installed together (`query.py` hard-imports `schema.py`
  as a sibling), so a second directory would only add a path to keep in
  sync for zero isolation benefit. A Django project copies `schema.py`
  alone and never touches `query.py` — file-level, not directory-level,
  is where the reusability boundary actually lives.
- **`Page.create()` is the only sanctioned constructor for a real `Page`,
  not documented as a strict runtime requirement.** Nothing stops a
  caller from constructing `Page(...)` directly with a hand-computed
  `pages` value — Pydantic has no mechanism to forbid that without a
  private-constructor pattern this component doesn't adopt (it would
  complicate the common, harmless case of building a `Page` in a test
  fixture). Documented convention, not an enforced one.
- **`paginate_select` always issues two queries, never `COUNT(*) OVER()`.**
  See "Why two round trips" — a deliberate portability choice (sqlite +
  PostgreSQL) over a PostgreSQL-only optimization.
