"""Tabulka „Obsah pásky“ – sloupce přesně podle vzoru Herního archivu, plus stav SAKRA."""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QComboBox, QStyledItemDelegate

from ..jadro.analyza import popis_stavu
from ..jadro.model import (FUNKCNI_EDIT, FUNKCNI_ORIG, OBSAHY, TURBA, TYPY, ZADNA_DATA, Kazeta, Zaznam, cas_text,
                           cas_z_textu, urci_platformu)
from ..metadata import sablona
from ..platformy import RUCNI, VSECHNY
from ..i18n import tr, tr_data
from . import ikony, vzhled

SLOUPCE = [(tr("Strana"), "_strana"), (tr("Stav"), "_stav")] + [(tr(z), pole) for _, z, pole in sablona.SLOUPCE]
PISMENO = {pole: sl for sl, _, pole in sablona.SLOUPCE}
PLATFORMY = list(dict.fromkeys([p.nazev for p in VSECHNY] + RUCNI + [ZADNA_DATA]))
VOLBY = {"typ": TYPY, "obsah": OBSAHY, "funkcni_orig": FUNKCNI_ORIG, "funkcni_edit": FUNKCNI_EDIT, "turbo": TURBA,
         "platforma": PLATFORMY}
ZASTUPNE = {"(nerozpoznáno)", "(žádná data)", "(zvukový záznam)"}     # zástupné názvy úseků bez programu
AUTOMATICKA = {"cas_od", "cas_do", "typ", "platforma", "turbo", "nazev_bloku", "typ_bloku"}
STAVY = {"ok": (tr("✓ v pořádku"), "#2EA866"), "opraveno": (tr("✓ opraveno"), "#D08A10"),
         "neověřeno": (tr("~ bez součtu"), "#4A86C8"),
         "chyba": (tr("✗ chyba"), "#E04848"), "nerozpoznáno": (tr("? nerozpoznáno"), "#8A93A3"),
         "žádná data": (tr("♪ žádná data"), "#8A93A3")}


class ObsahModel(QAbstractTableModel):
    def __init__(self, kazeta: Kazeta, parent=None):
        super().__init__(parent)
        self.kazeta = kazeta
        self.radky: list[tuple[int, Zaznam]] = []
        self.obnov()

    def nastav(self, kazeta: Kazeta) -> None:
        self.kazeta = kazeta
        self.obnov()

    def obnov(self) -> None:
        self.beginResetModel()
        self.radky = [(s.cislo, z) for s in self.kazeta.strany for z in s.zaznamy]
        self.endResetModel()

    def radek_zaznamu(self, z: Zaznam) -> int:
        return next((i for i, (_, x) in enumerate(self.radky) if x is z), -1)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.radky)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(SLOUPCE)

    def headerData(self, sekce, orientace, role=Qt.ItemDataRole.DisplayRole):
        if orientace != Qt.Orientation.Horizontal:
            return None
        nazev, pole = SLOUPCE[sekce]
        if role == Qt.ItemDataRole.DisplayRole:
            return nazev
        if role == Qt.ItemDataRole.ToolTipRole:
            sl = PISMENO.get(pole)
            if sl in sablona.NAPOVEDY:
                return sablona.NAPOVEDY[sl]
            if pole == "_stav":
                return tr("Výsledek dekódování (není ve vzoru, je na listu „SAKRA“)")
            if pole in AUTOMATICKA:
                return tr("Vyplňuje SAKRA z nahrávky (lze přepsat)")
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        strana, z = self.radky[index.row()]
        _, pole = SLOUPCE[index.column()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if pole == "_strana":
                return str(strana)
            if pole == "_stav":
                return STAVY.get(z.stav, (z.stav, ""))[0]
            hod = getattr(z, pole)
            if pole in ("cas_od", "cas_do"):
                return cas_text(hod)
            if role == Qt.ItemDataRole.DisplayRole and (pole == "typ_bloku" or pole == "nazev" and hod in ZASTUPNE):
                return tr_data(hod)            # typ z dekodéru; uložená hodnota zůstává česky
            return hod
        if role == Qt.ItemDataRole.DecorationRole and pole == "platforma":
            return ikony.ikona(ikony.klic_zaznamu(z))
        if role == Qt.ItemDataRole.ForegroundRole and pole == "_stav":
            return QBrush(QColor(STAVY.get(z.stav, ("", "#8A93A3"))[1]))
        if role == Qt.ItemDataRole.BackgroundRole:
            tmave = vzhled.je_tmave()
            if PISMENO.get(pole, "") and PISMENO[pole] in z.zvyrazneni:          # tmavší buňka ze vzoru
                return QBrush(QColor("#6B4A2A" if tmave else "#F9CB9C"))
            if z.soubor is not None and pole in AUTOMATICKA:                     # vyplnila SAKRA
                return QBrush(QColor("#2C2A22" if tmave else "#FFF6E3"))
        if role == Qt.ItemDataRole.FontRole and pole == "nazev":
            f = QFont()
            f.setBold(True)
            return f
        if role == Qt.ItemDataRole.ToolTipRole:
            if pole == "_stav" and z.soubor is not None:
                return tr_data(popis_stavu(z.soubor)) or tr("Všechny bloky v pořádku")
            if pole == "poznamky":
                return z.poznamky
        return None

    def flags(self, index):
        f = super().flags(index)
        if SLOUPCE[index.column()][1].startswith("_"):
            return f
        return f | Qt.ItemFlag.ItemIsEditable

    def setData(self, index, hodnota, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole:
            return False
        _, z = self.radky[index.row()]
        _, pole = SLOUPCE[index.column()]
        if pole in ("cas_od", "cas_do"):
            setattr(z, pole, cas_z_textu(hodnota))
        elif pole == "platforma" and z.nerozpoznano:
            urci_platformu(z, str(hodnota).strip())
            self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), len(SLOUPCE) - 1))
            return True
        else:
            setattr(z, pole, str(hodnota).strip())
        self.dataChanged.emit(index, index)
        return True


class VolbyDelegat(QStyledItemDelegate):
    """U sloupců s povolenými hodnotami (podle komentářů ve vzoru) nabídne rozbalovací seznam."""

    def createEditor(self, parent, option, index):
        pole = SLOUPCE[index.column()][1]
        if pole in VOLBY:
            cb = QComboBox(parent)
            cb.setEditable(True)
            cb.addItem("")
            for hodnota in VOLBY[pole]:
                if pole == "platforma":
                    cb.addItem(ikony.ikona(hodnota), hodnota)
                else:
                    cb.addItem(hodnota)
            return cb
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if isinstance(editor, QComboBox):
            editor.setCurrentText(index.data(Qt.ItemDataRole.EditRole) or "")
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentText())
        else:
            super().setModelData(editor, model, index)
