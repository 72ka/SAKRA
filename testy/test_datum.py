"""Navrhované datum digitalizace = čas změny souboru nahrávky (ne dnešek)."""
import datetime as dt
import os
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from sakra.jadro.model import Kazeta
from sakra.projekt import zpracuj
from testy.signal import pulzy_tesla, signal_z_pulzu, soubor_tesla, uloz_wav

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def nahravka(den: dt.date) -> Path:
    tmp = Path(tempfile.mkdtemp())
    data = np.random.default_rng(1).integers(0, 256, 300, np.uint8).tobytes()
    cesta = tmp / "HH00092 (1).wav"
    uloz_wav(cesta, signal_z_pulzu(pulzy_tesla(soubor_tesla(b"DATUM", data), 44100), 44100), 44100)
    t = time.mktime(den.timetuple()) + 12 * 3600
    os.utime(cesta, (t, t))
    return cesta


class Datum(unittest.TestCase):
    def test_datum_z_casu_zmeny_souboru(self):
        k = Kazeta()
        zpracuj(k, {1: nahravka(dt.date(2023, 5, 17))})
        self.assertEqual(k.digitalizace.datum, dt.date(2023, 5, 17))

    def test_rucni_datum_se_neprepise(self):
        k = Kazeta()
        k.digitalizace.datum = dt.date(2020, 1, 2)
        zpracuj(k, {1: nahravka(dt.date(2023, 5, 17))})
        self.assertEqual(k.digitalizace.datum, dt.date(2020, 1, 2))

    def test_karta_neulozi_dnesek(self):
        try:
            from PySide6.QtWidgets import QApplication
            from sakra.gui.karta import KartaKazety
        except ImportError:
            self.skipTest("PySide6 není k dispozici")
        app = QApplication.instance() or QApplication([])  # noqa: F841
        k = Kazeta()
        karta = KartaKazety()
        karta.nastav(k)
        karta.autor.setText("Tester")
        karta.autor.textEdited.emit("Tester")          # úprava jiného pole před analýzou
        self.assertEqual(k.digitalizace.autor, "Tester")
        self.assertIsNone(k.digitalizace.datum)          # dnešek se jen ukazuje, neuloží se
        zpracuj(k, {1: nahravka(dt.date(2023, 5, 17))})
        self.assertEqual(k.digitalizace.datum, dt.date(2023, 5, 17))
        karta.nastav(k)
        self.assertEqual(karta.datum.date().toPython(), dt.date(2023, 5, 17))
        karta.datum.setDate(karta.datum.date().addDays(1))   # ruční změna se uloží
        self.assertEqual(k.digitalizace.datum, dt.date(2023, 5, 18))


if __name__ == "__main__":
    unittest.main()
