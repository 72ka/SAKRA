# PyInstaller: složka dist/SAKRA se SAKRA(.exe) (okno) a sakra-cli(.exe) (příkazová řádka, dávky).
# Sestavení: pyinstaller --noconfirm --clean instalator/sakra.spec   (spouštět z kořene projektu)
import sys
from pathlib import Path

KOREN = Path(SPECPATH).parent
WIN = sys.platform == "win32"

# moduly Qt, které SAKRA nepoužívá (zmenší balík o desítky MB)
NEPOUZITE = ["tkinter", "matplotlib", "scipy", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickControls2",
             "PySide6.QtQuickWidgets", "PySide6.QtQuickTest", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
             "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtXml",
             "PySide6.QtSvgWidgets", "PySide6.QtConcurrent", "PySide6.QtDBus", "PySide6.QtNetwork",
             "PySide6.QtLabsStyleKit", "PySide6.QtQmlFeatures"]

from PyInstaller.utils.hooks import collect_data_files, copy_metadata


def licence_knihoven():
    """Metadata (.dist-info) použitých knihoven – jsou v nich jejich licenční texty (LGPL, BSD, MIT…)."""
    out = []
    for balik in ("PySide6_Essentials", "shiboken6", "numpy", "soundfile", "sounddevice", "pycparser", "cffi",
                  "opencv-python-headless",
                  "openpyxl", "et_xmlfile", "zx",
                  "py7zr", "pyzstd", "pybcj", "pyppmd", "inflate64", "multivolumefile", "brotli", "pycryptodomex",
                  "texttable", "psutil"):
        try:
            out += copy_metadata(balik)
        except Exception:  # balík v prostředí sestavení chybí nebo nemá metadata
            pass
    return out


# kamera (OpenCV) jen když je v prostředí sestavení (volitelný doplněk „kamera“; ~40 MB)
try:
    import cv2  # noqa: F401
    KAMERA = ["cv2"]
except ImportError:
    KAMERA = []


# licence SAKRA vedle SAKRA.exe (program PolyForm Noncommercial, návod a logo CC BY-NC 4.0)
LICENCE = [(str(KOREN / f), ".") for f in ("LICENSE", "LICENSE-CC-BY-NC-4.0.txt", "NOTICE.txt",
                                            "THIRD-PARTY-NOTICES.txt")]
# plné texty LGPL/GPL (Qt/PySide6 je nemá v metadatech, py7zr a spol. LGPL-2.1)
LICENCE += [(str(p), "licence-knihoven") for p in sorted((KOREN / "licence-knihoven").glob("*.txt"))]

# emulátor ZX Spectra (snímky obrazovky) běží bez okna – SDL (okno, zvuk) se nebalí
a = Analysis([str(KOREN / "instalator" / "spust.py")], pathex=[str(KOREN)], excludes=NEPOUZITE + ["sdl2"],
             hiddenimports=["openpyxl.cell._writer", "zx._spectrum", "zx._file", "py7zr", "sounddevice",
                            "_sounddevice"] + KAMERA,
             datas=collect_data_files("zx", includes=["roms/*"])
             + collect_data_files("_sounddevice_data")      # PortAudio (Windows, macOS)
             + [(str(KOREN / "sakra" / "dokumenty" / "SAKRA-navod.pdf"), "sakra/dokumenty"),
                (str(KOREN / "sakra" / "data" / "logo.png"), "sakra/data"),
                (str(KOREN / "sakra" / "data" / "ikona.png"), "sakra/data")] + LICENCE + licence_knihoven())
pyz = PYZ(a.pure)
okno = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SAKRA", console=False,
           icon=str(KOREN / "instalator" / "sakra.ico"))
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="sakra-cli", console=True,
          icon=str(KOREN / "instalator" / "sakra.ico"))
COLLECT(okno, cli, a.binaries, a.datas, name="SAKRA")
