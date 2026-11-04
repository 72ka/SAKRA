import tempfile
import unittest
from pathlib import Path

import numpy as np

from sakra.formaty import csw
from sakra.jadro.analyza import analyzuj_stranu
from sakra.platformy import ondra
from sakra.projekt import zpracuj
from sakra.jadro.model import Kazeta
from testy.signal import (pulzy_tesla, pulzy_vili, signal_z_pulzu, soubor_tesla, uloz_wav, zaznam_vili)

RATE = 44100


def data_basic(n: int, seed: int = 3) -> bytes:
    rng = np.random.default_rng(seed)
    return b"\xf6\xf6\xf6\x42" + b"AUTORI: TEST" + rng.integers(0, 256, n, dtype=np.uint8).tobytes()


class TeslaRom(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _wav(self, bloky, jmeno="t.wav", rychlost=1.0, uprav=None):
        x = signal_z_pulzu(pulzy_tesla(bloky, RATE, rychlost), RATE)
        if uprav:
            uprav(x)
        uloz_wav(self.tmp / jmeno, x, RATE)
        return self.tmp / jmeno

    def test_dekodovani_pri_ruzne_rychlosti(self):
        data = data_basic(900)
        bloky = soubor_tesla(b"PERSPEKTIVA", data)
        for r in (0.9, 1.0, 1.1):
            with self.subTest(rychlost=r):
                v = analyzuj_stranu(self._wav(bloky, rychlost=r), 1)
                self.assertEqual(len(v.soubory), 1)
                s = v.soubory[0]
                self.assertEqual(s.nazev, "PERSPEKTIVA")
                self.assertEqual(s.stav, "ok")
                self.assertEqual(s.typ_bloku, "BASIC")
                self.assertEqual([b.data for b in s.bloky], bloky)
                self.assertAlmostEqual(s.info["rychlost"], r, delta=0.03)

    def test_csw_zpet_stejne_bloky(self):
        bloky = soubor_tesla(b"KORAB", data_basic(600))
        v = analyzuj_stranu(self._wav(bloky), 1)
        ondra.OndraTesla().zapis(v.soubory[0], self.tmp / "korab")
        rate, pulzy, u0 = csw.nacti(self.tmp / "korab.csw")
        self.assertEqual(pulzy, pulzy_tesla(bloky, rate))

    def test_vypadek_neni_tise_opraven(self):
        bloky = soubor_tesla(b"RAKETA", data_basic(500))

        def vypadek(x):           # krátký výpadek uprostřed druhého bloku
            t = 0.5 + 0.39 + 1.24 + 0.2 + 0.39 + 0.6
            x[int(t * RATE):int((t + 0.0035) * RATE)] = 0
        v = analyzuj_stranu(self._wav(bloky, uprav=vypadek), 1)
        s = v.soubory[0]
        # každý blok označený jako dobrý musí mít přesně původní data
        for b in s.bloky:
            if b.ok:
                self.assertIn(b.data, bloky)
        self.assertEqual(s.stav, "chyba")
        self.assertEqual(sum(not b.ok for b in s.bloky), 1)

    def test_oprava_z_druhe_kopie(self):
        bloky = soubor_tesla(b"T5 TEST", data_basic(1200))
        pz = pulzy_tesla(bloky, RATE) * 2                  # dvě kopie za sebou
        x = signal_z_pulzu(pz, RATE)
        t = 0.5 + 0.39 + 1.24 + 0.2 + 2 * (0.39 + 1.24 + 0.0435) + 0.7   # uprostřed 3. bloku první kopie
        x[int(t * RATE):int((t + 0.05) * RATE)] = 0
        uloz_wav(self.tmp / "dve.wav", x, RATE)
        k = Kazeta()
        zpracuj(k, {1: self.tmp / "dve.wav"})
        soubory = [z.soubor for z in k.strany[0].zaznamy if z.soubor]
        self.assertEqual(len(soubory), 2)
        prvni = soubory[0]
        self.assertEqual(prvni.stav, "opraveno")
        self.assertIn("kopie", " ".join(b.oprava for b in prvni.bloky))
        self.assertEqual([b.data for b in sorted(prvni.bloky, key=lambda b: b.cislo)], bloky)
        self.assertEqual(k.strany[0].zaznamy[0].funkcni_orig, "Audio")


class ViLiRom(unittest.TestCase):
    def test_dva_zaznamy(self):
        tmp = Path(tempfile.mkdtemp())
        data = bytes(range(256)) * 6                       # 1536 B = 2 záznamy
        zaz = zaznam_vili(b"HRA", data)
        uloz_wav(tmp / "v.wav", signal_z_pulzu(pulzy_vili(zaz, RATE), RATE), RATE)
        v = analyzuj_stranu(tmp / "v.wav", 1)
        self.assertEqual(len(v.soubory), 1)
        s = v.soubory[0]
        self.assertEqual(s.platforma, "ondra-vili")
        self.assertEqual(s.nazev, "HRA.KÓD")
        self.assertEqual(s.stav, "ok")
        ondra.OndraViLi().zapis(s, tmp / "hra")
        self.assertEqual((tmp / "hra.tap").read_bytes(), b"".join(zaz))
        self.assertEqual((tmp / "hra.bin").read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
