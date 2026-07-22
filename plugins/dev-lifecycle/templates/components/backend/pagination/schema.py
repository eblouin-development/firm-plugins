"""Framework-neutral pagination shapes: request-side page parameters and a
generic response envelope. Pydantic v2 only (pinned per
references/compatibility-matrix.md's Backend — Python row to Pydantic v2,
2.13.x) — NO SQLAlchemy import in this file. This is one of the two THE-
CONTRACT shapes (alongside error-envelope/errors.py) that Stage 4's Django
track reimplements against, not just Stage 3's FastAPI: a DRF view returns
the same `{items, total, page, size, pages}` shape from its own pagination
class, even though it never imports this file directly.

Drop-in: copy this file into app/core/pagination/schema.py (or alongside
query.py at app/core/db/pagination/schema.py — either placement works, this
file has no directory-relative imports of its own). The SQLAlchemy-specific
half of pagination lives in this same component's query.py; keep both
together when copying into a SQLAlchemy-backed (Stage 3) project. A Django
project (Stage 4) copies schema.py alone.
"""

from __future__ import annotations

from typing import Generic, Sequence, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PageParams(BaseModel):
    """Request-side pagination parameters: page/size, 1-indexed. `extra="forbid"`
    so an unrecognized query param (a typo, or an old `offset=`/`limit=`
    caller that hasn't migrated) is a hard 422 instead of being silently
    ignored."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1, description="1-indexed page number.")
    size: int = Field(default=20, ge=1, le=200, description="Items per page (max 200).")

    @property
    def offset(self) -> int:
        """The 0-indexed row offset this page starts at — `(page - 1) *
        size`, computed once here so every consumer (the SQLAlchemy half
        in query.py, a Django queryset slice) uses the identical formula
        rather than each re-deriving it."""
        return (self.page - 1) * self.size


class Page(BaseModel, Generic[T]):
    """THE generic response envelope for every paginated list endpoint in
    this app: `{items, total, page, size, pages}`. Pydantic v2 generic
    (`Page[WidgetOut]`, `Page[int]`, ...) — FastAPI resolves the concrete
    schema per route from the type parameter, same as any other Pydantic
    generic response model.

    `model_config = ConfigDict(arbitrary_types_allowed=True)` deliberately:
    `Page[T]` is used in two distinct places with two distinct `T` shapes —
    at the API boundary `T` is always a serializable Pydantic schema (the
    common case, no `arbitrary_types_allowed` even needed there), but
    `repository/`'s `AsyncRepository.list()` also returns a `Page[ModelT]`
    where `ModelT` is a raw SQLAlchemy ORM instance (not yet mapped to an
    output schema) — internal plumbing between the repository and the
    route handler that maps ORM rows to a response schema before they ever
    reach a client. `arbitrary_types_allowed=True` is what lets `Page`
    hold either shape without two separate envelope classes."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    size: int = Field(ge=1)
    pages: int = Field(ge=0)

    @classmethod
    def create(cls, items: Sequence[T], *, total: int, params: PageParams) -> "Page[T]":
        """The one place page-count math happens — `ceil(total / size)`,
        computed without importing `math.ceil` (integer ceiling division:
        `-(-total // size)`), floored at 0 for an empty result set. Every
        producer of a `Page` (query.py's `paginate_select`, a Django DRF
        paginator reimplementing this shape) should go through this
        constructor rather than hand-computing `pages` inline."""
        pages = -(-total // params.size) if total else 0
        return cls(items=list(items), total=total, page=params.page, size=params.size, pages=pages)
