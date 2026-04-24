"""Streamlit launcher. Run from project root:

    streamlit run run_ui.py
"""
import runpy
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
for p in (_ROOT, _SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

runpy.run_module("quoting.ui.review_app", run_name="__main__", alter_sys=True)
