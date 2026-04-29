from __future__ import annotations

import sys
from pathlib import Path

_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[3]
_SRC_DIR = _THIS_FILE.parents[2]

for p in (_PROJECT_ROOT, _SRC_DIR):
    path = str(p)
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)

# Streamlit keeps one Python process alive across reruns. Drop any cached
# ``quoting`` modules so imports resolve cleanly from this workspace's ``src``
# tree instead of a previously installed package or a mixed old/new state.
for name in list(sys.modules):
    if name != "quoting" and not name.startswith("quoting."):
        continue
    del sys.modules[name]

from quoting.ui.review_ui.main import run

run()
