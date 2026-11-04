"""Ruční určení nerozpoznaného úseku jako „žádná data (šum, řeč, hudba…)“."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from sakra.balicek import exportuj
from sakra.jadro.model import ZADNA_DATA, Kazeta, Zaznam, urci_platformu
from sakra.projekt import analyzuj_strany, vloz_vysledky
from testy.signal import pulzy_tesla, signal_z_pulzu, soubor_tesla, uloz_wav


class ZadnaData(unittest.TestCase):
    def test_urceni_a_navrat(self):
        z = Zaznam(cas_od=1.0, cas_do=5.0, typ="Data", platforma="?", nazev="(nerozpoznáno)", nerozpoznano=True)
        self.assertEqual(z.stav, "nerozpoznáno")
        urci_platformu(z, ZADNA_DATA)
        self.assertEqual((z.typ, z.platforma, z.nazev, z.stav), ("Audio", "", "(žádná data)", "žádná data"))
        urci_platformu(z, "ZX Spectrum")
        self.assertEqual((z.typ, z.platforma, z.nazev, z.stav), ("Data", "ZX Spectrum", "(nerozpoznáno)",
                                                                 "nerozpoznáno"))
        urci_platformu(z, "(neznámá)")
        self.assertEqual(z.platforma, "?")

    def test_balicek_a_nova_analyza(self):
        tmp = Path(tempfile.mkdtemp())
        rate = 44100
        prog = signal_z_pulzu(pulzy_tesla(soubor_tesla(b"PRG", bytes(300)), rate), rate)
        # neznámý signál: obdélník 3 kHz, 4 s (nesedí na žádnou platformu)
        t = np.arange(4 * rate) / rate
        divny = (0.6 * np.sign(np.sin(2 * np.pi * 3000 * t * (1 + 0.3 * np.sin(2 * np.pi * 0.7 * t))))).astype(np.float32)
        x = np.concatenate([prog, np.zeros(rate, np.float32), divny, np.zeros(rate, np.float32)])
        uloz_wav(tmp / "HH00090 (1).wav", x, rate)
        k = Kazeta()
        v = analyzuj_strany({1: tmp / "HH00090 (1).wav"})
        vloz_vysledky(k, v)
        nezn = [z for z in k.strany[0].zaznamy if z.nerozpoznano and z.typ != "Audio"]
        self.assertTrue(nezn, [(z.nazev, z.typ) for z in k.strany[0].zaznamy])
        urci_platformu(nezn[0], ZADNA_DATA)
        nezn[0].poznamky = "znělka"
        # nová analýza (např. po změně kanálu) určení zachová
        vloz_vysledky(k, analyzuj_strany({1: tmp / "HH00090 (1).wav"}))
        z = next(z for z in k.strany[0].zaznamy if z.nerozpoznano and abs(z.cas_od - nezn[0].cas_od) < 1)
        self.assertEqual((z.typ, z.nazev, z.poznamky, z.stav), ("Audio", "(žádná data)", "znělka", "žádná data"))
        d = exportuj(k, tmp / "archiv", v, kopirovat_zdroj=False, pdf=False, snimky=False)
        jmena = [p.name for p in d.rglob("*")]
        self.assertTrue(any("(zvuk)" in j and j.endswith(".wav") for j in jmena), jmena)
        self.assertFalse(any("(zvuk)" in j and j.endswith(".csw") for j in jmena), jmena)


if __name__ == "__main__":
    unittest.main()
