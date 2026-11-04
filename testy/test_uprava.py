"""Ruční úprava signálu: přidání / odebrání přechodu a opakované dekódování bloku."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from sakra.jadro.analyza import analyzuj_stranu, znovu_dekoduj_blok
from sakra.jadro.pulzy import odeber_hranu, vloz_hranu
from testy.signal import pulzy_tesla, signal_z_pulzu, soubor_tesla, uloz_wav


class Uprava(unittest.TestCase):
    def test_chybejici_a_navic_prechod(self):
        tmp = Path(tempfile.mkdtemp())
        data = np.random.default_rng(2).integers(0, 256, 700, dtype=np.uint8).tobytes()
        uloz_wav(tmp / "t.wav", signal_z_pulzu(pulzy_tesla(soubor_tesla(b"KORAB", data), 44100), 44100), 44100)
        v = analyzuj_stranu(tmp / "t.wav", 1)
        s = v.soubory[0]
        b = next(x for x in s.bloky if x.cislo == 3)
        self.assertTrue(b.ok)
        p = v.pulzy
        stred = (b.zacatek + 0.6 * (b.konec - b.zacatek)) * p.rate
        i = int(np.searchsorted(p.hrany, stred))
        vzorek = int(p.hrany[i])

        # 1) chybějící přechod (výpadek) -> blok vadný; ruční přidání ho opraví
        v.pulzy = odeber_hranu(p, i)
        spatny = znovu_dekoduj_blok(v, s, b)
        self.assertFalse(spatny is not None and spatny.ok)
        v.pulzy = vloz_hranu(v.pulzy, vzorek)
        opraveny = znovu_dekoduj_blok(v, s, b)
        self.assertTrue(opraveny.ok)
        self.assertEqual(opraveny.data, b.data)

        # 2) přechod navíc (zákmit) -> vadný; odebrání ho opraví
        v.pulzy = vloz_hranu(p, vzorek + 3)
        self.assertFalse(znovu_dekoduj_blok(v, s, b).ok)
        j = int(np.searchsorted(v.pulzy.hrany, vzorek + 3))
        v.pulzy = odeber_hranu(v.pulzy, j)
        self.assertTrue(znovu_dekoduj_blok(v, s, b).ok)
        # úrovně se po úpravách pořád střídají
        self.assertTrue((v.pulzy.urovne[1:] == -v.pulzy.urovne[:-1]).all())


if __name__ == "__main__":
    unittest.main()
