"""Test-only root URLconf — mirrors what a real scaffolded project's
`config/urls.py` does per this block's README ("Wiring into apps/api"):
wires BOTH `core.urls` (the existing JSON API, unchanged) and
`webapp.urls` (this block's server-rendered routes) into one URLconf, so
this block's own standalone test run exercises the exact route
composition a real project ends up with — including proving the two
don't collide (see `webapp/urls.py`'s own "Judgment call" docstring on
why the item-browsing page is `/browse/items`, not `/items`)."""

from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    path("", include("webapp.urls")),
    path("", include("core.urls")),
]

__all__ = ["urlpatterns"]
