"""Start aplikace."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QRect, Qt, QTranslator
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from .. import IKONA, __version__, i18n
from ..projekt import PRIPONA
from . import vzhled
from .okno import HlavniOkno


# výřez kazety v ikona.png (bez čepelí) – pro malé velikosti, kde by široká ikona byla nečitelná
VYREZ_KAZETY = QRect(100, 0, 276, 216)
MALE = 32


def _ctverec(obr: QImage, n: int) -> QPixmap:
    """Obrázek zmenšený do čtverce n×n, vycentrovaný na průhledném pozadí."""
    pm = QPixmap(n, n)
    pm.fill(Qt.GlobalColor.transparent)
    zmenseny = obr.scaled(n, n, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    p = QPainter(pm)
    p.drawImage((n - zmenseny.width()) // 2, (n - zmenseny.height()) // 2, zmenseny)
    p.end()
    return pm


def ikona() -> QIcon:
    """Ikona aplikace z data/ikona.png: velké velikosti celá (kazeta s čepelemi), malé jen kazeta."""
    obr = QImage(str(IKONA))
    ik = QIcon()
    if obr.isNull():
        return ik
    kazeta = obr.copy(VYREZ_KAZETY)
    for n in (16, 20, 24, 32, 48, 64, 128, 256):
        ik.addPixmap(_ctverec(kazeta if n <= MALE else obr, n))
    return ik


def ikona_zahlavi(vyska: int, dpr: float = 1.0) -> QPixmap:
    """Celá široká ikona v dané výšce (záhlaví okna vlevo nahoře)."""
    obr = QImage(str(IKONA))
    if obr.isNull():
        return QPixmap()
    pm = QPixmap.fromImage(obr.scaledToHeight(int(round(vyska * dpr)), Qt.TransformationMode.SmoothTransformation))
    pm.setDevicePixelRatio(dpr)
    return pm


def _preklad_qt(app: QApplication) -> None:
    """Standardní texty Qt (Storno, Ano/Ne v dialozích) v jazyce aplikace; angličtina je v Qt vestavěná."""
    if i18n.jazyk() == "en":
        return
    t = QTranslator(app)
    if t.load(f"qtbase_{i18n.jazyk()}", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(t)


def spust(soubor: str | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("SAKRA")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("HerniArchiv")
    app.setWindowIcon(ikona())
    _preklad_qt(app)
    vzhled.pouzij(app)
    okno = HlavniOkno()
    okno.pouzij_vzhled()
    okno.show()
    vzhled.hlidej_system(app, okno.pouzij_vzhled)
    if soubor:
        if soubor.endswith(PRIPONA):
            okno.otevri_projekt(soubor)
        elif Path(soubor).suffix.lower() == ".xlsx":
            pass
        else:
            okno.otevri_nahravky([soubor], zeptat=True)
    return app.exec()
