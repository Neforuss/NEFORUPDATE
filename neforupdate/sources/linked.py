"""Untracked apps the user linked to a winget package (see linker.py).

Installed version: the app's own Uninstall registry entry. Latest version: the winget
catalog. Updating runs `winget install` for the linked package, which runs the vendor's
installer over the existing copy (winget itself doesn't consider the app installed).
"""
from __future__ import annotations

import shutil
from typing import Callable

from .base import Candidate, Context, Job, Result, Source
from .winget import NO_INSTALLER, decode_result, run_winget

NOTE = "Linked by you - installs winget's version over the installed copy"


def candidates(links: dict[str, dict], latest: dict,
               log: Callable[[str], None] = lambda t: None) -> list[Candidate]:
    """Linked apps whose winget package is newer than what's installed. latest: package id -> linker.Match"""
    from .. import inventory, linker  # imported here: both modules import this package (cycle)
    out = []
    for arp_id, link in links.items():
        reg, scope = inventory.locate(arp_id)
        label = link.get("app") or link["id"]
        if not reg:
            log(f"[Linked apps] {label}: not installed any more - link ignored")
            continue
        m = latest.get(link["id"])
        if not m:
            log(f"[Linked apps] {label}: {link['id']} wasn't found in the winget catalog")
            continue
        installed = str(reg.get("DisplayVersion") or "")
        cmp = linker.compare_versions(m.version, installed)
        if cmp is not None and cmp <= 0:
            continue  # up to date (or the catalog is behind)
        c = Candidate("linked", link["id"], str(reg.get("DisplayName") or label), installed or "Unknown", m.version,
                      note=NOTE, extra={"arp_id": arp_id, "scope": "user" if scope == "This user" else "machine"})
        if cmp is None:
            c.caution = True
            c.note = "Linked by you - versions can't be compared, so check before updating"
        out.append(c)
    return out


class LinkedSource(Source):
    id = "linked"
    name = "Linked apps"

    def __init__(self) -> None:
        self.exe = shutil.which("winget") or "winget"
        self.links: dict[str, dict] = {}
        self.latest: dict = {}   # package id -> linker.Match (catalog entry), for the Untracked tab

    def configure(self, settings: dict) -> None:
        self.links = dict(settings.get("links") or {})

    def available(self) -> tuple[bool, str]:
        if shutil.which("winget") is None:
            return False, "needs winget"
        if not self.links:
            return False, "none linked yet"
        return True, ""

    def scan(self, ctx: Context) -> list[Candidate]:
        from .. import linker
        self.latest = linker.latest_versions([l["id"] for l in self.links.values()], ctx)
        return candidates(self.links, self.latest, ctx.log)

    def update(self, job: Job, ctx: Context, report) -> Result:
        c = job.cand
        argv = [self.exe, "install", "--id", c.package_id, "--exact", "--source", "winget", "--silent",
                "--accept-source-agreements", "--accept-package-agreements", "--disable-interactivity"]
        report(-1, "Starting")
        scope = c.extra.get("scope")
        if scope:  # match the existing install so it's replaced, not duplicated
            code, out = run_winget(ctx, argv + ["--scope", scope], report)
            if (code & 0xFFFFFFFF) != NO_INSTALLER and "no applicable installer" not in out.lower():
                return decode_result(code, out, c.package_id)
            ctx.log(f"  winget has no {scope}-scope installer for {c.package_id} - retrying without --scope")
        code, out = run_winget(ctx, argv, report)
        return decode_result(code, out, c.package_id)
