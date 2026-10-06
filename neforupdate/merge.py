"""Merge results from all sources into one list, showing each app once.

Two candidates from different sources are treated as the same app when a name/id key
matches AND their installed versions agree. Different installed versions usually mean
two separate copies (e.g. Scoop's Python and winget's Python), so those stay separate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .sources.base import Candidate

DEFAULT_ORDER = ["winget", "msstore", "choco", "scoop", "linked", "wu"]


@dataclass
class UpdateItem:
    key: str
    candidates: dict[str, Candidate]     # source id -> candidate
    chosen: str
    selected: bool = False
    status: str = ""
    state: str = ""                      # '', queued, running, ok, failed, skipped
    progress: Optional[float] = None     # None: no bar, -1: indeterminate, 0..100
    reboot: bool = False
    forced_source: Optional[str] = None  # user picked a source for this row
    extra_notes: list[str] = field(default_factory=list)

    @property
    def cand(self) -> Candidate:
        return self.candidates[self.chosen]

    @property
    def name(self) -> str:
        return self.cand.name

    @property
    def installed(self) -> str:
        return self.cand.installed

    @property
    def available(self) -> str:
        return self.cand.available

    @property
    def locked(self) -> bool:
        return any(c.locked for c in self.candidates.values()) or self.chosen == "wu"

    @property
    def caution(self) -> bool:
        return any(c.caution for c in self.candidates.values())

    @property
    def note(self) -> str:
        notes = [c.note for c in self.candidates.values() if c.note]
        return " | ".join(dict.fromkeys(notes + self.extra_notes))


_STRIP = re.compile(r"\(.*?\)|\b(x64|x86|64-?bit|32-?bit|amd64|arm64|version|user|machine|portable)\b|"
                    r"\bv?\d+(\.\d+)+\S*|[®™©]", re.I)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _STRIP.sub(" ", (s or "").lower()))


def keys_for(c: Candidate) -> set[str]:
    if c.source == "wu":
        return set()  # Windows updates never merge with apps
    raw = [c.name, c.package_id, c.package_id.split(".")[-1], c.package_id.replace(".", " ")]
    return {k for k in map(_norm, raw) if len(k) >= 3 and not k.isdigit()}


def _vkey(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3])


def versions_agree(a: str, b: str) -> bool:
    if not a or not b or re.match(r"^(unknown|<)", a, re.I) or re.match(r"^(unknown|<)", b, re.I):
        return True
    return _vkey(a) == _vkey(b)


def merge(cands: list[Candidate], order: list[str], forced: dict[str, str]) -> list[UpdateItem]:
    parent = list(range(len(cands)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    index: dict[str, list[int]] = {}
    for i, c in enumerate(cands):
        for k in keys_for(c):
            index.setdefault(k, []).append(i)
    for idxs in index.values():
        for a in idxs:
            for b in idxs:
                if a < b and cands[a].source != cands[b].source and \
                        versions_agree(cands[a].installed, cands[b].installed):
                    ra, rb = find(a), find(b)
                    if ra != rb:
                        # never put two candidates of the same source in one group
                        srcs_a = {cands[i].source for i in range(len(cands)) if find(i) == ra}
                        srcs_b = {cands[i].source for i in range(len(cands)) if find(i) == rb}
                        if not srcs_a & srcs_b:
                            parent[rb] = ra

    groups: dict[int, list[Candidate]] = {}
    for i, c in enumerate(cands):
        groups.setdefault(find(i), []).append(c)

    rank = {s: n for n, s in enumerate(order + [s for s in DEFAULT_ORDER if s not in order])}
    items = []
    for members in groups.values():
        by_source = {c.source: c for c in members}
        key = sorted(c.ref for c in members)[0]
        chosen = forced.get(key) if forced.get(key) in by_source else \
            min(by_source, key=lambda s: rank.get(s, 99))
        items.append(UpdateItem(key=key, candidates=by_source, chosen=chosen,
                                forced_source=forced.get(key) if forced.get(key) in by_source else None))
    return items
