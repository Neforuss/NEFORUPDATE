"""Which updates start unticked (caution) or can't be ticked at all (locked), and why."""
from __future__ import annotations

import re

from .sources.base import Candidate

LOCKED = [
    (r"cold ?turkey", "Cold Turkey Blocker is left alone on purpose"),
]

CAUTION = [
    (r"nvidia", "NVIDIA software - the NVIDIA app is the safer updater"),
    (r"focusrite", "Audio-interface software - update from Focusrite Control"),
    (r"intel.*graphics|intelgraphics", "Graphics-driver tool - Intel's own updater is safer"),
    (r"virtualbox", "Replaces kernel drivers - shut down VMs first"),
    (r"paragon", "Filesystem driver; big version jumps may need a new license"),
    (r"dokan", "Filesystem driver other apps depend on"),
    (r"maxon|cinema ?4d", "License-tied pro app - update from the Maxon App"),
    (r"^discord\b|discord\.discord", "Discord updates itself on launch"),
]

HEADS_UP = [
    (r"protonvpn|proton vpn", "VPN disconnects briefly"),
    (r"powertoys", "PowerToys closes during the update"),
    (r"microsoft\.edge|^microsoft edge", "Restart Edge afterwards"),
]


def locked_reason(name: str) -> str:
    """Why an app must never be touched (''= it's fine). Used before linking untracked apps."""
    for pat, note in LOCKED:
        if re.search(pat, (name or "").lower()):
            return note
    return ""


def apply(c: Candidate) -> None:
    """Add notes/flags to a candidate in place (source-specific notes are kept)."""
    hay = f"{c.name} {c.package_id}".lower()
    for pat, note in LOCKED:
        if re.search(pat, hay):
            c.locked, c.note = True, note
            return
    for pat, note in CAUTION:
        if re.search(pat, hay):
            c.caution, c.note = True, note
            return
    if re.match(r"^(unknown|<)", c.installed or "", re.I):
        c.caution = True
        c.note = c.note or "Installed version unknown - it may reinstall instead of update"
        return
    if c.note:
        return
    for pat, note in HEADS_UP:
        if re.search(pat, hay):
            c.note = note
            return
    cur = re.match(r"^v?(\d+)\.", c.installed or "")
    new = re.match(r"^v?(\d+)\.", c.available or "")
    if cur and new and int(cur.group(1)) < 100 and int(new.group(1)) > int(cur.group(1)):
        c.note = f"Major update ({cur.group(1)} -> {new.group(1)})"
