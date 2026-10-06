"""Microsoft Store apps, through Windows' own Store API (AppInstallManager).

winget's msstore source doesn't recognise most Store apps on Windows 10, so this asks
the Store itself. The scan passes AutomaticallyDownloadAndInstallUpdateIfFound = false
so searching doesn't queue downloads (the plain search does queue them).
"""
from __future__ import annotations

import json
import re
import urllib.request

from ..runner import ps_args
from .base import Candidate, Context, Job, Result, Source, extract_json

PREAMBLE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.ApplicationModel.Store.Preview.InstallControl.AppInstallManager, Windows.ApplicationModel.Store.Preview, ContentType = WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
function Await($op, [type]$t) {
    $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op))
    if (-not $task.Wait(240000)) { throw 'Timed out waiting for the Microsoft Store' }
    $task.Result
}
$NS = 'Windows.ApplicationModel.Store.Preview.InstallControl'
$mgr = New-Object "$NS.AppInstallManager"
$opt = New-Object "$NS.AppUpdateOptions"
"""

SCAN_SCRIPT = PREAMBLE + r"""
$opt.AutomaticallyDownloadAndInstallUpdateIfFound = $false
$listType = [System.Collections.Generic.IReadOnlyList`1].MakeGenericType([type]"$NS.AppInstallItem")
$found = @(Await ($mgr.SearchForAllUpdatesAsync('', '', $opt)) $listType)
$queued = @($mgr.AppInstallItems)
$queuedIds = @($queued | ForEach-Object { $_.ProductId })

$pk = @{}
Get-AppxPackage | ForEach-Object {
    $cur = $pk[$_.PackageFamilyName]
    if (-not $cur -or [version]$_.Version -gt [version]$cur.Version) { $pk[$_.PackageFamilyName] = $_ }
}
$names = @{}
try { Get-StartApps | ForEach-Object { $f = ($_.AppID -split '!')[0]; if (-not $names[$f]) { $names[$f] = $_.Name } } } catch { }

$out = [ordered]@{}
foreach ($i in ($found + $queued)) {
    if (-not $i -or $out.Contains($i.ProductId)) { continue }
    $s = $i.GetCurrentStatus()
    $state = [string]$s.InstallState
    if ($state -eq 'Completed' -or $state -eq 'Canceled') { continue }
    $p = $pk[$i.PackageFamilyName]
    $out[$i.ProductId] = [pscustomobject]@{
        ProductId = [string]$i.ProductId
        Pfn       = [string]$i.PackageFamilyName
        Name      = [string]$names[$i.PackageFamilyName]
        PkgName   = [string]$p.Name
        Installed = [string]$p.Version
        State     = $state
        Queued    = ($queuedIds -contains $i.ProductId)
    }
}
ConvertTo-Json -InputObject @($out.Values) -Compress
"""

UPDATE_SCRIPT = PREAMBLE + r"""
$productId = '__PID__'
$opt.AutomaticallyDownloadAndInstallUpdateIfFound = $true
$opt.AllowForcedAppRestart = $false
$item = $mgr.AppInstallItems | Where-Object { $_.ProductId -eq $productId } | Select-Object -First 1
if (-not $item) { $item = Await ($mgr.SearchForUpdatesAsync($productId, '', '', '', $opt)) ([type]"$NS.AppInstallItem") }
if (-not $item) { 'RESULT NOUPDATE 0'; exit 0 }
$t0 = Get-Date; $changed = Get-Date; $lastPct = -1; $lastState = ''
while ($true) {
    $s = $item.GetCurrentStatus()
    $st = [string]$s.InstallState; $pct = [int]$s.PercentComplete
    "PROGRESS $pct $st"
    if ($st -ne $lastState) { "STATE $st"; $lastState = $st }
    if ($st -eq 'Completed') { 'RESULT OK 0'; break }
    if ($st -eq 'Error') { $hr = 0; try { $hr = $s.ErrorCode.HResult } catch { }; "RESULT ERROR $hr"; break }
    if ($st -eq 'Canceled') { 'RESULT CANCELED 0'; break }
    if ($pct -ne $lastPct) { $lastPct = $pct; $changed = Get-Date }
    if ($st -like 'Paused*' -and ((Get-Date) - $changed).TotalSeconds -gt 90) { "RESULT PAUSED 0"; break }
    if (((Get-Date) - $t0).TotalMinutes -gt 30) { 'RESULT TIMEOUT 0'; break }
    Start-Sleep -Milliseconds 700
}
"""

CAUTION = [
    (r"IntelGraphics|Intel.*Graphics", "Graphics-driver tool - Intel's own updater is safer"),
    (r"NVIDIA", "NVIDIA software - the NVIDIA app is the safer updater"),
]


def _pretty(pkg_name: str) -> str:
    """Microsoft.WindowsCalculator -> Windows Calculator (fallback when no display name is known)."""
    tail = pkg_name.split(".")[-1] if pkg_name else ""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", tail) or pkg_name


def _catalog_titles(product_ids: list[str]) -> dict[str, str]:
    """Display names from the public Store catalog (read-only). Empty dict if offline."""
    if not product_ids:
        return {}
    url = ("https://displaycatalog.mp.microsoft.com/v7.0/products?bigIds=" + ",".join(product_ids)
           + "&market=US&languages=en-US")
    try:
        with urllib.request.urlopen(url, timeout=12) as r:
            data = json.load(r)
        return {p["ProductId"]: p["LocalizedProperties"][0]["ProductTitle"] for p in data.get("Products", [])}
    except Exception:
        return {}


class StoreSource(Source):
    id = "msstore"
    name = "Microsoft Store"

    def scan(self, ctx: Context) -> list[Candidate]:
        code, out = ctx.ps(SCAN_SCRIPT, "Store: search for updates (no auto-download)")
        if code != 0:
            raise RuntimeError(f"Store search failed: {out.strip().splitlines()[-1] if out.strip() else code}")
        rows = json.loads(extract_json(out))
        missing = [r["ProductId"] for r in rows if not r.get("Name")]
        titles = _catalog_titles(missing)
        result = []
        for r in rows:
            name = r.get("Name") or titles.get(r["ProductId"]) or _pretty(r.get("PkgName", ""))
            c = Candidate(self.id, r["ProductId"], name, r.get("Installed") or "", "Newer version",
                          extra={"pfn": r.get("Pfn", "")})
            state = r.get("State", "")
            if state.startswith("Paused"):
                c.note = "Paused in the Store"
            elif r.get("Queued"):
                c.note = f"Already queued in the Store ({state})"
            hay = f"{name} {r.get('Pfn', '')}"
            for pat, note in CAUTION:
                if re.search(pat, hay, re.I):
                    c.caution, c.note = True, note
            result.append(c)
        return result

    def update(self, job: Job, ctx: Context, report) -> Result:
        pid = job.cand.package_id
        if not re.fullmatch(r"[A-Za-z0-9]+", pid):
            return Result(False, "Invalid Store product id")
        final = {"kind": "", "arg": ""}

        def seg(text: str, _p: bool) -> None:
            parts = text.strip().split()
            if len(parts) >= 3 and parts[0] == "PROGRESS":
                state = parts[2]
                pct = float(parts[1])
                if state in ("Downloading", "Installing") or pct > 0:
                    report(pct, state)
                else:
                    report(-1, state)
            elif len(parts) >= 2 and parts[0] == "RESULT":
                final["kind"], final["arg"] = parts[1], (parts[2] if len(parts) > 2 else "")

        report(-1, "Asking the Store")
        # PROGRESS lines arrive every 0.7 s; keep them out of the log (STATE lines are logged)
        code, out = ctx.run(ps_args(UPDATE_SCRIPT.replace("__PID__", pid)), seg,
                            label=f"powershell: Store update {pid}", hide=re.compile(r"^PROGRESS "))
        kind = final["kind"]
        if kind == "OK":
            return Result(True, "Updated")
        if kind == "NOUPDATE":
            return Result(True, "Already up to date")
        if kind == "PAUSED":
            return Result(False, "The Store paused this update (the app may be running). It will continue in the Store.")
        if kind == "TIMEOUT":
            return Result(False, "Still running after 30 minutes - check the Store's Downloads page.")
        if kind == "CANCELED":
            return Result(False, "Cancelled in the Store", skipped=True)
        if kind == "ERROR":
            hr = int(final["arg"] or 0) & 0xFFFFFFFF
            return Result(False, f"The Store reported an error (0x{hr:08X})")
        return Result(False, f"Store update didn't start (exit code {code})")
