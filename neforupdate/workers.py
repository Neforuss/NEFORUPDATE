"""Scan and update jobs. They run on background threads and talk to the UI only through Qt signals."""
from __future__ import annotations

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from PySide6.QtCore import QObject, Signal

from . import inventory, rules
from .runner import ProcessRegistry
from .sources import Callbacks, Context, Job, Result, Source

# Update order: one source at a time, so installers never run side by side.
UPDATE_ORDER = ["winget", "linked", "choco", "scoop", "msstore"]


class Bridge(QObject):
    log = Signal(str)
    sourceState = Signal(str, str, str)      # source id, state, text
    sourceResult = Signal(str, list)         # source id, [Candidate]
    scanDone = Signal(bool)                  # cancelled?
    itemStarted = Signal(str, int, int)      # key, n, total
    itemProgress = Signal(str, float, str)   # key, pct (-1 = unknown), text
    itemFinished = Signal(str, object)       # key, Result
    updateDone = Signal(bool)                # cancelled?
    untrackedReady = Signal(object)          # [UntrackedApp] or None (not available)


def scan_one(src: Source, log: Callable[[str], None], cancel: threading.Event, registry: ProcessRegistry,
             settings: dict, state: Callable[[str, str], None]) -> list | None:
    """Scan one source. Shared by the GUI and the --list command line mode."""
    src.configure(settings)
    ok, why = src.available()
    if not ok:
        state("missing", why)
        log(f"[{src.name}] {why} - skipped")
        return None
    state("scanning", "scanning...")
    ctx = Context(src.name, log, cancel, registry, settings, lambda t: state("scanning", t))
    try:
        cands = src.scan(ctx)
    except Exception as e:
        if cancel.is_set():
            state("cancelled", "cancelled")
            return None
        log(f"[{src.name}] scan failed: {e}\n{traceback.format_exc()}")
        state("error", str(e)[:120] or "error")
        return None
    if cancel.is_set():
        state("cancelled", "cancelled")
        return None
    for c in cands:
        rules.apply(c)
    state("done", f"{len(cands)} found")
    return cands


class ScanJob:
    def __init__(self, sources: list[Source], settings: dict, bridge: Bridge, log: Callable[[str], None]) -> None:
        self.sources, self.settings, self.bridge, self.log = sources, settings, bridge, log
        self.cancel_event = threading.Event()
        self.registry = ProcessRegistry()

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="scan").start()

    def cancel(self) -> None:
        self.cancel_event.set()
        self.registry.kill_all()

    def _run(self) -> None:
        def one(src: Source) -> None:
            cands = scan_one(src, self.log, self.cancel_event, self.registry, self.settings,
                             lambda st, text: self.bridge.sourceState.emit(src.id, st, text))
            if cands is not None:
                self.bridge.sourceResult.emit(src.id, cands)

        with ThreadPoolExecutor(max_workers=max(1, len(self.sources))) as ex:
            list(ex.map(one, self.sources))
        untracked = None
        if not self.cancel_event.is_set():
            try:
                untracked = inventory.from_sources(self.sources)
                if untracked is not None:
                    self.log(f"[Untracked] {len(untracked)} installed programs aren't tracked by any package manager")
            except Exception as e:
                self.log(f"[Untracked] couldn't build the list: {e}\n{traceback.format_exc()}")
        self.bridge.untrackedReady.emit(untracked)
        self.bridge.scanDone.emit(self.cancel_event.is_set())


class UpdateJob:
    """Runs the selected updates one after another, grouped by source."""

    def __init__(self, sources: dict[str, Source], jobs: list[Job], settings: dict, bridge: Bridge,
                 log: Callable[[str], None]) -> None:
        self.sources, self.jobs, self.settings, self.bridge, self.log = sources, jobs, settings, bridge, log
        self.cancel_event = threading.Event()
        self.registry = ProcessRegistry()

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="update").start()

    def cancel(self) -> None:
        # Stop after the current item. Killing an installer half-way can break the app.
        self.cancel_event.set()

    def _run(self) -> None:
        total = len(self.jobs)
        counter = {"n": 0}

        def started(job: Job) -> None:
            counter["n"] += 1
            self.bridge.itemStarted.emit(job.key, counter["n"], total)

        finished_keys: set[str] = set()

        def finished(job: Job, res: Result) -> None:
            finished_keys.add(job.key)
            self.bridge.itemFinished.emit(job.key, res)

        cb = Callbacks(started,
                       lambda job, pct, text: self.bridge.itemProgress.emit(job.key, float(pct), text),
                       finished)
        for sid in UPDATE_ORDER:
            group = [j for j in self.jobs if j.cand.source == sid]
            if not group:
                continue
            src = self.sources[sid]
            ctx = Context(src.name, self.log, self.cancel_event, self.registry, self.settings)
            try:
                src.update_many(group, ctx, cb)
            except Exception as e:
                self.log(f"[{src.name}] batch error: {e}\n{traceback.format_exc()}")
                for j in group:
                    if j.key not in finished_keys:
                        finished(j, Result(False, f"Error: {e}"))
        self.bridge.updateDone.emit(self.cancel_event.is_set())
