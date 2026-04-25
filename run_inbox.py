"""Launcher for the Outlook inbox dashboard.

Usage:
    streamlit run run_inbox.py
"""
from pathlib import Path
from streamlit.web import cli as stcli
import sys

if __name__ == "__main__":
    app = Path(__file__).parent / "src" / "quoting" / "ui" / "inbox_app.py"
    sys.argv = ["streamlit", "run", str(app)]
    sys.exit(stcli.main())
