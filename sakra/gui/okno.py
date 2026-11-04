"""Hlavní okno se třemi režimy: Průvodce (návrh A), Pracovní stůl (B – časová osa, strom, tabulka podle vzoru,
karta kazety, detail) a Dávky (C)."""
from __future__ import annotations

import html
import re
import sys
import traceback
from pathlib import Path

import numpy as np
from PySide6.QtCore import QProcess, QSettings, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDockWidget,
                               QApplication, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
                               QMenuBar, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QSplitter, QStackedWidget, QTableView,
                               QTabWidget, QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import NAVOD, __version__
from ..balicek import bezpecne_jmeno, exportuj as exportuj_balicek
from ..jadro.analyza import VysledekStrany, obnov_navrhy, prenes_rucni, znovu_dekoduj_blok
from ..jadro.model import Kazeta, Zaznam, cas_text
from ..jadro.pulzy import odeber_hranu, vloz_hranu
from ..jadro.texty import pocet
from ..metadata import excel
from ..platformy import podle_id
from ..projekt import PRIPONA, analyzuj_strany, cislo_strany, otevri, uloz, vloz_vysledky
from .. import i18n
from ..i18n import tr, tr_data
from . import ikony, vzhled
from .casova_osa import CasovaOsa
from .davky import Davky
from .detail import Detail
from .karta import KartaKazety, posuvne
from .obsah import SLOUPCE, STAVY, ObsahModel, VolbyDelegat
from .prehravac import Prehravac
from .stul_panely import HistogramDelek, PrehledKazety, PulzyPohled, nadpis_sekce
from .pruvodce import Pruvodce
from .vyber_platformy import DialogPlatformy, combo_platformy
from .zahlavi import DialogNastaveni, Zahlavi

REZIMY = [("pruvodce", tr("Průvodce")), ("stul", tr("Pracovní stůl")), ("davky", tr("Dávky"))]

FILTR_ZVUK = tr("Nahrávky (*.wav *.flac *.aif *.aiff *.ogg);;Všechny soubory (*)")


class Ukol(QThread):
    """Práce na pozadí (analýza, export) s průběhem."""
    prubeh = Signal(float, str)
    hotovo = Signal(object)
    chyba = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.hotovo.emit(self.fn(lambda x, t="": self.prubeh.emit(float(x), tr_data(str(t)))))
        except Exception:  # noqa: BLE001 – chyba se ukáže uživateli
            self.chyba.emit(traceback.format_exc())


def _sekce(nadpis, vpravo, *obsah, natahnout: int = 0) -> QWidget:
    """Sekce Pracovního stolu: řádek s nadpisem (a údajem vpravo), pod ním obsah; poslední prvek se natahuje."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(10, 6, 10, 6)
    lay.setSpacing(4)
    r = QHBoxLayout()
    r.addWidget(nadpis)
    r.addStretch(1)
    if vpravo is not None:
        r.addWidget(vpravo)
    lay.addLayout(r)
    for i, o in enumerate(obsah):
        lay.addWidget(o, natahnout if i == len(obsah) - 1 else 0)
    return w


class HlavniOkno(QMainWindow):
    prehravani_skoncilo = Signal()      # dohrálo, nebo bylo zastaveno

    def __init__(self):
        super().__init__()
        self.kazeta = Kazeta()
        self.vysledky: dict[int, VysledekStrany] = {}
        self.cesta_projektu: Path | None = None
        self.ukol: Ukol | None = None
        self.nastaveni = QSettings("HerniArchiv", "SAKRA")
        # výchozí velikost podle obrazovky (ne víc, než se vejde), pak naposledy použitá
        plocha = self.screen().availableGeometry() if self.screen() else None
        if plocha is not None:
            self.resize(min(1440, int(plocha.width() * 0.92)), min(900, int(plocha.height() * 0.88)))
        else:
            self.resize(1280, 760)

        # časová osa + výběr strany
        self.osa = CasovaOsa()
        self.osa.klik.connect(self._klik_na_ose)
        self.osa.uprava.connect(self._uprava_signalu)
        self.uprava: dict | None = None
        self._vybrany: tuple | None = None       # (záznam, blok) – co je vybrané v tabulce, stromu nebo na ose
        self.strana = QComboBox()
        self.strana.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.strana.setMinimumContentsLength(14)
        self.strana.currentIndexChanged.connect(self._zobraz_stranu)
        nad_osou = QToolBar()
        nad_osou.addWidget(QLabel(tr(" Strana: ")))
        nad_osou.addWidget(self.strana)
        # kanál a polarita nahrávky (změna = nová analýza strany)
        self.volba_kanalu = QComboBox()
        for text, k in ((tr("Auto"), "auto"), (tr("Levý"), "levy"), (tr("Pravý"), "pravy")):
            self.volba_kanalu.addItem(text, k)
        self.volba_kanalu.setToolTip(tr("Kanál stereo nahrávky: Auto = ten se silnějším signálem"))
        self.volba_polarity = QComboBox()
        for text, k in ((tr("Auto"), "auto"), (tr("Normální"), "normalni"), (tr("Obrácená"), "obracena")):
            self.volba_polarity.addItem(text, k)
        self.volba_polarity.setToolTip(
            tr("Polarita signálu: Auto = při chybách se zkusí i obrácený signál a ponechá se lepší výsledek")
        )
        self.volba_kanalu.activated.connect(lambda _: self._zmena_volby())
        self.volba_polarity.activated.connect(lambda _: self._zmena_volby())
        # pro jaký počítač je kazeta (ruční volba = jen jeho dekodéry, rychlejší); změna = nová analýza stran
        self.volba_platformy = combo_platformy()
        self.volba_platformy.activated.connect(lambda _: self._zmena_platformy())
        for cb in (self.volba_kanalu, self.volba_polarity):
            cb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.volba_platformy.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.volba_platformy.setMinimumContentsLength(12)
        nad_osou.addAction(tr("Celá strana"), self.osa.cele)
        akce_prehrat = nad_osou.addAction(tr("▶ Přehrát"), self.prehraj_vyber)
        akce_prehrat.setToolTip(tr("Přehrát vybraný úsek (mezerník)"))
        nad_osou.addAction("■", self.zastav_prehravani).setToolTip(tr("Zastavit přehrávání"))
        nad_osou.addSeparator()
        self.akce_uprava = nad_osou.addAction(tr("✎ Ruční úprava"))
        self.akce_uprava.setCheckable(True)
        self.akce_uprava.setEnabled(False)
        self.akce_uprava.setToolTip(
            tr(
                "Oprava vadného bloku přidáním nebo odebráním přechodů přes nulu (po přiblížení "
                "na jednotlivé vzorky)"
            )
        )
        self.akce_uprava.toggled.connect(self._prepni_upravu)
        # pruh ruční úpravy: stav kontrolního součtu po každém kliknutí
        self.panel_upravy = QWidget()
        pu = QHBoxLayout(self.panel_upravy)
        pu.setContentsMargins(10, 4, 10, 4)
        self.stav_upravy = QLabel()
        self.stav_upravy.setTextFormat(Qt.TextFormat.RichText)
        self.stav_upravy.setWordWrap(True)
        pu.addWidget(self.stav_upravy, 1)
        vratit = QPushButton(tr("Vrátit úpravy"))
        vratit.clicked.connect(self._vrat_upravy)
        hotovo = QPushButton(tr("Hotovo"))
        hotovo.clicked.connect(lambda: self.akce_uprava.setChecked(False))
        pu.addWidget(vratit)
        pu.addWidget(hotovo)
        self.panel_upravy.hide()
        self.osa.rozsah.connect(self._zmena_pohledu)
        self.osa.mys.connect(self._mys_na_ose)

        # přehled kazety: všechny strany, rámeček = co ukazuje detail strany
        self.prehled = PrehledKazety()
        self.prehled.klik.connect(self._klik_v_prehledu)
        self.legenda = QLabel()
        self.legenda.setTextFormat(Qt.TextFormat.RichText)
        # záhlaví přehledu: pro jaký počítač kazeta je (týká se celé kazety)
        zahlavi_prehledu = QWidget()
        zp = QHBoxLayout(zahlavi_prehledu)
        zp.setContentsMargins(0, 0, 0, 0)
        zp.addWidget(nadpis_sekce(tr("PŘEHLED KAZETY")))
        zp.addSpacing(10)
        zp.addWidget(self.volba_platformy)
        sekce_prehled = _sekce(zahlavi_prehledu, self.legenda, self.prehled)

        # detail strany
        self.nadpis_strany = nadpis_sekce("STRANA")
        self.info_strany = QLabel()
        self.info_strany.setStyleSheet("color:#8C95A6")
        horni = _sekce(self.nadpis_strany, self.info_strany, nad_osou, self.panel_upravy, self.osa, natahnout=4)

        # pulzy a histogram délek
        self.pulzy = PulzyPohled()
        self.nadpis_pulzu = nadpis_sekce(tr("PULZY"))
        self.histogram = HistogramDelek()
        self.nadpis_histogramu = nadpis_sekce(tr("HISTOGRAM DÉLEK"))
        self._kotva_pulzu: float | None = None
        radek_pulzu = QWidget()
        rp = QHBoxLayout(radek_pulzu)
        rp.setContentsMargins(0, 0, 0, 0)
        rp.setSpacing(0)
        rp.addWidget(_sekce(self.nadpis_pulzu, None, self.pulzy, natahnout=2), 3)
        sh = _sekce(self.nadpis_histogramu, None, self.histogram, natahnout=2)
        sh.setMinimumWidth(220)
        sh.setMaximumWidth(340)
        rp.addWidget(sh, 1)

        # dolní záložky
        self.model = ObsahModel(self.kazeta)
        self.tabulka = QTableView()
        self.tabulka.setModel(self.model)
        self.tabulka.setItemDelegate(VolbyDelegat(self.tabulka))
        self.tabulka.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabulka.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabulka.setAlternatingRowColors(True)
        self.tabulka.verticalHeader().setDefaultSectionSize(22)
        self.tabulka.verticalHeader().hide()
        sirky = {"_strana": 60, "_stav": 110, "cas_od": 70, "cas_do": 70, "typ": 55, "platforma": 190,
                 "nazev": 190, "obsah": 75, "funkcni_orig": 95, "funkcni_edit": 90, "turbo": 100,
                 "nazev_bloku": 120, "typ_bloku": 75}
        for i, (_, pole) in enumerate(SLOUPCE):
            if pole in sirky:
                self.tabulka.setColumnWidth(i, sirky[pole])
        self.tabulka.horizontalHeader().setSectionResizeMode(len(SLOUPCE) - 1, QHeaderView.ResizeMode.Stretch)
        self.tabulka.selectionModel().currentRowChanged.connect(self._vybran_radek)
        self.model.dataChanged.connect(lambda *_: self._zmena())

        self.karta = KartaKazety()
        self.karta.zmeneno.connect(self._zmena_karty)
        self.detail = Detail()
        self.detail.ulozit.connect(self._uloz_program)
        self.detail.emulovat.connect(self.emuluj)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)

        self.zalozky = QTabWidget()
        self.zalozky.addTab(self.tabulka, tr("Obsah pásky"))
        self.zalozky.addTab(posuvne(self.karta), tr("Kazeta"))
        self.zalozky.addTab(self.log, tr("Protokol"))

        self.detail.blok.connect(lambda z, b: self._vyber_zaznam(z, blok=b))
        self.detail.setMinimumWidth(280)

        stred = QSplitter(Qt.Orientation.Vertical)
        stred.setChildrenCollapsible(False)
        for w in (sekce_prehled, horni, radek_pulzu, self.zalozky):
            stred.addWidget(w)
        stred.setStretchFactor(1, 3)
        stred.setStretchFactor(3, 2)
        stred.setSizes([110, 260, 130, 260])

        stul = QSplitter(Qt.Orientation.Horizontal)
        stul.addWidget(stred)
        stul.addWidget(self.detail)
        stul.setStretchFactor(0, 3)
        stul.setStretchFactor(1, 1)
        stul.setSizes([1000, 360])
        self.stul = stul

        # strom vlevo
        self.strom = QTreeWidget()
        self.strom.setHeaderLabels([tr("Obsah"), tr("Stav")])
        self.strom.setColumnWidth(0, 210)
        self.strom.itemClicked.connect(self._klik_ve_stromu)
        self.nadpis_obsahu = nadpis_sekce(tr("OBSAH KAZETY"))
        self.platformy = QLabel()
        self.platformy.setTextFormat(Qt.TextFormat.RichText)
        self.platformy.setContentsMargins(10, 0, 10, 8)
        levy = QWidget()
        ll = QVBoxLayout(levy)
        ll.setContentsMargins(0, 6, 0, 0)
        ll.setSpacing(4)
        self.nadpis_obsahu.setContentsMargins(10, 0, 10, 0)
        ll.addWidget(self.nadpis_obsahu)
        ll.addWidget(self.strom, 1)
        np_ = nadpis_sekce(tr("PLATFORMY NA PÁSCE"))
        np_.setContentsMargins(10, 6, 10, 0)
        ll.addWidget(np_)
        ll.addWidget(self.platformy)
        dok = QDockWidget(tr("Kazeta"), self)
        self.dok = dok
        dok.setObjectName("strom")
        dok.setTitleBarWidget(QWidget())        # nadpis je v panelu (Obsah kazety)
        dok.setWidget(levy)
        dok.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dok)
        self.resizeDocks([dok], [310], Qt.Orientation.Horizontal)

        # režimy: Průvodce, Pracovní stůl, Dávky
        self.pruvodce = Pruvodce(self)
        self.davky = Davky(self)
        self.stack = QStackedWidget()
        # Průvodce a Dávky v posuvné oblasti – okno jde zmenšit i na malou obrazovku
        self.stranky_rezimu = {"pruvodce": posuvne(self.pruvodce), "stul": self.stul, "davky": posuvne(self.davky)}
        for w in self.stranky_rezimu.values():
            self.stack.addWidget(w)
        self.setCentralWidget(self.stack)

        self.prehravac = Prehravac()
        self._strana_prehravani: int | None = None
        self.casovac_prehravani = QTimer(self)
        self.casovac_prehravani.setInterval(50)
        self.casovac_prehravani.timeout.connect(self._kurzor_prehravani)

        self._akce()
        self.prubeh = QProgressBar()
        self.prubeh.setMaximumWidth(260)
        self.prubeh.setRange(0, 1000)
        self.prubeh.hide()
        self.statusBar().addPermanentWidget(self.prubeh)
        self._nastav_kazetu(Kazeta())
        self.prepni_rezim(self.nastaveni.value("rezim", "stul"))
        geometrie = self.nastaveni.value("okno/geometrie")
        if geometrie:
            self.restoreGeometry(geometrie)
        self._zapis(tr("SAKRA {0} – připraveno.").format(__version__))

    # ------------------------------------------------------------ nabídky
    def _akce(self):
        # nahoře: (záhlaví), logo, nabídka a přepínač režimů jako segmenty – podle návrhu
        self.menu_lista = QMenuBar()
        self.zahlavi = Zahlavi(self, self.menu_lista, REZIMY, self.prepni_rezim)
        self.setMenuWidget(self.zahlavi)
        skupina = QActionGroup(self)
        self.akce_rezimu = {}
        for klic, text in REZIMY:
            a = QAction(text, self)
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, k=klic: self.prepni_rezim(k))
            skupina.addAction(a)
            self.akce_rezimu[klic] = a
        lista = QToolBar(tr("Hlavní"))
        lista.setObjectName("hlavni")
        lista.setMovable(False)
        lista.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(lista)
        self.lista = lista
        m_soubor = self.menu_lista.addMenu(tr("&Soubor"))
        m_metadata = self.menu_lista.addMenu(tr("&Metadata"))
        m_zobrazit = self.menu_lista.addMenu(tr("&Zobrazit"))
        m_pomoc = self.menu_lista.addMenu(tr("&Nápověda"))

        def akce(text, fn, menu, klavesa=None, do_listy=True):
            a = QAction(text, self)
            a.triggered.connect(fn)
            if klavesa:
                a.setShortcut(QKeySequence(klavesa))
            menu.addAction(a)
            if do_listy:
                lista.addAction(a)
            return a

        akce(tr("Nová kazeta"), self.nova, m_soubor, QKeySequence.StandardKey.New)
        akce(tr("Otevřít nahrávku…"), self.otevri_nahravky, m_soubor, "Ctrl+O")
        akce(tr("Otevřít projekt…"), self.otevri_projekt, m_soubor, "Ctrl+Shift+O")
        akce(tr("Uložit projekt"), self.uloz_projekt, m_soubor, QKeySequence.StandardKey.Save)
        m_soubor.addSeparator()
        lista.addSeparator()
        export = akce(tr("Archivní balíček…"), self.export_balicku, m_soubor, "Ctrl+E")
        lista.widgetForAction(export).setProperty("primarni", True)
        m_soubor.addSeparator()
        akce(tr("Nastavení…"), self.nastaveni_vzhledu, m_soubor, "Ctrl+,", do_listy=False)
        m_soubor.addSeparator()
        akce(tr("Konec"), self.close, m_soubor, "Ctrl+Q", do_listy=False)
        lista.addSeparator()
        akce(tr("Načíst z Excelu…"), self.nacti_excel, m_metadata)
        akce(tr("Uložit Excel…"), self.uloz_excel, m_metadata)
        lista.addSeparator()                     # jak se čte zobrazená strana (jako v návrhu: v hlavní liště)
        lista.addWidget(QLabel(tr(" Kanál: ")))
        lista.addWidget(self.volba_kanalu)
        lista.addWidget(QLabel(tr("  Polarita: ")))
        lista.addWidget(self.volba_polarity)
        for klic, text in REZIMY:
            m_zobrazit.addAction(self.akce_rezimu[klic])
        prehrat = QAction(tr("Přehrát výběr"), self)
        prehrat.setShortcut(QKeySequence(Qt.Key.Key_Space))
        prehrat.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        prehrat.triggered.connect(self.prehraj_vyber)
        self.osa.addAction(prehrat)
        m_zobrazit.addSeparator()
        m_zobrazit.addAction(prehrat)
        akce(tr("Návod (PDF)"), self.otevri_navod, m_pomoc, QKeySequence.StandardKey.HelpContents, do_listy=False)
        m_pomoc.addSeparator()
        akce(tr("O aplikaci"), self.o_aplikaci, m_pomoc, do_listy=False)

    # ------------------------------------------------------------ stav
    def _zapis(self, text: str) -> None:
        self.log.appendPlainText(text)
        self.statusBar().showMessage(text, 8000)

    def _titulek(self):
        cislo = self.kazeta.inventar.cislo or tr("nová kazeta")
        self.setWindowTitle(
            tr("SAKRA — {0}").format(cislo) + (f" ({self.cesta_projektu.name})" if self.cesta_projektu else "")
        )

    def _nastav_kazetu(self, k: Kazeta) -> None:
        self.kazeta = k
        self.model.nastav(k)
        self.karta.nastav(k)
        self.detail.nastav(None)
        if hasattr(self, "pruvodce"):
            self.pruvodce.karta.nastav(k)
        self._obnov_strany()
        self._obnov_strom()
        self._titulek()
        self._obnov_platformu()

    def _obnov_platformu(self):
        """Volba platformy kazety v liště (a v průvodci) podle kazety."""
        self.volba_platformy.setCurrentIndex(max(0, self.volba_platformy.findData(self.kazeta.platforma)))
        if hasattr(self, "pruvodce"):
            self.pruvodce.vyber_platformy.nastav(self.kazeta.platforma)

    def nastav_platformu(self, hodnota: str) -> None:
        self.kazeta.platforma = hodnota
        self._obnov_platformu()

    def _zmena_platformy(self):
        nova = self.volba_platformy.currentData() or ""
        if nova == self.kazeta.platforma:
            return
        nahravky = {s.cislo: Path(s.nahravka) for s in self.kazeta.strany if s.nahravka and Path(s.nahravka).exists()}
        if nahravky:
            if self.ukol and self.ukol.isRunning():
                QMessageBox.information(self, "SAKRA", tr("Počkejte, až doběhne předchozí úloha."))
                self._obnov_platformu()
                return
            if QMessageBox.question(self, "SAKRA", tr("Zpracovat znovu všechny strany kazety pro: {0}?").format(
                    self.volba_platformy.currentText())) != QMessageBox.StandardButton.Yes:
                self._obnov_platformu()
                return
        self.nastav_platformu(nova)
        if nahravky:
            self.analyzuj(nahravky)

    def _zmena(self):
        self._obnov_strom()
        self.obnov_oblasti()

    def obnov_oblasti(self):
        """Barvy nerozpoznaných úseků na časové ose a v přehledu podle ručního určení (žádná data = zvuk)."""
        zmena = False
        for s in self.kazeta.strany:
            v = self.vysledky.get(s.cislo)
            if v is None:
                continue
            for z in s.zaznamy:
                if not z.nerozpoznano or z.cas_od is None:
                    continue
                for o in v.oblasti:
                    if o.platforma is None and abs(o.zacatek - z.cas_od) < 0.05:
                        nazev = "audio" if z.typ == "Audio" else ""
                        if o.nazev != nazev:
                            o.nazev = nazev
                            zmena = True
        if zmena:
            self.prehled.nastav(self.vysledky)
            self._zmena_pohledu(self.osa.od, self.osa.do)
            self.osa.update()

    def _zmena_karty(self):
        self._titulek()
        if hasattr(self, "pruvodce"):
            self.pruvodce.obnov_inv()

    def _obnov_strany(self):
        self.prehled.nastav(self.vysledky)
        akt = self.strana.currentData()
        self.strana.blockSignals(True)
        self.strana.clear()
        for s in self.kazeta.strany:
            self.strana.addItem(f"{s.cislo} – {Path(s.nahravka).name if s.nahravka else 'bez nahrávky'}", s.cislo)
        i = self.strana.findData(akt)
        self.strana.setCurrentIndex(i if i >= 0 else 0)
        self.strana.blockSignals(False)
        self._zobraz_stranu()

    def _zobraz_stranu(self, *_):
        cislo = self.strana.currentData()
        self._kotva_pulzu = None
        self.osa.nastav(self.vysledky.get(cislo))
        self._obnov_volby()
        pl = {z.soubor.platforma for s in self.kazeta.strany for z in s.zaznamy if z.soubor}
        nazvy = {}
        for p in sorted(pl):
            if podle_id(p):
                nazvy.setdefault(podle_id(p).pocitac, podle_id(p).barva)
        self.legenda.setText("&nbsp;&nbsp;".join(
            f"<span style='color:{b}'>●</span> {n}" for n, b in nazvy.items())
            + tr("&nbsp;&nbsp;<span style='color:#8A93A3'>●</span> nerozpoznáno"))

    # ------------------------------------------------------------ kanál a polarita
    def _obnov_volby(self):
        """Výběry kanálu a polarity podle zobrazené strany; u Auto i to, co se skutečně použilo."""
        cislo = self.strana.currentData()
        s = next((s for s in self.kazeta.strany if s.cislo == cislo), None)
        v = self.vysledky.get(cislo)
        for cb, hodnota, auto in (
                (self.volba_kanalu, s.volba_kanalu if s else "auto",
                 (tr("levý"), tr("pravý"))[min(1, s.kanal)] if s else ""),
                (self.volba_polarity, s.polarita if s else "auto",
                 tr("obrácená") if s and s.signal.get("polarita_obracena") else tr("normální"))):
            cb.blockSignals(True)
            cb.setItemText(0, tr("Auto"))
            cb.setItemData(
                0, tr("Auto – použit: {0}").format(auto) if s and v else tr("Auto"), Qt.ItemDataRole.ToolTipRole
            )
            i = cb.findData(hodnota)
            cb.setCurrentIndex(i if i >= 0 else 0)
            cb.blockSignals(False)
        self.volba_kanalu.setEnabled(bool(v and v.nahravka.kanaly > 1))
        self.volba_polarity.setEnabled(v is not None)
        if v is not None and v.nahravka.kanaly == 1:
            self.volba_kanalu.setItemText(0, tr("Mono"))

    def _zmena_volby(self):
        cislo = self.strana.currentData()
        s = next((s for s in self.kazeta.strany if s.cislo == cislo), None)
        if s is None or not s.nahravka or not Path(s.nahravka).exists():
            self._obnov_volby()
            return
        kanal, polarita = self.volba_kanalu.currentData(), self.volba_polarity.currentData()
        if (kanal, polarita) == (s.volba_kanalu, s.polarita):
            return
        rucni = [z.nazev for z in s.zaznamy if z.soubor and any(b.oprava.startswith("ruční úprava")
                                                                  for b in z.soubor.bloky)]
        if rucni and QMessageBox.question(
                self, "SAKRA", tr("Nová analýza strany zahodí ruční úpravy signálu (") + ", ".join(rucni[:3])
                + tr("). Pokračovat?")) != QMessageBox.StandardButton.Yes:
            self._obnov_volby()
            return
        if self.uprava is not None:
            self.akce_uprava.setChecked(False)
        s.volba_kanalu, s.polarita = kanal, polarita
        self._zapis(
            tr("Strana {0}: kanál {1}, polarita {2} – nová analýza.").format(
                cislo,
                self.volba_kanalu.currentText().split(' (')[0].lower(),
                self.volba_polarity.currentText().split(' (')[0].lower(),
            )
        )
        self.analyzuj({cislo: Path(s.nahravka)})

    # ------------------------------------------------------------ přehled, pulzy, histogram
    def _strana_v(self):
        return self.vysledky.get(self.strana.currentData())

    def _chyby_strany(self, v) -> list[float]:
        return [b.konec for s in v.soubory for b in s.bloky if not b.ok] if v else []

    def _zmena_pohledu(self, od: float, do: float):
        v = self._strana_v()
        cislo = self.strana.currentData()
        self.prehled.nastav_vyber(cislo if v else None, od, do)
        self.histogram.nastav(v, od, do)
        z = self._vybrany[0] if self._vybrany else None
        nazev = f" · {z.nazev}" if z is not None and z in (self._zaznamy_strany() or []) else ""
        self.nadpis_strany.setText(
            tr("STRANA {0} · {1} – {2}{3}").format(
                cislo if cislo is not None else '', cas_text(od)[:8], cas_text(do)[:8], html.escape(nazev).upper()
            )
            if v
            else tr("STRANA")
        )
        if v:
            sig = v.strana.signal or {}
            rychl = sig.get("rychlost")
            casti = [tr("zobrazeno {0}").format(cas_text(do - od)[:8])]
            if rychl:
                rt = tr("rychlost {0:+.1f} %").format((rychl - 1) * 100)
                casti.append(rt.replace(".", ",") if i18n.jazyk() == "cs" else rt)
            casti.append(f"{v.nahravka.vzorkovani_popis}, {v.nahravka.format_popis}")
            if v.nahravka.kanaly > 1:
                casti.append((tr("levý"), tr("pravý"))[min(1, v.nahravka.kanal)] + tr(" kanál"))
            if sig.get("polarita_obracena"):
                casti.append(tr("obrácená polarita"))
            self.info_strany.setText(" · ".join(casti))
        else:
            self.info_strany.setText("")
        if self.osa._mys is None:
            self._ukaz_pulzy(self._kotva_pulzu if self._kotva_pulzu is not None and od <= self._kotva_pulzu <= do
                             else (od + do) / 2)

    def _zaznamy_strany(self):
        return next((s.zaznamy for s in self.kazeta.strany if s.cislo == self.strana.currentData()), [])

    def _ukaz_pulzy(self, t: float | None):
        v = self._strana_v()
        self.pulzy.nastav(v, t if v else None, self._chyby_strany(v))
        popis = self.pulzy.text_popisu() if v and t is not None else ""
        cas_pulzu = f"{t:.3f} s" if t is not None else ""
        if i18n.jazyk() == "cs":
            cas_pulzu = cas_pulzu.replace(".", ",")
        self.nadpis_pulzu.setText(tr("PULZY") + f" · {cas_pulzu}" + (
            tr("   <span style='font-weight:normal'>{0}</span>").format(popis) if popis else "") if v and t is not None
            else tr("PULZY"))

    def _mys_na_ose(self, t: float):
        if t != t:                                   # NaN: myš odešla z průběhu
            self._zmena_pohledu(self.osa.od, self.osa.do)
        else:
            self._ukaz_pulzy(t)

    def _klik_v_prehledu(self, strana: int, t: float):
        if strana != self.strana.currentData():
            self.strana.setCurrentIndex(self.strana.findData(strana))
        s = next((s for s in self.kazeta.strany if s.cislo == strana), None)
        z = next((z for z in (s.zaznamy if s else []) if z.cas_od is not None and z.cas_do is not None
                  and z.cas_od <= t <= z.cas_do and z.soubor is not None), None) if s else None
        if z is not None:
            self._vyber_zaznam(z)
        else:
            sirka = min(self.osa.do - self.osa.od, 30.0)
            self.osa.vyber = None
            self.osa._nastav_rozsah(t - sirka / 2, t + sirka / 2)

    def _obnov_platformy(self):
        pocty: dict[str, list] = {}
        nerozp = 0
        for s in self.kazeta.strany:
            for z in s.zaznamy:
                if z.soubor is None:
                    nerozp += z.nerozpoznano and z.typ != "Audio"
                    continue
                pl = podle_id(z.soubor.platforma)
                if pl is None:
                    continue
                d = pocty.setdefault(pl.pocitac, [pl.barva, 0, 0])
                d[1] += 1
                d[2] += z.soubor.stav in ("ok", "opraveno", "neověřeno")
        radky = [
            tr("<tr><td>{0} {1}</td><td align=right style='color:#8A93A3'>{2} · {3} v pořádku</td></tr>")
            .format(ikony.html(n, 16), html.escape(n), c, ok)
            for n, (_, c, ok) in sorted(pocty.items(), key=lambda x: -x[1][1])
        ]
        if nerozp:
            radky.append(tr("<tr><td>{0} Nerozpoznáno</td><td align=right style='color:#8A93A3'>{1}</td></tr>")
                         .format(ikony.html(ikony.NEROZPOZNANO, 16), nerozp))
        self.platformy.setText(tr("<table width='100%' cellspacing=0 cellpadding=2>") + "".join(radky) + "</table>"
                               if radky else tr("<span style='color:#8A93A3'>–</span>"))
        programu = sum(1 for s in self.kazeta.strany for z in s.zaznamy if z.soubor is not None)
        self.nadpis_obsahu.setText(
            tr("OBSAH KAZETY   <span style='font-weight:normal'>{0}</span>").format(
                pocet(programu, "soubor", "soubory", "souborů"))
        )

    def _obnov_strom(self):
        self._obnov_platformy()
        self.strom.clear()
        for s in self.kazeta.strany:
            it = QTreeWidgetItem([tr("Strana {0}").format(s.cislo), pocet(len(s.zaznamy), "položka", "položky", "položek")])
            it.setData(0, Qt.ItemDataRole.UserRole, ("strana", s.cislo))
            f = it.font(0)
            f.setBold(True)
            it.setFont(0, f)
            self.strom.addTopLevelItem(it)
            for z in s.zaznamy:
                text, barva = STAVY.get(z.stav, (z.stav, "#8A93A3"))
                pod = QTreeWidgetItem([f"{cas_text(z.cas_od)}  {tr_data(z.nazev)}", text])
                pod.setForeground(1, QColor(barva))
                pod.setIcon(0, ikony.ikona(ikony.klic_zaznamu(z)))
                pod.setData(0, Qt.ItemDataRole.UserRole, ("zaznam", z))
                it.addChild(pod)
                if z.soubor:
                    for b in z.soubor.bloky:
                        bl = QTreeWidgetItem(
                            [
                                f"{b.typ} {'' if b.cislo is None else b.cislo}".strip(),
                                "✓" + (tr(" opraveno") if b.oprava else "") if b.ok else tr("✗ chyba"),
                            ]
                        )
                        bl.setForeground(1, QColor("#2EA866" if b.ok and not b.oprava else
                                                   "#D08A10" if b.ok else "#E04848"))
                        bl.setData(0, Qt.ItemDataRole.UserRole, ("blok", z, b))
                        pod.addChild(bl)
            it.setExpanded(True)

    # ------------------------------------------------------------ výběr
    def _vyber_zaznam(self, z: Zaznam, z_tabulky: bool = False, blok=None):
        self.detail.nastav(z)
        self._vybrany = (z, blok)
        # pulzy: místo chyby (kde se čtení zastavilo), jinak začátek vybraného bloku / programu
        vadne = [b for b in (z.soubor.bloky if z.soubor else []) if not b.ok]
        if blok is not None:
            self._kotva_pulzu = blok.konec if not blok.ok else blok.zacatek + min(0.5, (blok.konec - blok.zacatek) / 2)
        elif vadne:
            self._kotva_pulzu = vadne[0].konec
        else:
            self._kotva_pulzu = None
        if not self.akce_uprava.isChecked():
            self.akce_uprava.setEnabled(bool(z.soubor and any(not b.ok for b in z.soubor.bloky)))
        strana = next((s.cislo for s in self.kazeta.strany if z in s.zaznamy), None)
        if strana is not None and strana != self.strana.currentData():
            self.strana.setCurrentIndex(self.strana.findData(strana))
        if blok is not None:
            self.osa.ukaz(blok.zacatek, blok.konec)
        elif z.cas_od is not None and z.cas_do is not None:
            self.osa.ukaz(z.cas_od, z.cas_do)
        if not z_tabulky:
            r = self.model.radek_zaznamu(z)
            if r >= 0:
                self.tabulka.selectRow(r)
                self.tabulka.scrollTo(self.model.index(r, 0))

    def _vybran_radek(self, aktualni, _):
        if aktualni.isValid():
            self._vyber_zaznam(self.model.radky[aktualni.row()][1], z_tabulky=True)

    def _klik_ve_stromu(self, it, _):
        d = it.data(0, Qt.ItemDataRole.UserRole)
        if not d:
            return
        if d[0] == "zaznam":
            self._vyber_zaznam(d[1])
        elif d[0] == "blok":
            self._vyber_zaznam(d[1], blok=d[2])
        elif d[0] == "strana":
            self.strana.setCurrentIndex(self.strana.findData(d[1]))
            self.osa.cele()

    def _klik_na_ose(self, t: float):
        s = next((s for s in self.kazeta.strany if s.cislo == self.strana.currentData()), None)
        if not s:
            return
        z = next((z for z in s.zaznamy if z.cas_od is not None and z.cas_do is not None
                  and z.cas_od - 0.5 <= t <= z.cas_do + 0.5), None)
        if z:
            self._vyber_zaznam(z)

    # ------------------------------------------------------------ režimy
    def prepni_rezim(self, klic: str):
        if klic not in self.stranky_rezimu:
            klic = "stul"
        self.stack.setCurrentWidget(self.stranky_rezimu[klic])
        self.akce_rezimu[klic].setChecked(True)
        self.zahlavi.nastav_rezim(klic)
        self.dok.setVisible(klic == "stul")
        self.lista.setVisible(klic == "stul")
        self.nastaveni.setValue("rezim", klic)
        if klic == "pruvodce":
            self.pruvodce.obnov()

    # ------------------------------------------------------------ vzhled
    def nastaveni_vzhledu(self):
        d = DialogNastaveni(vzhled.Nastaveni.nacti(), self)
        if d.exec() == QDialog.DialogCode.Accepted:
            n = d.vysledek()
            n.uloz()
            self.pouzij_vzhled(n)
            if d.vybrany_jazyk() != i18n.jazyk():
                i18n.uloz(d.vybrany_jazyk())
                self._restart_kvuli_jazyku()

    def _restart_kvuli_jazyku(self):
        """Texty oken se vytvářejí při startu v nastaveném jazyce – nový jazyk vyžaduje restart."""
        odp = QMessageBox.question(self, "SAKRA", "Jazyk se změní po restartu aplikace. Restartovat teď?\n\n"
                                   "The language changes after restarting the application. Restart now?")
        if odp != QMessageBox.StandardButton.Yes or not self.close():
            return
        args = sys.argv[1:] if getattr(sys, "frozen", False) else ["-m", "sakra"] + sys.argv[1:]
        QProcess.startDetached(sys.executable, args)

    def pouzij_vzhled(self, n: vzhled.Nastaveni | None = None):
        app = QApplication.instance()
        n = vzhled.pouzij(app, n, koren=self)
        bez_ramu = n.styl == "navrh" and n.zahlavi
        self.zahlavi.titulek.setVisible(bez_ramu)
        if bool(self.windowFlags() & Qt.WindowType.FramelessWindowHint) != bez_ramu:
            viditelne = self.isVisible()
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, bez_ramu)
            if viditelne:
                self.show()
        self.zahlavi.nazev.setText(self.windowTitle())
        # barvy, které se kreslí v kódu (tabulka, osa, detail, karty průvodce)
        self.model.obnov()
        self._obnov_strom()
        self.osa.update()
        self.detail.nastav(self.detail.z)
        self.pruvodce.jdi(self.pruvodce.krok)

    # ------------------------------------------------------------ ruční úprava signálu
    def _prepni_upravu(self, zapnout: bool):
        if not zapnout:
            self._ukonci_upravu()
            return
        z, blok = self._vybrany or (None, None)
        s = z.soubor if z else None
        if blok is None or blok.ok:
            blok = next((b for b in s.bloky if not b.ok), None) if s else None
        strana = next((st.cislo for st in self.kazeta.strany if z in st.zaznamy), None)
        v = self.vysledky.get(strana)
        if blok is None or v is None:
            self.akce_uprava.setChecked(False)
            QMessageBox.information(self, "SAKRA",
                                    tr("Vyberte program s vadným blokem (nahrávka musí být načtená)."))
            return
        self.uprava = {"z": z, "s": s, "b": blok, "puvodni_blok": blok, "puvodni_pulzy": v.pulzy, "v": v,
                       "pridano": 0, "odebrano": 0}
        self.osa.rezim_upravy = True
        self.osa.pridane = set()
        self.osa.ukaz(blok.zacatek, blok.konec)
        self.panel_upravy.show()
        cislo = f" {blok.cislo}" if blok.cislo is not None else ""
        self._stav_upravy(
            tr(
                "Úprava bloku{0}: přibližte kolečkem na jednotlivé vzorky, levé tlačítko přidá přechod "
                "přes nulu, pravé odebere nejbližší."
            ).format(cislo),
            "",
        )

    def _stav_upravy(self, text: str, barva: str):
        self.stav_upravy.setText(tr("<span style='color:{0}'>{1}</span>").format(barva, text) if barva else text)
        self.statusBar().showMessage(re.sub(r"<[^>]+>", "", text), 6000)

    def _uprava_signalu(self, t: float, odebrat: bool):
        u = self.uprava
        if u is None:
            return
        v = u["v"]
        if self.osa.vzorku_na_pixel() > 2:
            self._stav_upravy(tr("Přibližte víc – kolečkem myši až na jednotlivé vzorky."), "#D08A10")
            return
        p = v.pulzy
        vzorek = int(round(t * p.rate))
        if odebrat:
            if not len(p.hrany):
                return
            i = int(np.argmin(np.abs(p.hrany - vzorek)))
            if abs(int(p.hrany[i]) - vzorek) / max(self.osa.vzorku_na_pixel(), 1e-9) > 8:
                self._stav_upravy(tr("V místě kliknutí není přechod (pravé tlačítko odebírá nejbližší přechod)."),
                                  "#D08A10")
                return
            hr = int(p.hrany[i])
            v.pulzy = odeber_hranu(p, i)
            if hr in self.osa.pridane:
                self.osa.pridane.discard(hr)
                u["pridano"] -= 1
            else:
                u["odebrano"] += 1
        else:
            x = vzorek                          # přesně tam, kam uživatel klikl (bez přichycení)
            if x in set(p.hrany[max(0, np.searchsorted(p.hrany, x) - 1):np.searchsorted(p.hrany, x) + 1].tolist()):
                return
            v.pulzy = vloz_hranu(p, x)
            self.osa.pridane.add(x)
            u["pridano"] += 1
        self._zkontroluj_blok()

    def _zkontroluj_blok(self):
        """Po každé úpravě znovu dekóduje blok a ukáže, jestli už sedí kontrolní součet."""
        u = self.uprava
        s, z = u["s"], u["z"]
        nb = znovu_dekoduj_blok(u["v"], s, u["puvodni_blok"])
        zmeny = tr("přidáno {0}, odebráno {1} přechodů").format(u['pridano'], u['odebrano'])
        if nb is None:
            self._stav_upravy(tr("✗ Blok se z upraveného signálu nepodařilo přečíst ({0}).").format(zmeny),
                              "#E04848")
        else:
            if nb.ok:
                nb.oprava = "ruční úprava signálu (+{0}/−{1} přechodů)".format(
                    u['pridano'], u['odebrano']
                )  # data česky
            self._nahrad_blok(nb)
            cislo = f" {nb.cislo}" if nb.cislo is not None else ""
            if nb.ok:
                self._stav_upravy(tr("<b>✓ Kontrolní součet bloku{0} sedí</b> – blok opraven ({1}).")
                                  .format(cislo, zmeny), "#2EA866")
            else:
                nezname = len(nb.chybne_bajty)
                self._stav_upravy(
                    tr("<b>✗ Součet bloku{0} nesedí</b> · chybných nebo neznámých bajtů: {1} · {2}").format(
                        cislo, nezname, zmeny
                    ),
                    "#E04848",
                )
        self.osa.update()
        self._zmena_pohledu(self.osa.od, self.osa.do)      # pulzy a histogram z upraveného signálu

    def _nahrad_blok(self, nb):
        u = self.uprava
        s, z = u["s"], u["z"]
        i = next((k for k, b in enumerate(s.bloky) if b is u["b"]), None)
        if i is None:
            return
        s.bloky[i] = nb
        u["b"] = nb
        pl = podle_id(s.platforma)
        if pl is not None and hasattr(pl, "dokonci"):
            pl.dokonci(s)
        obnov_navrhy(z)
        r = self.model.radek_zaznamu(z)
        if r >= 0:
            self.model.dataChanged.emit(self.model.index(r, 0), self.model.index(r, len(SLOUPCE) - 1))
        self.detail.nastav(z)

    def _vrat_upravy(self):
        u = self.uprava
        if u is None:
            return
        u["v"].pulzy = u["puvodni_pulzy"]
        self._nahrad_blok(u["puvodni_blok"])
        u["pridano"] = u["odebrano"] = 0
        self.osa.pridane = set()
        self.osa.update()
        self._stav_upravy(tr("Úpravy vráceny – blok je v původním stavu."), "")
        self._zmena_pohledu(self.osa.od, self.osa.do)

    def _ukonci_upravu(self):
        u = self.uprava
        if u is not None and not u["b"].ok and (u["pridano"] or u["odebrano"]):
            self._vrat_upravy()                 # nedokončenou úpravu nenechávat v datech
            self._zapis(tr("Ruční úprava ukončena bez opravy – blok vrácen do původního stavu."))
        elif u is not None and u["b"] is not u["puvodni_blok"] and u["b"].ok:
            self._zapis(tr("Ruční úprava: {0} – {1}.").format(u['z'].nazev, u['b'].oprava))
        self.uprava = None
        self.osa.rezim_upravy = False
        self.osa.pridane = set()
        self.panel_upravy.hide()
        if self.akce_uprava.isChecked():
            self.akce_uprava.blockSignals(True)
            self.akce_uprava.setChecked(False)
            self.akce_uprava.blockSignals(False)
        self.osa.update()

    # ------------------------------------------------------------ přehrávání
    def prehraj(self, strana: int, od: float, do: float):
        v = self.vysledky.get(strana)
        if v is None:
            QMessageBox.information(self, "SAKRA", tr("Nahrávka této strany není načtená."))
            return
        if Prehravac.dostupny() is None:
            QMessageBox.information(
                self,
                "SAKRA",
                tr("Pro přehrávání chybí přehrávač (v Linuxu pw-play, paplay nebo aplay "
                   "z balíčku alsa-utils)."),
            )
            return
        if self.prehravac.prehraj(v.nahravka.vzorky, v.nahravka.rate, od, do):
            self._strana_prehravani = strana
            self.casovac_prehravani.start()
            return True
        return False

    def prehraj_vyber(self):
        cislo = self.strana.currentData()
        if cislo is not None:
            self.prehraj(cislo, *self.osa.viditelny_usek())

    def zastav_prehravani(self):
        self.prehravac.stop()
        self.casovac_prehravani.stop()
        self.osa.prehravani = None
        self.osa.update()
        self.prehravani_skoncilo.emit()

    def _kurzor_prehravani(self):
        t = self.prehravac.pozice()
        self.osa.prehravani = t if self._strana_prehravani == self.strana.currentData() else None
        if t is None:
            self.casovac_prehravani.stop()
            self.prehravani_skoncilo.emit()
        self.osa.update()

    # ------------------------------------------------------------ práce na pozadí
    def _spust(self, popis: str, fn, po, prubeh=None):
        if self.ukol and self.ukol.isRunning():
            QMessageBox.information(self, "SAKRA", tr("Počkejte, až doběhne předchozí úloha."))
            return
        self._zapis(popis)
        self.prubeh.setValue(0)
        self.prubeh.show()
        self.ukol = Ukol(fn, self)
        self.ukol.prubeh.connect(lambda x, t: (self.prubeh.setValue(int(x * 1000)),
                                               self.statusBar().showMessage(t)))
        if prubeh is not None:
            self.ukol.prubeh.connect(prubeh)
        self.ukol.hotovo.connect(lambda r: (self.prubeh.hide(), po(r)))
        self.ukol.chyba.connect(self._chyba)
        self.ukol.start()

    def _chyba(self, text: str):
        self.prubeh.hide()
        self._zapis("CHYBA:\n" + text)
        QMessageBox.critical(self, tr("SAKRA – chyba"), text.strip().splitlines()[-1])

    # ------------------------------------------------------------ soubory
    def nova(self):
        self.vysledky = {}
        self.cesta_projektu = None
        self._nastav_kazetu(Kazeta())

    def otevri_nahravky(self, cesty=None, zeptat: bool | None = None):
        """`zeptat`: u nové kazety se zeptat na platformu (výchozí: jen při výběru souborů v dialogu)."""
        if zeptat is None:
            zeptat = not cesty
        if not cesty:
            cesty, _ = QFileDialog.getOpenFileNames(self, tr("Nahrávky stran kazety"), self._slozka(), FILTR_ZVUK)
        if not cesty:
            return
        self._pamatuj(cesty[0])
        obsazene = {s.cislo for s in self.kazeta.strany if s.nahravka}
        if zeptat and not obsazene:        # nová kazeta: pro jaký počítač je? (ruční volba = rychlejší zpracování)
            d = DialogPlatformy(self.kazeta.platforma, self)
            if d.exec() != QDialog.DialogCode.Accepted:
                return
            self.nastav_platformu(d.hodnota())
        nahravky: dict[int, Path] = {}
        for c in cesty:
            n = cislo_strany(c, 0)
            if not n:
                n = 1
                while n in obsazene or n in nahravky:
                    n += 1
            nahravky[n] = Path(c)
        self.analyzuj(nahravky)

    def analyzuj(self, nahravky: dict[int, Path], dale=None, prubeh=None):
        def po(vysledky):
            ostatni = {k: v for k, v in self.vysledky.items() if k not in vysledky}
            vloz_vysledky(self.kazeta, vysledky, ostatni)
            self.vysledky.update(vysledky)
            self._nastav_kazetu(self.kazeta)
            for c, v in sorted(vysledky.items()):
                n = len(v.soubory)
                ok = sum(1 for s in v.soubory if s.ok)
                self._zapis(
                    tr("Strana {0}: {1} – programů: {2}, v pořádku: {3}, nerozpoznaných úseků: {4}.").format(
                        c, Path(v.strana.nahravka).name, n, ok, len(v.strana.zaznamy) - n
                    )
                )
            from ..jadro import analyza
            for chyba in analyza.CHYBY_DEKODERU:
                self._zapis(tr("Varování – dekodér selhal (strana se zpracovala bez něj): {0}").format(chyba))
            analyza.CHYBY_DEKODERU.clear()
            if vysledky:
                self.strana.setCurrentIndex(self.strana.findData(min(vysledky)))
            if dale:
                dale()

        volby = {s.cislo: (s.volba_kanalu, s.polarita) for s in self.kazeta.strany}
        platforma = self.kazeta.platforma
        self._spust(tr("Analyzuji ") + ", ".join(p.name for p in nahravky.values()),
                    lambda pr: analyzuj_strany(nahravky, pr, volby, platforma), po, prubeh)

    def otevri_projekt(self, cesta=None):
        if not cesta:
            cesta, _ = QFileDialog.getOpenFileName(self, tr("Otevřít projekt"), self._slozka(),
                                                   tr("Projekt SAKRA (*{0})").format(PRIPONA))
        if not cesta:
            return
        self._pamatuj(cesta)
        try:
            k = otevri(Path(cesta))
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "SAKRA", tr("Projekt nejde otevřít:\n{0}").format(e))
            return
        self.vysledky = {}
        self.cesta_projektu = Path(cesta)
        self._nastav_kazetu(k)
        self._zapis(tr("Otevřen projekt {0}").format(cesta))
        nahravky = {s.cislo: Path(s.nahravka) for s in k.strany if s.nahravka and Path(s.nahravka).exists()}
        if nahravky:          # znovu načíst nahrávky kvůli časové ose (ruční údaje zůstanou)
            self.analyzuj(nahravky)

    def uloz_projekt(self):
        cesta = self.cesta_projektu
        if cesta is None:
            navrh = str(Path(self._slozka()) / ((self.kazeta.inventar.cislo or "kazeta") + PRIPONA))
            c, _ = QFileDialog.getSaveFileName(
                self, tr("Uložit projekt"), navrh, tr("Projekt SAKRA (*{0})").format(PRIPONA)
            )
            if not c:
                return
            cesta = Path(c if c.endswith(PRIPONA) else c + PRIPONA)
        uloz(self.kazeta, cesta)
        self.cesta_projektu = cesta
        self._titulek()
        self._zapis(tr("Projekt uložen: {0}").format(cesta))

    def nacti_excel(self):
        c, _ = QFileDialog.getOpenFileName(self, tr("Načíst metadata z Excelu"), self._slozka(), tr("Excel (*.xlsx)"))
        if not c:
            return
        stara = {s.cislo: s for s in self.kazeta.strany}
        k = excel.importuj(Path(c), Kazeta())
        # strany s nahrávkou: zachovat výsledky dekódování, převzít ruční údaje z tabulky
        for s in k.strany:
            if s.cislo in stara and stara[s.cislo].nahravka:
                nova = stara[s.cislo]
                prenes_rucni(s, nova)
                k.strany[k.strany.index(s)] = nova
        for c_, s in stara.items():
            if c_ not in {x.cislo for x in k.strany}:
                k.strany.append(s)
        k.strany.sort(key=lambda s: s.cislo)
        if not k.digitalizace.vzorkovani:
            k.digitalizace.vzorkovani = self.kazeta.digitalizace.vzorkovani
            k.digitalizace.format = self.kazeta.digitalizace.format
        self._nastav_kazetu(k)
        self._zapis(tr("Načtena metadata z {0}").format(c))

    def uloz_excel(self):
        navrh = str(Path(self._slozka()) / ((self.kazeta.inventar.cislo or "kazeta") + ".xlsx"))
        c, _ = QFileDialog.getSaveFileName(self, tr("Uložit Excel"), navrh, tr("Excel (*.xlsx)"))
        if c:
            excel.exportuj(self.kazeta, Path(c))
            self._zapis(tr("Excel uložen: {0}").format(c))

    def export_balicku(self, kam: Path | None = None, kopirovat_zdroj: bool = True, cisty_wav: bool = False,
                       dale=None, snimky: bool = True, sbalit_7z: bool = False):
        if not self.kazeta.inventar.cislo:
            QMessageBox.information(self, "SAKRA", tr("Vyplňte nejdřív inventární číslo (záložka Kazeta)."))
            self.zalozky.setCurrentIndex(1)
            return
        if kam is None:
            volby = self._volby_exportu()
            if volby is None:
                return
            kam, kopirovat_zdroj, cisty_wav, snimky = volby

        def po(d):
            self._zapis(tr("Balíček hotov: {0}").format(d))
            self.detail.nastav(self.detail.z)
            if dale:
                dale(d)
        self._spust(tr("Vytvářím archivní balíček…"),
                    lambda pr: exportuj_balicek(self.kazeta, Path(kam), self.vysledky, pr,
                                                kopirovat_zdroj=kopirovat_zdroj, cisty_wav=cisty_wav,
                                                snimky=snimky, sbalit_7z=sbalit_7z), po)

    def _volby_exportu(self):
        d = QDialog(self)
        d.setWindowTitle(tr("Archivní balíček"))
        lay = QVBoxLayout(d)
        r = QHBoxLayout()
        r.addWidget(QLabel(tr("Složka archivu:")))
        kam = QLineEdit(self.nastaveni.value("archiv", self._slozka()))
        kam.setMinimumWidth(380)
        r.addWidget(kam, 1)
        b = QPushButton("Vybrat…")
        b.clicked.connect(lambda: kam.setText(QFileDialog.getExistingDirectory(d, tr("Složka archivu"), kam.text())
                                              or kam.text()))
        r.addWidget(b)
        lay.addLayout(r)
        zdroj = QCheckBox(tr("Přiložit bezztrátovou kopii celé nahrávky (FLAC)"))
        zdroj.setChecked(True)
        cisty = QCheckBox(tr("WAV programů jako čistý signál (u opravených programů vždy)"))
        snimky = QCheckBox(tr("Snímky z emulátoru: nahrávací obrazovka a obrazovka po spuštění (ZX Spectrum)"))
        snimky.setChecked(True)
        lay.addWidget(zdroj)
        lay.addWidget(cisty)
        lay.addWidget(snimky)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        lay.addWidget(bb)
        if d.exec() != QDialog.DialogCode.Accepted or not kam.text():
            return None
        self.nastaveni.setValue("archiv", kam.text())
        return Path(kam.text()), zdroj.isChecked(), cisty.isChecked(), snimky.isChecked()

    def emuluj(self, z: Zaznam):
        """Spustí program v emulátoru na pozadí; náhled pak ukáže nahrávací obrazovku a obrazovku po spuštění."""
        pl = podle_id(z.soubor.platforma) if z.soubor else None
        if pl is None or not hasattr(pl, "snimky"):
            return

        def hotovo(r):
            self._zapis(tr("Emulátor: {0} – {1}.").format(z.nazev, r['zpusob']))
            if self.detail.z is z:
                self.detail.nastav(z)
        self._spust(tr("Spouštím {0} v emulátoru…").format(z.nazev), lambda pr: pl.snimky(z.soubor), hotovo)

    def _uloz_program(self, z: Zaznam):
        kam = QFileDialog.getExistingDirectory(self, tr("Kam uložit {0}").format(z.nazev), self._slozka())
        if not kam or z.soubor is None:
            return
        pl = podle_id(z.soubor.platforma)
        soubory = pl.zapis(z.soubor, Path(kam) / bezpecne_jmeno(z.nazev)) if pl else []
        self._zapis(tr("Uloženo: ") + ", ".join(p.name for p in soubory))

    def o_aplikaci(self):
        from .o_aplikaci import DialogOAplikaci
        DialogOAplikaci(self, self.otevri_navod).exec()

    def otevri_navod(self):
        if not NAVOD.exists():
            QMessageBox.warning(self, tr("Návod"), tr("Návod nebyl nalezen:\n{0}").format(NAVOD))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(NAVOD)))

    # ------------------------------------------------------------ pomocné
    def _slozka(self) -> str:
        return self.nastaveni.value("slozka", str(Path.home()))

    def _pamatuj(self, cesta: str):
        self.nastaveni.setValue("slozka", str(Path(cesta).parent))

    def closeEvent(self, e):
        self.nastaveni.setValue("okno/geometrie", self.saveGeometry())
        self.prehravac.stop()
        if self.davky.bezi():
            self.davky.pozastav()
            self.davky.vlakno.wait(30000)
        if self.ukol and self.ukol.isRunning():
            self.ukol.wait(10000)
        super().closeEvent(e)
