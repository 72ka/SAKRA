"""Slabá místa signálu (pokles úrovně proti okolí) – značky na časové ose."""
import unittest

import numpy as np

from sakra.jadro.slabe import slaba_mista

RATE = 44100


def signal(sekund: float = 6.0) -> np.ndarray:
    """Souvislý datový signál jako z pásky: obdélník s náhodnými půlperiodami (bity 0/1), zaoblený, se šumem."""
    rng = np.random.default_rng(3)
    pulzy = rng.choice([9, 18], int(sekund * RATE / 13))
    x = np.concatenate([np.full(n, 12000.0 if i % 2 else -12000.0) for i, n in enumerate(pulzy)])
    x = np.convolve(x, np.ones(5) / 5, mode="same")
    return x + rng.normal(0, 300, len(x))


class Slabe(unittest.TestCase):
    def test_cisty_signal_bez_hlaseni(self):
        x = signal()
        self.assertEqual(slaba_mista(x.astype(np.int16), RATE, [(0.0, len(x) / RATE)]), [])

    def test_vypadek_a_sestup(self):
        x = signal()
        t = np.arange(len(x)) / RATE
        delka = len(x) / RATE
        v1, v2 = 0.4 * delka, 0.7 * delka
        obalka = np.ones(len(x))
        obalka[(t >= v1) & (t < v1 + 0.008)] = 0.1                  # výpadek 8 ms
        sestup = (t >= v2 - 0.05) & (t < v2 + 0.01)                 # pozvolný sestup na 35 % a zpět
        obalka[sestup] = np.interp(t[sestup], [v2 - 0.05, v2, v2 + 0.01], [1.0, 0.35, 1.0])
        mista = slaba_mista((x * obalka).astype(np.int16), RATE, [(0.0, delka)])
        self.assertEqual(len(mista), 2, mista)
        a, b = mista
        self.assertTrue(a.vypadek)
        self.assertLess(abs(a.zacatek - v1), 0.004)
        self.assertGreater(a.konec - a.zacatek, 0.005)
        self.assertFalse(b.vypadek)
        self.assertLess(b.zacatek, v2)
        self.assertGreater(b.konec, v2)
        self.assertLess(b.uroven, 0.45)

    def test_mezery_mezi_bloky_se_nehodnoti(self):
        x = signal()
        delka = len(x) / RATE
        y = x.copy()
        y[int(0.5 * delka * RATE):int(0.6 * delka * RATE)] = 0           # ticho mezi bloky
        useky = [(0.0, 0.5 * delka), (0.6 * delka, delka)]
        self.assertEqual(slaba_mista(y.astype(np.int16), RATE, useky), [])


if __name__ == "__main__":
    unittest.main()
