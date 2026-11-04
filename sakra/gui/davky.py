"""Dávková linka (návrh C): fronta nahrávek, automatické zpracování, ruční kontrola jen sporných kazet.

Soubory se seskupí do kazet podle inventárního čísla v názvu (HH08518 (1).wav + HH08518 (2).wav = jedna kazeta).
Leží-li vedle nahrávek Excel se stejným inventárním číslem, načtou se z něj metadata.
Každá zpracovaná kazeta se uloží jako projekt .sakra (dá se otevřít na Pracovním stole); bezchybné se mohou
rovnou exportovat do archivu.
"""
from __future__ import annotations

import html
import re
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import soundfile as sf
from PySide6.QtCore import QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QFileDialog, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                               QTextBrowser, QVBoxLayout, QWidget)

from ..balicek import bezpecne_jmeno, exportuj
from ..jadro.analyza import popis_stavu
from ..jadro.model import Kazeta, cas_text
from ..jadro.texty import pocet
from ..metadata import excel
from ..platformy import podle_id
from ..projekt import PRIPONA, cislo_strany, inventarni_cislo, uloz, zpracuj
from ..i18n import tr, tr_data
from . import ikony
from .vyber_platformy import combo_platformy

PRIPONY = (".wav", ".flac", ".aif", ".aiff", ".ogg")
STAVY = {
    "fronta": (tr("◷ ve frontě"), "#8A93A3"),
    "bezi": (tr("⟳ zpracovává se"), "#4A86C8"),
    "hotovo": (tr("✓ hotovo"), "#2EA866"),
    "kontrola": (tr("⚠ ke kontrole"), "#D08A10"),
    "chyba": (tr("✗ chyba"), "#E04848"),
}


@dataclass
class Polozka:
    inv: str
    nahravky: dict[int, Path]
    xlsx: Path | None = None
    stav: str = "fronta"
    delka: float = 0.0
    platformy: list[str] = field(default_factory=list)
    souboru: int = 0
    chyb: int = 0
    k_kontrole: list[str] = field(default_factory=list)
    vysledek: list[str] = field(default_factory=list)
    projekt: Path | None = None
    balicek: Path | None = None
    zprava: str = ""
    prubeh: float = 0.0


def seskup(cesty: list[Path]) -> list[Polozka]:
    """Nahrávky -> kazety podle inventárního čísla (nebo jména bez označení strany)."""
    kazety: dict[str, Polozka] = {}
    for c in sorted(cesty):
        inv = inventarni_cislo(c)
        klic = inv or re.sub(r"\s*(\(\d\)|[ _-](strana|side|str)[ _-]*[12AB]|[ _-][AB])$", "", c.stem, flags=re.I)
        p = kazety.setdefault(klic, Polozka(inv or bezpecne_jmeno(klic), {}))
        n = cislo_strany(c, 0) or 1
        while n in p.nahravky:
            n += 1
        p.nahravky[n] = c
        xlsx = c.with_name(f"{p.inv}.xlsx")
        if inv and xlsx.exists():
            p.xlsx = xlsx
        try:
            p.delka += sf.info(str(c)).duration
        except Exception:  # noqa: BLE001
            pass
    return list(kazety.values())


class Zpracovani(QThread):
    zmena = Signal(int)

    def __init__(self, davky: "Davky", volby: dict):
        super().__init__(davky)
        self.d = davky
        self.volby = volby            # kopie nastavení z widgetů (vlákno na widgety nesahá)
        self.zastavit = False

    def run(self):
        while not self.zastavit:
            i = next((i for i, p in enumerate(self.d.polozky) if p.stav == "fronta"), None)
            if i is None:
                return
            p = self.d.polozky[i]
            p.stav = "bezi"
            self.zmena.emit(i)
            try:
                self._zpracuj(i, p)
            except Exception:  # noqa: BLE001 – chyba jedné kazety nezastaví dávku
                p.stav, p.zprava = "chyba", traceback.format_exc().strip().splitlines()[-1]
            self.zmena.emit(i)

    def _zpracuj(self, i: int, p: Polozka):
        kazeta = excel.importuj(p.xlsx) if p.xlsx else Kazeta()
        kazeta.inventar.cislo = kazeta.inventar.cislo or p.inv
        kazeta.platforma = self.volby.get("platforma", "")

        def pr(x, t=""):
            p.prubeh = float(x)
            self.zmena.emit(i)
        vysledky = zpracuj(kazeta, p.nahravky, pr)
        zaznamy = [(s.cislo, z) for s in kazeta.strany for z in s.zaznamy]
        p.souboru = sum(1 for _, z in zaznamy if z.soubor)
        p.chyb = sum(1 for _, z in zaznamy if z.stav == "chyba")
        p.platformy = sorted({podle_id(z.soubor.platforma).pocitac if podle_id(z.soubor.platforma) else z.platforma
                              for _, z in zaznamy if z.soubor})
        p.k_kontrole = [f"{c}-{cas_text(z.cas_od)} {tr_data(z.nazev)}: " + {
            "chyba": tr("chyba čtení – ") + (tr_data(popis_stavu(z.soubor)) if z.soubor else ""),
            "nerozpoznáno": tr("úsek bez platformy (uložen jako CSW). Určit platformu?"),
            "neověřeno": tr("formát bez kontrolního součtu, ověřeno jen délkou")}[z.stav]
            for c, z in zaznamy if z.stav in ("chyba", "nerozpoznáno", "neověřeno") and z.typ != "Audio"]
        pocty: dict[str, int] = {}
        for _, z in zaznamy:
            if z.soubor:
                pl = podle_id(z.soubor.platforma)
                k = f"{z.platforma} · {pl.pripona.upper() if pl else ''}"
                pocty[k] = pocty.get(k, 0) + 1
        nerozp = sum(1 for _, z in zaznamy if z.nerozpoznano and z.typ != "Audio")
        p.vysledek = [f"{k}: {v}" for k, v in pocty.items()] + (
            [tr("Nerozpoznáno (CSW): {0}").format(nerozp)] if nerozp else []
        )
        opr = sum(1 for _, z in zaznamy if z.stav == "opraveno")
        if opr:
            p.vysledek.append(tr("Opraveno z kopií: {0}").format(opr))
        vystup = Path(self.volby["vystup"])
        (vystup / "projekty").mkdir(parents=True, exist_ok=True)
        p.projekt = vystup / "projekty" / f"{bezpecne_jmeno(kazeta.inventar.cislo)}{PRIPONA}"
        uloz(kazeta, p.projekt)
        sporna = bool(p.chyb or nerozp)
        p.stav = "kontrola" if sporna else "hotovo"
        if self.volby["auto"] and not sporna:
            p.balicek = exportuj(kazeta, vystup, vysledky, kopirovat_zdroj=self.volby["zdroj"],
                                 cisty_wav=self.volby["cisty"], snimky=self.volby["snimky"])
            uloz(kazeta, p.projekt)


class Davky(QWidget):
    def __init__(self, okno, parent=None):
        super().__init__(parent)
        self.okno = okno
        self.nastaveni = QSettings("HerniArchiv", "SAKRA")
        self.polozky: list[Polozka] = []
        self.vlakno: Zpracovani | None = None
        self.filtr = "vse"
        self._velikosti: dict[str, int] = {}

        # lišta
        pridat = QPushButton(tr("+ Přidat nahrávky…"))
        pridat.clicked.connect(self._pridej_soubory)
        slozka = QPushButton(tr("+ Přidat složku…"))
        slozka.clicked.connect(self._pridej_slozku)
        self.start = QPushButton(tr("▶ Spustit"))
        self.start.setProperty("primarni", True)
        self.start.clicked.connect(self.spust)
        self.pauza = QPushButton(tr("Pozastavit"))
        self.pauza.clicked.connect(self.pozastav)
        self.export = QPushButton(tr("Exportovat schválené"))
        self.export.clicked.connect(self.exportuj_hotove)
        lista = QHBoxLayout()
        for b in (pridat, slozka, self.start, self.pauza, self.export):
            lista.addWidget(b)
        lista.addStretch(1)

        # pravidla
        pr = QGroupBox(tr("Pravidla dávky"))
        lp = QVBoxLayout(pr)
        r = QHBoxLayout()
        r.addWidget(QLabel(tr("Výstup (archiv):")))
        self.vystup = QLineEdit(self.nastaveni.value("davky/vystup", str(Path.home() / "SAKRA-archiv")))
        self.vystup.editingFinished.connect(lambda: self.nastaveni.setValue("davky/vystup", self.vystup.text()))
        r.addWidget(self.vystup, 1)
        b = QPushButton("…")
        b.clicked.connect(lambda: self._vyber_slozku(self.vystup, "davky/vystup"))
        r.addWidget(b)
        lp.addLayout(r)
        rp = QHBoxLayout()
        rp.addWidget(QLabel(tr("Platforma kazet:")))
        self.volba_platformy = combo_platformy()
        self.volba_platformy.setCurrentIndex(max(0, self.volba_platformy.findData(
            self.nastaveni.value("davky/platforma", ""))))
        self.volba_platformy.currentIndexChanged.connect(
            lambda _: self.nastaveni.setValue("davky/platforma", self.volba_platformy.currentData() or ""))
        rp.addWidget(self.volba_platformy, 1)
        lp.addLayout(rp)
        self.auto_export = QCheckBox(tr("Kazety bez chyb rovnou exportovat do archivu"))
        self.auto_export.setChecked(self.nastaveni.value("davky/auto", True, bool))
        self.zdroj = QCheckBox(tr("Přiložit kopii nahrávky (FLAC)"))
        self.zdroj.setChecked(True)
        self.cisty = QCheckBox(tr("WAV programů jako čistý signál"))
        self.snimky = QCheckBox(tr("Snímky z emulátoru (ZX Spectrum)"))
        self.snimky.setChecked(True)
        for c in (self.auto_export, self.zdroj, self.cisty, self.snimky):
            lp.addWidget(c)
        r2 = QHBoxLayout()
        self.sledovat = QCheckBox(tr("Sledovat složku:"))
        self.sledovat.toggled.connect(self._sledovani)
        self.sledovana = QLineEdit(self.nastaveni.value("davky/sledovana", ""))
        b2 = QPushButton("…")
        b2.clicked.connect(lambda: self._vyber_slozku(self.sledovana, "davky/sledovana"))
        r2.addWidget(self.sledovat)
        r2.addWidget(self.sledovana, 1)
        r2.addWidget(b2)
        lp.addLayout(r2)
        pozn = QLabel(tr("<span style='color:gray'>Nové nahrávky ve sledované složce se zařadí samy, jakmile se "
                         "dopíšou.</span>"))
        pozn.setWordWrap(True)
        lp.addWidget(pozn)
        lp.addStretch(1)
        self.casovac = QTimer(self)
        self.casovac.setInterval(5000)
        self.casovac.timeout.connect(self._zkontroluj_slozku)

        # filtry a tabulka
        self.filtry = QHBoxLayout()
        self.skupina = QButtonGroup(self)
        self.tlacitka_filtru = {}
        for klic, text in (("vse", tr("▤ Všechny")), ("fronta", STAVY["fronta"][0]), ("bezi", STAVY["bezi"][0]),
                           ("kontrola", STAVY["kontrola"][0]), ("chyba", STAVY["chyba"][0]),
                           ("hotovo", STAVY["hotovo"][0])):
            t = QPushButton(text)
            t.setCheckable(True)
            t.setChecked(klic == "vse")
            t.clicked.connect(lambda _=False, k=klic: self._nastav_filtr(k))
            self.skupina.addButton(t)
            self.tlacitka_filtru[klic] = (t, text)
            self.filtry.addWidget(t)
        self.filtry.addStretch(1)
        self.tabulka = QTableWidget(0, 7)
        self.tabulka.setHorizontalHeaderLabels(
            [tr("Inv. číslo"), tr("Nahrávky"), tr("Délka"), tr("Platformy"), tr("Souborů"), tr("Chyby"), tr("Stav")]
        )
        self.tabulka.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabulka.verticalHeader().hide()
        self.tabulka.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabulka.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabulka.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabulka.itemSelectionChanged.connect(self._ukaz_detail)
        self.tabulka.doubleClicked.connect(lambda _: self._otevri())
        self.souhrn = QLabel()

        # detail vybrané kazety
        self.detail = QTextBrowser()
        self.otevrit = QPushButton(tr("Otevřít na pracovním stole"))
        self.otevrit.clicked.connect(self._otevri)
        self.schvalit = QPushButton(tr("Schválit"))
        self.schvalit.setToolTip(tr("Kazetu ke kontrole označí jako hotovou (export pak přes „Exportovat schválené“)"))
        self.schvalit.clicked.connect(self._schval)
        self.znovu = QPushButton(tr("Zpracovat znovu"))
        self.znovu.clicked.connect(self._znovu)
        pravy = QWidget()
        lpr = QVBoxLayout(pravy)
        lpr.setContentsMargins(0, 0, 0, 0)
        lpr.addWidget(self.detail, 1)
        for b in (self.otevrit, self.schvalit, self.znovu):
            lpr.addWidget(b)
        lpr.addWidget(pr)

        levy = QWidget()
        ll = QVBoxLayout(levy)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addLayout(lista)
        ll.addWidget(self.souhrn)
        ll.addLayout(self.filtry)
        ll.addWidget(self.tabulka, 1)
        from .karta import posuvne
        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(levy)
        prava_oblast = posuvne(pravy)
        prava_oblast.setMinimumWidth(220)
        sp.addWidget(prava_oblast)
        sp.setSizes([840, 480])
        lay = QVBoxLayout(self)
        lay.addWidget(sp)
        self.obnov()

    # ------------------------------------------------------------ fronta
    def pridej(self, cesty: list[Path]) -> None:
        zname = {str(c) for p in self.polozky for c in p.nahravky.values()}
        nove = seskup([c for c in cesty if str(c) not in zname])
        self.polozky += nove
        self.obnov()

    def _pridej_soubory(self):
        cesty, _ = QFileDialog.getOpenFileNames(self, tr("Nahrávky do dávky"), self.okno._slozka(),
                                                tr("Nahrávky (*.wav *.flac *.aif *.aiff *.ogg)"))
        if cesty:
            self.okno._pamatuj(cesty[0])
            self.pridej([Path(c) for c in cesty])

    def _pridej_slozku(self):
        d = QFileDialog.getExistingDirectory(self, tr("Složka s nahrávkami"), self.okno._slozka())
        if d:
            self.pridej([p for p in sorted(Path(d).rglob("*")) if p.suffix.lower() in PRIPONY])

    def _vyber_slozku(self, pole: QLineEdit, klic: str):
        d = QFileDialog.getExistingDirectory(self, tr("Složka"), pole.text())
        if d:
            pole.setText(d)
            self.nastaveni.setValue(klic, d)

    def _sledovani(self, zapnuto: bool):
        self.nastaveni.setValue("davky/sledovana", self.sledovana.text())
        (self.casovac.start if zapnuto else self.casovac.stop)()
        if zapnuto:
            self._zkontroluj_slozku()

    def _zkontroluj_slozku(self):
        """Nový soubor se zařadí, až se jeho velikost mezi dvěma kontrolami nezmění (dopsaný)."""
        d = Path(self.sledovana.text())
        if not d.is_dir():
            return
        zname = {str(c) for p in self.polozky for c in p.nahravky.values()}
        hotove = []
        for c in d.iterdir():
            if c.suffix.lower() not in PRIPONY or str(c) in zname:
                continue
            vel = c.stat().st_size
            if self._velikosti.get(str(c)) == vel:
                hotove.append(c)
            self._velikosti[str(c)] = vel
        if hotove:
            self.pridej(hotove)
            self.spust()

    def spust(self):
        if self.vlakno and self.vlakno.isRunning():
            return
        Path(self.vystup.text()).mkdir(parents=True, exist_ok=True)
        self.nastaveni.setValue("davky/auto", self.auto_export.isChecked())
        self.vlakno = Zpracovani(self, {"vystup": self.vystup.text(), "auto": self.auto_export.isChecked(),
                                        "platforma": self.volba_platformy.currentData() or "",
                                        "zdroj": self.zdroj.isChecked(), "cisty": self.cisty.isChecked(),
                                        "snimky": self.snimky.isChecked()})
        self.vlakno.zmena.connect(self._zmena_polozky)
        self.vlakno.finished.connect(self.obnov)
        self.vlakno.start()
        self.obnov()

    def pozastav(self):
        if self.vlakno:
            self.vlakno.zastavit = True

    def bezi(self) -> bool:
        return bool(self.vlakno and self.vlakno.isRunning())

    def exportuj_hotove(self):
        """Hotové a schválené kazety, které ještě nemají balíček (export ve vlákně okna)."""
        cekaji = [p for p in self.polozky if p.stav == "hotovo" and p.balicek is None and p.projekt]
        if not cekaji:
            return

        def prace(pr):
            from ..projekt import otevri
            for i, p in enumerate(cekaji):
                pr(i / len(cekaji), tr("Export {0}").format(p.inv))
                k = otevri(p.projekt)
                p.balicek = exportuj(k, Path(self.vystup.text()), None, kopirovat_zdroj=self.zdroj.isChecked(),
                                     cisty_wav=self.cisty.isChecked(), snimky=self.snimky.isChecked())
            return len(cekaji)
        self.okno._spust(tr("Export schválených kazet…"), prace,
                         lambda n: (self.okno._zapis(tr("Exportováno kazet: {0}").format(n)), self.obnov()))

    # ------------------------------------------------------------ zobrazení
    def _zmena_polozky(self, i: int):
        self._radek(i)
        self._souhrn()
        if self.tabulka.currentRow() >= 0 and self._viditelne()[self.tabulka.currentRow()] == i:
            self._ukaz_detail()

    def _viditelne(self) -> list[int]:
        return [i for i, p in enumerate(self.polozky) if self.filtr == "vse" or p.stav == self.filtr]

    def _nastav_filtr(self, k: str):
        self.filtr = k
        self.obnov()

    def obnov(self):
        vid = self._viditelne()
        self.tabulka.setRowCount(len(vid))
        for r, _ in enumerate(vid):
            self._radek(vid[r], r)
        self._souhrn()
        bezi = self.bezi()
        self.start.setEnabled(not bezi and any(p.stav == "fronta" for p in self.polozky))
        self.pauza.setEnabled(bezi)

    def _radek(self, i: int, r: int | None = None):
        if r is None:
            vid = self._viditelne()
            if i not in vid:
                return
            r = vid.index(i)
        p = self.polozky[i]
        text, barva = STAVY[p.stav]
        if p.stav == "bezi":
            text += f" {p.prubeh * 100:.0f} %"
        hodnoty = [p.inv, ", ".join(c.name for _, c in sorted(p.nahravky.items())), cas_text(p.delka),
                   ", ".join(p.platformy) or "–", str(p.souboru) if p.stav not in ("fronta", "bezi") else "–",
                   str(p.chyb) if p.stav not in ("fronta", "bezi") else "–", text]
        for c, h in enumerate(hodnoty):
            it = QTableWidgetItem(h)
            if c == 6:
                it.setForeground(QColor(barva))
            if c == 3 and p.platformy:            # ikona první platformy, všechny v popisku
                it.setIcon(ikony.ikona(p.platformy[0]))
                it.setToolTip(", ".join(p.platformy))
            self.tabulka.setItem(r, c, it)

    def _souhrn(self):
        pocty = {k: sum(1 for p in self.polozky if p.stav == k) for k in STAVY}
        for k, (t, text) in self.tlacitka_filtru.items():
            t.setText(f"{text}  {len(self.polozky) if k == 'vse' else pocty.get(k, 0)}")
        souboru = sum(p.souboru for p in self.polozky)
        self.souhrn.setText(
            tr("{0} v dávce · {1} hotovo · {2} ke kontrole · {3}").format(
                pocet(len(self.polozky), 'kazeta', 'kazety', 'kazet'),
                pocty['hotovo'],
                pocty['kontrola'],
                pocet(souboru, 'dekódovaný soubor', 'dekódované soubory', 'dekódovaných souborů'),
            )
        )

    def _vybrana(self) -> Polozka | None:
        r = self.tabulka.currentRow()
        vid = self._viditelne()
        return self.polozky[vid[r]] if 0 <= r < len(vid) else None

    def _ukaz_detail(self):
        p = self._vybrana()
        self.otevrit.setEnabled(bool(p and p.projekt))
        self.schvalit.setEnabled(bool(p and p.stav == "kontrola"))
        self.znovu.setEnabled(bool(p and p.stav in ("kontrola", "chyba", "hotovo")))
        if p is None:
            self.detail.setHtml(tr("<p style='color:gray'>Vyberte kazetu.</p>"))
            return
        e = html.escape
        casti = [
            tr("<h3>{0}</h3><p style='color:gray'>{1} · {2}").format(
                e(p.inv), e(', '.join((c.name for c in p.nahravky.values()))), cas_text(p.delka)
            )
            + (tr(" · metadata z {0}").format(e(p.xlsx.name)) if p.xlsx else "")
            + "</p>"
        ]
        if p.zprava:
            casti.append(tr("<p style='color:#E04848'>{0}</p>").format(e(p.zprava)))
        if p.k_kontrole:
            casti.append(
                tr("<h4>Co potřebuje člověk</h4><ul>") + "".join(f"<li>⚠ {e(x)}</li>" for x in p.k_kontrole) + "</ul>"
            )
        if p.vysledek:
            casti.append(tr("<h4>Výsledek</h4><ul>") + "".join(f"<li>{e(x)}</li>" for x in p.vysledek) + "</ul>")
        if p.balicek:
            casti.append(tr("<p>Balíček: {0}</p>").format(e(str(p.balicek))))
        self.detail.setHtml("".join(casti))

    def _otevri(self):
        p = self._vybrana()
        if p and p.projekt:
            self.okno.prepni_rezim("stul")
            self.okno.otevri_projekt(str(p.projekt))

    def _schval(self):
        p = self._vybrana()
        if p and p.stav == "kontrola":
            p.stav = "hotovo"
            self.obnov()

    def _znovu(self):
        p = self._vybrana()
        if p and not self.bezi():
            p.stav, p.zprava, p.balicek = "fronta", "", None
            self.obnov()
