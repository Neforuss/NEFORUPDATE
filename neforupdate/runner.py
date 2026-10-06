"""Running external commands (winget, choco, PowerShell...) without blocking the UI.

Output is streamed segment by segment: a segment ends at "\n" (a real line) or at
"\r" (a progress redraw). Callers get both so they can parse progress, while only
real lines go to the log.
"""
from __future__ import annotations

import base64
import ctypes
import subprocess
import threading
from typing import Callable, Optional

CREATE_NO_WINDOW = 0x08000000

LineCallback = Callable[[str, bool], None]  # (text, is_progress_redraw)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def ps_args(script: str) -> list[str]:
    """powershell.exe arguments that run `script` with UTF-8 output and no progress noise."""
    prefix = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
              "$OutputEncoding = [Text.Encoding]::UTF8; $ProgressPreference = 'SilentlyContinue'\n")
    encoded = base64.b64encode((prefix + script).encode("utf-16-le")).decode("ascii")
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-EncodedCommand", encoded]


class ProcessRegistry:
    """Tracks running child processes so Cancel can kill them (and their children)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._procs: set[subprocess.Popen] = set()

    def add(self, p: subprocess.Popen) -> None:
        with self._lock:
            self._procs.add(p)

    def remove(self, p: subprocess.Popen) -> None:
        with self._lock:
            self._procs.discard(p)

    def kill_all(self) -> None:
        with self._lock:
            procs = list(self._procs)
        for p in procs:
            if p.poll() is None:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)],
                               capture_output=True, creationflags=CREATE_NO_WINDOW)


def run(argv: list[str], on_segment: Optional[LineCallback] = None,
        registry: Optional[ProcessRegistry] = None) -> tuple[int, str]:
    """Run a command, stream its output, return (exit_code, full_text_of_real_lines)."""
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
    if registry:
        registry.add(proc)
    lines: list[str] = []
    pending = b""

    def emit(raw: bytes, is_progress: bool) -> None:
        text = raw.decode("utf-8", errors="replace").rstrip()
        if not is_progress:
            lines.append(text)
        if on_segment and text.strip():
            on_segment(text, is_progress)

    try:
        while True:
            chunk = proc.stdout.read1(4096)
            if not chunk:
                break
            pending += chunk
            while True:
                cut = min((i for i in (pending.find(b"\n"), pending.find(b"\r")) if i >= 0), default=-1)
                if cut < 0:
                    break
                seg, sep = pending[:cut], pending[cut:cut + 1]
                # "\r\n" is a normal line ending, not a progress redraw
                if sep == b"\r" and pending[cut + 1:cut + 2] == b"\n":
                    pending = pending[cut + 2:]
                    emit(seg, False)
                elif sep == b"\r" and cut + 1 == len(pending):
                    break  # wait to see whether "\n" follows
                else:
                    pending = pending[cut + 1:]
                    emit(seg, sep == b"\r")
        if pending:
            emit(pending, False)
        proc.wait()
    finally:
        if registry:
            registry.remove(proc)
    code = proc.returncode
    if code is not None and code > 0x7FFFFFFF:  # make HRESULTs signed like winget reports them
        code -= 1 << 32
    return code, "\n".join(lines)
