"""Dialog „Nahrát z magnetofonu“: strana kazety ze zvukového vstupu rovnou do WAV, pak dál jako obvykle.

Soubor se pojmenuje podle zvyklosti archivu „<inventární číslo> (<strana>).wav“, takže SAKRA pozná
stranu i číslo kazety. Úroveň se dá nastavit předem (Sledovat úroveň), přebuzení se hlásí červeně.
Ladění hlavy (azimut): histogram délek pulzů, rozptyl hlavní špičky a posun kanálů L/R z posledního
půl sekundy přehrávaného záznamu (viz jadro/ladeni.py).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QProgressBar, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from .. import nastaveni
from ..i18n import jazyk, tr
from ..jadro import ladeni, zaznam
from ..jadro.model import cas_text


def jmeno_souboru(inv: str, strana: int) -> str:
    return f"{inv.strip() or 'nahravka'} ({strana}).wav"


class Merak(QProgressBar):
    """Úroveň jednoho kanálu (dB škála -60..0), přebuzení červeně."""

    def __init__(self):
        super().__init__()
        self.setRange(0, 600)
        self.setTextVisible(False)
        self.setProperty("bez_textu", True)
        self.setFixedHeight(12)

    def nastav(self, spicka: float, prebuzeno: bool):
        import math
        db = 20 * math.log10(max(spicka, 1e-6))
        self.setValue(int(max(0.0, min(60.0, db + 60.0)) * 10))
        barva = "#E04848" if prebuzeno else "#F2C14E" if db > -3 else "#46C27D"
        self.setStyleSheet(f"QProgressBar::chunk{{background:{barva}}}")


def _cislo(x: float) -> str:
    t = f"{x:.1f}"
    return t.replace(".", ",") if jazyk() == "cs" else t


class LadeniHlavy(QWidget):
    """Histogram délek pulzů a posun kanálů L/R – vodítko pro šroubek azimutu hlavy."""
    VYSKA_GRAFU = 90

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(self.VYSKA_GRAFU + 64)
        self.v: ladeni.Ladeni | None = None
        self.vyhlazeny: np.ndarray | None = None
        self.nejlepsi: float | None = None     # nejmenší rozptyl od začátku sledování
        self._spicka_nejlepsi: float | None = None

    def vynuluj(self):
        self.v, self.vyhlazeny, self.nejlepsi, self._spicka_nejlepsi = None, None, None, None
        self.update()

    def nastav(self, v: ladeni.Ladeni):
        self.v = v
        h = v.histogram.astype(float)
        self.vyhlazeny = h if self.vyhlazeny is None else 0.5 * self.vyhlazeny + 0.5 * h
        if v.rozptyl is not None and v.spicka_us:
            if self._spicka_nejlepsi and abs(v.spicka_us / self._spicka_nejlepsi - 1) > 0.2:
                self.nejlepsi = None                  # jiný signál (jiná rychlost, jiný úsek): znovu
            if self.nejlepsi is None or v.rozptyl < self.nejlepsi:
                self.nejlepsi, self._spicka_nejlepsi = v.rozptyl, v.spicka_us
        self.update()

    def texty(self) -> tuple[str, str]:
        v = self.v
        if v is None or v.rozptyl is None:
            return tr("Délky pulzů: pusťte nahrávku (zaváděcí tón nebo data)"), ""
        prvni = tr("Délky pulzů: špička {0} µs, rozptyl ±{1} %").format(round(v.spicka_us), _cislo(100 * v.rozptyl))
        if self.nejlepsi is not None:
            prvni += tr("  (nejlépe ±{0} %)").format(_cislo(100 * self.nejlepsi))
        if v.posun_us is None:
            return prvni, tr("Posun kanálů: jen u sterea")
        if (v.korelace or 0) < 0.5:
            return prvni, tr("Kanály L/R nesouhlasí (korelace {0} %) – mono magnetofon nebo prázdná stopa").format(
                round(100 * (v.korelace or 0)))
        return prvni, tr("Posun kanálů L/R: {0} µs, korelace {1} % – ideál 0 µs").format(
            f"{v.posun_us:+.0f}", round(100 * v.korelace))

    def paintEvent(self, _):
        p = QPainter(self)
        pal = self.palette()
        w, h = self.width(), self.VYSKA_GRAFU
        p.fillRect(QRectF(0, 0, w, h), pal.alternateBase())
        sloupcu = int(1500 / ladeni.KROK_US)                      # zobrazit 0..1500 µs
        if self.vyhlazeny is not None and self.vyhlazeny[:sloupcu].max() > 0:
            hh = self.vyhlazeny[:sloupcu]
            dx = w / sloupcu
            mx = hh.max()
            spicka = self.v.spicka_us if self.v else None
            for i, n in enumerate(hh):
                if not n:
                    continue
                us = (i + 0.5) * ladeni.KROK_US
                hlavni = spicka is not None and abs(us - spicka) <= 0.25 * spicka
                p.fillRect(QRectF(i * dx, h - n / mx * (h - 4), max(1.0, dx - 0.5), n / mx * (h - 4)),
                           QColor("#F2A93B" if hlavni else "#3B6FB6"))
        p.setPen(pal.placeholderText().color())
        for us in (0, 500, 1000, 1500):
            x = us / 1500 * w
            p.drawLine(QPointF(x, h - 4), QPointF(x, h))
            p.drawText(QPointF(min(x + 3, w - 50), h - 6), f"{us} µs")
        prvni, druhy = self.texty()
        p.setPen(pal.text().color())
        p.drawText(QPointF(0, h + 18), prvni)
        p.drawText(QPointF(0, h + 38), druhy)
        v = self.v
        if v is not None and v.posun_us is not None and (v.korelace or 0) >= 0.5:   # ukazatel posunu
            y, x0, x1 = h + 48, 0.0, float(w)
            p.fillRect(QRectF(x0, y, x1 - x0, 8), pal.alternateBase())
            stred = (x0 + x1) / 2
            zona = 20 / ladeni.MAX_POSUN_US * (x1 - x0) / 2
            p.fillRect(QRectF(stred - zona, y, 2 * zona, 8), QColor(70, 194, 125, 90))
            x = stred + max(-1.0, min(1.0, v.posun_us / ladeni.MAX_POSUN_US)) * (x1 - x0) / 2
            barva = "#46C27D" if abs(v.posun_us) < 20 else "#F2C14E" if abs(v.posun_us) < 60 else "#E04848"
            p.setPen(QPen(QColor(barva), 4))
            p.drawLine(QPointF(x, y - 3), QPointF(x, y + 11))
        p.end()


class DialogNahravani(QDialog):
    def __init__(self, inv: str = "", slozka: str = "", parent=None, zdroj=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Nahrát z magnetofonu"))
        self.setMinimumWidth(560)
        self.nastaveni = nastaveni.nastaveni()
        self._zdroj = zdroj                    # (testy) náhradní zdroj zvuku
        self.nahravac: zaznam.Nahravac | None = None
        self.hotove: list[Path] = []           # nahrané strany
        lay = QVBoxLayout(self)
        popis = QLabel(tr("Nahrávka strany kazety ze zvukového vstupu (line-in). Nejdřív nastavte úroveň "
                          "(Sledovat úroveň – špičky do žluté, nikdy do červené), pak spusťte Nahrávat a "
                          "magnetofon. Po nahrání se strana otevře v SAKRA jako obvykle."))
        popis.setWordWrap(True)
        lay.addWidget(popis)
        f = QFormLayout()
        self.vstup = QComboBox()
        self.vstupy = zaznam.vstupy() if zdroj is None else [zaznam.Vstup("test", "test")]
        for v in self.vstupy:
            self.vstup.addItem(v.nazev)
        f.addRow(tr("Vstup"), self.vstup)
        self.vzorkovani = QComboBox()
        for r in zaznam.VZORKOVANI:
            self.vzorkovani.addItem(f"{r} Hz", r)
        self.vzorkovani.setCurrentIndex(max(0, self.vzorkovani.findData(int(self.nastaveni.value("nahravani/rate", 48000)))))
        self.bitu = QComboBox()
        for b in zaznam.BITU:
            self.bitu.addItem(tr("{0} bitů").format(b), b)
        self.bitu.setCurrentIndex(max(0, self.bitu.findData(int(self.nastaveni.value("nahravani/bitu", 16)))))
        self.kanaly = QComboBox()
        self.kanaly.addItem(tr("stereo"), 2)
        self.kanaly.addItem(tr("mono"), 1)
        self.kanaly.setCurrentIndex(max(0, self.kanaly.findData(int(self.nastaveni.value("nahravani/kanaly", 2)))))
        r = QHBoxLayout()
        for w in (self.vzorkovani, self.bitu, self.kanaly):
            r.addWidget(w)
        f.addRow(tr("Formát"), r)
        self.inv = QLineEdit(inv)
        self.inv.setPlaceholderText(tr("např. HH08518"))
        self.strana = QSpinBox()
        self.strana.setRange(1, 9)
        r = QHBoxLayout()
        r.addWidget(self.inv)
        r.addWidget(QLabel(tr("strana")))
        r.addWidget(self.strana)
        f.addRow(tr("Inventární číslo"), r)
        self.slozka = QLineEdit(self.nastaveni.value("nahravani/slozka", slozka or str(Path.home())))
        vyber = QPushButton(tr("Vybrat…"))
        vyber.clicked.connect(self._vyber_slozku)
        r = QHBoxLayout()
        r.addWidget(self.slozka, 1)
        r.addWidget(vyber)
        f.addRow(tr("Složka"), r)
        self.soubor = QLabel()
        self.soubor.setStyleSheet("color:#8A93A3")
        f.addRow("", self.soubor)
        lay.addLayout(f)
        self.meraky = [Merak(), Merak()]
        for m in self.meraky:
            lay.addWidget(m)
        napoveda = QLabel(tr("<b>Ladění hlavy (azimut):</b> pusťte nahranou kazetu (zaváděcí tón nebo data) a "
                             "šroubkem azimutu otáčejte, až bude oranžová špička nejužší (rozptyl nejmenší) "
                             "a posun kanálů nejblíž 0 µs."))
        napoveda.setWordWrap(True)
        lay.addWidget(napoveda)
        self.ladeni = LadeniHlavy()
        lay.addWidget(self.ladeni)
        self.stav = QLabel()
        lay.addWidget(self.stav)
        tl = QHBoxLayout()
        self.sledovat = QPushButton(tr("Sledovat úroveň"))
        self.sledovat.setCheckable(True)
        self.sledovat.toggled.connect(self._sledovani)
        self.nahravat = QPushButton(tr("● Nahrávat"))
        self.nahravat.setProperty("primarni", True)
        self.nahravat.clicked.connect(self._nahravani)
        self.otevrit = QPushButton(tr("Otevřít v SAKRA"))
        self.otevrit.setEnabled(False)
        self.otevrit.clicked.connect(self.accept)
        zavrit = QPushButton(tr("Zavřít"))
        zavrit.clicked.connect(self.reject)
        for b in (self.sledovat, self.nahravat):
            tl.addWidget(b)
        tl.addStretch(1)
        tl.addWidget(self.otevrit)
        tl.addWidget(zavrit)
        lay.addLayout(tl)
        for w in (self.inv, self.slozka):
            w.textChanged.connect(self._obnov_soubor)
        self.strana.valueChanged.connect(self._obnov_soubor)
        self.kanaly.currentIndexChanged.connect(lambda _: self.meraky[1].setVisible(self.kanaly.currentData() == 2))
        self.casovac = QTimer(self)
        self.casovac.setInterval(100)
        self.casovac.timeout.connect(self._tik)
        self._obnov_soubor()
        if not self.vstupy:
            self.stav.setText(tr("<span style='color:#E04848'>Není k dispozici žádný zvukový vstup. Windows a macOS: "
                                 "připojte zvukovou kartu; Linux: nainstalujte libportaudio2 nebo "
                                 "pulseaudio-utils / alsa-utils.</span>"))
            for b in (self.sledovat, self.nahravat):
                b.setEnabled(False)

    # ---- pomocné ----
    def cesta(self) -> Path:
        return Path(self.slozka.text()) / jmeno_souboru(self.inv.text(), self.strana.value())

    def _obnov_soubor(self):
        self.soubor.setText(str(self.cesta()))

    def _vyber_slozku(self):
        d = QFileDialog.getExistingDirectory(self, tr("Složka nahrávek"), self.slozka.text())
        if d:
            self.slozka.setText(d)

    def _novy_nahravac(self) -> zaznam.Nahravac:
        v = self.vstupy[self.vstup.currentIndex()]
        return zaznam.Nahravac(v, self.vzorkovani.currentData(), self.kanaly.currentData(), self.bitu.currentData(),
                               zdroj=self._zdroj)

    def _formular(self, povolit: bool):
        for w in (self.vstup, self.vzorkovani, self.bitu, self.kanaly, self.inv, self.strana, self.slozka):
            w.setEnabled(povolit)

    def _spust(self, cesta: Path | None) -> bool:
        self.nahravac = self._novy_nahravac()
        try:
            self.nahravac.start(cesta)
        except Exception as e:  # noqa: BLE001
            self.nahravac = None
            QMessageBox.warning(self, "SAKRA", tr("Zvukový vstup nejde otevřít:\n{0}").format(e))
            return False
        self._formular(False)
        self.ladeni.vynuluj()
        self._tiku = 0
        self.casovac.start()
        return True

    def _zastav(self) -> Path | None:
        self.casovac.stop()
        cesta = self.nahravac.stop() if self.nahravac else None
        chyba = self.nahravac.chyba if self.nahravac else ""
        self.nahravac = None
        self._formular(True)
        for m in self.meraky:
            m.nastav(0.0, False)
        if chyba:
            QMessageBox.warning(self, "SAKRA", tr("Nahrávání skončilo s chybou:\n{0}").format(chyba))
        return cesta

    # ---- ovládání ----
    def _sledovani(self, zapnout: bool):
        if zapnout:
            if not self._spust(None):
                self.sledovat.setChecked(False)
            else:
                self.stav.setText(tr("Sledování úrovně – nic se neukládá."))
        elif self.nahravac and self.nahravac.cesta is None:
            self._zastav()
            self.stav.setText("")

    def _nahravani(self):
        if self.nahravac and self.nahravac.cesta is not None:          # ■ Zastavit
            cesta = self._zastav()
            self.nahravat.setText(tr("● Nahrávat"))
            self.sledovat.setEnabled(True)
            if cesta and cesta.exists():
                self.hotove = [c for c in self.hotove if c != cesta] + [cesta]
                self.otevrit.setEnabled(True)
                self.stav.setText(tr("Uloženo: {0}. Můžete nahrát další stranu, nebo nahrávky otevřít.").format(cesta.name))
                self.strana.setValue(min(9, self.strana.value() + 1))
            return
        if not self.inv.text().strip():
            QMessageBox.information(self, "SAKRA", tr("Vyplňte inventární číslo – podle něj se soubor pojmenuje."))
            return
        cesta = self.cesta()
        if cesta.exists() and QMessageBox.question(
                self, "SAKRA", tr("Soubor {0} už existuje. Přepsat?").format(cesta.name)) != QMessageBox.StandardButton.Yes:
            return
        if self.nahravac:                                                # ze sledování rovnou do nahrávání
            self.sledovat.blockSignals(True)
            self.sledovat.setChecked(False)
            self.sledovat.blockSignals(False)
            self._zastav()
        if self._spust(cesta):
            self._uloz_volby()
            self.nahravat.setText(tr("■ Zastavit"))
            self.sledovat.setEnabled(False)
            self.otevrit.setEnabled(False)

    def _uloz_volby(self):
        self.nastaveni.setValue("nahravani/rate", self.vzorkovani.currentData())
        self.nastaveni.setValue("nahravani/bitu", self.bitu.currentData())
        self.nastaveni.setValue("nahravani/kanaly", self.kanaly.currentData())
        nastaveni.zapamatuj_slozku("nahravani/slozka", self.slozka.text())

    def _tik(self):
        n = self.nahravac
        if n is None:
            return
        urovne = n.uroven()
        for i, m in enumerate(self.meraky):
            if i < len(urovne):
                m.nastav(urovne[i], n.prebuzeno)
        self._tiku += 1
        if self._tiku % 2 == 0:                       # ladění hlavy 5× za sekundu
            x = n.posledni()
            if len(x):
                self.ladeni.nastav(ladeni.vyhodnot(x, n.rate))
        if n.cesta is not None:
            text = tr("● Nahrávám {0} – {1}").format(n.cesta.name, cas_text(n.delka))
            if n.prebuzeno:
                text += tr("  <span style='color:#E04848'>přebuzeno – snižte úroveň a nahrajte znovu</span>")
            self.stav.setText(text)
        if n.chyba:
            self._nahravani() if n.cesta is not None else self._zastav()

    def done(self, r):
        if self.nahravac:
            if self.nahravac.cesta is not None and QMessageBox.question(
                    self, "SAKRA", tr("Nahrávání běží. Zastavit a zavřít?")) != QMessageBox.StandardButton.Yes:
                return
            self._zastav()
        super().done(r)
