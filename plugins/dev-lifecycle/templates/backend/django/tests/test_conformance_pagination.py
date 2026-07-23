"""Conformance-proof tests for `core.pagination.ContractPageNumberPagination`
— Stage 4 Step 2 (#27). Creates N items, asserts `GET /items`'s JSON body
equals `{items, total, page, size, pages}` and cross-checks it against
`core.contract.pagination.Page.create(...)` built directly from the same
data — the vendored contract source's own page-count math, not a
re-implementation of it."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from core.contract.pagination import Page, PageParams
from core.models import Item
from core.serializers import ItemOutSerializer

pytestmark = pytest.mark.django_db


def _make_items(n: int) -> list[Item]:
    return [Item.objects.create(name=f"Item {i}") for i in range(n)]


def test_default_page_matches_contract_page_shape(api_client: APIClient) -> None:
    items = _make_items(5)

    response = api_client.get("/items")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"items", "total", "page", "size", "pages"}

    expected_out = [ItemOutSerializer(obj).data for obj in sorted(items, key=lambda i: i.id.hex)]
    expected = Page.create(expected_out, total=5, params=PageParams(page=1, size=20)).model_dump(mode="json")

    # Compare everything except item order (the DRF queryset and the
    # expected list above aren't guaranteed the same ordering) — total/
    # page/size/pages must match exactly, and the item *set* must match.
    assert body["total"] == expected["total"] == 5
    assert body["page"] == expected["page"] == 1
    assert body["size"] == expected["size"] == 20
    assert body["pages"] == expected["pages"] == 1
    assert {item["id"] for item in body["items"]} == {item["id"] for item in expected_out}


def test_page_and_size_query_params_and_pages_math(api_client: APIClient) -> None:
    _make_items(25)

    response = api_client.get("/items", {"page": 2, "size": 10})

    assert response.status_code == 200
    body = response.json()

    params = PageParams(page=2, size=10)
    expected_shape = Page.create([], total=25, params=params).model_dump(mode="json")

    assert body["total"] == 25
    assert body["page"] == 2 == expected_shape["page"]
    assert body["size"] == 10 == expected_shape["size"]
    # ceil(25 / 10) == 3, per Page.create's own page-count math.
    assert body["pages"] == 3 == expected_shape["pages"]
    assert len(body["items"]) == 10


def test_empty_list_matches_contract_page_zero_pages(api_client: APIClient) -> None:
    response = api_client.get("/items")

    assert response.status_code == 200
    body = response.json()

    expected = Page.create([], total=0, params=PageParams()).model_dump(mode="json")
    assert body == expected


def test_max_page_size_is_capped_at_200(api_client: APIClient) -> None:
    _make_items(3)

    response = api_client.get("/items", {"size": 500})

    assert response.status_code == 200
    # ACCEPTED DIVERGENCE (see core/pagination.py's own docstring):
    # PageParams(size=500) would be a hard 422 on FastAPI (`le=200`); DRF's
    # PageNumberPagination instead silently clamps to max_page_size.
    assert response.json()["size"] == 200
