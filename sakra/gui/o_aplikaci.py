"""Okno „O aplikaci“: logo, akronym, autor, Herní archiv."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from .. import (AKRONYM_HTML, AUTOR, KONTAKT, LICENCE, LICENCE_NAVODU, LICENCE_NAVODU_URL, LICENCE_URL, LOGO,
               PREZDIVKA, ROK, WEB, __version__)
from ..i18n import tr
from ..platformy import POCITACE, VSECHNY
from . import ikony

SIRKA_LOGA = 520


class DialogOAplikaci(QDialog):
    def __init__(self, parent=None, otevri_navod=None):
        super().__init__(parent)
        self.setWindowTitle(tr("O aplikaci SAKRA"))
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        logo = QLabel()
        pm = QPixmap(str(LOGO))
        if not pm.isNull():
            pm = pm.scaledToWidth(SIRKA_LOGA, Qt.TransformationMode.SmoothTransformation)
            logo.setPixmap(pm)
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(logo)
        text = QLabel(
            tr(
                "<p align=center style='font-size:22pt;font-weight:bold;margin:0'>SAKRA <span "
                "style='font-size:11pt;font-weight:normal;color:gray'>{0}</span></p><p align=center "
                "style='font-size:12pt;margin:2px 0 10px 0'>{1}</p><p align=center>Digitalizace a archivace audiokazet "
                "s programy pro staré počítače.</p><p align=center>Autor: <b>{2}</b>, alias <b>{3}</b>, {4}<br>"
                "Vyrobeno pro potřeby Herního archivu – <a href='https://{5}'>{6}</a></p><p align=center "
                "style='color:gray;font-size:9pt'>Platformy: "
            ).format(__version__, AKRONYM_HTML, AUTOR, PREZDIVKA, ROK, WEB, WEB)
            + ", ".join(dict.fromkeys(p.nazev for p in VSECHNY))
            + "</p><p align=center>" + " ".join(ikony.html(p, 24) for p in POCITACE) + "</p>"
        )
        # licence zvlášť – v jednom dlouhém popisku s obrázky Qt špatně spočítá výšku a konec ořízne
        licence = QLabel(
            tr("<p align=center style='font-size:9pt'>Licence: nekomerční použití – <a href='{0}'>{1}</a>; "
               "návod a logo <a href='{2}'>{3}</a>.<br>Komerční použití jen s písemným souhlasem autora: "
               "<a href='mailto:{4}'>{4}</a></p>").format(LICENCE_URL, LICENCE, LICENCE_NAVODU_URL, LICENCE_NAVODU,
                                                           KONTAKT)
        )
        for popisek in (text, licence):
            popisek.setWordWrap(True)
            popisek.setOpenExternalLinks(True)
            popisek.setMaximumWidth(SIRKA_LOGA + 40)
            lay.addWidget(popisek)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.button(QDialogButtonBox.StandardButton.Close).setText(tr("Zavřít"))
        if otevri_navod:
            bb.addButton(tr("Návod (PDF)"), QDialogButtonBox.ButtonRole.HelpRole).clicked.connect(otevri_navod)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
