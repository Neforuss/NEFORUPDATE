"""Windows Update through the built-in COM API (Microsoft.Update.Session). List-only for now."""
from __future__ import annotations

import json

from .base import Candidate, Context, Job, Result, Source, extract_json

SCAN_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$session = New-Object -ComObject Microsoft.Update.Session
$result = $session.CreateUpdateSearcher().Search('IsInstalled=0 and IsHidden=0')
$rows = @(foreach ($u in $result.Updates) {
    [pscustomobject]@{
        Id       = [string]$u.Identity.UpdateID
        Title    = [string]$u.Title
        KB       = (($u.KBArticleIDs | ForEach-Object { "KB$_" }) -join ', ')
        Driver   = ($u.Type -eq 2)
        Optional = (-not $u.AutoSelectOnWebSites)
        Reboot   = [int]$u.InstallationBehavior.RebootBehavior
        SizeMB   = [math]::Round($u.MaxDownloadSize / 1MB, 1)
    }
})
ConvertTo-Json -InputObject $rows -Compress
"""


class WindowsUpdateSource(Source):
    id = "wu"
    name = "Windows Update"
    can_update = False

    def scan(self, ctx: Context) -> list[Candidate]:
        code, out = ctx.ps(SCAN_SCRIPT, "Windows Update search (Microsoft.Update.Session)")
        if code != 0:
            raise RuntimeError("Windows Update search failed - see log")
        result = []
        for r in json.loads(extract_json(out)):
            bits = ["List-only: install from Settings > Windows Update"]
            if r.get("Driver"):
                bits.insert(0, "Driver")
            elif r.get("Optional"):
                bits.insert(0, "Optional")
            if r.get("Reboot"):
                bits.insert(0, "Needs restart")
            c = Candidate(self.id, r["Id"], r["Title"], "", r.get("KB") or "Update",
                          note=" - ".join(bits), locked=True, extra={"reboot": bool(r.get("Reboot"))})
            result.append(c)
        return result

    def update(self, job: Job, ctx: Context, report) -> Result:
        return Result(False, "Windows updates are list-only in this version", skipped=True)
