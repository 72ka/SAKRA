"""Dialog „Snímek z kamery“: živý náhled z USB kamery, Vyfotit uloží JPEG „<inv> foto <n>.jpg“.

Pořízené snímky se po zavření přidají k fotkám kazety (karta kazety). Bez OpenCV dialog napíše, jak doplněk
nainstalovat.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListView, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)

from .. import nastaveni
from ..i18n import tr, tr_data
from ..jadro import kamera


def _pixmapa(rgb) -> QPixmap:
    h, w, _ = rgb.shape
    return QPixmap.fromImage(QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy())


class DialogKamera(QDialog):
    def __init__(self, inv: str = "", slozka: str = "", parent=None, zarizeni=None, otevri=None):
        """`zarizeni`, `otevri` (testy): seznam kamer a funkce index -> objekt s posledni(), zavri(), chyba."""
        super().__init__(parent)
        self.setWindowTitle(tr("Snímek z kamery"))
        self.setMinimumSize(720, 640)
        self.nastaveni = nastaveni.nastaveni()
        self._otevri = otevri or kamera.Kamera
        self.kam = None
        self.snimky: list[str] = []
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.vyber = QComboBox()
        self.zarizeni = zarizeni if zarizeni is not None else kamera.kamery()
        for z in self.zarizeni:
            self.vyber.addItem(z.nazev, z.index)
        self.vyber.currentIndexChanged.connect(lambda _: self._otevri_kameru())
        f.addRow(tr("Kamera"), self.vyber)
        self.inv = QLineEdit(inv)
        self.inv.setPlaceholderText(tr("např. HH08518"))
        f.addRow(tr("Inventární číslo"), self.inv)
        self.slozka = QLineEdit(self.nastaveni.value("kamera/slozka", slozka or str(Path.home())))
        vyber = QPushButton(tr("Vybrat…"))
        vyber.clicked.connect(self._vyber_slozku)
        r = QHBoxLayout()
        r.addWidget(self.slozka, 1)
        r.addWidget(vyber)
        f.addRow(tr("Složka"), r)
        lay.addLayout(f)
        self.nahled = QLabel()
        self.nahled.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nahled.setMinimumSize(640, 360)
        self.nahled.setStyleSheet("background:#1B1F27;color:#DCE1EA;border-radius:8px")
        lay.addWidget(self.nahled, 1)
        self.stav = QLabel()
        self.stav.setStyleSheet("color:#8A93A3")
        lay.addWidget(self.stav)
        self.porizene = QListWidget()
        self.porizene.setViewMode(QListView.ViewMode.IconMode)
        self.porizene.setIconSize(QSize(96, 72))
        self.porizene.setFixedHeight(104)
        lay.addWidget(self.porizene)
        tl = QHBoxLayout()
        self.vyfotit = QPushButton(tr("Vyfotit"))
        self.vyfotit.setProperty("primarni", True)
        self.vyfotit.setDefault(True)
        self.vyfotit.clicked.connect(self.vyfot)
        hotovo = QPushButton(tr("Hotovo – přidat ke kazetě"))
        hotovo.clicked.connect(self.accept)
        zrusit = QPushButton(tr("Zavřít"))
        zrusit.clicked.connect(self.reject)
        tl.addWidget(self.vyfotit)
        tl.addStretch(1)
        tl.addWidget(hotovo)
        tl.addWidget(zrusit)
        lay.addLayout(tl)
        self.casovac = QTimer(self)
        self.casovac.setInterval(66)                  # náhled asi 15 snímků za sekundu
        self.casovac.timeout.connect(self._tik)
        if not kamera.dostupna() and otevri is None:
            self._bez_kamery(tr("Snímání z kamery potřebuje doplněk OpenCV:\n{0}\n(spouštěcí skripty run.sh / "
                                "run.bat ho instalují samy)").format(kamera.INSTALACE))
        elif not self.zarizeni:
            self._bez_kamery(tr("Není připojená žádná kamera (nebo ji používá jiný program)."))
        else:
            v = self.nastaveni.value("kamera/index")
            i = self.vyber.findData(int(v)) if v is not None else -1
            if i > 0:
                self.vyber.setCurrentIndex(i)          # otevře ji signál
            else:
                self._otevri_kameru()

    def _bez_kamery(self, text: str):
        self.nahled.setText(text)
        self.vyfotit.setEnabled(False)
        self.vyber.setEnabled(False)

    def _vyber_slozku(self):
        d = QFileDialog.getExistingDirectory(self, tr("Složka fotek"), self.slozka.text())
        if d:
            self.slozka.setText(d)

    def _zavri_kameru(self):
        self.casovac.stop()
        if self.kam is not None:
            self.kam.zavri()
            self.kam = None

    def _otevri_kameru(self):
        self._zavri_kameru()
        index = self.vyber.currentData()
        if index is None:
            return
        try:
            self.kam = self._otevri(index)
        except Exception as e:  # noqa: BLE001 – kamera obsazená, odpojená…
            self.nahled.setText(tr_data(str(e)))
            self.vyfotit.setEnabled(False)
            return
        self.nastaveni.setValue("kamera/index", index)
        self.vyfotit.setEnabled(True)
        self.nahled.setText(tr("Čekám na obraz z kamery…"))
        self.casovac.start()

    def _tik(self):
        if self.kam is None:
            return
        if self.kam.chyba:
            self.nahled.setText(tr_data(self.kam.chyba))
            self._zavri_kameru()
            return
        rgb = self.kam.posledni()
        if rgb is None:
            return
        self.nahled.setPixmap(_pixmapa(rgb).scaled(self.nahled.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation))
        self.stav.setText(tr("Rozlišení {0} × {1}").format(rgb.shape[1], rgb.shape[0]))

    def vyfot(self) -> Path | None:
        rgb = self.kam.posledni() if self.kam else None
        if rgb is None:
            return None
        cesta = kamera.dalsi_jmeno(Path(self.slozka.text()), self.inv.text())
        try:
            kamera.uloz_jpeg(rgb, cesta)
        except OSError as e:
            QMessageBox.warning(self, "SAKRA", str(e))
            return None
        nastaveni.zapamatuj_slozku("kamera/slozka", self.slozka.text())
        self.snimky.append(str(cesta))
        it = QListWidgetItem(QIcon(_pixmapa(rgb).scaled(96, 72, Qt.AspectRatioMode.KeepAspectRatio,
                                                        Qt.TransformationMode.SmoothTransformation)), cesta.name)
        it.setToolTip(str(cesta))
        self.porizene.addItem(it)
        self.stav.setText(tr("Uloženo: {0}").format(cesta.name))
        return cesta

    def done(self, r):
        self._zavri_kameru()
        super().done(r)
