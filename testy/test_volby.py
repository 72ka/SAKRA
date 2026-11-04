"""Volba kanálu (auto / levý / pravý) a polarity (auto / normální / obrácená) nahrávky."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from sakra.jadro.analyza import analyzuj_stranu
from sakra.jadro.model import Kazeta, kazeta_do_json, kazeta_z_json
from sakra.projekt import analyzuj_strany, vloz_vysledky
from testy.signal import pulzy_tesla, signal_z_pulzu, soubor_tesla, uloz_wav


class Volby(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        x = signal_z_pulzu(pulzy_tesla(soubor_tesla(b"KANAL", bytes(range(256)) * 2), 44100), 44100)
        sum_ = np.random.default_rng(3).normal(0, 0.9, len(x)).astype(np.float32)
        # vlevo silný šum (automatika vybere levý kanál), vpravo data
        uloz_wav(cls.tmp / "stereo.wav", np.stack([sum_, x], axis=1), 44100)
        uloz_wav(cls.tmp / "mono.wav", x, 44100)

    def test_kanal(self):
        auto = analyzuj_stranu(self.tmp / "stereo.wav", 1)
        self.assertEqual(auto.strana.kanal, 0)
        pravy = analyzuj_stranu(self.tmp / "stereo.wav", 1, volba_kanalu="pravy")
        self.assertEqual((pravy.strana.kanal, pravy.strana.volba_kanalu), (1, "pravy"))
        self.assertEqual([s.nazev for s in pravy.soubory], ["KANAL"])
        self.assertTrue(pravy.soubory[0].ok)
        self.assertFalse(any(s.ok for s in auto.soubory))

    def test_obalky_kanalu(self):
        """Obálka obou stop pro přehled kazety: vlevo šum, vpravo data – časově sedí s nahrávkou."""
        v = analyzuj_stranu(self.tmp / "stereo.wav", 1, volba_kanalu="pravy")
        n = v.nahravka
        self.assertEqual(n.obalky.shape[0], 2)
        self.assertAlmostEqual(n.obalky.shape[1] * n.krok_obalky, n.delka, delta=0.02)
        mono = analyzuj_stranu(self.tmp / "mono.wav", 1).nahravka
        self.assertEqual(mono.obalky.shape[0], 1)

    def test_polarita(self):
        n = analyzuj_stranu(self.tmp / "mono.wav", 1, polarita="normalni")
        o = analyzuj_stranu(self.tmp / "mono.wav", 1, polarita="obracena")
        a = analyzuj_stranu(self.tmp / "mono.wav", 1)
        self.assertFalse(n.strana.signal["polarita_obracena"])
        self.assertTrue(o.strana.signal["polarita_obracena"])
        self.assertTrue(np.array_equal(o.nahravka.vzorky, -n.nahravka.vzorky))
        self.assertEqual(a.strana.polarita, "auto")
        for v in (n, o, a):
            self.assertEqual([s.nazev for s in v.soubory], ["KANAL"])
            self.assertTrue(v.soubory[0].ok)

    def test_projekt_si_volby_pamatuje(self):
        k = Kazeta()
        v = analyzuj_strany({1: self.tmp / "stereo.wav"}, volby={1: ("pravy", "obracena")})
        vloz_vysledky(k, v)
        k2 = kazeta_z_json(kazeta_do_json(k))
        s = k2.strany[0]
        self.assertEqual((s.volba_kanalu, s.polarita, s.kanal), ("pravy", "obracena", 1))


if __name__ == "__main__":
    unittest.main()
