from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
APP_PATH = PROJECT_ROOT / "src" / "quoting" / "ui" / "review_app.py"
SRC_DIR = PROJECT_ROOT / "src"

if __name__ == "__main__":
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(SRC_DIR)
        if not existing_pythonpath
        else f"{SRC_DIR}{os.pathsep}{existing_pythonpath}"
    )
    raise SystemExit(
        subprocess.call(
            [sys.executable, "-m", "streamlit", "run", str(APP_PATH), *sys.argv[1:]],
            env=env,
        )
    )
