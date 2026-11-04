"""Skutečná nahrávka ZX Spectra (kazeta RH07860), je-li v projektu: bloky se musí shodovat s TZX,
které ze stejné kazety vyrobil jiný (ověřený) převodník."""
import unittest
from pathlib import Path

from sakra.jadro.analyza import analyzuj_stranu

ADR = Path(__file__).resolve().parents[1] / "skills" / "testdata" / "RH07860_v1" / "RH07860"


def bloky_tzx(cesta: Path) -> list[bytes]:
    d = cesta.read_bytes()
    out, i = [], 10
    while i < len(d):
        assert d[i] == 0x10, "čekám jen standardní bloky"
        n = int.from_bytes(d[i + 3:i + 5], "little")
        out.append(d[i + 5:i + 5 + n])
        i += 5 + n
    return out


@unittest.skipUnless((ADR / "RH07860 (A).wav").exists(), "chybí testovací data RH07860")
class RH07860(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref = {b for t in ADR.glob("side_*/*/*.tzx") for b in bloky_tzx(t)}
        cls.a = analyzuj_stranu(ADR / "RH07860 (A).wav", 1)
        cls.b = analyzuj_stranu(ADR / "RH07860 (B).wav", 2)

    def test_strana_a(self):
        # 2× „video“ (18 135 B, plovoucí nula – dřív se blok utrhl) + „h.c.“
        self.assertEqual([s.nazev for s in self.a.soubory], ["video", "video"])
        self.assertTrue(all(s.kompletni for s in self.a.soubory))
        bloky = [b for s in self.a.soubory for b in s.bloky]
        self.assertEqual(len(bloky), 8)
        self.assertTrue(all(b.data in self.ref for b in bloky))

    def test_strana_b(self):
        # vše kromě posledního programu (Receptar29 – nahrávka končí uprostřed dat)
        sb = self.b.soubory
        self.assertEqual(sb[-1].nazev, "Receptar29")
        self.assertFalse(sb[-1].kompletni)
        bloky = [b for s in sb[:-1] for b in s.bloky]
        self.assertTrue(all(b.ok for b in bloky))
        self.assertEqual(len(bloky), 22)
        # hlavička „b“ první kopie: úvodní tón přerušený zkreslenou půlvlnou
        self.assertIn(b"\x00\x02b         ", [b.data[:12] for b in bloky])
        jine = [b for b in bloky if b.data not in self.ref]
        self.assertEqual([b.data[2:12] for b in jine], [b"font      ", b"h.c.      "])   # hlavičky jiné kopie


if __name__ == "__main__":
    unittest.main()
