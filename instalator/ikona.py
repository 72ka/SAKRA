"""Vytvoří sakra.ico (16–256 px, PNG uvnitř) z ikony aplikace: python instalator/ikona.py"""
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from sakra.gui.aplikace import ikona  # noqa: E402


def main() -> None:
    app = QApplication.instance() or QApplication([])  # noqa: F841
    ik = ikona()
    obrazky = []
    for n in (16, 24, 32, 48, 64, 128, 256):
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        ik.pixmap(n, n).save(buf, "PNG")
        obrazky.append((n, bytes(ba)))
    hlavicka = struct.pack("<HHH", 0, 1, len(obrazky))
    posun = 6 + 16 * len(obrazky)
    zaznamy, data = b"", b""
    for n, png in obrazky:
        zaznamy += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(png), posun + len(data))
        data += png
    cil = Path(__file__).with_name("sakra.ico")
    cil.write_bytes(hlavicka + zaznamy + data)
    print(cil, cil.stat().st_size, "B")


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    os._exit(0)
