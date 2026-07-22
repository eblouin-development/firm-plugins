<!-- fragment: block:components/backend/db-mixins -->

## Setup
Copy `mixins.py` into `app/core/db/mixins.py`, alongside `session.py` and
`repository.py` (also SQLAlchemy-specific — keep the SQLAlchemy half of
`backend/` together in one `app/core/db/` directory). Every model extends
`Base`; compose `UUIDPrimaryKey`, `TimestampMixin`, `SoftDeleteMixin` as
needed:

```python
class Widget(Base, UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "widgets"
    name: Mapped[str] = mapped_column(String(100))
```

## Maintenance
SQLAlchemy-specific — Django models (Stage 4) do not reuse this file; they
use `models.UUIDField`, `auto_now_add`/`auto_now`, and a custom soft-delete
manager instead.
