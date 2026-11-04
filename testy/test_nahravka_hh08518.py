"""Skutečná nahrávka z Herního archivu (strana 2 kazety HH08518), je-li v projektu."""
import unittest
from pathlib import Path

from sakra.jadro.analyza import analyzuj_stranu

WAV = Path(__file__).resolve().parents[1] / "HH08518 (2)_44kHz.wav"
OCEKAVANE = ["MIKOS.KÓD", "BASIC EXP V5.0/G", "PERSPEKTIVA", "KORAB", "BAJKONUR", "RAKETA", "T2 VSEOBECNY",
             "T3 RYBARSTVI", "T4 KRITICKE DNY", "S1 STO", "W1 ANO-NE", "P1 PROFESOR", "Q1 PORADI", "D1 DELENI",
             "D2 DELITEL", "T5 TEST", "G1 KORAB", "G2 BAJKONUR", "G2 BAJKONUR"]


@unittest.skipUnless(WAV.exists(), "chybí nahrávka HH08518 (2)_44kHz.wav")
class HH08518Strana2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = analyzuj_stranu(WAV, 2)

    def test_programy(self):
        self.assertEqual([s.nazev for s in self.v.soubory], OCEKAVANE)

    def test_stav(self):
        stavy = {s.nazev: s.stav for s in self.v.soubory}
        self.assertEqual(stavy["MIKOS.KÓD"], "chyba")                # jen záznamy 4–5 z 5
        self.assertEqual(stavy["BASIC EXP V5.0/G"], "chyba")         # výpadek signálu v bloku 48
        self.assertEqual([s.stav for s in self.v.soubory[2:]], ["ok"] * 17)
        basic = self.v.soubory[1]
        self.assertEqual([b.cislo for b in basic.bloky if not b.ok], [48])
        self.assertEqual(sum(b.ok for s in self.v.soubory if s.platforma == "ondra-tesla" for b in s.bloky), 182)

    def test_kopie_g2_shodne(self):
        g2 = [s for s in self.v.soubory if s.nazev == "G2 BAJKONUR"]
        self.assertEqual(g2[0]._data, g2[1]._data)


if __name__ == "__main__":
    unittest.main()
