"""Turn a square image into NEFORUPDATE's icons.

    python tools\\make_icon.py path\\to\\image.png

Writes assets\\neforupdate.ico (16-256 px; used for the .exe) and assets\\icon.png (512 px; the
window and taskbar icon). The image is scaled down, never cropped. Rebuild the .exe afterwards
with build.cmd.
"""
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


def scaled(img: QImage, size: int) -> QImage:
    # halve repeatedly first: much cleaner small icons than one big jump
    while img.width() >= size * 2:
        img = img.scaled(img.width() // 2, img.height() // 2, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return img.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(
        QImage.Format_ARGB32)


def png_bytes(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def dib_bytes(img: QImage) -> bytes:
    """32-bit BMP icon frame (what every Windows component can read): header + bottom-up BGRA + AND mask."""
    w, h = img.width(), img.height()
    raw = bytes(img.constBits())  # ARGB32 in memory = B,G,R,A per pixel
    bpl = img.bytesPerLine()
    pixels = b"".join(raw[y * bpl:y * bpl + w * 4] for y in reversed(range(h)))
    mask = b"\x00" * (((w + 31) // 32) * 4 * h)  # transparency comes from the alpha channel
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(pixels) + len(mask), 0, 0, 0, 0)
    return header + pixels + mask


def make_ico(img: QImage, path: Path) -> None:
    # small frames as BMP, 256 px as PNG: the standard layout Windows Explorer expects
    frames = [png_bytes(scaled(img, s)) if s == 256 else dib_bytes(scaled(img, s)) for s in SIZES]
    out = struct.pack("<HHH", 0, 1, len(SIZES))
    offset = 6 + 16 * len(SIZES)
    for s, data in zip(SIZES, frames):
        out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.write_bytes(out + b"".join(frames))


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    img = QImage(sys.argv[1])
    if img.isNull():
        print(f"Can't read {sys.argv[1]}")
        return 1
    if img.width() != img.height():
        side = min(img.width(), img.height())  # centre a non-square image instead of stretching it
        img = img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side)
    img = img.convertToFormat(QImage.Format_ARGB32)
    ASSETS.mkdir(exist_ok=True)
    make_ico(img, ASSETS / "neforupdate.ico")
    scaled(img, 512).save(str(ASSETS / "icon.png"), "PNG")
    print(f"Wrote {ASSETS / 'neforupdate.ico'} ({', '.join(map(str, SIZES))} px) and {ASSETS / 'icon.png'} (512 px)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
