"""Paths to bundled images (the assets folder next to main.py, or inside the packaged .exe)."""
from __future__ import annotations

import sys
from pathlib import Path

_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))  # _MEIPASS: PyInstaller's unpack dir

SPLASH = _BASE / "assets" / "splash.png"
ICON = _BASE / "assets" / "icon.png"
ICO = _BASE / "assets" / "neforupdate.ico"
CHECK = _BASE / "assets" / "check.png"   # checkbox tick (theme.py)

CREDIT_URL = "https://neforus.com"
SOURCE_URL = "https://github.com/Neforuss/NEFORUPDATE"   # open source (MIT)
