"""The NEFORUPDATE window."""
from __future__ import annotations

import ctypes
import os
import platform
import sys
import time

from PySide6.QtCore import (QAbstractTableModel, QModelIndex, QRect, QSortFilterProxyModel, Qt, QTimer)
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QSplashScreen, QSplitter,
                               QStyledItemDelegate, QTableView, QTabWidget, QVBoxLayout, QWidget)

from . import __version__, assets, linker, rules, theme
from .logger import Logger
from .merge import UpdateItem, merge
from .runner import is_admin
from .settings import Settings
from .sources import Job, Result, all_sources
from .sources.linked import candidates as linked_candidates
from .untracked_ui import UntrackedPage
from .workers import Bridge, ScanJob, UpdateJob

COLS = ["", "Name", "Installed", "Available", "Update via", "Note", "Status"]
C_CHECK, C_NAME, C_INST, C_AVAIL, C_VIA, C_NOTE, C_STATUS = range(7)


# ====================================================================== table model
class UpdatesModel(QAbstractTableModel):
    def __init__(self, win: "MainWindow") -> None:
        super().__init__()
        self.win = win
        self.items: list[UpdateItem] = []
        self.busy = False

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLS[section]
        return None

    def set_items(self, items: list[UpdateItem]) -> None:
        self.beginResetModel()
        self.items = items
        self.endResetModel()

    def row_of(self, key: str) -> int:
        for i, it in enumerate(self.items):
            if it.key == key:
                return i
        return -1

    def refresh_all(self) -> None:
        if self.items:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.items) - 1, len(COLS) - 1))

    def refresh_row(self, row: int) -> None:
        if row >= 0:
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLS) - 1))

    def via_text(self, it: UpdateItem) -> str:
        names = self.win.source_names
        others = [names.get(s, s) for s in it.candidates if s != it.chosen]
        text = names.get(it.chosen, it.chosen)
        if it.chosen == "winget" and it.cand.extra.get("winget_source") == "msstore":
            text += " (msstore)"
        return text + (f"  (+{', '.join(others)})" if others else "")

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        it = self.items[index.row()]
        col = index.column()
        t = self.win.tokens
        if role == Qt.CheckStateRole and col == C_CHECK:
            return Qt.Checked if it.selected else Qt.Unchecked
        if role in (Qt.DisplayRole, Qt.EditRole):
            return {C_NAME: it.name, C_INST: it.installed, C_AVAIL: it.available, C_VIA: self.via_text(it),
                    C_NOTE: it.note, C_STATUS: it.status}.get(col)
        if role == Qt.UserRole:  # sort key
            if col == C_CHECK:
                return 0 if it.selected else 1
            return (self.data(index) or "").lower()
        if role == Qt.ToolTipRole:
            if col == C_NAME:
                return "\n".join(f"{self.win.source_names.get(s, s)}: {c.package_id}  ({c.installed} -> {c.available})"
                                 for s, c in it.candidates.items())
            if col == C_VIA:
                tip = "Right-click to choose which package manager updates this app."
                return tip if len(it.candidates) > 1 else None
            if col in (C_NOTE, C_STATUS):
                return self.data(index) or None
            if col == C_CHECK and it.locked:
                return it.note or "Can't be updated from here"
        if role == Qt.ForegroundRole:
            if it.locked and col != C_STATUS:
                return QColor(t["muted"])
            if col == C_NOTE:
                return QColor(t["warn"])
            if col == C_STATUS:
                return QColor({"ok": t["ok"], "failed": t["bad"], "skipped": t["muted"]}.get(it.state, t["text"]))
        if role == Qt.FontRole and col == C_NAME:
            f = QApplication.font()
            f.setWeight(f.Weight.DemiBold)
            return f
        return None

    def flags(self, index):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == C_CHECK:
            it = self.items[index.row()]
            if not it.locked and not self.busy:
                return base | Qt.ItemIsUserCheckable
            return Qt.ItemIsSelectable
        return base

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.CheckStateRole and index.column() == C_CHECK:
            it = self.items[index.row()]
            checked = value in (Qt.Checked, 2) or getattr(value, "value", None) == 2
            it.selected = bool(checked)
            self.win.remember_tick(it)
            self.refresh_row(index.row())
            self.win.update_counts()
            return True
        return False


class SortProxy(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.setSortRole(Qt.UserRole)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setFilterKeyColumn(-1)


# ====================================================================== status cell with progress bar
class StatusDelegate(QStyledItemDelegate):
    def __init__(self, win: "MainWindow") -> None:
        super().__init__()
        self.win = win
        self.phase = 0.0

    def paint(self, painter: QPainter, option, index) -> None:
        model = self.win.model
        src = self.win.proxy.mapToSource(index)
        it = model.items[src.row()]
        if it.progress is None:
            return super().paint(painter, option, index)
        t = self.win.tokens
        painter.save()
        r = option.rect.adjusted(8, 4, -10, -4)
        painter.setPen(QColor(t["text"]))
        painter.drawText(QRect(r.left(), r.top(), r.width(), r.height() - 8), Qt.AlignLeft | Qt.AlignVCenter,
                         it.status)
        bar = QRect(r.left(), r.bottom() - 4, r.width(), 4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(t["track"]))
        painter.drawRoundedRect(bar, 2, 2)
        painter.setBrush(QColor(t["accent"]))
        if it.progress >= 0:
            painter.drawRoundedRect(QRect(bar.left(), bar.top(), int(bar.width() * it.progress / 100), 4), 2, 2)
        else:  # indeterminate: a sliding segment
            seg = max(24, bar.width() // 4)
            x = bar.left() + int((bar.width() + seg) * self.phase) - seg
            painter.setClipRect(bar)
            painter.drawRoundedRect(QRect(x, bar.top(), seg, 4), 2, 2)
        painter.restore()


# ====================================================================== source chip
class SourceChip(QFrame):
    ICONS = {"waiting": "...", "scanning": "", "done": "✓", "missing": "-", "error": "!", "cancelled": "x",
             "disabled": "-"}

    def __init__(self, name: str) -> None:
        super().__init__()
        self.setObjectName("Chip")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 8)
        lay.setSpacing(3)
        self.name = QLabel(name)
        self.name.setObjectName("ChipName")
        self.text = QLabel("waiting")
        self.text.setObjectName("Muted")
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        lay.addWidget(self.name)
        lay.addWidget(self.text)
        lay.addWidget(self.bar)
        self.state = "waiting"
        self.setMinimumWidth(130)

    def set_state(self, state: str, text: str) -> None:
        self.state = state
        icon = self.ICONS.get(state, "")
        self.text.setText(f"{icon} {text}".strip() if state in ("done", "error") else text)
        self.setToolTip(text)
        if state == "scanning":
            self.bar.setRange(0, 0)          # animated, never frozen
        else:
            self.bar.setRange(0, 1)
            self.bar.setValue(1 if state == "done" else 0)

    def summary(self) -> str:
        if self.state == "missing":  # "not installed", "none linked yet", ...
            return f"{self.name.text()}: {self.text.text()}"
        label = {"done": "✓", "scanning": "scanning…", "waiting": "waiting",
                 "error": "error", "cancelled": "cancelled", "disabled": "off"}[self.state]
        return f"{self.name.text()} {label}"


# ====================================================================== settings dialog
class SettingsDialog(QDialog):
    def __init__(self, win: "MainWindow") -> None:
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Settings")
        self.resize(420, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<b>Preferred package manager</b><br>When several can update the same app, "
                             "the highest one in this list is used. Untick to stop scanning a source."))
        self.list = QListWidget()
        disabled = set(win.settings.disabled_sources)
        for sid in win.settings.source_order:
            it = QListWidgetItem(win.source_names.get(sid, sid))
            it.setData(Qt.UserRole, sid)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked if sid in disabled else Qt.Checked)
            self.list.addItem(it)
        lay.addWidget(self.list)
        row = QHBoxLayout()
        up, down = QPushButton("Move up"), QPushButton("Move down")
        up.clicked.connect(lambda: self._move(-1))
        down.clicked.connect(lambda: self._move(1))
        row.addWidget(up)
        row.addWidget(down)
        row.addStretch()
        lay.addLayout(row)
        self.scoop = QCheckBox("Refresh Scoop app lists before scanning (runs 'scoop update')")
        self.scoop.setChecked(win.settings.scoop_refresh)
        lay.addWidget(self.scoop)
        reset = QPushButton("Forget my ticks and per-app source choices")
        reset.clicked.connect(self._reset)
        lay.addWidget(reset)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _move(self, d: int) -> None:
        r = self.list.currentRow()
        if r < 0 or not 0 <= r + d < self.list.count():
            return
        it = self.list.takeItem(r)
        self.list.insertItem(r + d, it)
        self.list.setCurrentRow(r + d)

    def _reset(self) -> None:
        self.win.settings.ticks = {}
        self.win.settings.forced_sources = {}
        QMessageBox.information(self, "Settings", "Done. Ticks go back to the recommendations on the next scan.")

    def accept(self) -> None:
        order, disabled = [], []
        for i in range(self.list.count()):
            it = self.list.item(i)
            sid = it.data(Qt.UserRole)
            order.append(sid)
            if it.checkState() != Qt.Checked:
                disabled.append(sid)
        s = self.win.settings
        s.source_order, s.disabled_sources, s.scoop_refresh = order, disabled, self.scoop.isChecked()
        super().accept()


# ====================================================================== main window
class MainWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.settings = Settings()
        self.sources = {s.id: s for s in all_sources()}
        self.source_names = {sid: s.name for sid, s in self.sources.items()}
        self.bridge = Bridge()
        self.logger = Logger(self.bridge.log.emit)
        self.admin = is_admin()
        self.cands: dict[str, list] = {}
        self.scan_job: ScanJob | None = None
        self.update_job: UpdateJob | None = None
        self.update_total = 0
        self.update_index = 0
        self.current_key = ""
        self.summary = {"ok": 0, "bad": 0, "reboot": []}
        self.tokens = theme.tokens(False)
        self._dark = None

        self.setWindowTitle("NEFORUPDATE")
        self.setMinimumSize(900, 560)
        self.resize(1180, 760)
        if self.settings.geometry():
            self.restoreGeometry(self.settings.geometry())
        self._build()
        self._wire()
        self.apply_theme()

        self.theme_timer = QTimer(self, interval=3000, timeout=self._theme_tick)
        self.theme_timer.start()
        self.anim = QTimer(self, interval=40, timeout=self._animate)
        QTimer.singleShot(200, self.start_scan)

    # ------------------------------------------------------------ layout
    def _build(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 16, 22, 14)
        outer.setSpacing(10)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("NEFORUPDATE")
        title.setObjectName("Title")
        self.subtitle = QLabel("Starting…")
        self.subtitle.setObjectName("Muted")
        titles.addWidget(title)
        titles.addWidget(self.subtitle)
        head.addLayout(titles)
        head.addStretch()
        self.theme_box = QComboBox()
        self.theme_box.addItems(["System", "Light", "Dark"])
        self.theme_box.setCurrentIndex(["system", "light", "dark"].index(self.settings.theme))
        self.theme_box.setToolTip("Theme")
        self.btn_settings = QPushButton("Settings")
        self.btn_scan = QPushButton("Check for updates")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("Danger")
        self.btn_cancel.hide()
        self.btn_update = QPushButton("Update all")
        self.btn_update.setObjectName("Primary")
        for w in (self.theme_box, self.btn_settings, self.btn_scan, self.btn_cancel, self.btn_update):
            head.addWidget(w)
        outer.addLayout(head)

        self.banner = QLabel()
        self.banner.setObjectName("Banner")
        self.banner.setWordWrap(True)
        self.banner.setTextFormat(Qt.RichText)
        self.banner.hide()
        outer.addWidget(self.banner)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.chips: dict[str, SourceChip] = {}
        for sid in self.sources:
            chip = SourceChip(self.source_names[sid])
            self.chips[sid] = chip
            chips.addWidget(chip)
        chips.addStretch()
        outer.addLayout(chips)

        prog = QVBoxLayout()
        prog.setSpacing(4)
        self.overall_label = QLabel("")
        self.overall = QProgressBar()
        self.overall.setTextVisible(False)
        self.current = QProgressBar()
        self.current.setTextVisible(False)
        self.current.hide()
        prog.addWidget(self.overall_label)
        prog.addWidget(self.overall)
        prog.addWidget(self.current)
        outer.addLayout(prog)

        updates_page = QWidget()
        page = QVBoxLayout(updates_page)
        page.setContentsMargins(0, 10, 0, 0)
        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter…")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(280)
        self.btn_all = QPushButton("Select all")
        self.btn_none = QPushButton("Select none")
        self.btn_reco = QPushButton("Recommended")
        for b in (self.btn_all, self.btn_none, self.btn_reco):
            b.setObjectName("Link")
        self.btn_log = QPushButton("Show log")
        self.btn_log.setObjectName("Link")
        self.btn_logdir = QPushButton("Open log file")
        self.btn_logdir.setObjectName("Link")
        tools.addWidget(self.search)
        tools.addSpacing(10)
        for b in (self.btn_all, self.btn_none, self.btn_reco):
            tools.addWidget(b)
        tools.addStretch()
        page.addLayout(tools)

        self.model = UpdatesModel(self)
        self.proxy = SortProxy()
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setHighlightSections(False)
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setSectionResizeMode(C_NOTE, QHeaderView.Stretch)
        for col, w in ((C_CHECK, 34), (C_NAME, 290), (C_INST, 120), (C_AVAIL, 120), (C_VIA, 150), (C_STATUS, 230)):
            self.table.setColumnWidth(col, w)
        self.delegate = StatusDelegate(self)
        self.table.setItemDelegateForColumn(C_STATUS, self.delegate)
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.sortByColumn(C_NAME, Qt.AscendingOrder)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(20000)
        self.log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.log_view.hide()

        page.addWidget(self.table, 1)

        self.untracked = UntrackedPage(self)
        self.tabs = QTabWidget()
        # Not document mode: there Qt draws a second base line under the corner buttons at a different
        # height. The single full-width separator comes from the pane's top border (theme.py).
        self.tabs.addTab(updates_page, "Updates")
        self.tabs.addTab(self.untracked, "Untracked apps")
        corner = QWidget()
        cl = QHBoxLayout(corner)
        cl.setContentsMargins(0, 0, 0, 3)  # lift the links to the tab labels' baseline
        cl.addWidget(self.btn_log)
        cl.addWidget(self.btn_logdir)
        self.tabs.setCornerWidget(corner, Qt.TopRightCorner)

        split = QSplitter(Qt.Vertical)
        split.addWidget(self.tabs)
        split.addWidget(self.log_view)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        outer.addWidget(split, 1)

        foot = QHBoxLayout()
        version = QLabel(f'v{__version__}  ·  <a href="{assets.SOURCE_URL}" style="text-decoration:none">'
                         'Open source (MIT)</a>')
        version.setObjectName("Muted")
        version.setTextFormat(Qt.RichText)
        version.setOpenExternalLinks(True)
        version.setToolTip(assets.SOURCE_URL)
        credit = QLabel(f'<a href="{assets.CREDIT_URL}" style="text-decoration:none">Made by Neforus</a>')
        credit.setObjectName("Credit")
        credit.setTextFormat(Qt.RichText)
        credit.setOpenExternalLinks(True)
        credit.setToolTip(assets.CREDIT_URL)
        foot.addWidget(version)
        foot.addStretch()
        foot.addWidget(credit)
        outer.addLayout(foot)

    def _wire(self) -> None:
        b = self.bridge
        b.log.connect(self.log_view.appendPlainText)
        b.sourceState.connect(self.on_source_state)
        b.sourceResult.connect(self.on_source_result)
        b.scanDone.connect(self.on_scan_done)
        b.itemStarted.connect(self.on_item_started)
        b.itemProgress.connect(self.on_item_progress)
        b.itemFinished.connect(self.on_item_finished)
        b.updateDone.connect(self.on_update_done)
        b.untrackedReady.connect(self.untracked.set_apps)
        self.btn_scan.clicked.connect(self.start_scan)
        self.btn_update.clicked.connect(self.start_update)
        self.btn_cancel.clicked.connect(self.cancel)
        self.btn_settings.clicked.connect(self.open_settings)
        self.btn_all.clicked.connect(lambda: self.bulk_select("all"))
        self.btn_none.clicked.connect(lambda: self.bulk_select("none"))
        self.btn_reco.clicked.connect(lambda: self.bulk_select("reco"))
        self.btn_log.clicked.connect(self.toggle_log)
        self.btn_logdir.clicked.connect(lambda: os.startfile(str(self.logger.path)))
        self.search.textChanged.connect(self.proxy.setFilterFixedString)
        self.theme_box.currentIndexChanged.connect(self.on_theme_choice)
        self.table.customContextMenuRequested.connect(self.context_menu)

    # ------------------------------------------------------------ theme
    def on_theme_choice(self, i: int) -> None:
        self.settings.theme = ["system", "light", "dark"][i]
        self.apply_theme()

    def _theme_tick(self) -> None:
        if self.settings.theme == "system" and theme.resolve("system") != self._dark:
            self.apply_theme()

    def apply_theme(self) -> None:
        dark = theme.resolve(self.settings.theme)
        if dark == self._dark:
            return
        self._dark = dark
        self.tokens = theme.apply(self.app, dark)
        theme.set_title_bar(int(self.winId()), dark)
        if self.isVisible():  # Windows 10 repaints the title bar only after a frame change
            self.resize(self.width() + 1, self.height())
            self.resize(self.width() - 1, self.height())
        self.model.refresh_all()
        um = self.untracked.model
        if um.apps:
            um.dataChanged.emit(um.index(0, 0), um.index(len(um.apps) - 1, um.columnCount() - 1))

    # ------------------------------------------------------------ helpers
    def set_busy(self, busy: bool, updating: bool = False) -> None:
        self.model.busy = busy
        for w in (self.btn_scan, self.btn_update, self.btn_settings, self.btn_all, self.btn_none, self.btn_reco):
            w.setEnabled(not busy)
        self.btn_cancel.setVisible(busy)
        self.btn_cancel.setText("Stop after this one" if updating else "Cancel")
        if busy:
            self.anim.start()
        else:
            self.anim.stop()
            self.update_counts()
        self.model.refresh_all()
        self.untracked.busy_changed()

    def _animate(self) -> None:
        self.delegate.phase = (self.delegate.phase + 0.02) % 1.0
        row = self.model.row_of(self.current_key)
        if row >= 0:
            self.model.dataChanged.emit(self.model.index(row, C_STATUS), self.model.index(row, C_STATUS))

    def selectable(self) -> list[UpdateItem]:
        return [i for i in self.model.items if not i.locked]

    def update_counts(self) -> None:
        if self.model.busy:
            return
        items = self.selectable()
        sel = [i for i in items if i.selected]
        total = len(self.model.items)
        self.btn_update.setEnabled(bool(sel))
        if not sel:
            self.btn_update.setText("Nothing selected")
        elif len(sel) == len(items):
            self.btn_update.setText(f"Update all ({len(sel)})")
        else:
            self.btn_update.setText(f"Update selected ({len(sel)})")
        locked = total - len(items)
        extra = f"  ·  {locked} list-only or locked" if locked else ""
        self.subtitle.setText(f"{total} updates found  ·  {len(sel)} selected{extra}" if total
                              else "Everything is up to date.")

    def default_tick(self, it: UpdateItem) -> bool:
        return not it.caution and not it.locked

    def remember_tick(self, it: UpdateItem) -> None:
        ticks = self.settings.ticks
        if it.selected == self.default_tick(it):
            ticks.pop(it.key, None)
        else:
            ticks[it.key] = it.selected
        self.settings.ticks = ticks

    def bulk_select(self, how: str) -> None:
        for it in self.selectable():
            it.selected = True if how == "all" else False if how == "none" else self.default_tick(it)
        if how == "reco":
            self.settings.ticks = {}
        self.model.refresh_all()
        self.update_counts()

    def toggle_log(self) -> None:
        self.log_view.setVisible(not self.log_view.isVisible())
        self.btn_log.setText("Hide log" if self.log_view.isVisible() else "Show log")

    def show_banner(self) -> None:
        msgs = []
        build = int(platform.version().split(".")[-1]) if platform.version().count(".") >= 2 else 0
        if 0 < build < 22000:
            msgs.append("<b>Windows 10 is out of support.</b> Windows Update only delivers security fixes to this PC "
                        "if it's enrolled in Extended Security Updates (Settings › Windows Update).")
        if not self.admin and any(i.selected and i.chosen == "choco" for i in self.model.items):
            msgs.append("Chocolatey updates need administrator rights - Windows will ask once for the whole batch.")
        if self.summary["reboot"]:
            msgs.append("<b>Restart needed</b> to finish: " + ", ".join(self.summary["reboot"]) +
                        ". NEFORUPDATE never restarts your PC by itself.")
        self.banner.setText("<br>".join(msgs))
        self.banner.setVisible(bool(msgs))

    # ------------------------------------------------------------ scanning
    def start_scan(self) -> None:
        if self.model.busy:
            return
        self.cands.clear()
        self.model.set_items([])
        self.untracked.set_scanning()
        self.summary = {"ok": 0, "bad": 0, "reboot": []}
        disabled = set(self.settings.disabled_sources)
        active = [s for sid, s in self.sources.items() if sid not in disabled]
        for sid, chip in self.chips.items():
            chip.set_state("disabled" if sid in disabled else "waiting", "off" if sid in disabled else "waiting")
        self.scan_total = len(active)
        self.overall.setRange(0, max(1, self.scan_total))
        self.overall.setValue(0)
        self.current.hide()
        self.logger(f"=== Scan started ({'administrator' if self.admin else 'standard user'})")
        self.set_busy(True)
        self._scan_label()
        self.scan_job = ScanJob(active, self.settings.as_source_settings(), self.bridge, self.logger)
        self.scan_job.start()

    def _scan_label(self) -> None:
        parts = [c.summary() for sid, c in self.chips.items() if c.state != "disabled"]
        self.overall_label.setText("  ·  ".join(parts))

    def on_source_state(self, sid: str, state: str, text: str) -> None:
        self.chips[sid].set_state(state, text)
        finished = sum(1 for c in self.chips.values() if c.state in ("done", "missing", "error", "cancelled"))
        self.overall.setValue(finished)
        self._scan_label()

    def on_source_result(self, sid: str, cands: list) -> None:
        self.cands[sid] = cands
        self.rebuild()

    def rebuild(self) -> None:
        old = {i.key: i for i in self.model.items}
        all_c = [c for lst in self.cands.values() for c in lst]
        items = merge(all_c, self.settings.source_order, self.settings.forced_sources)
        ticks = self.settings.ticks
        for it in items:
            if it.locked:
                it.selected = False
            elif it.key in old:
                it.selected = old[it.key].selected
            else:
                it.selected = ticks.get(it.key, self.default_tick(it))
            if len(it.candidates) > 1:
                ins = {c.installed for c in it.candidates.values() if c.installed}
                if len(ins) > 1:
                    it.extra_notes.append("Sources report different installed versions")
        self.model.set_items(items)
        self.update_counts()

    def refresh_linked(self) -> None:
        """Recompute linked-app updates right after linking/unlinking, without a full rescan."""
        links = self.settings.links
        latest = dict(self.sources["linked"].latest)
        for a in self.untracked.model.apps:
            if a.link_id and a.latest:
                latest[a.link_id] = linker.Match(a.link_id, "", a.latest, 0)
        cands = linked_candidates(links, latest, self.logger)
        for c in cands:
            rules.apply(c)
        self.cands["linked"] = cands
        if links:
            self.chips["linked"].set_state("done", f"{len(cands)} found")
        else:
            self.chips["linked"].set_state("missing", "none linked yet")
        self._scan_label()
        self.rebuild()
        self.show_banner()

    def on_scan_done(self, cancelled: bool) -> None:
        self.scan_job = None
        self.set_busy(False)
        self._scan_label()
        n = len(self.model.items)
        self.logger(f"=== Scan {'cancelled' if cancelled else 'finished'}: {n} updates")
        if cancelled:
            self.subtitle.setText(f"Scan cancelled - showing {n} found so far")
        self.show_banner()

    # ------------------------------------------------------------ updating
    def start_update(self) -> None:
        sel = [i for i in self.selectable() if i.selected]
        if not sel:
            return
        names = "\n".join(f"  • {i.name}  ({self.source_names[i.chosen]})" for i in sel[:12])
        more = f"\n  …and {len(sel) - 12} more" if len(sel) > 12 else ""
        admin_note = ("\n\nChocolatey updates will ask for administrator permission once."
                      if not self.admin and any(i.chosen == "choco" for i in sel) else "")
        msg = (f"Update {len(sel)} app(s), one at a time?\n\n{names}{more}\n\n"
               f"Installers may close the apps they update, so save your work first.{admin_note}")
        if QMessageBox.question(self, "NEFORUPDATE", msg, QMessageBox.Ok | QMessageBox.Cancel) != QMessageBox.Ok:
            return
        for it in self.model.items:
            it.progress = None
            if it.selected and not it.locked:
                it.state, it.status = "queued", "Waiting"
            elif not it.locked:
                it.state, it.status = "skipped", "Not selected"
        self.summary = {"ok": 0, "bad": 0, "reboot": []}
        self.update_total = len(sel)
        self.update_index = 0
        self.overall.setRange(0, 1000)
        self.overall.setValue(0)
        self.current.show()
        self.current.setRange(0, 0)
        self.overall_label.setText(f"Starting {len(sel)} update(s)…")
        self.set_busy(True, updating=True)
        jobs = [Job(i.key, i.cand) for i in sel]
        self.logger(f"=== Updating {len(jobs)} item(s)")
        self.update_job = UpdateJob(self.sources, jobs, self.settings.as_source_settings(), self.bridge, self.logger)
        self.update_job.start()

    def _item(self, key: str) -> tuple[int, UpdateItem | None]:
        row = self.model.row_of(key)
        return row, (self.model.items[row] if row >= 0 else None)

    def _overall(self, frac: float) -> None:
        done = max(0, self.update_index - 1) + max(0.0, min(1.0, frac))
        self.overall.setValue(int(1000 * done / max(1, self.update_total)))

    def on_item_started(self, key: str, n: int, total: int) -> None:
        row, it = self._item(key)
        self.update_index, self.current_key = n, key
        if it:
            it.state, it.status, it.progress = "running", "Starting", -1
            self.model.refresh_row(row)
            self.table.scrollTo(self.proxy.mapFromSource(self.model.index(row, 0)))
            self.overall_label.setText(f"Updating {n} of {total}: {it.name}")
        self.current.setRange(0, 0)
        self._overall(0)

    def on_item_progress(self, key: str, pct: float, text: str) -> None:
        row, it = self._item(key)
        if not it:
            return
        it.progress = pct if pct >= 0 else -1
        it.status = f"{text} {pct:.0f}%" if pct >= 0 else text
        if it.state != "running":
            it.state = "queued"
        self.model.refresh_row(row)
        if key == self.current_key:
            if pct >= 0:
                self.current.setRange(0, 100)
                self.current.setValue(int(pct))
                self._overall(pct / 100 * 0.9)   # last 10 % is the install step
            else:
                self.current.setRange(0, 0)
            self.overall_label.setText(f"Updating {self.update_index} of {self.update_total}: {it.name} - {it.status}")

    def on_item_finished(self, key: str, res: Result) -> None:
        row, it = self._item(key)
        if not it:
            return
        it.progress = None
        it.status = res.message
        it.state = "ok" if res.ok else ("skipped" if res.skipped else "failed")
        if res.ok:
            self.summary["ok"] += 1
            it.selected = False
        elif not res.skipped:
            self.summary["bad"] += 1
        if res.reboot:
            it.reboot = True
            self.summary["reboot"].append(it.name)
        self.logger(f"[result] {it.name}: {res.message}")
        self.model.refresh_row(row)
        self._overall(1)

    def on_update_done(self, cancelled: bool) -> None:
        self.update_job = None
        self.current_key = ""
        self.current.hide()
        self.overall.setValue(1000)
        s = self.summary
        msg = f"Done: {s['ok']} updated, {s['bad']} failed"
        if s["reboot"]:
            msg += f", {len(s['reboot'])} need a restart"
        if cancelled:
            msg += " (stopped early)"
        self.overall_label.setText(msg)
        self.logger("=== " + msg)
        self.set_busy(False)
        self.subtitle.setText(msg)
        self.show_banner()
        if s["bad"]:
            failed = [f"• {i.name}: {i.status}" for i in self.model.items if i.state == "failed"]
            QMessageBox.warning(self, "NEFORUPDATE", msg + "\n\n" + "\n".join(failed[:15]))
        elif s["reboot"]:
            QMessageBox.information(self, "NEFORUPDATE", msg + "\n\nRestart when it suits you.")

    def cancel(self) -> None:
        if self.scan_job:
            self.scan_job.cancel()
            self.logger("=== Cancelling scan")
        if self.update_job:
            self.update_job.cancel()
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText("Stopping after this one…")
            self.logger("=== Will stop after the current update")

    # ------------------------------------------------------------ misc
    def context_menu(self, pos) -> None:
        idx = self.table.indexAt(pos)
        if not idx.isValid() or self.model.busy:
            return
        it = self.model.items[self.proxy.mapToSource(idx).row()]
        menu = QMenu(self)
        if len(it.candidates) > 1 and not it.locked:
            sub = menu.addMenu("Update with")
            for sid in it.candidates:
                act = QAction(self.source_names[sid], sub, checkable=True, checked=sid == it.chosen)
                act.triggered.connect(lambda _=False, s=sid: self.force_source(it, s))
                sub.addAction(act)
        copy = menu.addAction("Copy package ID")
        copy.triggered.connect(lambda: QApplication.clipboard().setText(it.cand.package_id))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def force_source(self, it: UpdateItem, sid: str) -> None:
        forced = self.settings.forced_sources
        forced[it.key] = sid
        self.settings.forced_sources = forced
        it.chosen, it.forced_source = sid, sid
        self.model.refresh_row(self.model.row_of(it.key))

    def open_settings(self) -> None:
        if SettingsDialog(self).exec():
            self.rebuild()
            self.logger("Settings changed")

    def closeEvent(self, e) -> None:
        if self.update_job:
            r = QMessageBox.warning(self, "NEFORUPDATE", "Updates are still running. Quit anyway?\n\n"
                                    "The installer that's running now will keep going; the rest are skipped.",
                                    QMessageBox.Yes | QMessageBox.No)
            if r != QMessageBox.Yes:
                e.ignore()
                return
            self.update_job.cancel()
        if self.scan_job:
            self.scan_job.cancel()
        self.settings.set_geometry(self.saveGeometry())
        e.accept()


def _pyinstaller_splash():
    """The splash PyInstaller shows while the .exe unpacks (None when running from source)."""
    if not getattr(sys, "frozen", False):
        return None
    try:
        import pyi_splash  # only exists inside an .exe built with --splash
        return pyi_splash
    except ImportError:
        return None


def run_gui() -> int:
    try:  # own taskbar identity (matches the Start menu shortcut), so Windows shows the NEFORUPDATE icon
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Neforus.NEFORUPDATE")
        # Lets the installer/uninstaller see that NEFORUPDATE is running (AppMutex in installer\neforupdate.iss)
        _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "NEFORUPDATE_running")  # noqa: F841 (lives until exit)
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("NEFORUPDATE")
    app.setOrganizationName("Neforus")
    app.setWindowIcon(QIcon(str(assets.ICON)))

    exe_splash = _pyinstaller_splash()
    qt_splash = None
    if exe_splash is None:  # from source: show the same splash with Qt
        pix = QPixmap(str(assets.SPLASH))
        if not pix.isNull():
            screen = app.primaryScreen()
            pix.setDevicePixelRatio(screen.devicePixelRatio())  # 1280x720 real pixels, sharp at any scaling
            room = screen.availableGeometry()
            if pix.width() / pix.devicePixelRatio() > room.width() * 0.8:
                pix = pix.scaledToWidth(int(room.width() * 0.8 * pix.devicePixelRatio()), Qt.SmoothTransformation)
            qt_splash = QSplashScreen(pix)
            qt_splash.show()
            app.processEvents()
    shown_at = time.monotonic()

    win = MainWindow(app)

    def reveal() -> None:
        win.show()
        if qt_splash:
            qt_splash.finish(win)
        if exe_splash:
            exe_splash.close()

    # The .exe's splash has been up since launch; from source, keep it at least 1.5 s so it doesn't just flash
    delay = 0 if exe_splash else max(0, int((1.5 - (time.monotonic() - shown_at)) * 1000))
    QTimer.singleShot(delay, reveal)
    return app.exec()
