"""Custom DRF pagination class — Stage 4 Step 2 (#27) — emitting
`core.contract.pagination.Page`'s `{items, total, page, size, pages}` shape
over HTTP. DRF's own `PageNumberPagination` default emits `{count, next,
previous, results}`; wiring THIS class as `DEFAULT_PAGINATION_CLASS`
(config/settings.py) is what makes `GET /items` wire-identical to
backend/fastapi's `Page[ItemOut]` response (app/api/routers/items.py's
`list_items` + app/core/db/schema.py's `Page.create`, the same
`Page.create` classmethod this class calls — `core/contract/pagination.py`
is the byte-copy vendored for exactly this reuse)."""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from core.contract.pagination import Page, PageParams


class ContractPageNumberPagination(PageNumberPagination):
    """`page`/`size` query params (1-indexed page, `size` capped at
    `max_page_size`) — matches `core.contract.pagination.PageParams`'s own
    field names/bounds (`page: int = Field(ge=1)`, `size: int = Field(ge=1,
    le=200)`) field-for-field.

    ACCEPTED DIVERGENCE (documented per this step's own instructions, not
    forced): `PageParams.model_config = ConfigDict(extra="forbid")` means
    an unrecognized query param on the FastAPI block is a hard 422 (e.g. an
    old, unmigrated caller still sending `?offset=5&limit=20`). DRF's
    pagination classes have no equivalent "reject unknown query param"
    hook without a custom view-level allowlist this class does not add —
    an unknown param here is silently ignored, the same as every other DRF
    endpoint's normal query-param handling. Enforcing a closed query-param
    surface project-wide (a drf-spectacular schema validation step, a
    request-level middleware) is a bigger, separate decision than this one
    pagination class should make unilaterally — see this block's README,
    "Conformance"."""

    page_query_param = "page"
    page_size_query_param = "size"
    page_size = 20
    max_page_size = 200

    def get_paginated_response(self, data):
        params = PageParams(page=self.page.number, size=self.page.paginator.per_page)
        page = Page.create(list(data), total=self.page.paginator.count, params=params)
        return Response(page.model_dump(mode="json"))
