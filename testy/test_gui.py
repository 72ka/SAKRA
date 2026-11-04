"""Kouřový test GUI (bez obrazovky: QT_QPA_PLATFORM=offscreen)."""
import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from sakra.gui.okno import HlavniOkno
    QT = True
except ImportError:          # např. chybí systémové knihovny Qt
    QT = False

from testy.signal import pulzy_tesla, signal_z_pulzu, soubor_tesla, uloz_wav

APP = None


@unittest.skipUnless(QT, "PySide6 není k dispozici")
class Gui(unittest.TestCase):
    def test_nahravka_tabulka_detail(self):
        global APP
        APP = QApplication.instance() or QApplication([])
        tmp = Path(tempfile.mkdtemp())
        uloz_wav(tmp / "HH00001 (1).wav",
                 signal_z_pulzu(pulzy_tesla(soubor_tesla(b"KORAB", b"\xf6\xf6\xf6\x42" + bytes(600)), 44100), 44100),
                 44100)
        o = HlavniOkno()
        o.show()
        o.otevri_nahravky([str(tmp / "HH00001 (1).wav")])
        konec = time.time() + 60
        while o.ukol and o.ukol.isRunning() and time.time() < konec:
            APP.processEvents()
            time.sleep(0.01)
        for _ in range(20):
            APP.processEvents()
        self.assertEqual(o.model.rowCount(), 1)
        self.assertEqual(o.model.radky[0][1].nazev, "KORAB")
        self.assertEqual(o.windowTitle(), "SAKRA — HH00001")
        o.tabulka.selectRow(0)
        APP.processEvents()
        self.assertIn("KORAB", o.detail.text.toPlainText())
        self.assertIsNotNone(o.osa.vyber)
        self.assertFalse(o.grab().isNull())
        o.close()

    def _cekej(self, podminka, limit=90):
        konec = time.time() + limit
        while not podminka() and time.time() < konec:
            APP.processEvents()
            time.sleep(0.01)
        for _ in range(10):
            APP.processEvents()

    def test_pruvodce(self):
        global APP
        APP = QApplication.instance() or QApplication([])
        tmp = Path(tempfile.mkdtemp())
        wav = tmp / "HH00002 (1).wav"
        uloz_wav(wav, signal_z_pulzu(pulzy_tesla(soubor_tesla(b"RAKETA", b"\xf6\xf6\xf6\x42" + bytes(500)), 44100),
                                     44100), 44100)
        o = HlavniOkno()
        o.show()
        o.prepni_rezim("pruvodce")
        p = o.pruvodce
        self.assertFalse(p.dale.isEnabled())
        p.pridej_soubory([wav])
        self.assertEqual(p.inv.text(), "HH00002")
        p.jdi(1)
        p.jdi(2)                                     # spustí analýzu
        self._cekej(lambda: p._analyzovano is not None)
        self.assertEqual(o.model.rowCount(), 1)
        self.assertTrue(p.dale.isEnabled())
        for k in (3, 4, 5):
            p.jdi(k)
        self.assertEqual(p.krok, 5)
        p.kam.setText(str(tmp / "archiv"))
        p.volba_zdroj.setChecked(False)
        self.assertTrue(p.volba_7z.isChecked())             # výchozí: jeden soubor 7z
        p.volba_7z.setChecked(False)
        p._uloz()
        self._cekej(lambda: p._balicek is not None)
        self.assertTrue((tmp / "archiv" / "HH00002" / "protokol.pdf").exists())
        self.assertTrue(list((tmp / "archiv" / "HH00002").glob("1-01 RAKETA.csw")))
        # znovu jako 7z: jeden soubor se stejnou složkou uvnitř, složka zmizí
        import py7zr
        p._balicek = None
        p.volba_7z.setChecked(True)
        p._uloz()
        self._cekej(lambda: p._balicek is not None)
        self.assertEqual(p._balicek, tmp / "archiv" / "HH00002.7z")
        self.assertEqual(sorted(x.name for x in (tmp / "archiv").iterdir()), ["HH00002.7z"])
        with py7zr.SevenZipFile(p._balicek) as z:
            jmena = z.getnames()
        self.assertIn("HH00002/protokol.pdf", jmena)
        self.assertIn("HH00002/SHA1SUMS", jmena)
        self.assertIn("HH00002/1-01 RAKETA.csw", jmena)
        o.close()

    def test_volba_platformy(self):
        """Průvodce: volba počítače kazety se propíše do kazety i do lišty pracovního stolu a změní podpis analýzy;
        jen dekodéry zvoleného počítače – Ondra se při volbě ZX Spectrum nenajde."""
        global APP
        APP = QApplication.instance() or QApplication([])
        tmp = Path(tempfile.mkdtemp())
        wav = tmp / "HH00005 (1).wav"
        uloz_wav(wav, signal_z_pulzu(pulzy_tesla(soubor_tesla(b"RAKETA", b"\xf6\xf6\xf6\x42" + bytes(500)), 44100),
                                     44100), 44100)
        o = HlavniOkno()
        o.show()
        o.prepni_rezim("pruvodce")
        p = o.pruvodce
        p.pridej_soubory([wav])
        podpis = p._podpis()
        p.vyber_platformy.tlacitka["ZX Spectrum"].click()
        self.assertEqual(o.kazeta.platforma, "ZX Spectrum")
        self.assertEqual(o.volba_platformy.currentData(), "ZX Spectrum")
        self.assertNotEqual(p._podpis(), podpis)
        p.jdi(2)
        self._cekej(lambda: p._analyzovano is not None)
        self.assertFalse([z for s in o.kazeta.strany for z in s.zaznamy if z.soubor is not None])
        p.vyber_platformy.tlacitka["Ondra SPO 186"].click()
        p.jdi(2)
        self._cekej(lambda: p._analyzovano == p._podpis())
        self.assertEqual([z.soubor.platforma for s in o.kazeta.strany for z in s.zaznamy if z.soubor is not None],
                         ["ondra-tesla"])
        o.nova()                                     # nová kazeta = zase automaticky
        self.assertEqual((o.kazeta.platforma, o.volba_platformy.currentData(), p.vyber_platformy.hodnota()),
                         ("", "", ""))
        o.close()

    def test_inventarni_cislo_pri_ulozeni(self):
        """Bez inventárního čísla nejde uložit; doplnit jde v kroku 2 i přímo v posledním kroku, varování pak zmizí
        a číslo je ve všech polích (krok 1, 2, 6 a karta pracovního stolu)."""
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        global APP
        APP = QApplication.instance() or QApplication([])
        tmp = Path(tempfile.mkdtemp())
        wav = tmp / "kazeta strana 1.wav"                    # v názvu není inventární číslo
        uloz_wav(wav, signal_z_pulzu(pulzy_tesla(soubor_tesla(b"RAKETA", b"\xf6\xf6\xf6\x42" + bytes(500)), 44100),
                                     44100), 44100)
        o = HlavniOkno()
        o.show()
        o.prepni_rezim("pruvodce")
        p = o.pruvodce
        p.pridej_soubory([wav])
        p.jdi(1)
        p.jdi(2)
        self._cekej(lambda: p._analyzovano == p._podpis())
        for k in (3, 4, 5):
            p.jdi(k)
        self.assertFalse(p.ulozit.isEnabled())
        self.assertIn("inventární číslo", p.vysledek.text())
        # doplnění v kroku 2 a návrat
        p.jdi(1)
        QTest.keyClicks(p.karta.cislo, "HH01234")
        p.jdi(5)
        self.assertTrue(p.ulozit.isEnabled())
        self.assertEqual(p.vysledek.text(), "")
        self.assertEqual({p.inv.text(), p.inv_ulozeni.text(), o.karta.cislo.text(), o.kazeta.inventar.cislo},
                         {"HH01234"})
        # smazání a doplnění přímo v posledním kroku
        p.inv_ulozeni.selectAll()
        QTest.keyClick(p.inv_ulozeni, Qt.Key.Key_Backspace)
        self.assertFalse(p.ulozit.isEnabled())
        QTest.keyClicks(p.inv_ulozeni, "HH05555")
        self.assertTrue(p.ulozit.isEnabled())
        self.assertEqual(p.vysledek.text(), "")
        self.assertEqual((o.kazeta.inventar.cislo, p.karta.cislo.text(), p.inv.text()), ("HH05555",) * 3)
        o.close()

    def test_stul_rozvrzeni(self):
        """Pracovní stůl: přehled kazety, pulzy, histogram délek a mřížka bloků (zelená = bez chyby)."""
        global APP
        APP = QApplication.instance() or QApplication([])
        import numpy as np
        from sakra.gui.stul_panely import CHYBA, OK, MrizkaBloku
        tmp = Path(tempfile.mkdtemp())
        pulzy = pulzy_tesla(soubor_tesla(b"KORAB", np.random.default_rng(6).integers(0, 256, 700, np.uint8).tobytes()),
                            44100)
        k = len(pulzy) // 2
        uloz_wav(tmp / "HH00078 (1).wav", signal_z_pulzu(pulzy[:k] + [pulzy[k] + pulzy[k + 1]] + pulzy[k + 2:], 44100),
                 44100)
        o = HlavniOkno()
        o.resize(1400, 900)
        o.show()
        o.prepni_rezim("stul")
        o.otevri_nahravky([str(tmp / "HH00078 (1).wav")])
        self._cekej(lambda: not (o.ukol and o.ukol.isRunning()))
        self.assertEqual([c for c, _ in o.prehled.strany], [1])
        self.assertEqual(len(o.prehled._obalky[1]), 1)                 # mono: jedna stopa
        o.tabulka.selectRow(0)
        APP.processEvents()
        z = o.model.radky[0][1]
        bloky = z.soubor.bloky
        self.assertEqual(o.detail.mrizka.bloky, bloky)
        self.assertEqual([MrizkaBloku.barva(b) for b in bloky], [OK if b.ok else CHYBA for b in bloky])
        self.assertIn(CHYBA, [MrizkaBloku.barva(b) for b in bloky])
        self.assertEqual(o.prehled.vyber[0], 1)                     # rámeček v přehledu = zobrazený úsek
        self.assertEqual(o.prehled.vyber[1:], (o.osa.od, o.osa.do))
        vadny = next(b for b in bloky if not b.ok)
        self.assertAlmostEqual(o.pulzy.t, vadny.konec)              # pulzy ukazují místo chyby
        self.assertIn(vadny.konec, o.pulzy.chyby)
        self.assertTrue(o.histogram.vrcholy())                      # Tesla: dvě délky půlvln
        o.osa.mys.emit(1.0)
        self.assertEqual(o.pulzy.t, 1.0)
        o.detail.mrizka.vybran.emit(bloky[0])                       # klik na blok v mřížce -> výběr na ose
        self.assertEqual(o.osa.vyber, (bloky[0].zacatek, bloky[0].konec))
        o._klik_v_prehledu(1, 0.2)
        self.assertFalse(o.grab().isNull())
        o.close()

    def test_kanal_polarita(self):
        """Výběr kanálu a polarity nad průběhem strany: změna = nová analýza strany, volba se zapamatuje."""
        global APP
        APP = QApplication.instance() or QApplication([])
        tmp = Path(tempfile.mkdtemp())
        uloz_wav(tmp / "HH00079 (1).wav",
                 signal_z_pulzu(pulzy_tesla(soubor_tesla(b"POL", bytes(300)), 44100), 44100), 44100)
        o = HlavniOkno()
        o.show()
        o.prepni_rezim("stul")
        o.otevri_nahravky([str(tmp / "HH00079 (1).wav")])
        self._cekej(lambda: not (o.ukol and o.ukol.isRunning()))
        self.assertFalse(o.volba_kanalu.isEnabled())                  # mono
        self.assertEqual(o.volba_kanalu.itemText(0), "Mono")
        self.assertEqual(o.volba_polarity.itemText(0), "Auto")
        self.assertNotIn("obrácená", o.info_strany.text())
        o.volba_polarity.setCurrentIndex(o.volba_polarity.findData("obracena"))
        o._zmena_volby()
        self._cekej(lambda: not (o.ukol and o.ukol.isRunning()))
        s = o.kazeta.strany[0]
        self.assertEqual(s.polarita, "obracena")
        self.assertTrue(s.signal["polarita_obracena"])
        self.assertEqual(o.volba_polarity.currentData(), "obracena")
        self.assertIn("obrácená polarita", o.info_strany.text())
        self.assertEqual(o.model.radky[0][1].nazev, "POL")
        o.close()

    def test_zadna_data(self):
        """Nerozpoznaný úsek jde v tabulce i v průvodci označit jako „žádná data“."""
        global APP
        APP = QApplication.instance() or QApplication([])
        from sakra.gui.obsah import SLOUPCE
        from sakra.jadro.model import ZADNA_DATA, Kazeta, Strana, Zaznam
        o = HlavniOkno()
        k = Kazeta()
        s = Strana(1)
        z = Zaznam(cas_od=1.0, cas_do=5.0, typ="Data", platforma="?", nazev="(nerozpoznáno)", nerozpoznano=True)
        s.zaznamy.append(z)
        k.strany.append(s)
        o._nastav_kazetu(k)
        sl = [p for _, p in SLOUPCE].index("platforma")
        o.model.setData(o.model.index(0, sl), ZADNA_DATA)
        self.assertEqual((z.typ, z.stav), ("Audio", "žádná data"))
        self.assertEqual(o.model.data(o.model.index(0, 1)), "♪ žádná data")
        o.pruvodce._rucni_platforma(z, "(neznámá)")
        self.assertEqual((z.typ, z.platforma, z.stav), ("Data", "?", "nerozpoznáno"))
        o.close()

    def test_poslech_prepinac(self):
        """Tlačítko Poslechnout v průvodci během přehrávání zastaví poslech."""
        global APP
        APP = QApplication.instance() or QApplication([])
        o = HlavniOkno()
        p = o.pruvodce
        hraje = []
        o.prehraj = lambda s, a, b: (hraje.append((s, a, b)), o.casovac_prehravani.stop())[0] is None
        o.prehravac.stop = lambda: None
        b1 = p._tlacitko_poslechu(1, 10.0, 100.0)
        b2 = p._tlacitko_poslechu(1, 50.0, 55.0)
        b1.click()
        self.assertEqual(hraje, [(1, 10.0, 30.0)])                  # nejvýš 20 s
        self.assertEqual(b1.text(), p.ZASTAVIT)
        b1.click()                                                  # zastavit
        self.assertEqual(b1.text(), p.POSLECH)
        self.assertEqual(len(hraje), 1)
        b1.click()
        b2.click()                                                  # jiný úsek: první se vrátí
        self.assertEqual((b1.text(), b2.text()), (p.POSLECH, p.ZASTAVIT))
        o.prehravani_skoncilo.emit()                                # dohrálo samo
        self.assertEqual(b2.text(), p.POSLECH)
        o.close()

    def test_davky(self):
        global APP
        APP = QApplication.instance() or QApplication([])
        tmp = Path(tempfile.mkdtemp())
        for jm, strana in (("HH00010", 1), ("HH00010", 2), ("HH00011", 1)):
            uloz_wav(tmp / f"{jm} ({strana}).wav",
                     signal_z_pulzu(pulzy_tesla(soubor_tesla(f"P{strana}{jm[-1]}".encode(), bytes(300)), 44100),
                                    44100), 44100)
        o = HlavniOkno()
        o.show()
        o.prepni_rezim("davky")
        d = o.davky
        d.vystup.setText(str(tmp / "archiv"))
        d.zdroj.setChecked(False)
        d.pridej(sorted(tmp.glob("*.wav")))
        self.assertEqual([(x.inv, sorted(x.nahravky)) for x in d.polozky], [("HH00010", [1, 2]), ("HH00011", [1])])
        d.spust()
        self._cekej(lambda: not d.bezi())
        self.assertEqual([x.stav for x in d.polozky], ["hotovo", "hotovo"])
        self.assertTrue((tmp / "archiv" / "HH00010" / "HH00010.xlsx").exists())
        self.assertTrue((tmp / "archiv" / "projekty" / "HH00011.sakra").exists())
        o.close()

    def test_nahled_zx(self):
        global APP
        APP = QApplication.instance() or QApplication([])
        import struct
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QTextDocument
        from sakra.gui.detail import Detail
        from sakra.jadro.analyza import analyzuj_stranu
        from sakra.platformy.zx import pulzy_z_bloku
        from testy.test_zx import basic_radek, blok
        tmp = Path(tempfile.mkdtemp())
        prg = basic_radek(10, b"\xef\"\"\xaa")
        obr = bytes(range(256)) * 27
        bl = [blok(0, bytes([0]) + b"HRA       " + struct.pack("<HHH", len(prg), 10, len(prg))), blok(255, prg),
              blok(0, bytes([3]) + b"obr       " + struct.pack("<HHH", 6912, 16384, 32768)), blok(255, obr)]
        uloz_wav(tmp / "zx.wav", signal_z_pulzu(pulzy_z_bloku(bl), 44100), 44100)
        v = analyzuj_stranu(tmp / "zx.wav", 1)
        d = Detail()
        d.nastav(v.strana.zaznamy[0])
        self.assertIn('10 LOAD "" SCREEN$', d.text.toPlainText())
        img = d.text.loadResource(QTextDocument.ResourceType.ImageResource, QUrl("nahled:0"))
        self.assertEqual((img.width(), img.height()), (256, 192))

    def test_vzhled(self):
        global APP
        APP = QApplication.instance() or QApplication([])
        from PySide6.QtCore import Qt
        from sakra.gui import vzhled
        from sakra.gui.zahlavi import DialogNastaveni
        o = HlavniOkno()
        o.show()
        for barvy in ("svetle", "tmave", "system"):
            for styl in ("navrh", "klasicky"):
                for zahlavi in (False, True):
                    n = vzhled.Nastaveni(barvy, styl, zahlavi)
                    o.pouzij_vzhled(n)
                    APP.processEvents()
                    bez_ramu = styl == "navrh" and zahlavi
                    self.assertEqual(bool(o.windowFlags() & Qt.WindowType.FramelessWindowHint), bez_ramu)
                    self.assertEqual(o.zahlavi.titulek.isVisibleTo(o), bez_ramu)
                    if barvy == "tmave":
                        self.assertLess(APP.palette().window().color().lightness(), 80)
                    self.assertFalse(o.grab().isNull())
        d = DialogNastaveni(vzhled.Nastaveni("tmave", "navrh", True))
        self.assertEqual(d.vysledek(), vzhled.Nastaveni("tmave", "navrh", True))
        d.klasicky.setChecked(True)
        self.assertEqual(d.vysledek(), vzhled.Nastaveni("tmave", "klasicky", False))
        vzhled.pouzij(APP, vzhled.Nastaveni("svetle", "navrh", False))
        o.close()

    def test_rucni_uprava(self):
        global APP
        APP = QApplication.instance() or QApplication([])
        import numpy as np
        from sakra.jadro.analyza import analyzuj_stranu
        tmp = Path(tempfile.mkdtemp())
        pulzy = pulzy_tesla(soubor_tesla(b"KORAB", np.random.default_rng(6).integers(0, 256, 700, np.uint8).tobytes()),
                            44100)
        uloz_wav(tmp / "cista.wav", signal_z_pulzu(pulzy, 44100), 44100)
        b3 = next(b for b in analyzuj_stranu(tmp / "cista.wav", 1).soubory[0].bloky if b.cislo == 3)
        konce = np.cumsum([int(n) for n in pulzy])
        k = int(np.searchsorted(konce, (b3.zacatek + 0.6 * (b3.konec - b3.zacatek)) * 44100))
        t_prechodu = konce[k] / 44100
        poskozene = pulzy[:k] + [pulzy[k] + pulzy[k + 1]] + pulzy[k + 2:]      # výpadek: chybí jeden přechod
        uloz_wav(tmp / "HH00077 (1).wav", signal_z_pulzu(poskozene, 44100), 44100)
        o = HlavniOkno()
        o.resize(1400, 900)
        o.show()
        o.prepni_rezim("stul")
        o.otevri_nahravky([str(tmp / "HH00077 (1).wav")])
        self._cekej(lambda: not (o.ukol and o.ukol.isRunning()))
        z = o.model.radky[0][1]
        self.assertEqual(z.stav, "chyba")
        o.tabulka.selectRow(0)
        APP.processEvents()
        self.assertTrue(o.akce_uprava.isEnabled())
        o.akce_uprava.setChecked(True)
        self.assertIsNotNone(o.uprava)
        o._uprava_signalu(t_prechodu, False)                    # málo přiblíženo -> jen upozornění
        self.assertIn("Přibližte", o.stav_upravy.text())
        o.osa._nastav_rozsah(t_prechodu - 0.003, t_prechodu + 0.003)
        o._uprava_signalu(t_prechodu, False)
        self.assertIn("sedí", o.stav_upravy.text())
        self.assertEqual(z.stav, "opraveno")
        self.assertIn("ruční úprava", o.detail.text.toPlainText())
        o._uprava_signalu(t_prechodu + 0.0005, False)           # přechod navíc -> zase chyba
        self.assertIn("nesedí", o.stav_upravy.text())
        o._uprava_signalu(t_prechodu + 0.0005, True)            # odebrat ho -> zase v pořádku
        self.assertIn("sedí", o.stav_upravy.text())
        o.akce_uprava.setChecked(False)
        self.assertEqual(z.stav, "opraveno")
        self.assertFalse(o.osa.rezim_upravy)
        o.close()


if __name__ == "__main__":
    unittest.main()
