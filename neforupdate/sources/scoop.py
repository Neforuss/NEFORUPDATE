"""Scoop: `scoop status` (PowerShell objects -> JSON) to scan, `scoop update <app>` to update."""
from __future__ import annotations

import json
import re
import shutil
import sys

from .base import Candidate, Context, Job, Result, Source, extract_json, last_meaningful, parse_percent

SCAN_SCRIPT = r"""
$all = scoop status 6>&1
$stale = [bool]($all | Where-Object { $_ -is [System.Management.Automation.InformationRecord] -and "$_" -match 'out of date' })
$rows = @($all | Where-Object { $_ -isnot [System.Management.Automation.InformationRecord] -and $_.Name } | ForEach-Object {
    [pscustomobject]@{ Name = [string]$_.Name; Installed = [string]$_.'Installed Version'
                       Latest = [string]$_.'Latest Version'; Info = [string]$_.Info } })
$installed = @(scoop list 6>$null | Where-Object { $_.Name } | ForEach-Object {
    [pscustomobject]@{ Name = [string]$_.Name; Version = [string]$_.Version } })
ConvertTo-Json -InputObject ([pscustomobject]@{ Stale = $stale; Items = $rows; Installed = $installed }) -Depth 4 -Compress
"""


class ScoopSource(Source):
    id = "scoop"
    name = "Scoop"

    def __init__(self) -> None:
        self.installed: list[Candidate] = []   # everything Scoop manages (for the Untracked apps list)

    def available(self) -> tuple[bool, str]:
        return (shutil.which("scoop") is not None, "not installed")

    def scan(self, ctx: Context) -> list[Candidate]:
        if ctx.settings.get("scoop_refresh"):
            ctx.status("refreshing app lists...")
            ctx.ps("scoop update", "scoop update (refresh buckets)")
        code, out = ctx.ps(SCAN_SCRIPT, "scoop status")
        data = json.loads(extract_json(out) or "{}")
        if isinstance(data, list):
            data = {"Items": data}
        self.installed = [Candidate(self.id, r["Name"], r["Name"], r.get("Version", ""), "")
                          for r in data.get("Installed") or [] if r.get("Name")]
        if data.get("Stale"):
            ctx.status("app lists out of date")
            ctx.log("Scoop's app lists are out of date, so newer versions may be missing. "
                    "Turn on 'Refresh Scoop app lists' in Settings to run 'scoop update' first.")
        runtime = sys.executable.lower()
        result = []
        for r in data.get("Items") or []:
            if not r.get("Latest"):
                continue
            c = Candidate(self.id, r["Name"], r["Name"], r.get("Installed", ""), r["Latest"])
            info = r.get("Info") or ""
            if re.search(r"held", info, re.I):
                c.locked, c.note = True, "Held in Scoop (scoop unhold to update)"
            elif info:
                c.note = info
            if r["Name"].lower() == "python" and f"scoop\\apps\\python" in runtime:
                c.caution = True
                c.note = "NEFORUPDATE runs on this Python - updating it removes PySide6 until reinstalled"
            result.append(c)
        return result

    def update(self, job: Job, ctx: Context, report) -> Result:
        name = job.cand.package_id
        if not re.fullmatch(r"[\w.\-/]+", name):
            return Result(False, "Invalid app name")
        report(-1, "Starting")

        def seg(text: str, _p: bool) -> None:
            pct = parse_percent(text)
            if pct is not None:
                report(pct, "Downloading")
            elif "installing" in text.lower() or "linking" in text.lower():
                report(-1, "Installing")

        code, out = ctx.ps(f"scoop update {name}", f"scoop update {name}", seg)
        errors = [l.strip() for l in out.splitlines() if l.strip().upper().startswith("ERROR")]
        if code == 0 and not errors:
            return Result(True, "Updated")
        return Result(False, errors[-1] if errors else (last_meaningful(out) or f"scoop exited with {code}"))
