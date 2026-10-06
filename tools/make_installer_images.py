"""Wizard artwork for the installer, made from assets\\icon.png.

    python tools\\make_installer_images.py

Writes installer\\wizard-large-*.bmp (the tall panel on the welcome/finish pages) and
installer\\wizard-small-*.bmp (top-right corner), in the sizes Inno Setup picks from for
100-250 % display scaling.
"""
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QImage, QLinearGradient, QPainter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "installer"
LARGE = [(164, 314), (192, 386), (246, 459), (273, 556), (328, 604), (355, 700), (410, 797)]
SMALL = [(55, 55), (64, 68), (83, 80), (92, 97), (110, 106), (119, 123), (138, 140)]


def _fit_font(text: str, width: int, weight: QFont.Weight) -> QFont:
    f = QFont("Segoe UI")
    f.setWeight(weight)
    size = 40.0
    while size > 4:
        f.setPixelSize(int(size))
        if QFontMetrics(f).horizontalAdvance(text) <= width:
            break
        size -= 0.5
    return f


def large(icon: QImage, w: int, h: int) -> QImage:
    out = QImage(w, h, QImage.Format_RGB32)
    p = QPainter(out)
    p.setRenderHints(QPainter.SmoothPixmapTransform | QPainter.Antialiasing | QPainter.TextAntialiasing)
    grad = QLinearGradient(QPointF(0, 0), QPointF(0, h))   # the splash's navy into the icon's dark purple
    grad.setColorAt(0, QColor(6, 14, 40))
    grad.setColorAt(1, QColor(40, 8, 44))
    p.fillRect(out.rect(), grad)
    side = int(w * 0.62)
    top = int(h * 0.24)
    p.drawImage(QRect((w - side) // 2, top, side, side), icon)
    name = _fit_font("NEFORUPDATE", int(w * 0.84), QFont.Bold)
    p.setFont(name)
    p.setPen(QColor(255, 255, 255))
    y = top + side + int(h * 0.05)
    lh = QFontMetrics(name).height()
    p.drawText(QRect(0, y, w, lh), Qt.AlignHCenter | Qt.AlignTop, "NEFORUPDATE")
    by = QFont("Segoe UI")
    by.setPixelSize(max(9, int(name.pixelSize() * 0.6)))
    p.setFont(by)
    p.setPen(QColor(190, 190, 205))
    p.drawText(QRect(0, y + lh, w, lh), Qt.AlignHCenter | Qt.AlignTop, "by Neforus")
    p.end()
    return out


def small(icon: QImage, w: int, h: int) -> QImage:
    out = QImage(w, h, QImage.Format_RGB32)
    out.fill(Qt.white)
    side = min(w, h)
    p = QPainter(out)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.drawImage(QRect((w - side) // 2, (h - side) // 2, side, side), icon)
    p.end()
    return out


def main() -> None:
    app = QGuiApplication(sys.argv)  # needed for drawing text  # noqa: F841
    icon = QImage(str(ROOT / "assets" / "icon.png"))
    OUT.mkdir(exist_ok=True)
    for w, h in LARGE:
        large(icon, w, h).save(str(OUT / f"wizard-large-{w}x{h}.bmp"), "BMP")
    for w, h in SMALL:
        small(icon, w, h).save(str(OUT / f"wizard-small-{w}x{h}.bmp"), "BMP")
    print(f"Wrote {len(LARGE) + len(SMALL)} images to {OUT}")


if __name__ == "__main__":
    main()
