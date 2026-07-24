"""Request/response schemas for `Item` — strict Pydantic v2, kept separate
from app/models/item.py's SQLAlchemy model per references/backend/
pydantic.md's "Schema design" (never reuse an ORM model as a request/
response body).

Stage 3 Step 3b (#26): built on `input_validation.StrictModel`
(vendored, app/core/security/input_validation/validation.py) rather than
`BaseModel` + a hand-rolled `ConfigDict(extra="forbid")` — `StrictModel`
already gives everything the earlier ad hoc config gave (`extra="forbid"`)
plus `str_strip_whitespace`/`validate_assignment`/`strict=True` for free,
matching this catalog's reject-don't-drop posture in `error-envelope/` and
`pagination/schema.py` more completely than the field-by-field config did.
`name`/`description` stay plain `str` fields with `Field(min_length=...,
max_length=...)` rather than adopting `input_validation`'s `SafeText`/
`ShortStr` `Annotated` types: those add a `no_control_chars` check this
free-text "widget name" exemplar field has no documented need for yet (a
real project's own free-text fields — descriptions, comments — are exactly
where `SafeText` belongs; swap it in here once a concrete need, not this
generic exemplar, calls for it — see input-validation/README.md's own
field-type table for which shape fits which use). Pydantic v2 merges
`model_config` across the MRO (child keys override, everything else is
inherited from `StrictModel`), so `ItemOut` below only needs to add
`from_attributes=True` on top, not repeat `extra="forbid"` etc."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import ConfigDict, Field

from app.core.security.input_validation import StrictModel


class ItemBase(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ItemCreate(ItemBase):
    """The create-body schema — everything `ItemBase` declares, required as
    specified there (`name` required, `description` optional)."""


class ItemUpdate(StrictModel):
    """The update-body schema — every field optional, so a client can PATCH
    a subset. The route maps only explicitly-set fields
    (`model_dump(exclude_unset=True)`) onto the existing row.

    `name` is NOT NULL at the DB level (`app/models/item.py`'s
    `Item.name`) — unlike `description` (nullable), an explicit
    `{"name": null}` must never reach `update_item`'s
    `model_dump(exclude_unset=True)` as a "set the column to NULL"
    instruction (that 500s on the NOT NULL constraint; issue #41). `name`
    is deliberately typed plain `str` — NOT `str | None` — with a `None`
    *default* standing in as the "omitted" sentinel: `StrictModel`'s
    `strict=True` (`app/core/security/input_validation/validation.py`)
    means Pydantic only ever *coerces/checks* a value against `str` when
    the field is actually supplied, never against an unvalidated default,
    so `{}` (name omitted) still leaves `name=None` internally with
    `"name" not in model_fields_set` — exactly what lets `update_item`'s
    `model_dump(exclude_unset=True)` keep treating an omitted `name` as
    "leave the column alone", the same partial-update contract as before.
    An explicitly supplied `{"name": null}`, though, now hits real `str`
    type validation and is rejected by Pydantic itself as a plain
    `string_type` error — a 422 `validation_failed` envelope, same as any
    other malformed field — with NO extra `model_validator` needed. This
    also fixes the OTHER half of #41: since the field's declared type is
    now plain `str` (not `str | None`), the generated OpenAPI schema for
    `name` is `{"type": "string", ...}` with no `anyOf`-`null` branch,
    so the contract itself no longer claims a `null` `name` is valid —
    unlike `app/schemas/blog.py`'s `BlogPostUpdate`, which behaviorally
    rejects an explicit `null` via a `model_validator` (`_reject_explicit_
    null`) but still leaves its own OpenAPI schema nullable; this sentinel
    approach was chosen here specifically because the frozen contract
    (`packages/api-client/openapi.json`) is what #41 flagged as wrong, not
    only the runtime 500. (Previously a documented, NOT mirrored,
    divergence from the Django track — see `tests/
    test_schema_conformance.py`'s `_KNOWN_DIVERGENCES` — now removed since
    the two tracks match again.)"""

    name: str = Field(default=None, min_length=1, max_length=200)  # type: ignore[assignment]
    description: str | None = Field(default=None, max_length=2000)


class ItemOut(ItemBase):
    """The read schema — adds the DB-generated fields (`id`, timestamps).
    `from_attributes=True` is what lets `ItemOut.model_validate(orm_obj)`
    read straight off the SQLAlchemy instance's attributes (see
    references/backend/pydantic.md's v2 config note). `StrictModel`'s
    `strict=True` is compatible with `from_attributes` reading real
    `uuid.UUID`/`datetime` Python objects straight off the ORM instance —
    strict mode restricts silent type COERCION (a JSON string for a `UUID`
    field), not an already-correctly-typed native Python attribute, so
    this doesn't need to (and doesn't) opt back out of strict mode."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
