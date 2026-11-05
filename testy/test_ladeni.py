"""Ladění azimutu hlavy: histogram délek pulzů, rozptyl špičky, posun kanálů L/R."""
import unittest

import numpy as np

from sakra.jadro.ladeni import posun_kanalu, vyhodnot

RATE = 48000


def data(n_s=0.5, rozmazani=0.0, seed=1):
    """Obdélník s půlperiodami 250 a 500 µs (bity), volitelně rozmazaný (jitter jako šikmá hlava)."""
    rng = np.random.default_rng(seed)
    delky = rng.choice([250e-6, 500e-6], int(n_s / 375e-6))
    delky = delky * (1 + rozmazani * rng.standard_normal(len(delky)))
    hrany = np.cumsum(delky) * RATE
    t = np.arange(int(hrany[-1]))
    x = np.where(np.searchsorted(hrany, t) % 2, 1.0, -1.0)
    return np.convolve(x, np.ones(4) / 4, mode="same") * 0.5 * 2 ** 31


class Ladeni(unittest.TestCase):
    def test_spicky_histogramu(self):
        v = vyhodnot(data(), RATE)
        self.assertGreater(v.pulzu, 500)
        self.assertIn(round(v.spicka_us / 250) * 250, (250, 500))
        self.assertLess(abs(v.spicka_us - round(v.spicka_us / 250) * 250), 15)
        self.assertLess(v.rozptyl, 0.05)
        self.assertIsNone(v.posun_us)                          # mono

    def test_rozmazani_zvysi_rozptyl(self):
        ostre = vyhodnot(data(rozmazani=0.0), RATE).rozptyl
        rozmazane = vyhodnot(data(rozmazani=0.12), RATE).rozptyl
        self.assertGreater(rozmazane, ostre * 2)

    def test_posun_kanalu(self):
        x = data()
        for zpozdeni in (0, 3, -5):
            r = np.roll(x, zpozdeni)
            posun, kor = posun_kanalu(x, r, RATE)
            self.assertAlmostEqual(posun, zpozdeni * 1e6 / RATE, delta=6)
            self.assertGreater(kor, 0.9)
        v = vyhodnot(np.stack([x, np.roll(x, 2)], axis=1), RATE)
        self.assertAlmostEqual(v.posun_us, 2 * 1e6 / RATE, delta=6)

    def test_ticho(self):
        v = vyhodnot(np.zeros((4800, 2)), RATE)
        self.assertEqual(v.pulzu, 0)
        self.assertIsNone(v.rozptyl)
        self.assertIsNone(v.posun_us)


if __name__ == "__main__":
    unittest.main()
