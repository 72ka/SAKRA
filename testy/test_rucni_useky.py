"""Ručně označené úseky (šum, hudba, řeč): vyřadí se z analýzy a mají vlastní řádek obsahu."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from sakra.jadro.analyza import analyzuj_stranu, oznac_usek, oznac_usek_vysledku, uplatni_rucni_useky
from sakra.jadro.model import Kazeta, RucniUsek, kazeta_do_json, kazeta_z_json, urci_platformu
from testy.signal import pulzy_tesla, signal_z_pulzu, soubor_tesla, uloz_wav

RATE = 44100


def nahravka() -> tuple[Path, float]:
    """Dva programy za sebou; vrátí cestu a čas mezi nimi."""
    tmp = Path(tempfile.mkdtemp())
    rng = np.random.default_rng(4)
    a = signal_z_pulzu(pulzy_tesla(soubor_tesla(b"PRVNI", rng.integers(0, 256, 300, np.uint8).tobytes()), RATE), RATE)
    b = signal_z_pulzu(pulzy_tesla(soubor_tesla(b"DRUHY", rng.integers(0, 256, 300, np.uint8).tobytes()), RATE), RATE)
    uloz_wav(tmp / "HH00090 (1).wav", np.concatenate([a, b]), RATE)
    return tmp / "HH00090 (1).wav", len(a) / RATE


class RucniUseky(unittest.TestCase):
    def test_oznaceni_bez_nove_analyzy_a_zruseni(self):
        cesta, hranice = nahravka()
        v = analyzuj_stranu(cesta, 1)
        self.assertEqual([s.nazev for s in v.soubory], ["PRVNI", "DRUHY"])
        druhy = v.soubory[1]
        oznac_usek(v.strana, druhy.zacatek - 0.2, druhy.konec + 0.2, "hudba")
        uplatni_rucni_useky(v)
        self.assertEqual([s.nazev for s in v.soubory], ["PRVNI"])
        radky = [(z.nazev, z.typ, z.rucni_usek) for z in v.strana.zaznamy]
        self.assertIn(("(hudba)", "Audio", True), radky)
        self.assertNotIn("DRUHY", [n for n, _, _ in radky])
        self.assertTrue(any(o.rucni and o.nazev == "hudba" for o in v.oblasti))
        # zrušení: úsek se vrátí jako nerozpoznaný (program najde až nová analýza)
        oznac_usek(v.strana, druhy.zacatek - 0.2, druhy.konec + 0.2, "")
        uplatni_rucni_useky(v)
        self.assertEqual(v.strana.rucni_useky, [])
        self.assertFalse(any(z.rucni_usek for z in v.strana.zaznamy))
        self.assertTrue(any(z.nerozpoznano and (z.cas_od or 0) >= hranice - 1 for z in v.strana.zaznamy))

    def test_oznaceni_presahujici_na_program_ho_nezmeni(self):
        """Výběr od začátku přes celý druhý program: přeznačí se jen nerozpoznaná část, programy zůstanou
        (i po nové analýze)."""
        cesta, hranice = nahravka()
        v = analyzuj_stranu(cesta, 1)
        prvni, druhy = v.soubory
        oznac_usek_vysledku(v, 0.0, v.nahravka.delka, "šum")
        uplatni_rucni_useky(v)
        self.assertEqual([s.nazev for s in v.soubory], ["PRVNI", "DRUHY"])
        for r in v.strana.rucni_useky:
            for s in (prvni, druhy):
                self.assertTrue(r.konec <= s.zacatek - 0.99 or r.zacatek >= s.konec + 0.49, (r, s.zacatek, s.konec))
        v2 = analyzuj_stranu(cesta, 1, rucni_useky=v.strana.rucni_useky)
        self.assertEqual([s.nazev for s in v2.soubory], ["PRVNI", "DRUHY"])
        self.assertTrue(all(s.ok for s in v2.soubory))
        # výběr celý na programu (klik na program) program označí
        oznac_usek_vysledku(v, druhy.zacatek + 0.5, druhy.konec - 0.5, "hudba")
        uplatni_rucni_useky(v)
        self.assertEqual([s.nazev for s in v.soubory], ["PRVNI"])

    def test_analyza_vynecha_oznacene(self):
        cesta, hranice = nahravka()
        delka = analyzuj_stranu(cesta, 1).nahravka.delka
        v = analyzuj_stranu(cesta, 1, rucni_useky=[RucniUsek(hranice, delka, "řeč")])
        self.assertEqual([s.nazev for s in v.soubory], ["PRVNI"])
        self.assertEqual(v.strana.rucni_useky, [RucniUsek(hranice, delka, "řeč")])
        self.assertEqual([z.nazev for z in v.strana.zaznamy if z.rucni_usek], ["(řeč)"])
        # nic jiného (nerozpoznaný kus) z označeného místa nezbylo
        self.assertFalse(any(z.nerozpoznano and not z.rucni_usek and (z.cas_do or 0) > hranice + 0.1
                             for z in v.strana.zaznamy))

    def test_oznaceni_prekryva_starsi(self):
        from sakra.jadro.model import Strana
        s = Strana(1)
        oznac_usek(s, 10, 20, "šum")
        oznac_usek(s, 15, 30, "hudba")
        self.assertEqual(s.rucni_useky, [RucniUsek(10, 15, "šum"), RucniUsek(15, 30, "hudba")])
        oznac_usek(s, 12, 13, "")
        self.assertEqual(s.rucni_useky, [RucniUsek(10, 12, "šum"), RucniUsek(13, 15, "šum"), RucniUsek(15, 30, "hudba")])

    def test_projekt_a_volba_druhu(self):
        cesta, hranice = nahravka()
        v = analyzuj_stranu(cesta, 1, rucni_useky=[RucniUsek(0.0, 0.3, "šum")])
        k = Kazeta()
        k.strany.append(v.strana)
        k2 = kazeta_z_json(json.loads(json.dumps(kazeta_do_json(k), ensure_ascii=False)))
        self.assertEqual(k2.strany[0].rucni_useky, [RucniUsek(0.0, 0.3, "šum")])
        self.assertTrue(any(z.rucni_usek and z.nazev == "(šum)" for z in k2.strany[0].zaznamy))
        z = next(z for z in v.strana.zaznamy if z.soubor is None and not z.rucni_usek) \
            if any(z.soubor is None and not z.rucni_usek for z in v.strana.zaznamy) else None
        from sakra.jadro.model import Zaznam
        z = z or Zaznam(nazev="(nerozpoznáno)", nerozpoznano=True)
        urci_platformu(z, "žádná data – řeč")
        self.assertEqual((z.typ, z.nazev), ("Audio", "(řeč)"))
        urci_platformu(z, "(neznámá)")
        self.assertEqual((z.typ, z.nazev), ("Data", "(nerozpoznáno)"))


if __name__ == "__main__":
    unittest.main()
