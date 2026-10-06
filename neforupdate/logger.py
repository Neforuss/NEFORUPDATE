"""Thread-safe log: every line goes to a timestamped file and to the UI's log panel."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "NEFORUPDATE"
LOG_DIR = DATA_DIR / "logs"


class Logger:
    def __init__(self, sink: Optional[Callable[[str], None]] = None) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.path = LOG_DIR / time.strftime("neforupdate-%Y%m%d-%H%M%S.log")
        self._lock = threading.Lock()
        self._sink = sink
        self._prune()

    def __call__(self, text: str) -> None:
        line = time.strftime("%H:%M:%S ") + text
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        if self._sink:
            self._sink(line)

    @staticmethod
    def _prune(keep: int = 30) -> None:
        logs = sorted(LOG_DIR.glob("neforupdate-*.log"))
        for old in logs[:-keep]:
            try:
                old.unlink()
            except OSError:
                pass
