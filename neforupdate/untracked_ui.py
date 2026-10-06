"""The "Untracked apps" tab: installed programs no package manager tracks, and linking them to winget."""
from __future__ import annotations

import csv
import os
import threading
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QSortFilterProxyModel, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QDialog, QDialogButtonBox, QFileDialog,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox, QProgressBar,
                               QPushButton, QTableView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import linker, rules
from .inventory import UntrackedApp
from .runner import ProcessRegistry
from .sources.base import Context

if TYPE_CHECKING:
    from .ui import MainWindow

COLS = ["Name", "Version", "Publisher", "winget match", "Latest", "Installed", "Type", "Website"]
C_NAME, C_VER, C_PUB, C_MATCH, C_LATEST, C_DATE, C_TYPE, C_WEB = range(8)

INSTALL_MODULE_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
if (-not (Get-PackageProvider -ListAvailable -Name NuGet -ErrorAction SilentlyContinue | Where-Object { $_.Version -ge '2.8.5.201' })) {
    Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Scope CurrentUser -Force | Out-Null
}
Install-Module Microsoft.WinGet.Client -Scope CurrentUser -Force -AllowClobber -Repository PSGallery
'INSTALLED ' + (Get-Module -ListAvailable Microsoft.WinGet.Client | Select-Object -First 1).Version
"""


def _host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.removeprefix("www.") if url else ""


class Task(QObject):
    """Runs fn(task) on a background thread. fn may emit task.progress; finished carries (result, error)."""
    progress = Signal(int, int)
    finished = Signal(object, object)

    def __init__(self, fn: Callable[["Task"], object]) -> None:
        super().__init__()
        self.fn = fn
        self.cancel_event = threading.Event()
        self.registry = ProcessRegistry()

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="untracked-task").start()

    def cancel(self) -> None:
        self.cancel_event.set()
        self.registry.kill_all()

    def context(self, win: "MainWindow", label: str) -> Context:
        return Context(label, win.logger, self.cancel_event, self.registry, {})

    def _run(self) -> None:
        try:
            result, error = self.fn(self), None
        except Exception as e:  # reported in the UI
            result, error = None, e
        self.finished.emit(result, error)


def latest_of(a: UntrackedApp) -> str:
    if a.link_id:
        return a.latest
    return a.matches[0].version if a.matches else ""


# ====================================================================== table model
class UntrackedModel(QAbstractTableModel):
    def __init__(self, win: "MainWindow") -> None:
        super().__init__()
        self.win = win
        self.apps: list[UntrackedApp] = []
        self.hidden: set[str] = set(win.settings.hidden_untracked)

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.apps)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        return COLS[section] if orientation == Qt.Horizontal and role == Qt.DisplayRole else None

    def set_apps(self, apps: list[UntrackedApp]) -> None:
        self.beginResetModel()
        self.apps = apps
        self.endResetModel()

    def refresh(self) -> None:
        if self.apps:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.apps) - 1, len(COLS) - 1))

    def row_of(self, app: UntrackedApp) -> int:
        for i, a in enumerate(self.apps):
            if a is app:
                return i
        return -1

    def _match_text(self, a: UntrackedApp) -> str:
        if a.link_id:
            return f"✓ {a.link_id}"
        if rules.locked_reason(a.name):
            return ""
        if a.matches:
            return f"{a.matches[0].id}?"
        return "no match" if a.searched else ""

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        a, col = self.apps[index.row()], index.column()
        t = self.win.tokens
        latest = latest_of(a)
        cmp = linker.compare_versions(latest, a.version) if latest else None
        if role == Qt.DisplayRole:
            if col == C_LATEST:
                return f"{latest}  ↑" if cmp == 1 else latest
            return {C_NAME: a.name, C_VER: a.version, C_PUB: a.publisher, C_MATCH: self._match_text(a),
                    C_DATE: a.installed_on, C_TYPE: a.scope, C_WEB: _host(a.website)}[col]
        if role == Qt.UserRole:  # sort key
            return (self.data(index) or "").lower()
        if role == Qt.UserRole + 1:  # hidden flag, for filtering
            return a.id in self.hidden
        if role == Qt.ToolTipRole:
            if col == C_WEB and a.website:
                return a.website
            if col == C_NAME:
                size = f"Size: {a.size_mb:,.0f} MB" if a.size_mb >= 1 else ""
                return "\n".join(x for x in (a.name, a.folder and f"Folder: {a.folder}", size,
                                             f"Registry: {a.id}") if x)
            if col == C_MATCH:
                lock = rules.locked_reason(a.name)
                if lock:
                    return lock
                if a.link_id:
                    return f"Linked to {a.link_id}. Updates for it appear in the Updates tab.\nRight-click to unlink."
                if a.matches:
                    m = a.matches[0]
                    return (f"Suggested ({m.confidence.lower()} confidence): {m.name} [{m.id}] {m.version}\n"
                            "Not linked yet - right-click to link it, or use Review matches.")
                if a.searched:
                    return "No likely winget package. Right-click > Link to a winget package... to search yourself."
            if col == C_LATEST and latest:
                return {1: "Newer than the installed version", 0: "Same as the installed version",
                        -1: "Older than the installed version - probably not the same app, or the catalog is behind"
                        }.get(cmp, "Versions can't be compared")
        if role == Qt.ForegroundRole:
            if a.id in self.hidden:
                return QColor(t["muted"])
            if col == C_WEB:
                return QColor(t["accent"])
            if col == C_MATCH:
                if a.link_id:
                    return QColor(t["ok"])
                return QColor(t["warn"] if a.matches else t["muted"])
            if col == C_LATEST:
                return QColor(t["accent"] if cmp == 1 else t["muted"])
        if role == Qt.FontRole:
            f = QApplication.font()
            if col == C_NAME:
                f.setWeight(f.Weight.DemiBold)
                return f
            if col == C_MATCH and a.matches and not a.link_id:
                f.setItalic(True)
                return f
        return None

    def toggle_hidden(self, row: int) -> None:
        a = self.apps[row]
        self.hidden.symmetric_difference_update({a.id})
        self.win.settings.hidden_untracked = sorted(self.hidden)
        self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLS) - 1))


class UntrackedProxy(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.show_hidden = False
        self.setSortRole(Qt.UserRole)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setFilterKeyColumn(-1)

    def filterAcceptsRow(self, row, parent) -> bool:
        if not self.show_hidden and self.sourceModel().index(row, 0, parent).data(Qt.UserRole + 1):
            return False
        return super().filterAcceptsRow(row, parent)

    def refilter(self) -> None:
        if hasattr(self, "beginFilterChange"):  # Qt 6.10+; invalidateFilter() is deprecated there
            self.beginFilterChange()
            self.endFilterChange()
        else:
            self.invalidateFilter()

    def set_show_hidden(self, on: bool) -> None:
        self.show_hidden = on
        self.refilter()


# ====================================================================== dialogs
def _table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().hide()
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setShowGrid(False)
    t.setAlternatingRowColors(True)
    t.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    t.horizontalHeader().setHighlightSections(False)
    return t


def _cell(text: str, tip: str = "") -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    if tip:
        it.setToolTip(tip)
    return it


class ReviewDialog(QDialog):
    """All suggested matches at once. High-confidence ones start ticked."""

    def __init__(self, parent: QWidget, apps: list[UntrackedApp]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review winget matches")
        self.resize(980, 520)
        self.apps = apps
        lay = QVBoxLayout(self)
        info = QLabel("Linking tells NEFORUPDATE which winget package an installed app is. When the package has a "
                      "newer version, the app shows up in the Updates tab, and updating runs that package's "
                      "installer over your copy.<br><b>Only link apps you're sure about.</b> High-confidence "
                      "matches (same name and publisher) are ticked; check the others yourself.")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.table = _table(["Link", "Installed app", "Installed", "winget package", "Latest", "Confidence"])
        self.table.setRowCount(len(apps))
        for r, a in enumerate(apps):
            m = a.matches[0]
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            check.setCheckState(Qt.Checked if m.score >= linker.HIGH else Qt.Unchecked)
            cmp = linker.compare_versions(m.version, a.version)
            latest = m.version + {1: "  ↑ newer", 0: "  (same)", -1: "  (older!)"}.get(cmp, "")
            self.table.setItem(r, 0, check)
            self.table.setItem(r, 1, _cell(a.name, a.publisher))
            self.table.setItem(r, 2, _cell(a.version))
            self.table.setItem(r, 3, _cell(f"{m.name}  [{m.id}]", m.id))
            self.table.setItem(r, 4, _cell(latest))
            self.table.setItem(r, 5, _cell(m.confidence, "High: same name and publisher. "
                                                         "Medium: similar name only - double-check."))
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        lay.addWidget(self.table, 1)
        box = QDialogButtonBox()
        self.ok = box.addButton("Link selected", QDialogButtonBox.AcceptRole)
        box.addButton(QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.table.itemChanged.connect(self._count)
        self._count()

    def _count(self, *_) -> None:
        n = len(self.chosen())
        self.ok.setText(f"Link {n} app(s)" if n else "Link selected")
        self.ok.setEnabled(n > 0)

    def chosen(self) -> list[tuple[UntrackedApp, linker.Match]]:
        return [(a, a.matches[0]) for r, a in enumerate(self.apps)
                if self.table.item(r, 0).checkState() == Qt.Checked]


class LinkDialog(QDialog):
    """Search the winget catalog by hand and pick the package an app should be linked to."""

    def __init__(self, page: "UntrackedPage", app: UntrackedApp) -> None:
        super().__init__(page)
        self.page, self.app = page, app
        self.results: list[linker.Match] = []
        self.task: Task | None = None
        self._last_task: Task | None = None
        self.setWindowTitle(f"Link {app.name}")
        self.resize(820, 440)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b>{app.name}</b> {app.version}  ·  {app.publisher or 'unknown publisher'}"
                             "<br>Pick the winget package that is this exact app. Updating it later runs that "
                             "package's installer over your copy."))
        row = QHBoxLayout()
        self.query = QLineEdit(linker.clean_query(app.name))
        self.btn_search = QPushButton("Search")
        row.addWidget(self.query, 1)
        row.addWidget(self.btn_search)
        lay.addLayout(row)
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        lay.addWidget(self.status)
        self.table = _table(["Package", "Id", "Latest", "Match"])
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        lay.addWidget(self.table, 1)
        box = QDialogButtonBox()
        self.ok = box.addButton("Link", QDialogButtonBox.AcceptRole)
        box.addButton(QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.ok.setEnabled(False)
        self.btn_search.clicked.connect(self.search)
        self.query.returnPressed.connect(self.search)
        self.table.itemSelectionChanged.connect(lambda: self.ok.setEnabled(bool(self.table.selectedItems())))
        self.table.doubleClicked.connect(lambda _: self.accept())
        self.search()

    def search(self) -> None:
        q = self.query.text().strip()
        if not q or self.task:
            return
        self.status.setText("Searching the winget catalog… (the first search takes a few seconds)")
        self.btn_search.setEnabled(False)
        win, app = self.page.win, self.app
        self.task = Task(lambda t: linker.search_one(q, app.name, app.publisher, t.context(win, "winget search")))
        self.task.finished.connect(self._done)
        self.task.start()

    def _done(self, results, error) -> None:
        self._last_task, self.task = self.task, None
        self.btn_search.setEnabled(True)
        if error:
            self.status.setText(f"Search failed: {error}")
            return
        self.results = results or []
        self.table.setRowCount(len(self.results))
        for r, m in enumerate(self.results):
            cmp = linker.compare_versions(m.version, self.app.version)
            label = {1: "  ↑ newer", 0: "  (same)", -1: "  (older)"}.get(cmp, "")
            strength = "high" if m.score >= linker.HIGH else "medium" if m.score >= linker.SUGGEST else "weak"
            self.table.setItem(r, 0, _cell(m.name))
            self.table.setItem(r, 1, _cell(m.id))
            self.table.setItem(r, 2, _cell(m.version + label))
            self.table.setItem(r, 3, _cell(strength))
        self.status.setText(f"{len(self.results)} result(s)" if self.results
                            else "No packages found - try a shorter or different name.")
        if self.results and self.results[0].score >= linker.SUGGEST:
            self.table.selectRow(0)

    def chosen(self) -> linker.Match | None:
        rows = {i.row() for i in self.table.selectedItems()}
        return self.results[rows.pop()] if rows else None

    def done(self, r: int) -> None:
        if self.task:
            self.task.cancel()
        super().done(r)


# ====================================================================== the tab
class UntrackedPage(QWidget):
    def __init__(self, win: "MainWindow") -> None:
        super().__init__()
        self.win = win
        self.task: Task | None = None
        self._last_task: Task | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 0)

        intro = QLabel("Installed programs that no package manager tracks. <b>Find winget matches</b> to link them "
                       "to a winget package: linked apps get checked for updates and show up in the Updates tab. "
                       "For the rest, use the program's own updater or website (right-click a row).")
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter…")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(260)
        self.btn_find = QPushButton("Find winget matches")
        self.btn_review = QPushButton("Review matches")
        self.btn_review.setObjectName("Primary")
        self.find_bar = QProgressBar()
        self.find_bar.setTextVisible(False)
        self.find_bar.setFixedWidth(140)
        self.find_bar.hide()
        self.show_hidden = QCheckBox("Show hidden")
        self.count = QLabel("")
        self.count.setObjectName("Muted")
        self.btn_export = QPushButton("Export CSV…")
        self.btn_export.setObjectName("Link")
        tools.addWidget(self.search)
        tools.addSpacing(8)
        tools.addWidget(self.btn_find)
        tools.addWidget(self.find_bar)
        tools.addWidget(self.btn_review)
        tools.addSpacing(8)
        tools.addWidget(self.show_hidden)
        tools.addStretch()
        tools.addWidget(self.count)
        tools.addWidget(self.btn_export)
        lay.addLayout(tools)

        self.notice = QLabel("")
        self.notice.setObjectName("Muted")
        self.notice.setWordWrap(True)
        self.notice.hide()
        lay.addWidget(self.notice)

        # Shown instead of the table while scanning or when the list can't be built
        self.empty = QWidget()
        el = QVBoxLayout(self.empty)
        el.addStretch()
        self.message = QLabel("Untracked apps appear here after a scan.")
        self.message.setObjectName("Muted")
        self.message.setAlignment(Qt.AlignCenter)
        self.message.setWordWrap(True)
        self.btn_module = QPushButton("Install the WinGet PowerShell module")
        self.btn_module.hide()
        el.addWidget(self.message)
        el.addWidget(self.btn_module, 0, Qt.AlignHCenter)
        el.addStretch()
        lay.addWidget(self.empty, 1)

        self.model = UntrackedModel(win)
        self.proxy = UntrackedProxy()
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        hh = self.table.horizontalHeader()
        hh.setHighlightSections(False)
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setSectionResizeMode(C_PUB, QHeaderView.Stretch)
        for col, w in ((C_NAME, 280), (C_VER, 110), (C_MATCH, 230), (C_LATEST, 120), (C_DATE, 95),
                       (C_TYPE, 135), (C_WEB, 150)):
            self.table.setColumnWidth(col, w)
        self.table.sortByColumn(C_NAME, Qt.AscendingOrder)
        self.table.hide()
        lay.addWidget(self.table, 1)

        self.search.textChanged.connect(self._filter)
        self.show_hidden.toggled.connect(self._show_hidden)
        self.btn_export.clicked.connect(self.export)
        self.btn_find.clicked.connect(self.find_matches)
        self.btn_review.clicked.connect(self.review)
        self.btn_module.clicked.connect(self.install_module)
        self.table.customContextMenuRequested.connect(self.context_menu)
        self.table.doubleClicked.connect(self._open_default)
        self._buttons()

    # ------------------------------------------------------------ data
    def set_scanning(self) -> None:
        if self.task:
            self.task.cancel()
        self.model.set_apps([])
        self.table.hide()
        self.btn_module.hide()
        self.notice.hide()
        self.message.setText("Scanning…")
        self.empty.show()
        self._buttons()
        self._update_count()

    def set_apps(self, apps: list[UntrackedApp] | None) -> None:
        if apps is None:
            self.message.setText("This list needs winget and Microsoft's WinGet PowerShell module "
                                 "(Microsoft.WinGet.Client). If the module is missing, NEFORUPDATE can install "
                                 "it for your user account - no administrator rights needed.")
            self.btn_module.show()
            self.model.set_apps([])
            self.table.hide()
            self.empty.show()
        else:
            cache = linker.load_matches()
            links = self.win.settings.links
            for a in apps:
                if not a.link_id and a.id in links:
                    a.link_id = links[a.id]["id"]
                if a.id in cache:
                    a.searched, a.matches = True, cache[a.id]
            self.model.set_apps(apps)
            self.btn_module.hide()
            self.empty.hide()
            self.table.show()
        self._buttons()
        self._update_count()

    def _filter(self, text: str) -> None:
        self.proxy.setFilterFixedString(text)
        self._update_count()

    def _show_hidden(self, on: bool) -> None:
        self.proxy.set_show_hidden(on)
        self._update_count()

    def reviewable(self) -> list[UntrackedApp]:
        return [a for a in self.model.apps if a.matches and not a.link_id and a.id not in self.model.hidden
                and not rules.locked_reason(a.name)]

    def _buttons(self) -> None:
        busy = self.win.model.busy if hasattr(self.win, "model") else False
        searching = self.task is not None
        has_apps = bool(self.model.apps)
        self.btn_find.setText("Stop" if searching else "Find winget matches")
        self.btn_find.setEnabled(has_apps and (searching or not busy))
        n = len(self.reviewable())
        self.btn_review.setText(f"Review matches ({n})" if n else "Review matches")
        self.btn_review.setEnabled(n > 0 and not searching and not busy)
        self.btn_export.setEnabled(has_apps)

    def _update_count(self) -> None:
        total = len(self.model.apps)
        hidden = sum(1 for a in self.model.apps if a.id in self.model.hidden)
        linked = sum(1 for a in self.model.apps if a.link_id)
        parts = [f"{total} untracked"] + ([f"{linked} linked"] if linked else []) + \
                ([f"{hidden} hidden"] if hidden else [])
        self.count.setText("  ·  ".join(parts) if total else "")
        if hasattr(self.win, "tabs"):
            self.win.tabs.setTabText(1, f"Untracked apps ({total - hidden})" if total else "Untracked apps")

    def busy_changed(self) -> None:
        self._buttons()

    # ------------------------------------------------------------ finding matches
    def find_matches(self) -> None:
        if self.task:  # "Stop"
            self.task.cancel()
            return
        apps = [a for a in self.model.apps
                if not a.link_id and a.id not in self.model.hidden and not rules.locked_reason(a.name)]
        if not apps:
            return
        self.find_bar.setRange(0, len(apps))
        self.find_bar.setValue(0)
        self.find_bar.show()
        self.notice.setText(f"Searching the winget catalog for {len(apps)} apps…")
        self.notice.show()
        win = self.win
        self.task = Task(lambda t: linker.search(apps, t.context(win, "winget search"), t.progress.emit))
        self.task.progress.connect(lambda n, total: self.find_bar.setValue(n))
        self.task.finished.connect(lambda res, err: self._found(apps, res, err))
        self.task.start()
        self._buttons()

    def _found(self, apps: list[UntrackedApp], found, error) -> None:
        # keep the finished task referenced: other slots of its signal may still be queued
        self._last_task, self.task = self.task, None
        cancelled = self._last_task is not None and self._last_task.cancel_event.is_set()
        self.find_bar.hide()
        if error and not cancelled:
            self.notice.setText(f"The search failed: {error}. See the log for details.")
        else:
            found = found or {}
            cache = linker.load_matches()
            for a in apps:
                if a.id in found:
                    a.searched, a.matches = True, found[a.id]
                    cache[a.id] = found[a.id]
            linker.save_matches(cache)
            self.model.refresh()
            n = len(self.reviewable())
            newer = sum(1 for a in self.reviewable()
                        if linker.compare_versions(a.matches[0].version, a.version) == 1)
            msg = (f"Searched {len(found)} of {len(apps)} apps{' (stopped early)' if cancelled else ''}. "
                   f"Likely winget packages for {n} app(s)"
                   + (f", {newer} with a newer version" if newer else "")
                   + (". Click Review matches to link them." if n else "."))
            self.notice.setText(msg)
            self.win.logger(f"[Untracked] {msg}")
        self.notice.show()
        self._buttons()

    def review(self) -> None:
        apps = self.reviewable()
        if not apps:
            return
        dlg = ReviewDialog(self, apps)
        if dlg.exec():
            pairs = dlg.chosen()
            for a, m in pairs:
                self._set_link(a, m)
            self._after_linking(len(pairs))

    # ------------------------------------------------------------ linking
    def _set_link(self, a: UntrackedApp, m: linker.Match) -> None:
        links = self.win.settings.links
        links[a.id] = {"id": m.id, "name": m.name, "app": a.name}
        self.win.settings.links = links
        a.link_id, a.latest = m.id, m.version
        self.win.logger(f"[Untracked] linked {a.name} ({a.version}) to winget package {m.id} ({m.version})")

    def _after_linking(self, n: int) -> None:
        if not n:
            return
        before = len(self.win.cands.get("linked", []))
        self.win.refresh_linked()
        newer = len(self.win.cands.get("linked", [])) - before
        self.model.refresh()
        self._buttons()
        self._update_count()
        msg = f"Linked {n} app(s)."
        if newer > 0:
            msg += f" {newer} {'has' if newer == 1 else 'have'} a newer version - see the Updates tab."
        self.notice.setText(msg)
        self.notice.show()

    def link_manually(self, a: UntrackedApp) -> None:
        dlg = LinkDialog(self, a)
        if dlg.exec() and dlg.chosen():
            self._set_link(a, dlg.chosen())
            self._after_linking(1)

    def unlink(self, a: UntrackedApp) -> None:
        links = self.win.settings.links
        links.pop(a.id, None)
        self.win.settings.links = links
        self.win.logger(f"[Untracked] unlinked {a.name} from {a.link_id}")
        a.link_id, a.latest = "", ""
        self.win.refresh_linked()
        self.model.refresh()
        self._buttons()
        self._update_count()

    # ------------------------------------------------------------ WinGet module
    def install_module(self) -> None:
        r = QMessageBox.question(
            self, "NEFORUPDATE",
            "Install Microsoft's WinGet PowerShell module (Microsoft.WinGet.Client) from the PowerShell "
            "Gallery for your user account?\n\nNo administrator rights needed. It takes about a minute, then "
            "NEFORUPDATE scans again.", QMessageBox.Ok | QMessageBox.Cancel)
        if r != QMessageBox.Ok:
            return
        self.btn_module.setEnabled(False)
        self.message.setText("Installing the WinGet PowerShell module…")
        win = self.win

        def work(t: Task):
            code, out = t.context(win, "WinGet module").ps(INSTALL_MODULE_SCRIPT, "Install-Module Microsoft.WinGet.Client")
            if "INSTALLED" not in out:
                raise RuntimeError("the install didn't finish - see the log")
            return out

        self.task = Task(work)
        self.task.finished.connect(self._module_done)
        self.task.start()

    def _module_done(self, _out, error) -> None:
        self._last_task, self.task = self.task, None
        self.btn_module.setEnabled(True)
        if error:
            self.message.setText(f"Couldn't install the module: {error}")
            return
        self.win.logger("[Untracked] WinGet PowerShell module installed - scanning again")
        self.win.start_scan()

    # ------------------------------------------------------------ row actions
    def _app(self, proxy_index) -> tuple[int, UntrackedApp]:
        row = self.proxy.mapToSource(proxy_index).row()
        return row, self.model.apps[row]

    @staticmethod
    def _search_url(a: UntrackedApp) -> QUrl:
        q = f"{a.name} {a.publisher} latest version download".strip()
        return QUrl("https://www.google.com/search?q=" + urllib.parse.quote_plus(q))

    def _open_default(self, index) -> None:
        _, a = self._app(index)
        QDesktopServices.openUrl(QUrl(a.website) if a.website else self._search_url(a))

    def context_menu(self, pos) -> None:
        idx = self.table.indexAt(pos)
        if not idx.isValid():
            return
        row, a = self._app(idx)
        busy = self.win.model.busy or self.task is not None
        menu = QMenu(self)
        lock = rules.locked_reason(a.name)
        if lock:
            menu.addAction(f"Can't link: {lock}").setEnabled(False)
        elif a.link_id:
            act = menu.addAction(f"Unlink from {a.link_id}")
            act.triggered.connect(lambda: self.unlink(a))
            act.setEnabled(not busy)
        else:
            if a.matches:
                m = a.matches[0]
                act = menu.addAction(f"Link to {m.id} ({m.version})")
                act.triggered.connect(lambda: (self._set_link(a, m), self._after_linking(1)))
                act.setEnabled(not busy)
            act = menu.addAction("Link to a winget package…")
            act.triggered.connect(lambda: self.link_manually(a))
            act.setEnabled(not busy)
        menu.addSeparator()
        if a.website:
            menu.addAction(f"Open website ({_host(a.website)})").triggered.connect(
                lambda: QDesktopServices.openUrl(QUrl(a.website)))
        menu.addAction("Search the web for the latest version").triggered.connect(
            lambda: QDesktopServices.openUrl(self._search_url(a)))
        if a.folder and os.path.isdir(a.folder):
            menu.addAction("Open install folder").triggered.connect(lambda: os.startfile(a.folder))
        menu.addAction("Copy name").triggered.connect(lambda: QApplication.clipboard().setText(a.name))
        menu.addSeparator()
        hidden = a.id in self.model.hidden
        menu.addAction("Unhide" if hidden else "Hide (I've checked this one)").triggered.connect(
            lambda: (self.model.toggle_hidden(row), self.proxy.refilter(), self._update_count(), self._buttons()))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def export(self) -> None:
        default = str(Path.home() / "Documents" / "untracked-apps.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export untracked apps", default, "CSV files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["Name", "Version", "Publisher", "Installed", "Size (MB)", "Type", "Website",
                            "Install folder", "Linked to", "Suggested match", "Latest", "Hidden", "Registry id"])
                for a in self.model.apps:
                    w.writerow([a.name, a.version, a.publisher, a.installed_on, a.size_mb or "", a.scope,
                                a.website, a.folder, a.link_id, a.matches[0].id if a.matches else "",
                                latest_of(a), "yes" if a.id in self.model.hidden else "", a.id])
        except OSError as e:
            QMessageBox.warning(self, "Export", f"Couldn't save the file:\n{e}")
            return
        self.win.logger(f"[Untracked] exported {len(self.model.apps)} rows to {path}")
