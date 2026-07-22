"""Puts this component's directory (one level up from tests/) on sys.path
so `import schema` and `import query` resolve to the co-located drop-in
modules — this component is a standalone flat-file drop-in with no
package/__init__.py, matching how a scaffolded project consumes it (bare
files copied into app/core/db/pagination/).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
