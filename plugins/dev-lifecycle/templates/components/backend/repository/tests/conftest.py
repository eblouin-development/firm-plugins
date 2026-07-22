"""Puts this component's directory on sys.path so `import repository`
resolves, plus the sibling pagination/ and db-mixins/ component
directories — repository.py imports `query`/`schema` as flat sibling
modules (matching how the SQLAlchemy-specific half of backend/ lands
together in one app/core/db/ directory once copied into a real project),
and these tests additionally compose db-mixins' Base/UUIDPrimaryKey/
TimestampMixin/SoftDeleteMixin to build a realistic test model — the same
composition a real app model uses.
"""

import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent.parent  # .../backend/repository
_BACKEND_DIR = _THIS_DIR.parent  # .../components/backend

sys.path.insert(0, str(_THIS_DIR))
sys.path.insert(0, str(_BACKEND_DIR / "pagination"))
sys.path.insert(0, str(_BACKEND_DIR / "db-mixins"))
