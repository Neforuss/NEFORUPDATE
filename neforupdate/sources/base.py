"""The common interface every update source implements.

To add a source (pip, npm, a vendor updater...):
  1. Create a module in this package with a subclass of `Source`.
  2. Implement `available()`, `scan()` and `update()` (or `update_many()` for batching).
  3. Add an instance to `ALL_SOURCES` in `sources/__init__.py`.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

from .. import runner


@dataclass
class Candidate:
    """One package as one source sees it."""
    source: str             # Source.id
    package_id: str         # what the source needs to update it
    name: str
    installed: str
    available: str
    note: str = ""
    caution: bool = False   # start unticked
    locked: bool = False    # can't be ticked at all
    extra: dict = field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"{self.source}:{self.package_id}"


@dataclass
class Result:
    ok: bool
    message: str
    reboot: bool = False
    skipped: bool = False


@dataclass
class Job:
    key: str                # UpdateItem key in the UI
    cand: Candidate


class Callbacks:
    """How a source reports update progress back to the worker."""

    def __init__(self, started: Callable[[Job], None],
                 progress: Callable[[Job, float, str], None],
                 finished: Callable[[Job, Result], None]) -> None:
        self.started, self.progress, self.finished = started, progress, finished


class Context:
    """What a source gets while scanning or updating: logging, cancel state, command runner."""

    def __init__(self, source_name: str, log: Callable[[str], None], cancel: threading.Event,
                 registry: runner.ProcessRegistry, settings: dict,
                 status: Optional[Callable[[str], None]] = None) -> None:
        self.source_name = source_name
        self._log = log
        self._cancel = cancel
        self.registry = registry
        self.settings = settings
        self._status = status

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def log(self, text: str) -> None:
        self._log(f"[{self.source_name}] {text}")

    def status(self, text: str) -> None:
        if self._status:
            self._status(text)

    def run(self, argv: list[str], on_segment: Optional[runner.LineCallback] = None,
            label: Optional[str] = None, hide: Optional[re.Pattern] = None) -> tuple[int, str]:
        """Run a command; every real output line goes to the log unless it matches `hide`."""
        self.log("$ " + (label or " ".join(argv)))

        def seg(text: str, is_progress: bool) -> None:
            if not is_progress and not _is_noise(text) and not (hide and hide.search(text)):
                self.log("  " + text)
            if on_segment:
                on_segment(text, is_progress)

        code, out = runner.run(argv, seg, self.registry)
        self.log(f"  (exit code {code})")
        return code, out

    def ps(self, script: str, label: str, on_segment: Optional[runner.LineCallback] = None,
           hide: Optional[re.Pattern] = None) -> tuple[int, str]:
        return self.run(runner.ps_args(script), on_segment, label=f"powershell: {label}", hide=hide)


_NOISE = re.compile(r"^[\s\-\\|/]*$|[█▒■□]{2,}|^\s*[\d.]+\s*[KMG]B\s*/\s*[\d.]+\s*[KMG]B\s*$")


def _is_noise(text: str) -> bool:
    return bool(_NOISE.search(text))


class Source:
    id = ""
    name = ""
    can_update = True
    needs_admin = False      # True: updates go through one elevated batch when the app isn't admin

    def configure(self, settings: dict) -> None:
        """Called with the app settings before each scan (most sources ignore them)."""

    def available(self) -> tuple[bool, str]:
        """(usable?, reason shown when not)."""
        return True, ""

    def scan(self, ctx: Context) -> list[Candidate]:
        raise NotImplementedError

    def update(self, job: Job, ctx: Context, report: Callable[[float, str], None]) -> Result:
        raise NotImplementedError

    def update_many(self, jobs: list[Job], ctx: Context, cb: Callbacks) -> None:
        """Update one at a time. Override to batch (e.g. a single elevation prompt)."""
        for job in jobs:
            if ctx.cancelled:
                cb.finished(job, Result(False, "Cancelled", skipped=True))
                continue
            cb.started(job)
            try:
                res = self.update(job, ctx, lambda pct, text, j=job: cb.progress(j, pct, text))
            except Exception as e:  # one broken update must not stop the batch
                ctx.log(f"  error: {e!r}")
                res = Result(False, f"Error: {e}")
            cb.finished(job, res)


# ---------------------------------------------------------------- shared helpers

_SIZE = re.compile(r"([\d.]+)\s*(KB|MB|GB)\s*/\s*([\d.]+)\s*(KB|MB|GB)", re.I)
_PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
_UNIT = {"KB": 1, "MB": 1024, "GB": 1024 * 1024}


def parse_percent(text: str) -> Optional[float]:
    """Pull a 0-100 progress value out of a progress line, if there is one."""
    m = _SIZE.search(text)
    if m:
        done = float(m.group(1)) * _UNIT[m.group(2).upper()]
        total = float(m.group(3)) * _UNIT[m.group(4).upper()]
        if total > 0:
            return max(0.0, min(100.0, done * 100 / total))
    m = _PCT.search(text)
    if m:
        v = float(m.group(1))
        if 0 <= v <= 100:
            return v
    return None


def last_meaningful(output: str) -> str:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if line and not _is_noise(line) and not line.startswith("(exit code"):
            return line[:200]
    return ""


def extract_json(text: str) -> str:
    """PowerShell may print warnings before the JSON; keep only the JSON part."""
    starts = [i for i in (text.find("["), text.find("{")) if i >= 0]
    if not starts:
        return "[]"
    start = min(starts)
    end = max(text.rfind("]"), text.rfind("}"))
    return text[start:end + 1] if end > start else "[]"
