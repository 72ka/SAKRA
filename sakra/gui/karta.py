"""Karta kazety: hlavička vzoru (Digitalizace, Inventář, Popis kazety) a profily pracoviště."""
from __future__ import annotations

import datetime as dt

from pathlib import Path

from PySide6.QtCore import QDate, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QComboBox, QDateEdit, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
                               QInputDialog, QLineEdit, QListView, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from ..jadro.model import Kazeta
from .. import nastaveni
from ..i18n import tr

VYROBCI = [
    "",
    "AGFA",
    "BASF",
    "emgeton",
    tr("Maxell"),
    "ORWO",
    tr("Philips"),
    tr("Scotch"),
    tr("Sony"),
    "TDK",
    tr("Tesla"),
]
MATERIALY = ["", tr("Type I"), tr("Type II"), tr("Type IV")]
POLE_PROFILU = nastaveni.POLE_PROFILU


def posuvne(w: QWidget) -> QScrollArea:
    """Obal, díky kterému jde okno zmenšit i na malou obrazovku (obsah se posouvá)."""
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QFrame.Shape.NoFrame)
    sc.setWidget(w)
    return sc


def _qdate(d: dt.date | None) -> QDate:
    return QDate(d.year, d.month, d.day) if d else QDate()


class KartaKazety(QWidget):
    zmeneno = Signal()
    spravovat_profily = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kazeta = Kazeta()
        self._plnim = False
        self.nastaveni = nastaveni.nastaveni()

        digi = QGroupBox(tr("Digitalizace"))
        fd = QFormLayout(digi)
        radek_profil = QHBoxLayout()
        self.profil = QComboBox()
        self.profil.setToolTip(tr("Uložená sestava pracoviště: magnetofon, převodník, DI-box, autor"))
        self.profil.activated.connect(self._pouzij_profil)
        ulozit = QPushButton(tr("Uložit jako profil…"))
        ulozit.clicked.connect(self._uloz_profil)
        spravovat = QPushButton(tr("Spravovat…"))
        spravovat.setToolTip(tr("Výchozí profil, přejmenování, mazání, import a export profilů (Nastavení)"))
        spravovat.clicked.connect(self.spravovat_profily)
        radek_profil.addWidget(self.profil, 1)
        radek_profil.addWidget(ulozit)
        radek_profil.addWidget(spravovat)
        fd.addRow(tr("Profil pracoviště"), radek_profil)
        self.tape_deck = self._radek(fd, tr("Tape-deck (značka)"))
        self.tape_deck_model = self._radek(fd, tr("Tape-deck (model)"))
        self.sound_card = self._radek(fd, "Sound-card")
        self.di_box = self._radek(fd, "DI-Box")
        self.vzorkovani = self._radek(fd, tr("Vzorkování"), tr("Vyplní se z nahrávky"))
        self.format = self._radek(fd, tr("Formát"), tr("Vyplní se z nahrávky"))
        self.datum = QDateEdit()
        self.datum.setCalendarPopup(True)
        self.datum.setDisplayFormat(tr("d. M. yyyy"))
        self.datum.dateChanged.connect(self._zmena_data)
        self._datum_rucne = False            # dnešek je jen zobrazený návrh, dokud ho člověk nezmění
        fd.addRow(tr("Datum"), self.datum)
        self.autor = self._radek(fd, tr("Autor"))

        inv = QGroupBox(tr("Inventář"))
        fi = QFormLayout(inv)
        self.cislo = self._radek(fi, tr("Inventární číslo"), tr("např. HH08518 – pojmenuje balíček i soubory"))
        self.puv_transakce = self._radek(fi, tr("Pův. transakce"))
        self.verze_dumpu = QSpinBox()
        self.verze_dumpu.setRange(1, 99)
        self.verze_dumpu.valueChanged.connect(self._uloz)
        fi.addRow(tr("Verze dumpu"), self.verze_dumpu)
        self.verze_metadat = QDateEdit()
        self.verze_metadat.setDisplayFormat(tr("d. M. yyyy"))
        self.verze_metadat.dateChanged.connect(self._uloz)
        fi.addRow(tr("Verze metadat"), self.verze_metadat)

        popis = QGroupBox(tr("Popis kazety"))
        fp = QFormLayout(popis)
        self.vyrobce = QComboBox()
        self.vyrobce.setEditable(True)
        self.vyrobce.addItems(VYROBCI)
        self.vyrobce.currentTextChanged.connect(self._uloz)
        fp.addRow(tr("Výrobce"), self.vyrobce)
        self.delka_strany = self._radek(fp, tr("Délka strany"), tr("Předvyplní se z délky nahrávky"))
        self.material = QComboBox()
        self.material.setEditable(True)
        self.material.addItems(MATERIALY)
        self.material.currentTextChanged.connect(self._uloz)
        fp.addRow(tr("Materiál"), self.material)

        foto = QGroupBox(tr("Fotky kazety a obalu"))
        lf = QVBoxLayout(foto)
        self.fotky = QListWidget()
        self.fotky.setViewMode(QListView.ViewMode.IconMode)
        self.fotky.setIconSize(QSize(96, 72))
        self.fotky.setResizeMode(QListView.ResizeMode.Adjust)
        self.fotky.setMinimumHeight(100)
        self.fotky.setToolTip(tr("Uloží se do balíčku (složka nahledy/) a vytisknou v protokolu"))
        lf.addWidget(self.fotky)
        tl = QHBoxLayout()
        pridat = QPushButton(tr("Přidat fotky…"))
        pridat.clicked.connect(self._pridej_fotky)
        z_kamery = QPushButton(tr("Z kamery…"))
        z_kamery.setToolTip(tr("Vyfotit kazetu a obal připojenou kamerou (USB webkamera)"))
        z_kamery.clicked.connect(self._fotky_z_kamery)
        odebrat = QPushButton(tr("Odebrat"))
        odebrat.clicked.connect(self._odeber_fotku)
        tl.addWidget(pridat)
        tl.addWidget(z_kamery)
        tl.addWidget(odebrat)
        tl.addStretch(1)
        lf.addLayout(tl)

        prava = QVBoxLayout()
        prava.addWidget(inv)
        prava.addWidget(popis)
        prava.addWidget(foto, 1)
        lay = QHBoxLayout(self)
        lay.addWidget(digi, 1)
        lay.addLayout(prava, 1)
        self._nacti_profily()

    def _radek(self, form: QFormLayout, popisek: str, napoveda: str = "") -> QLineEdit:
        e = QLineEdit()
        if napoveda:
            e.setPlaceholderText(napoveda)
        e.textEdited.connect(self._uloz)
        form.addRow(popisek, e)
        return e

    # ---- model <-> formulář ----
    def nastav(self, kazeta: Kazeta) -> None:
        self.kazeta = kazeta
        self._plnim = True
        d, i = kazeta.digitalizace, kazeta.inventar
        for jm in ("tape_deck", "tape_deck_model", "sound_card", "di_box", "vzorkovani", "format", "autor"):
            getattr(self, jm).setText(getattr(d, jm))
        self.datum.setDate(_qdate(d.datum) if d.datum else QDate.currentDate())
        self._datum_rucne = False
        self.cislo.setText(i.cislo)
        self.puv_transakce.setText(i.puv_transakce)
        self.verze_dumpu.setValue(i.verze_dumpu)
        self.verze_metadat.setDate(_qdate(i.verze_metadat) if i.verze_metadat else QDate(2024, 4, 1))
        self.vyrobce.setCurrentText(i.vyrobce)
        self.delka_strany.setText(i.delka_strany)
        self.material.setCurrentText(i.material)
        self._obnov_fotky()
        self._nacti_profily()
        self._plnim = False

    def obnov_profily(self) -> None:
        self._nacti_profily()

    def _zmena_data(self, *_):
        if not self._plnim:
            self._datum_rucne = True
        self._uloz()

    def _uloz(self, *_):
        if self._plnim:
            return
        d, i = self.kazeta.digitalizace, self.kazeta.inventar
        for jm in ("tape_deck", "tape_deck_model", "sound_card", "di_box", "vzorkovani", "format", "autor"):
            setattr(d, jm, getattr(self, jm).text().strip())
        if d.datum is not None or self._datum_rucne:     # prázdné datum doplní analýza z času změny nahrávky
            d.datum = self.datum.date().toPython()
        i.cislo = self.cislo.text().strip()
        i.puv_transakce = self.puv_transakce.text().strip()
        i.verze_dumpu = self.verze_dumpu.value()
        i.verze_metadat = self.verze_metadat.date().toPython()
        i.vyrobce = self.vyrobce.currentText().strip()
        i.delka_strany = self.delka_strany.text().strip()
        i.material = self.material.currentText().strip()
        self.zmeneno.emit()

    # ---- fotky ----
    def _obnov_fotky(self) -> None:
        self.fotky.clear()
        for f in self.kazeta.fotky:
            it = QListWidgetItem(QIcon(QPixmap(f).scaled(96, 72, Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation)), Path(f).name)
            it.setToolTip(f)
            self.fotky.addItem(it)

    def _pridej_fotky(self) -> None:
        cesty, _ = QFileDialog.getOpenFileNames(
            self,
            tr("Fotky kazety"),
            self.nastaveni.value("slozka", str(Path.home())),
            tr("Obrázky (*.jpg *.jpeg *.png *.tif *.tiff *.webp)"),
        )
        if cesty:
            self.kazeta.fotky += [c for c in cesty if c not in self.kazeta.fotky]
            self._obnov_fotky()
            self.zmeneno.emit()

    def _fotky_z_kamery(self) -> None:
        from .kamera import DialogKamera
        d = DialogKamera(self.kazeta.inventar.cislo, self.nastaveni.value("slozka", str(Path.home())), self)
        d.exec()                      # i po Zavřít: co se vyfotilo, je uložené a patří ke kazetě
        self.pridej_fotky(d.snimky)

    def pridej_fotky(self, cesty: list[str]) -> None:
        nove = [c for c in cesty if c not in self.kazeta.fotky]
        if nove:
            self.kazeta.fotky += nove
            self._obnov_fotky()
            self.zmeneno.emit()

    def _odeber_fotku(self) -> None:
        r = self.fotky.currentRow()
        if 0 <= r < len(self.kazeta.fotky):
            del self.kazeta.fotky[r]
            self._obnov_fotky()
            self.zmeneno.emit()

    # ---- profily pracoviště ----
    def _profily(self) -> dict:
        return nastaveni.profily()

    def _nacti_profily(self) -> None:
        """Seznam profilů (výchozí s hvězdičkou); vybraný je ten, se kterým údaje karty souhlasí."""
        self.profil.blockSignals(True)
        self.profil.clear()
        self.profil.addItem(tr("— vyberte —"))
        vychozi = nastaveni.vychozi_profil()
        p = self._profily()
        for jm in sorted(p):
            self.profil.addItem(jm + (tr(" (výchozí)") if jm == vychozi else ""), jm)
        d = self.kazeta.digitalizace
        shoda = next((jm for jm in sorted(p, key=lambda j: j != vychozi)
                      if all((p[jm].get(k) or "") == getattr(d, k) for k in POLE_PROFILU)
                      and any(p[jm].get(k) for k in POLE_PROFILU)), None)
        self.profil.setCurrentIndex(max(0, self.profil.findData(shoda)) if shoda else 0)
        self.profil.blockSignals(False)

    def _pouzij_profil(self, _):
        p = self._profily().get(self.profil.currentData() or "")
        if not p:
            return
        for jm in POLE_PROFILU:
            getattr(self, jm).setText(p.get(jm, ""))
        self._uloz()

    def _uloz_profil(self):
        jmeno, ok = QInputDialog.getText(self, tr("Profil pracoviště"), tr("Název profilu (např. Pracoviště 1):"),
                                         text=self.profil.currentData() or "")
        if not ok or not jmeno.strip():
            return
        p = self._profily()
        p[jmeno.strip()] = {jm: getattr(self, jm).text().strip() for jm in POLE_PROFILU}
        nastaveni.uloz_profily(p)
        self._nacti_profily()
