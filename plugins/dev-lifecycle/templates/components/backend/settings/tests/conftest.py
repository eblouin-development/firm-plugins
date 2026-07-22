"""Puts this component's directory (one level up from tests/) on sys.path
so `import settings` resolves to the co-located drop-in module, and also
puts the secrets-loading catalog component's directory on sys.path so the
composition-point test can `import secret_store` — demonstrating the
documented (not hard-wired) composition this component's README and
module docstring describe, without settings.py itself importing it.
"""

import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent.parent  # .../backend/settings
_BACKEND_DIR = _THIS_DIR.parent  # .../components/backend
_COMPONENTS_DIR = _BACKEND_DIR.parent  # .../components
_SECRETS_LOADING_DIR = _COMPONENTS_DIR / "security" / "secrets-loading"

sys.path.insert(0, str(_THIS_DIR))
sys.path.insert(0, str(_SECRETS_LOADING_DIR))
