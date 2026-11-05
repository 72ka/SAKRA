"""Stereo nahrávka: změření posunu stop, součet L+P s korekcí, zobrazení stop na časové ose."""
import os
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from sakra.jadro import audio
from testy.signal import pulzy_tesla, signal_z_pulzu, soubor_tesla, uloz_wav

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RATE = 44100
ZPOZDENI = 5                                    # pravá stopa se zpožďuje o 5 vzorků = 113 µs


def stereo_wav(cesta: Path, sum_: float = 0.02) -> None:
    x = signal_z_pulzu(pulzy_tesla(soubor_tesla(b"STEREO", bytes(range(256)) * 3), RATE), RATE, sum_=0)
    rng = np.random.default_rng(3)
    l = x + rng.normal(0, sum_, len(x)).astype(np.float32)
    r = np.concatenate([np.zeros(ZPOZDENI, np.float32), x[:-ZPOZDENI]]) * 0.7
    r = r + rng.normal(0, sum_, len(x)).astype(np.float32)
    uloz_wav(cesta, np.stack([l, r], axis=1), RATE)


class Soucet(unittest.TestCase):
    def test_posun_a_soucet(self):
        tmp = Path(tempfile.mkdtemp())
        stereo_wav(tmp / "s.wav")
        n = audio.nacti(tmp / "s.wav")
        self.assertEqual(n.stopy.shape, (len(n.vzorky), 2))
        self.assertAlmostEqual(n.posun_us, ZPOZDENI / RATE * 1e6, delta=12)
        self.assertGreater(n.korelace, 0.9)
        s = audio.nacti(tmp / "s.wav", kanal=audio.SOUCET)
        self.assertEqual(s.kanal, audio.SOUCET)
        self.assertAlmostEqual(s.posun_souctu_us, n.posun_us)
        # srovnaný součet sedí na levou stopu, nesrovnaný (posun 0) hůř
        l = n.stopy[:, 0].astype(np.float32)
        k_srovnany = np.corrcoef(l, s.vzorky.astype(np.float32))[0, 1]
        bez = audio.nacti(tmp / "s.wav", kanal=audio.SOUCET, posun_us=0.0)
        self.assertGreater(k_srovnany, np.corrcoef(l, bez.vzorky.astype(np.float32))[0, 1])
        self.assertGreater(k_srovnany, 0.97)
        # zlomkový posun: lineární interpolace mezi vzorky
        r = np.array([0, 0, 100, 200, 300], np.int16)
        np.testing.assert_allclose(audio.soucet(np.zeros(5, np.int16), r, 1.5), [25, 75, 125, 150, 150])

    def test_mono_bez_stop(self):
        tmp = Path(tempfile.mkdtemp())
        uloz_wav(tmp / "m.wav", signal_z_pulzu(pulzy_tesla(soubor_tesla(b"MONO", bytes(300)), RATE), RATE), RATE)
        n = audio.nacti(tmp / "m.wav", kanal=audio.SOUCET)        # mono: součet = jediný kanál
        self.assertEqual(n.kanal, 0)
        self.assertIsNone(n.stopy)
        self.assertIsNone(n.posun_us)

    def test_analyza_souctu(self):
        from sakra.jadro.analyza import analyzuj_stranu
        tmp = Path(tempfile.mkdtemp())
        stereo_wav(tmp / "s.wav")
        v = analyzuj_stranu(tmp / "s.wav", 1, volba_kanalu="soucet", posun_us=100.0)
        self.assertEqual(v.strana.volba_kanalu, "soucet")
        self.assertEqual(v.strana.posun_kanalu, 100.0)
        self.assertEqual(v.strana.signal["posun_souctu_us"], 100.0)
        self.assertTrue(v.soubory and all(b.ok for b in v.soubory[0].bloky))


class Zobrazeni(unittest.TestCase):
    def test_okno(self):
        try:
            from PySide6.QtWidgets import QApplication
            from sakra.gui.okno import HlavniOkno
        except ImportError:
            self.skipTest("PySide6 není k dispozici")
        app = QApplication.instance() or QApplication([])
        tmp = Path(tempfile.mkdtemp())
        stereo_wav(tmp / "HH00077 (1).wav")
        o = HlavniOkno()
        o.resize(1400, 900)
        o.show()
        o.prepni_rezim("stul")

        def cekej():
            konec = time.time() + 90
            while o.ukol and o.ukol.isRunning() and time.time() < konec:
                app.processEvents()
                time.sleep(0.02)
            app.processEvents()
        o.otevri_nahravky([str(tmp / "HH00077 (1).wav")])
        cekej()
        self.assertTrue(o.volba_zobrazeni.isEnabled())
        self.assertIn("µs", o.volba_zobrazeni.toolTip())
        for i in range(o.volba_zobrazeni.count()):                # každé zobrazení se vykreslí
            o.volba_zobrazeni.setCurrentIndex(i)
            self.assertEqual(o.osa.zobrazeni, o.volba_zobrazeni.itemData(i))
            o.osa.grab()
        self.assertFalse(o.akce_posunu.isVisible())
        o.volba_kanalu.setCurrentIndex(o.volba_kanalu.findData("soucet"))
        o._zmena_volby()
        cekej()
        s = o.kazeta.strany[0]
        self.assertEqual(s.volba_kanalu, "soucet")
        self.assertIsNone(s.posun_kanalu)
        self.assertTrue(o.akce_posunu.isVisible())
        self.assertIn("L+P", o.info_strany.text())
        o.posun_kanalu.setValue(o.posun_kanalu.minimum() + 5)       # z „auto“ se začne od změřené hodnoty
        self.assertAlmostEqual(o.posun_kanalu.value(), 113, delta=12)
        self.assertEqual(o.osa.zobrazeni, "soucet")
        o.posun_kanalu.setValue(50)
        self.assertEqual(o.osa.posun_souctu(), 50)
        o._zmena_volby()
        cekej()
        self.assertEqual(s.posun_kanalu, 50)
        self.assertEqual(o.vysledky[1].strana.signal["posun_souctu_us"], 50)
        o.close()


if __name__ == "__main__":
    unittest.main()
