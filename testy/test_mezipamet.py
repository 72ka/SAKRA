"""Mezipaměť analýzy: návrat ke kazetě bez nového čtení a dekódování."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from sakra.jadro import analyza, mezipamet
from sakra.jadro.model import RucniUsek
from testy.signal import pulzy_tesla, signal_z_pulzu, soubor_tesla, uloz_wav


class Mezipamet(unittest.TestCase):
    def setUp(self):
        self.slozka = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict(os.environ, {"SAKRA_CACHE": str(self.slozka)})
        self.env.start()
        tmp = Path(tempfile.mkdtemp())
        data = np.random.default_rng(8).integers(0, 256, 400, np.uint8).tobytes()
        self.cesta = tmp / "HH00094 (1).wav"
        uloz_wav(self.cesta, signal_z_pulzu(pulzy_tesla(soubor_tesla(b"PAMET", data), 44100), 44100), 44100)

    def tearDown(self):
        self.env.stop()

    def analyz(self, **kw):
        volani = []
        puvodni = analyza._analyzuj_stranu
        with mock.patch.object(analyza, "_analyzuj_stranu", lambda *a: volani.append(1) or puvodni(*a)):
            v = analyza.analyzuj_stranu(self.cesta, 1, **kw)
        return v, bool(volani)

    def test_druhe_otevreni_z_mezipameti(self):
        v1, pocitano = self.analyz()
        self.assertTrue(pocitano)
        self.assertEqual(len(list(self.slozka.glob("*" + mezipamet.PRIPONA))), 1)
        v2, pocitano = self.analyz()
        self.assertFalse(pocitano)
        self.assertIsNot(v1, v2)                                   # vlastní kopie (úpravy se nepřenesou)
        self.assertEqual([s.nazev for s in v2.soubory], ["PAMET"])
        self.assertEqual([b.data for b in v2.soubory[0].bloky], [b.data for b in v1.soubory[0].bloky])
        self.assertTrue(np.array_equal(v2.nahravka.vzorky, v1.nahravka.vzorky))
        v2.soubory.clear()                                         # úprava výsledku mezipaměť nezmění
        v3, pocitano = self.analyz()
        self.assertFalse(pocitano)
        self.assertEqual(len(v3.soubory), 1)

    def test_jine_volby_nebo_zmena_souboru(self):
        self.analyz()
        _, pocitano = self.analyz(polarita="obracena")
        self.assertTrue(pocitano)
        _, pocitano = self.analyz(rucni_useky=[RucniUsek(0.0, 0.2, "šum")])
        self.assertTrue(pocitano)
        t = time.time() + 5
        os.utime(self.cesta, (t, t))                               # soubor se změnil
        _, pocitano = self.analyz()
        self.assertTrue(pocitano)

    def test_poskozena_mezipamet_a_vypnuti(self):
        self.analyz()
        for f in self.slozka.glob("*" + mezipamet.PRIPONA):
            f.write_bytes(b"poskozeno")
        v, pocitano = self.analyz()
        self.assertTrue(pocitano)
        self.assertEqual([s.nazev for s in v.soubory], ["PAMET"])
        os.environ["SAKRA_CACHE"] = "0"
        _, pocitano = self.analyz()
        self.assertTrue(pocitano)

    def test_uklid_drzi_limit(self):
        for i in range(5):
            f = self.slozka / f"{i}{mezipamet.PRIPONA}"
            f.write_bytes(bytes(1000))
            os.utime(f, (1000 + i, 1000 + i))
        mezipamet.uklid(self.slozka, limit=2500)
        self.assertEqual(sorted(f.name for f in self.slozka.glob("*" + mezipamet.PRIPONA)),
                         [f"3{mezipamet.PRIPONA}", f"4{mezipamet.PRIPONA}"])


    def test_nastaveni_vymaze(self):
        try:
            from PySide6.QtWidgets import QApplication
            from sakra.gui import vzhled
            from sakra.gui.zahlavi import DialogNastaveni
        except ImportError:
            self.skipTest("PySide6 není k dispozici")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance() or QApplication([])  # noqa: F841
        self.analyz()
        d = DialogNastaveni(vzhled.Nastaveni())
        self.assertTrue(d.vymazat.isEnabled())
        self.assertIn("1", d.vymazat.text())
        d.vymazat.click()
        self.assertFalse(list(self.slozka.glob("*" + mezipamet.PRIPONA)))
        self.assertFalse(d.vymazat.isEnabled())


if __name__ == "__main__":
    unittest.main()
