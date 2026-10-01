"""pytest 路径设置：插件目录（plugin.py 与 maifetch 包）、同级 SDK、tests 目录（fakes）。"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
for _path in (PLUGIN_DIR, PLUGIN_DIR.parent / "maibot-plugin-sdk", PLUGIN_DIR / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
