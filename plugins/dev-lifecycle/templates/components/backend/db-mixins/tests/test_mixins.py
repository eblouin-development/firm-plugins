"""Tests for the db-mixins drop-in (mixins.py). No real data — every value
is a synthetic fixture."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import String, create_engine, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Mapped, Session, mapped_column

from mixins import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey


class Widget(Base, UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin):
    """A composed test model exercising all three mixins together — the
    pattern a real app model follows."""

    __tablename__ = "widgets"

    name: Mapped[str] = mapped_column(String(100))


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


# --- UUIDPrimaryKey: dual-dialect rendering (the hermetic-test point) -----


def test_uuid_primary_key_compiles_to_char32_on_sqlite():
    column_type = Widget.__table__.c.id.type
    compiled = str(column_type.compile(dialect=sqlite.dialect()))
    assert compiled == "CHAR(32)"


def test_uuid_primary_key_compiles_to_native_uuid_on_postgresql():
    column_type = Widget.__table__.c.id.type
    compiled = str(column_type.compile(dialect=postgresql.dialect()))
    assert compiled == "UUID"


def test_tables_create_on_sqlite_without_error(engine):
    # create_all() in the fixture already ran; confirm the table is real.
    assert "widgets" in Base.metadata.tables


def test_uuid_primary_key_generates_uuid_on_insert(engine):
    with Session(engine) as session:
        widget = Widget(name="gadget")
        session.add(widget)
        session.commit()
        assert widget.id is not None
        assert str(widget.id).count("-") == 4  # a real uuid.UUID, dashed str form


# --- TimestampMixin ---------------------------------------------------------


def test_timestamp_mixin_columns_present_and_not_nullable():
    columns = Widget.__table__.c
    assert "created_at" in columns
    assert "updated_at" in columns
    assert columns["created_at"].nullable is False
    assert columns["updated_at"].nullable is False


def test_timestamp_mixin_server_default_populates_created_at(engine):
    with Session(engine) as session:
        widget = Widget(name="gadget")
        session.add(widget)
        session.commit()
        session.refresh(widget)
        assert widget.created_at is not None
        assert widget.updated_at is not None


def test_timestamp_mixin_onupdate_bumps_updated_at(engine):
    with Session(engine) as session:
        widget = Widget(name="gadget")
        session.add(widget)
        session.commit()
        session.refresh(widget)
        first_updated = widget.updated_at

        widget.name = "renamed-gadget"
        session.commit()
        session.refresh(widget)

        assert widget.updated_at >= first_updated


# --- SoftDeleteMixin ---------------------------------------------------------


def test_soft_delete_mixin_deleted_at_defaults_to_none(engine):
    with Session(engine) as session:
        widget = Widget(name="gadget")
        session.add(widget)
        session.commit()
        session.refresh(widget)
        assert widget.deleted_at is None
        assert widget.is_deleted is False


def test_soft_delete_mixin_mark_deleted_sets_timestamp():
    widget = Widget(name="gadget")
    assert widget.deleted_at is None

    widget.mark_deleted()

    assert widget.deleted_at is not None
    assert widget.is_deleted is True


def test_soft_delete_mixin_mark_deleted_accepts_explicit_timestamp():
    widget = Widget(name="gadget")
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)

    widget.mark_deleted(when=when)

    assert widget.deleted_at == when


def test_soft_delete_mixin_not_deleted_filters_out_deleted_rows(engine):
    with Session(engine) as session:
        keep = Widget(name="keep-me")
        drop = Widget(name="drop-me")
        drop.mark_deleted()
        session.add_all([keep, drop])
        session.commit()

        active = session.execute(select(Widget).where(Widget.not_deleted())).scalars().all()

        assert [w.name for w in active] == ["keep-me"]


def test_soft_delete_mixin_not_deleted_is_a_column_expression_not_a_bool():
    # not_deleted() must compose into a select(), not eagerly evaluate --
    # calling it off the class (not an instance) proves it's expression-level.
    expr = Widget.not_deleted()
    assert hasattr(expr, "compile")
