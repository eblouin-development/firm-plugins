"""`webapp`'s URLconf — included from `config.urls` alongside the existing
`core.urls` include (see the block README's "Wiring into apps/api"
section for the exact line to add). Uses Django's own `<uuid:...>` path
converter (unlike `core/urls.py`'s deliberate `<str:...>` choice for
JSON-`ErrorEnvelope` consistency on malformed ids — see that file's own
comment) since an HTML route has no JSON envelope to keep consistent; a
malformed id 404s at the routing layer itself, which is the right shape
for a page route.

**Judgment call: the item-browsing page lives at `/browse/items`, NOT
`/items`.** `core/urls.py` (backend/django, unchanged, read-only) already
binds `GET /items` / `POST /items` to `ItemViewSet` — the JSON API. This
block's routes are additive, never a replacement for the JSON surface
(see the block README's "Placement & composition rule"), so the
server-rendered item list needed its own, non-colliding path rather than
literally `/items` — see the README's "Judgment calls" section for the
full rationale."""

from __future__ import annotations

from django.urls import path

from webapp import views

urlpatterns = [
    path("", views.home, name="webapp-home"),
    path("login", views.login_view, name="webapp-login"),
    path("logout", views.logout_view, name="webapp-logout"),
    path("browse/items", views.items_list, name="webapp-items"),
    path("browse/items/create", views.item_create, name="webapp-item-create"),
    path("browse/items/<uuid:item_id>/delete", views.item_delete, name="webapp-item-delete"),
]

__all__ = ["urlpatterns"]
