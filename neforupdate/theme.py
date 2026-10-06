"""Light/dark themes that follow Windows, plus a dark title bar on Windows 10 (build 19041+)."""
from __future__ import annotations

import ctypes
import winreg

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

LIGHT = {
    "window": "#f5f5f7", "base": "#ffffff", "alt": "#f7f7f9", "text": "#1d1d1f", "muted": "#6e6e73",
    "border": "#dcdce1", "button": "#e8e8ed", "accent": "#0071e3", "accent_text": "#ffffff",
    "warn": "#b25000", "ok": "#1a7f37", "bad": "#c62828", "chip": "#ffffff", "track": "#e3e3e8",
}
DARK = {
    "window": "#1c1c1e", "base": "#232326", "alt": "#28282b", "text": "#ececf0", "muted": "#9a9aa2",
    "border": "#3a3a3e", "button": "#2f2f33", "accent": "#0a84ff", "accent_text": "#ffffff",
    "warn": "#ffa94d", "ok": "#4cc26b", "bad": "#ff6b6b", "chip": "#26262a", "track": "#3a3a3e",
}


def system_is_dark() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def resolve(mode: str) -> bool:
    return system_is_dark() if mode == "system" else mode == "dark"


def tokens(dark: bool) -> dict:
    return DARK if dark else LIGHT


def apply(app: QApplication, dark: bool) -> dict:
    t = tokens(dark)
    app.setStyle("Fusion")
    p = QPalette()
    roles = {
        QPalette.Window: t["window"], QPalette.WindowText: t["text"], QPalette.Base: t["base"],
        QPalette.AlternateBase: t["alt"], QPalette.Text: t["text"], QPalette.Button: t["button"],
        QPalette.ButtonText: t["text"], QPalette.Highlight: t["accent"], QPalette.HighlightedText: t["accent_text"],
        QPalette.ToolTipBase: t["base"], QPalette.ToolTipText: t["text"], QPalette.PlaceholderText: t["muted"],
        QPalette.Link: t["accent"],
    }
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(t["muted"]))
    # Existing widgets keep the palette they were polished with while a stylesheet is set,
    # so drop the sheet, switch the palette, re-apply the sheet, then push the palette down.
    app.setStyleSheet("")
    app.setPalette(p)
    from .assets import CHECK  # local import: assets has no Qt dependency, but keep theme importable alone
    app.setStyleSheet(STYLE.format(**t, check=CHECK.as_posix()))
    for w in app.topLevelWidgets():
        w.setPalette(p)
    return t


def set_title_bar(hwnd: int, dark: bool) -> None:
    """DWMWA_USE_IMMERSIVE_DARK_MODE: 20 on Windows 10 20H1+ (19041+), 19 on older builds."""
    value = ctypes.c_int(1 if dark else 0)
    for attr in (20, 19):
        try:
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), attr, ctypes.byref(value),
                                                          ctypes.sizeof(value)) == 0:
                return
        except Exception:
            return


STYLE = """
QWidget {{ font-family: "Segoe UI"; font-size: 10pt; }}
QToolTip {{ border: 1px solid {border}; padding: 4px; }}
#Title {{ font-size: 22pt; font-weight: 700; }}
#Credit {{ font-weight: 600; }}
#Muted {{ color: {muted}; }}
#Banner {{ background: {chip}; border: 1px solid {border}; border-radius: 8px; padding: 8px 12px; }}
#Chip {{ background: {chip}; border: 1px solid {border}; border-radius: 10px; }}
#ChipName {{ font-weight: 600; }}
QPushButton {{ background: {button}; border: none; border-radius: 15px; padding: 6px 16px; min-height: 18px; }}
QPushButton:hover {{ background: {border}; }}
QPushButton:disabled {{ color: {muted}; }}
QPushButton#Primary {{ background: {accent}; color: {accent_text}; font-weight: 600; }}
QPushButton#Primary:disabled {{ background: {track}; color: {muted}; }}
QPushButton#Danger {{ background: {bad}; color: #ffffff; font-weight: 600; }}
QPushButton#Link {{ background: transparent; color: {accent}; padding: 2px 6px; border-radius: 4px; }}
QPushButton#Link:hover {{ background: {button}; }}
QComboBox, QLineEdit {{ background: {base}; border: 1px solid {border}; border-radius: 6px; padding: 4px 8px; }}
QTableView {{ background: {base}; alternate-background-color: {alt}; border: 1px solid {border};
             border-radius: 10px; gridline-color: transparent; selection-background-color: {track};
             selection-color: {text}; }}
QHeaderView::section {{ background: {base}; color: {muted}; border: none; border-bottom: 1px solid {border};
                        padding: 6px 8px; }}
QPlainTextEdit {{ background: {base}; border: 1px solid {border}; border-radius: 8px;
                  font-family: Consolas; font-size: 9pt; }}
QProgressBar {{ background: {track}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}
QSplitter::handle {{ background: transparent; height: 8px; }}
QTabWidget::pane {{ border: none; border-top: 1px solid {border}; top: -1px; }}
QTabWidget::tab-bar {{ left: 0px; }}
QTabBar::tab {{ background: transparent; color: {muted}; padding: 6px 14px; margin-right: 4px;
               border: none; border-bottom: 2px solid transparent; font-weight: 600; }}
QTabBar::tab:selected {{ color: {text}; border-bottom: 2px solid {accent}; }}
QTabBar::tab:hover:!selected {{ color: {text}; }}
QListWidget {{ background: {base}; border: 1px solid {border}; border-radius: 6px; }}
/* Checkboxes drawn by us: Fusion's own are white-on-white in the light theme */
QTableView::indicator, QListWidget::indicator, QCheckBox::indicator {{
    width: 14px; height: 14px; border: 1px solid {muted}; border-radius: 4px; background: {base}; }}
QTableView::indicator:checked, QListWidget::indicator:checked, QCheckBox::indicator:checked {{
    background: {accent}; border-color: {accent}; image: url("{check}"); }}
QTableView::indicator:disabled, QCheckBox::indicator:disabled {{ border-color: {border}; background: {alt}; }}
QTableView::indicator:checked:disabled {{ background: {muted}; border-color: {muted}; }}
"""
