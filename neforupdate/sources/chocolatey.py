"""Chocolatey: `choco outdated -r` (pipe-delimited) to scan, `choco upgrade` to update.

Chocolatey installs machine-wide, so updates need Administrator. When the app isn't
elevated, all selected Chocolatey updates run in one elevated batch (one UAC prompt).
"""
from __future__ import annotations

import re
import shutil

from .. import elevation, runner
from .base import Callbacks, Candidate, Context, Job, Result, Source, last_meaningful, parse_percent

REBOOT_CODES = {1641, 3010}


class ChocolateySource(Source):
    id = "choco"
    name = "Chocolatey"
    needs_admin = True

    def available(self) -> tuple[bool, str]:
        return (shutil.which("choco") is not None, "not installed")

    def __init__(self) -> None:
        self.installed: list[Candidate] = []   # everything Chocolatey manages (for the Untracked apps list)

    def scan(self, ctx: Context) -> list[Candidate]:
        _, listed = ctx.run(["choco", "list", "-r"])
        self.installed = [Candidate(self.id, n, n, v, "") for n, v in
                          (l.strip().split("|", 1) for l in listed.splitlines() if l.count("|") == 1)]
        code, out = ctx.run(["choco", "outdated", "-r", "--ignore-unfound"])
        result = []
        for line in out.splitlines():
            m = re.match(r"^([^|\s]+)\|([^|]*)\|([^|]*)\|(true|false)\s*$", line.strip(), re.I)
            if not m:
                continue
            c = Candidate(self.id, m.group(1), m.group(1), m.group(2), m.group(3))
            if m.group(4).lower() == "true":
                c.locked, c.note = True, "Pinned in Chocolatey (choco pin) - unpin it to update"
            result.append(c)
        if code not in (0, 2) and not result:  # 2 = "outdated packages found" on newer choco
            raise RuntimeError(last_meaningful(out) or f"choco exited with {code}")
        return result

    @staticmethod
    def _argv(job: Job) -> list[str]:
        return ["choco", "upgrade", job.cand.package_id, "-y", "--no-color"]

    @staticmethod
    def _result(code: int, out: str) -> Result:
        if code == 0:
            return Result(True, "Updated")
        if code in REBOOT_CODES:
            return Result(True, "Updated - restart needed", reboot=True)
        if code == 350:
            return Result(False, "Windows has a restart pending; restart, then try again.")
        if code == elevation.UAC_DECLINED:
            return Result(False, "You declined the administrator prompt.")
        err = next((l.strip() for l in reversed(out.splitlines()) if l.strip().startswith("ERROR")), "")
        return Result(False, f"{err or last_meaningful(out) or 'choco failed'} (exit {code})")

    def update(self, job: Job, ctx: Context, report) -> Result:
        report(-1, "Starting")
        code, out = ctx.run(self._argv(job), lambda t, _p: self._progress(t, report))
        return self._result(code, out)

    @staticmethod
    def _progress(text: str, report) -> None:
        pct = parse_percent(text) if "Progress" in text or "%" in text else None
        if pct is not None:
            report(pct, "Downloading")
        elif "installing" in text.lower():
            report(-1, "Installing")

    def update_many(self, jobs: list[Job], ctx: Context, cb: Callbacks) -> None:
        if runner.is_admin():
            return super().update_many(jobs, ctx, cb)
        # One elevated batch for all Chocolatey updates.
        outputs: dict[int, list[str]] = {i: [] for i in range(len(jobs))}
        done: set[int] = set()
        ctx.log(f"Asking for administrator permission to run {len(jobs)} Chocolatey update(s)")
        for j in jobs:
            cb.progress(j, -1, "Waiting for admin permission")

        def on_start(i: int) -> None:
            cb.started(jobs[i]); ctx.log("$ " + " ".join(self._argv(jobs[i])) + "   (elevated)")

        def on_line(i: int, line: str) -> None:
            outputs[i].append(line)
            if line.strip():
                ctx.log("  " + line)
            self._progress(line, lambda p, t: cb.progress(jobs[i], p, t))

        def on_exit(i: int, code: int) -> None:
            done.add(i); ctx.log(f"  (exit code {code})")
            cb.finished(jobs[i], self._result(code, "\n".join(outputs[i])))

        def on_skip(i: int) -> None:
            done.add(i); cb.finished(jobs[i], Result(False, "Cancelled", skipped=True))

        code = elevation.run_elevated_batch([self._argv(j) for j in jobs], ctx.registry,
                                            lambda: ctx.cancelled, on_start, on_line, on_exit, on_skip)
        for i, j in enumerate(jobs):
            if i not in done:
                msg = "You declined the administrator prompt." if code == elevation.UAC_DECLINED \
                    else "The elevated Chocolatey run stopped early."
                cb.finished(j, Result(False, msg, skipped=code == elevation.UAC_DECLINED))
