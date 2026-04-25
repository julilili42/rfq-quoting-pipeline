from __future__ import annotations

import sys
from pathlib import Path

_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[3]
_SRC_DIR = _THIS_FILE.parents[2]

for p in (_PROJECT_ROOT, _SRC_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from quoting.ui.review_ui.main import run

run()