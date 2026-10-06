"""Untracked apps: installed desktop programs that no package manager knows about.

winget reads Windows' installed-programs list (the Uninstall registry keys) and reports
entries it can't match to any source with ids like "ARP\\Machine\\X64\\<key>". Those are
looked up in the registry for publisher, website and install folder, then anything
Chocolatey or Scoop manage is removed. Read-only: nothing here installs or changes anything.
Apps the user links to a winget package (linker.py) become updatable through sources/linked.py.
"""
from __future__ import annotations

import re
import winreg
from dataclasses import dataclass, field

from .merge import keys_for
from .sources.base import Candidate

UNINSTALL = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"

# Entries that aren't really "apps you'd update yourself" (Windows Update services the last one)
NOISE = re.compile(r"^(windows driver package|update for |security update|hotfix for )|\(KB\d+\)|"
                   r"^microsoft update health tools", re.I)


@dataclass
class UntrackedApp:
    id: str                 # winget's ARP id, used as the stable key
    name: str
    version: str
    publisher: str = ""
    website: str = ""
    folder: str = ""
    installed_on: str = ""  # YYYY-MM-DD
    size_mb: float = 0.0
    scope: str = ""         # "All users (64-bit)" / "All users (32-bit)" / "This user"
    link_id: str = ""       # winget package the user linked this app to
    latest: str = ""        # newest version of that package in the catalog (if known)
    matches: list = field(default_factory=list)   # suggested linker.Match list from the last search
    searched: bool = False  # a winget search has been run for this app


def _reg_values(hive, path: str, view: int) -> dict:
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_READ | view) as k:
            out, i = {}, 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(k, i)
                except OSError:
                    return out
                out[name] = value
                i += 1
    except OSError:
        return {}


def locate(arp_id: str) -> tuple[dict, str]:
    """ARP\\Machine\\X64\\<key> -> (registry values, scope label)."""
    parts = arp_id.split("\\", 3)
    if len(parts) != 4:
        return {}, ""
    _, who, arch, key = parts
    path = f"{UNINSTALL}\\{key}"
    if who == "User":
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            v = _reg_values(winreg.HKEY_CURRENT_USER, path, view)
            if v:
                return v, "This user"
        return {}, "This user"
    view = winreg.KEY_WOW64_32KEY if arch == "X86" else winreg.KEY_WOW64_64KEY
    return _reg_values(winreg.HKEY_LOCAL_MACHINE, path, view), \
        "All users (32-bit)" if arch == "X86" else "All users (64-bit)"


def _date(raw) -> str:
    s = str(raw or "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if re.fullmatch(r"\d{8}", s) else ""


def _url(*candidates) -> str:
    for c in candidates:
        c = str(c or "").strip()
        if not c:
            continue
        if not re.match(r"^https?://", c, re.I):
            if re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", c, re.I):
                c = "https://" + c
            else:
                continue
        return c
    return ""


def from_sources(sources) -> list[UntrackedApp] | None:
    """Build the list from sources that just scanned. None if winget's module data isn't available."""
    wg = next((s for s in sources if s.id == "winget"), None)
    if wg is None or getattr(wg, "untracked", None) is None:
        return None
    managed = [c for s in sources for c in getattr(s, "installed", [])]
    apps = build(wg.untracked, managed)
    linked = next((s for s in sources if s.id == "linked"), None)
    if linked is not None:
        for a in apps:
            link = linked.links.get(a.id)
            if link:
                a.link_id = link["id"]
                m = linked.latest.get(link["id"])
                a.latest = m.version if m else ""
    return apps


def build(winget_untracked: list[dict], managed: list[Candidate]) -> list[UntrackedApp]:
    """winget_untracked: [{Id, Name, Version}] for source-less ARP entries.
    managed: everything Chocolatey/Scoop have installed (as Candidates, for name matching)."""
    managed_keys = set().union(*(keys_for(c) for c in managed)) if managed else set()
    apps = []
    for row in winget_untracked:
        arp_id, name = row.get("Id", ""), (row.get("Name") or "").strip()
        if not arp_id.startswith("ARP\\") or not name or NOISE.search(name):
            continue
        probe = Candidate("arp", arp_id.split("\\")[-1], name, row.get("Version", ""), "")
        if keys_for(probe) & managed_keys:
            continue  # Chocolatey or Scoop manage it
        reg, scope = locate(arp_id)
        if reg.get("SystemComponent") == 1 or reg.get("ParentKeyName"):
            continue
        size = reg.get("EstimatedSize")
        apps.append(UntrackedApp(
            id=arp_id, name=name,
            version=str(reg.get("DisplayVersion") or row.get("Version") or ""),
            publisher=str(reg.get("Publisher") or "").strip(),
            website=_url(reg.get("URLUpdateInfo"), reg.get("URLInfoAbout"), reg.get("HelpLink")),
            folder=str(reg.get("InstallLocation") or "").strip().strip('"'),
            installed_on=_date(reg.get("InstallDate")),
            size_mb=round(size / 1024, 1) if isinstance(size, int) else 0.0,
            scope=scope))
    apps.sort(key=lambda a: a.name.lower())
    return apps
