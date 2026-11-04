"""Volba, pro jaký počítač je kazeta: dlaždice s ikonami (Automaticky + počítače s dekodérem) a dialog.

Ruční volba zrychlí zpracování – zkusí se jen dekodéry zvoleného počítače (všechny jeho varianty).
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QGridLayout, QLabel, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from ..i18n import tr
from ..platformy import POCITACE
from . import ikony

POPIS = tr("Ruční výběr zpracuje kazetu rychleji – zkusí se jen dekodéry zvoleného počítače. "
           "Automaticky SAKRA platformu rozpozná sama (vhodné, když na kazetě může být víc počítačů).")


# kratší popisky dlaždic (celý název je v bublině)
KRATKE = {"Ondra SPO 186": "Ondra", "BBC Micro / Acorn Electron": "BBC / Acorn", "Sharp MZ-700/800": "Sharp MZ",
          "Commodore 64": "C64", "Amstrad CPC": "Amstrad"}


def volby() -> list[tuple[str, str]]:
    """[(hodnota, popisek)]; hodnota "" = automaticky."""
    return [("", tr("Automaticky"))] + [(p, p) for p in POCITACE]


class VyberPlatformy(QWidget):
    """Mřížka dlaždic; vybrána je vždy právě jedna."""
    zmeneno = Signal(str)

    def __init__(self, sloupcu: int = 6, velikost_ikony: int = 40, parent=None):
        super().__init__(parent)
        g = QGridLayout(self)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(6)
        self.skupina = QButtonGroup(self)
        self.skupina.setExclusive(True)
        self.tlacitka: dict[str, QToolButton] = {}
        for i, (hodnota, popisek) in enumerate(volby()):
            b = QToolButton()
            b.setCheckable(True)
            b.setIcon(ikony.ikona(hodnota or ikony.AUTO))
            b.setIconSize(QSize(velikost_ikony, velikost_ikony))
            b.setText(KRATKE.get(popisek, popisek))
            b.setToolTip(popisek)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setMinimumWidth(max(velikost_ikony + 56, b.fontMetrics().horizontalAdvance(b.text()) + 44))
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.setAutoRaise(False)
            b.clicked.connect(lambda _=False, h=hodnota: self.zmeneno.emit(h))
            self.skupina.addButton(b)
            self.tlacitka[hodnota] = b
            g.addWidget(b, i // sloupcu, i % sloupcu)
        self.nastav("")

    def nastav(self, hodnota: str) -> None:
        b = self.tlacitka.get(hodnota) or self.tlacitka[""]
        b.setChecked(True)

    def hodnota(self) -> str:
        return next((h for h, b in self.tlacitka.items() if b.isChecked()), "")


class DialogPlatformy(QDialog):
    """„Pro jaký počítač je kazeta?“ – kliknutí na dlaždici volbu rovnou potvrdí."""

    def __init__(self, hodnota: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Pro jaký počítač je kazeta?"))
        lay = QVBoxLayout(self)
        nadpis = QLabel(f"<h3 style='margin:0'>{tr('Pro jaký počítač je kazeta?')}</h3>")
        lay.addWidget(nadpis)
        popis = QLabel(POPIS)
        popis.setWordWrap(True)
        lay.addWidget(popis)
        self.vyber = VyberPlatformy(6, 40)
        self.vyber.nastav(hodnota)
        self.vyber.zmeneno.connect(lambda _: self.accept())
        lay.addWidget(self.vyber)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def hodnota(self) -> str:
        return self.vyber.hodnota()


def combo_platformy() -> QComboBox:
    """Rozbalovací volba s ikonami (lišta pracovního stolu, pravidla dávky); data = hodnota ("" = automaticky)."""
    cb = QComboBox()
    cb.setIconSize(QSize(18, 18))
    for hodnota, popisek in volby():
        cb.addItem(ikony.ikona(hodnota or ikony.AUTO), popisek, hodnota)
    cb.setToolTip(f"<b>{tr('Pro jaký počítač je kazeta?')}</b><br>{POPIS}")
    return cb
