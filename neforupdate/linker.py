"""Linking untracked apps to winget packages so they can be updated.

winget can't connect some installed programs to its catalog (different names, old
installers, odd registry entries). Here we search the catalog by name, score how likely
each result is the same app, and let the user confirm a link. A linked app is then
checked like any other source (see sources/linked.py) and updated with `winget install`,
which runs the vendor's installer over the existing copy.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Callable, Optional

from .logger import DATA_DIR
from .merge import _norm
from .sources.base import Context, extract_json

MATCHES_FILE = DATA_DIR / "matches.json"

# One PowerShell process searches every name (the catalog opens once, ~8 s; each search ~0.1 s).
# Prints one "MATCH <json>" line per app so the UI can show progress.
SEARCH_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Import-Module Microsoft.WinGet.Client
$items = Get-Content -Raw -Encoding UTF8 -LiteralPath '__FILE__' | ConvertFrom-Json
foreach ($it in $items) {
    $found = @()
    try {
        $found = @(Find-WinGetPackage -Query $it.q -Source winget -Count 6 -ErrorAction Stop | ForEach-Object {
            [pscustomobject]@{ Id = [string]$_.Id; Name = [string]$_.Name; Version = [string]$_.Version } })
    } catch { }
    'MATCH ' + (ConvertTo-Json -InputObject ([pscustomobject]@{ k = $it.k; r = $found }) -Depth 4 -Compress)
}
"""

# Latest catalog version for each linked package id.
LATEST_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Import-Module Microsoft.WinGet.Client
$ids = '__DATA__' | ConvertFrom-Json
$rows = @(foreach ($id in $ids) {
    $p = Find-WinGetPackage -Id $id -MatchOption Equals -Source winget -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($p) { [pscustomobject]@{ Id = [string]$p.Id; Name = [string]$p.Name; Version = [string]$p.Version } }
})
ConvertTo-Json -InputObject $rows -Compress
"""


@dataclass
class Match:
    id: str
    name: str
    version: str
    score: int          # 100 = same name and publisher, 70 = same name or close name + publisher

    @property
    def confidence(self) -> str:
        return "High" if self.score >= 100 else "Medium"


HIGH = 100
SUGGEST = 60

_SUFFIXES = re.compile(r"\b(inc|llc|ltd|limited|corp|corporation|co|gmbh|ag|sa|srl|bv|software|technologies|"
                       r"technology|tech|studios?|labs?|audio|media|games|team|the)\b\.?", re.I)


def _q(s: str) -> str:
    return s.replace("'", "''")


def clean_query(name: str) -> str:
    """'Ample Guitar M Lite II version 2.3.1' -> 'Ample Guitar M Lite II'."""
    s = re.sub(r"\bversion\b.*$", "", name, flags=re.I)
    s = re.sub(r"\(.*?\)|[®™©]|\bv?\d+(\.\d+)+\S*|\b(x64|x86|64-?bit|32-?bit)\b", " ", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip(" -_") or name


def _publisher_key(publisher: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _SUFFIXES.sub(" ", (publisher or "").lower()))


def score(app_name: str, publisher: str, res_id: str, res_name: str) -> int:
    a = _norm(app_name)
    names = {_norm(res_name), _norm(res_id.split(".")[-1]), _norm(res_id.replace(".", " "))}
    names.discard("")
    if not a:
        return 0
    if a in names:
        base = 70
    elif any(len(n) >= 4 and len(a) >= 4 and (a in n or n in a) for n in names):
        base = 40
    else:
        return 0
    pub, vendor = _publisher_key(publisher), _norm(res_id.split(".")[0])
    same_pub = len(vendor) >= 3 and len(pub) >= 3 and \
        (pub.startswith(vendor) or vendor.startswith(pub) or vendor in pub)
    if not same_pub and len(clean_query(app_name).split()) == 1 and len(a) < 10:
        return 0  # one short word ("Nexus", "Portal") matches too many unrelated apps without a publisher match
    return base + (30 if same_pub else 0)


def best_matches(app_name: str, publisher: str, results: list[dict]) -> list[Match]:
    out = []
    for r in results:
        if not r.get("Id"):
            continue
        s = score(app_name, publisher, r["Id"], r.get("Name", ""))
        if s >= SUGGEST:
            out.append(Match(r["Id"], r.get("Name", ""), r.get("Version", ""), s))
    out.sort(key=lambda m: (-m.score, len(m.id)))
    return out[:3]


def compare_versions(a: str, b: str) -> Optional[int]:
    """1 if a > b, -1 if a < b, 0 if equal, None if either isn't a comparable version."""
    pa = [int(x) for x in re.findall(r"\d+", a or "")]
    pb = [int(x) for x in re.findall(r"\d+", b or "")]
    if not pa or not pb:
        return None
    n = max(len(pa), len(pb))
    pa, pb = pa + [0] * (n - len(pa)), pb + [0] * (n - len(pb))
    return (pa > pb) - (pa < pb)


# ---------------------------------------------------------------- running the searches

def _run_search(items: list[dict], ctx: Context, on_row: Callable[[str, list[dict]], None], label: str) -> None:
    """items: [{"k": key, "q": query}]. Calls on_row(key, raw results) as each search finishes."""

    def seg(text: str, _p: bool) -> None:
        if not text.startswith("MATCH "):
            return
        try:
            row = json.loads(text[6:])
        except ValueError:
            return
        results = row.get("r") or []
        on_row(row.get("k", ""), [results] if isinstance(results, dict) else results)

    # The list can be long, so it goes through a file (command lines max out around 32,000 characters)
    with tempfile.NamedTemporaryFile("w", suffix=".json", prefix="neforupdate-search-", encoding="utf-8",
                                     delete=False) as f:
        json.dump(items, f)
        data_file = f.name
    try:
        ctx.ps(SEARCH_SCRIPT.replace("__FILE__", _q(data_file)), label, seg, hide=re.compile(r"^MATCH "))
    finally:
        os.unlink(data_file)


def search(apps: list, ctx: Context, progress: Callable[[int, int], None],
           workers: int = 4) -> dict[str, list[Match]]:
    """apps: UntrackedApp list. Returns ARP id -> suggested matches (empty list = searched, nothing likely).
    Runs `workers` PowerShell processes side by side; each opens the catalog once (~8 s)."""
    by_id = {a.id: a for a in apps}
    found: dict[str, list[Match]] = {}
    lock = threading.Lock()

    def on_row(key: str, results: list[dict]) -> None:
        app = by_id.get(key)
        if app:
            matches = best_matches(app.name, app.publisher, results)
            with lock:
                found[app.id] = matches
                done = len(found)
            progress(done, len(apps))

    items = [{"k": a.id, "q": clean_query(a.name)} for a in apps]
    n = max(1, min(workers, len(items) // 10 or 1))   # small lists don't need several processes
    chunks = [items[i::n] for i in range(n)]
    with ThreadPoolExecutor(max_workers=n) as ex:
        list(ex.map(lambda ch: _run_search(ch, ctx, on_row, f"search winget for {len(ch)} untracked app(s)"),
                    chunks))
    return found


def search_one(query: str, app_name: str, publisher: str, ctx: Context) -> list[Match]:
    """Every catalog result for a typed query, scored against the app (for picking a link by hand)."""
    out: list[Match] = []

    def on_row(_key: str, results: list[dict]) -> None:
        for r in results:
            if r.get("Id"):
                out.append(Match(r["Id"], r.get("Name", ""), r.get("Version", ""),
                                 score(app_name, publisher, r["Id"], r.get("Name", ""))))

    _run_search([{"k": "one", "q": query}], ctx, on_row, f"search winget for '{query}'")
    out.sort(key=lambda m: -m.score)
    return out


def latest_versions(ids: list[str], ctx: Context) -> dict[str, Match]:
    if not ids:
        return {}
    _, out = ctx.ps(LATEST_SCRIPT.replace("__DATA__", _q(json.dumps(sorted(set(ids))))),
                    f"latest winget versions for {len(set(ids))} linked app(s)")
    rows = json.loads(extract_json(out))
    if isinstance(rows, dict):
        rows = [rows]
    return {r["Id"]: Match(r["Id"], r.get("Name", ""), r.get("Version", ""), 0) for r in rows if r.get("Id")}


# ---------------------------------------------------------------- cache of the last search

def load_matches() -> dict[str, list[Match]]:
    try:
        raw = json.loads(MATCHES_FILE.read_text(encoding="utf-8"))
        return {k: [Match(**m) for m in v] for k, v in raw.items()}
    except (OSError, ValueError, TypeError):
        return {}


def save_matches(matches: dict[str, list[Match]]) -> None:
    try:
        MATCHES_FILE.parent.mkdir(parents=True, exist_ok=True)
        MATCHES_FILE.write_text(json.dumps({k: [asdict(m) for m in v] for k, v in matches.items()}),
                                encoding="utf-8")
    except OSError:
        pass
