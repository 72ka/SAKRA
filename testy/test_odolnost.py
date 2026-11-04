"""Chyba v jednom dekodéru nesmí shodit analýzu celé strany (dřív: Sharp MZ na neznámém turbu)."""
import tempfile
import unittest
from pathlib import Path

from sakra.jadro import analyza
from sakra.jadro.analyza import analyzuj_stranu
from sakra.platformy import VSECHNY
from testy.signal import pulzy_tesla, signal_z_pulzu, soubor_tesla, uloz_wav


class Odolnost(unittest.TestCase):
    def test_vyjimka_dekoderu(self):
        tmp = Path(tempfile.mkdtemp())
        uloz_wav(tmp / "o.wav", signal_z_pulzu(pulzy_tesla(soubor_tesla(b"PRG", bytes(300)), 44100), 44100), 44100)
        sharp = next(p for p in VSECHNY if p.id == "sharp-mz")
        puvodni = sharp.dekoduj
        sharp.skore = lambda u, r: 1.0                       # dekodér dostane každý úsek
        sharp.dekoduj = lambda ktx, useky: (_ for _ in ()).throw(ValueError("bytes must be in range(0, 256)"))
        try:
            v = analyzuj_stranu(tmp / "o.wav", 1, polarita="normalni")
        finally:
            sharp.dekoduj = puvodni
            del sharp.skore
        self.assertEqual([s.nazev for s in v.soubory], ["PRG"])
        self.assertTrue(any("Sharp" in c for c in analyza.CHYBY_DEKODERU))


if __name__ == "__main__":
    unittest.main()
