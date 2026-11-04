"""Autorství a návod: SAKRA uvádí autora a Herní archiv v protokolu, JSON, Excelu; návod v PDF je přiložen."""
import json
import tempfile
import unittest
from pathlib import Path

from sakra import AKRONYM, LOGO, NAVOD, PODPIS
from sakra.balicek import exportuj, protokol
from sakra.jadro.analyza import analyzuj_stranu
from sakra.jadro.model import Kazeta
from sakra.projekt import vloz_vysledky
from testy.signal import pulzy_tesla, signal_z_pulzu, soubor_tesla, uloz_wav


class Autor(unittest.TestCase):
    def test_podpis(self):
        self.assertIn("Jan Heřman", PODPIS)
        self.assertIn("72ka", PODPIS)
        self.assertIn("2026", PODPIS)
        self.assertIn("www.herniarchiv.cz", PODPIS)
        self.assertEqual(AKRONYM, "a Swiss Army Knife for Retrogaming Archaeologists")
        self.assertIn(AKRONYM, PODPIS)
        self.assertEqual(LOGO.read_bytes()[:4], b"\x89PNG")

    def test_o_aplikaci(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from sakra.gui.o_aplikaci import DialogOAplikaci
        except ImportError:
            self.skipTest("PySide6 není k dispozici")
        app = QApplication.instance() or QApplication([])  # noqa: F841
        d = DialogOAplikaci()
        texty = " ".join(w.text() for w in d.findChildren(type(d.findChild(type(d.layout().itemAt(1).widget())))))
        self.assertIn("etrogaming", texty)
        self.assertIn("72ka", texty)
        self.assertFalse(d.layout().itemAt(0).widget().pixmap().isNull())     # logo

    def test_navod(self):
        self.assertTrue(NAVOD.exists(), "chybí návod – python navod/vytvor_navod.py")
        self.assertEqual(NAVOD.read_bytes()[:5], b"%PDF-")

    def test_balicek(self):
        tmp = Path(tempfile.mkdtemp())
        uloz_wav(tmp / "HH00003 (1).wav",
                 signal_z_pulzu(pulzy_tesla(soubor_tesla(b"AUTOR", bytes(300)), 44100), 44100), 44100)
        k = Kazeta()
        k.inventar.cislo = "HH00003"
        v = {1: analyzuj_stranu(tmp / "HH00003 (1).wav", 1)}
        vloz_vysledky(k, v)
        self.assertIn(PODPIS, protokol(k, []))
        d = exportuj(k, tmp / "archiv", v, kopirovat_zdroj=False, pdf=False)
        meta = json.loads((d / "HH00003.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["sakra"]["web"], "www.herniarchiv.cz")
        self.assertIn("72ka", meta["sakra"]["autor"])


if __name__ == "__main__":
    unittest.main()
