"""DH-08 冒烟入口：设好环境变量 + PYTHONPATH，再 exec smoke_notepad.py。

PowerShell 里要同时设 env 和 sys.path 太麻烦，索性写个 wrapper。
双击或 `python run_smoke.py` 即可。
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DESKTOP_HAND_ENABLED", "true")
os.environ.setdefault("DESKTOP_HAND_INPUT_GROUP", "true")

script = REPO_ROOT / "agent" / "desktop" / "smoke_notepad.py"
sys.exit(runpy.run_path(str(script), run_name="__main__").get("main", lambda: 0)())
