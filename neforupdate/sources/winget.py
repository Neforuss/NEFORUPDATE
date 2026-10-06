"""winget: desktop apps (and anything winget matches from its msstore source)."""
from __future__ import annotations

import json
import re
import shutil

from .base import Candidate, Context, Job, Result, Source, extract_json, last_meaningful, parse_percent

# Structured data through the Microsoft.WinGet.Client module. Prints NOMODULE if it isn't installed.
SCAN_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
if (-not (Get-Module -ListAvailable Microsoft.WinGet.Client)) { 'NOMODULE'; exit 0 }
Import-Module Microsoft.WinGet.Client
$all = @(Get-WinGetPackage)
$rows = @($all | Where-Object { $_.IsUpdateAvailable } | ForEach-Object {
    [pscustomobject]@{
        Name      = [string]$_.Name
        Id        = [string]$_.Id
        Installed = [string]$_.InstalledVersion
        Available = [string]($_.AvailableVersions | Select-Object -First 1)
        Source    = [string]$_.Source
    }
})
# Installed programs no winget source recognises (for the Untracked apps list)
$untracked = @($all | Where-Object { -not $_.Source -and $_.Id -like 'ARP\*' } | ForEach-Object {
    [pscustomobject]@{ Id = [string]$_.Id; Name = [string]$_.Name; Version = [string]$_.InstalledVersion }
})
ConvertTo-Json -InputObject ([pscustomobject]@{ Updates = $rows; Untracked = $untracked }) -Depth 4 -Compress
"""

# Known winget results -> plain-language reasons.
ERRORS = {
    0x8A15008E: "The new version uses a different installer type. Uninstall the app, then install the new version.",
    0x8A150014: "winget couldn't find the installed package any more.",
    0x8A150110: "This portable app was changed by hand, so winget won't overwrite it.",
    0x80190193: "The vendor's download server refused the request (HTTP 403). Try again later or use the app's own updater.",
    0x8A150011: "The downloaded installer didn't match its expected checksum.",
    0x8A150006: "The app's installer reported an error.",
    0x8A150010: "winget has no installer that fits this PC (scope or architecture).",
}
INSTALLER_EXIT = {
    1223: "you declined the administrator prompt",
    0xC000013A: "the installer was closed or interrupted (is the app still running?)",
    1602: "the installer was cancelled",
    1618: "another installation was in progress",
}
NO_UPDATE = 0x8A15002B
REBOOT = 0x8A150109
NO_INSTALLER = 0x8A150010   # no installer matches the requested scope/architecture


def _u32(code: int) -> int:
    return code & 0xFFFFFFFF


class WingetSource(Source):
    id = "winget"
    name = "winget"

    def __init__(self) -> None:
        self.exe = shutil.which("winget") or "winget"
        self.untracked: list[dict] | None = None   # filled by scan(); None = not available

    def available(self) -> tuple[bool, str]:
        return (shutil.which("winget") is not None, "not installed")

    # ------------------------------------------------------------ scan
    def scan(self, ctx: Context) -> list[Candidate]:
        self.untracked = None
        code, out = ctx.ps(SCAN_SCRIPT, "Get-WinGetPackage (updates + untracked programs)",
                           hide=re.compile(r"^\s*[\[{]"))  # the JSON blob is huge; keep it out of the log
        if "NOMODULE" in out:
            ctx.log("Microsoft.WinGet.Client module not found - falling back to parsing winget's text output "
                    "(the Untracked apps list needs the module)")
            return self._scan_cli(ctx)
        if code != 0:
            ctx.log("Module scan failed - falling back to winget's text output")
            return self._scan_cli(ctx)
        data = json.loads(extract_json(out))
        self.untracked = data.get("Untracked") or []
        ctx.log(f"  {len(data.get('Updates') or [])} updates, {len(self.untracked)} programs no source recognises")
        return [self._cand(r["Id"], r["Name"], r["Installed"], r["Available"], r["Source"])
                for r in data.get("Updates") or [] if r.get("Id")]

    def _cand(self, pid: str, name: str, installed: str, available: str, src: str) -> Candidate:
        src = src or "winget"
        return Candidate(self.id, pid, name, installed or "Unknown", available,
                         extra={"winget_source": src})

    def _scan_cli(self, ctx: Context) -> list[Candidate]:
        _, out = ctx.run([self.exe, "upgrade", "--include-unknown", "--accept-source-agreements",
                          "--disable-interactivity"])
        result, cols = [], None
        for line in out.splitlines():
            m = re.match(r"^(.*?)Name\s+Id\s+Version\s+Available", line)
            if m:
                h = line[len(m.group(1)):]
                cols = [h.index(" Id ") + 1, h.index(" Version ") + 1, h.index(" Available") + 1,
                        (h.index(" Source") + 1) if " Source" in h else 0]
                continue
            if not cols or re.match(r"^-+$", line):
                continue
            if not line.strip() or re.match(r"^\d+ (upgrade|package)", line):
                cols = None
                continue
            i_id, i_ver, i_av, i_src = cols
            cut = lambda a, b: line[a:b].strip() if a < len(line) else ""
            pid = cut(i_id, i_ver)
            if pid:
                result.append(self._cand(pid, cut(0, i_id), cut(i_ver, i_av),
                                         cut(i_av, i_src or len(line)), cut(i_src, len(line)) if i_src else "winget"))
        return result

    # ------------------------------------------------------------ update
    def update(self, job: Job, ctx: Context, report) -> Result:
        c = job.cand
        argv = [self.exe, "upgrade", "--id", c.package_id, "--exact",
                "--source", c.extra.get("winget_source", "winget"), "--include-unknown", "--silent",
                "--accept-source-agreements", "--accept-package-agreements", "--disable-interactivity"]
        report(-1, "Starting")
        code, out = run_winget(ctx, argv, report)
        return decode_result(code, out, c.package_id)


# ---------------------------------------------------------------- shared with the linked-apps source

def run_winget(ctx: Context, argv: list[str], report) -> tuple[int, str]:
    """Run a winget install/upgrade, turning its output into progress reports."""

    def seg(text: str, _is_progress: bool) -> None:
        low = text.lower()
        pct = parse_percent(text)
        if pct is not None:
            report(pct, "Downloading")
        elif "verified installer hash" in low:
            report(-1, "Verifying")
        elif "starting package install" in low:
            report(-1, "Installing")
        elif "extracting archive" in low:
            report(-1, "Extracting")

    return ctx.run(argv, seg)


def decode_result(code: int, out: str, package_id: str) -> Result:
    """winget exit code + output -> Result with a plain-language reason."""
    u = _u32(code)
    if code == 0:
        reboot = bool(re.search(r"restart (your|the) (pc|computer|device)", out, re.I))
        return Result(True, "Updated - restart needed" if reboot else "Updated", reboot=reboot)
    if u == REBOOT:
        return Result(True, "Updated - restart needed", reboot=True)
    if u == NO_UPDATE:
        return Result(True, "Already up to date")
    reason = ERRORS.get(u, "")
    m = re.search(r"Installer failed with exit code:\s*(\d+)", out)
    if m:
        ic = int(m.group(1))
        extra = INSTALLER_EXIT.get(ic, f"installer exit code {ic}")
        reason = f"The installer failed: {extra}."
    if not reason:
        reason = last_meaningful(out) or "Unknown error"
    # winget installs dependencies first; say so when one of them is what failed
    found = re.findall(r"Found (.+?) \[([^\]]+)\]", out)
    if found and found[-1][1].lower() != package_id.lower():
        reason = f"Failed on its dependency {found[-1][0]} [{found[-1][1]}]: {reason}"
    return Result(False, f"{reason} (0x{u:08X})")
