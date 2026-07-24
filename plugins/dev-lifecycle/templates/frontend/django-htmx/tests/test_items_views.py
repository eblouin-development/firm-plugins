"""Items-demo-surface tests — the `HX-Request`-detected fragment/full-page
branch, `hx-post` item creation returning a row fragment, form-validation
re-render, and the login-required gate on create/delete."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db(transaction=True)


def _login(client, user_credentials) -> str:
    """Logs in and returns the csrf_token cookie value the caller needs
    for a subsequent mutating request."""
    response = client.post(
        "/login", {"email": user_credentials["email"], "password": user_credentials["password"]}
    )
    assert response.status_code == 302
    return client.cookies["csrf_token"].value


def test_plain_get_returns_full_page(client):
    from core.models import Item

    Item.objects.create(name="Widget")

    response = client.get("/browse/items")

    assert response.status_code == 200
    body = response.content.decode()
    assert "<html" in body
    assert "<nav" in body
    assert "Widget" in body


def test_hx_request_returns_only_the_fragment(client):
    from core.models import Item

    Item.objects.create(name="Widget")

    response = client.get("/browse/items", HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    body = response.content.decode()
    assert "<html" not in body
    assert "<nav" not in body
    assert "Widget" in body


def test_search_filters_by_name(client):
    from core.models import Item

    Item.objects.create(name="Alpha widget")
    Item.objects.create(name="Beta gadget")

    response = client.get("/browse/items", {"q": "widget"}, HTTP_HX_REQUEST="true")

    body = response.content.decode()
    assert "Alpha widget" in body
    assert "Beta gadget" not in body


def test_anonymous_visitor_does_not_see_create_form(client):
    response = client.get("/browse/items")
    assert "item-create-form" not in response.content.decode()


def test_item_create_via_hx_post_returns_new_row_fragment(client, verified_user, user_credentials):
    from core.models import Item

    csrf_value = _login(client, user_credentials)

    response = client.post(
        "/browse/items/create",
        {"name": "New Item", "description": "A description", "csrf_token": csrf_value},
        HTTP_HX_REQUEST="true",
        HTTP_X_CSRF_TOKEN=csrf_value,
    )

    assert response.status_code == 200
    body = response.content.decode()
    assert "New Item" in body
    assert "<html" not in body
    assert "<nav" not in body
    assert Item.objects.filter(name="New Item").exists()


def test_item_create_missing_csrf_is_forbidden(client, verified_user, user_credentials):
    _login(client, user_credentials)

    response = client.post("/browse/items/create", {"name": "Nope"})

    assert response.status_code == 403


def test_item_create_validation_failure_rerenders_form_with_errors(client, verified_user, user_credentials):
    from core.models import Item

    csrf_value = _login(client, user_credentials)

    response = client.post(
        "/browse/items/create",
        {"name": "", "csrf_token": csrf_value},
        HTTP_X_CSRF_TOKEN=csrf_value,
    )

    assert response.status_code == 400
    assert "This field is required." in response.content.decode()
    assert response["HX-Retarget"] == "#item-create-form"
    assert not Item.objects.filter(name="").exists()


def test_item_create_requires_login(client):
    response = client.post("/browse/items/create", {"name": "Nope"})
    assert response.status_code == 302
    assert response.url.startswith("/login?next=")


def test_item_delete_soft_deletes_and_removes_row(client, verified_user, user_credentials):
    from core.models import Item

    item = Item.objects.create(name="Doomed")
    csrf_value = _login(client, user_credentials)

    response = client.post(
        f"/browse/items/{item.id}/delete",
        {"csrf_token": csrf_value},
        HTTP_X_CSRF_TOKEN=csrf_value,
    )

    assert response.status_code == 200
    assert response.content == b""
    assert not Item.objects.filter(id=item.id).exists()  # soft-delete-scoped manager
    assert Item.all_objects.get(id=item.id).is_deleted


def test_item_delete_requires_login(client):
    from core.models import Item

    item = Item.objects.create(name="Protected")

    response = client.post(f"/browse/items/{item.id}/delete", {})

    assert response.status_code == 302
    assert Item.objects.filter(id=item.id).exists()
