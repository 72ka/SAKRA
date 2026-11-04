"""POTAS (ČSLA, VAAZ Brno): synchronní záznam – buňka ~204 µs, puls = 0, bajty od LSB, synchronizace FC 7E AA."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from sakra.jadro.analyza import analyzuj_stranu
from sakra.platformy.potas import POTAS, text_potas
from testy.signal import uloz_wav

RATE = 44100
ADR = Path(__file__).resolve().parents[1] / "skills" / "testdata" / "nezname_kazety_pwramp"


def potas(data: bytes, uvod_s: float = 1.0) -> np.ndarray:
    """Bit 0 = jeden kmit v buňce (nahoru, dolů), bit 1 = klid – bez stejnosměrné složky jako na pásce."""
    bunka = 204.4e-6 * RATE
    bity = [0] * int(uvod_s / 204.4e-6)
    for b in b"\xfc\x7e\xaa" + data:
        bity += [(b >> i) & 1 for i in range(8)]
    bity += [1] * 200
    x = np.zeros(int(len(bity) * bunka) + 10, np.float32)
    pul = int(bunka / 2)
    for i, bit in enumerate(bity):
        if bit == 0:
            a = int(round(i * bunka))
            x[a:a + pul] = 0.6
            x[a + pul:a + 2 * pul] = -0.6
    return x


class Potas(unittest.TestCase):
    def test_tri_kopie_vetsina(self):
        tmp = Path(tempfile.mkdtemp())
        # bez délky na pásce: jedničky na konci dat nejdou odlišit od ticha – data končí běžným bajtem
        program = (b"TEST\x00" + bytes([0x0A, 0x41, 0x0A, 0x00, 0x8E]) + b" ZKUSEBNI PROGRAM" + bytes(range(256)) * 4
                   + b"\x00KONEC\x00")
        vadny = bytearray(program)
        vadny[300] ^= 0x10                                         # převrácený bit v jedné kopii
        ticho = np.zeros(RATE, np.float32)
        x = np.concatenate([ticho, potas(program), ticho, potas(bytes(vadny)), ticho, potas(program), ticho])
        uloz_wav(tmp / "p.wav", x, RATE)
        v = analyzuj_stranu(tmp / "p.wav", 1, polarita="normalni")
        p = [s for s in v.soubory if s.platforma == "potas"]
        self.assertEqual([(s.nazev, s.typ_bloku) for s in p], [("TEST", "BASIC")] * 3)
        self.assertTrue(all(s.bloky[0].data[:len(program)] == program for s in p))
        self.assertTrue(all(s.overeno for s in p))
        self.assertIn("většina", p[1].bloky[0].oprava)

    def test_dve_kopie_chybejici_puls(self):
        """Výpadek signálu = chybějící puls (bit 0 přečtený jako 1): u dvou kopií vyhrává puls."""
        tmp = Path(tempfile.mkdtemp())
        program = b"DVE\x00" + bytes(range(1, 255)) * 2 + b"\x00KONEC\x00"
        vadny = bytearray(program)
        i = next(k for k in range(200, 300) if not program[k] & 0x10)
        vadny[i] |= 0x10                                           # chybějící puls ve 4. bitu
        ticho = np.zeros(RATE, np.float32)
        uloz_wav(tmp / "d.wav", np.concatenate([ticho, potas(bytes(vadny)), ticho, potas(program), ticho]), RATE)
        v = analyzuj_stranu(tmp / "d.wav", 1, polarita="normalni")
        p = [s for s in v.soubory if s.platforma == "potas"]
        self.assertEqual(len(p), 2)
        self.assertTrue(all(s.bloky[0].data[:len(program)] == program for s in p))
        self.assertIn("chybějící pulzy", p[0].bloky[0].oprava)

    def test_edis_text(self):
        tmp = Path(tempfile.mkdtemp())
        hlavicka = b"\x00\x9d\x01\xdc\x68[1] man TEST\r"
        text = "Úvod do editoru: kurzor na začátek řádku, výmaz posledního znaku.\r".encode("latin1", "replace")
        text = bytes({ord("č"): 0x97, ord("ř"): 0x9C, ord("á"): 0x87, ord("ý"): 0x8D, ord("í"): 0x89,
                      ord("ě"): 0x99}.get(ord(c), ord(c)) for c in "kurzor na začátek řádku, výmaz posledního znaku.\r")
        ticho = np.zeros(RATE // 2, np.float32)
        uloz_wav(tmp / "e.wav", np.concatenate([ticho, potas(hlavicka), ticho, potas(text * 20), ticho]), RATE)
        v = analyzuj_stranu(tmp / "e.wav", 1, polarita="normalni")
        p = [s for s in v.soubory if s.platforma == "potas"]
        self.assertEqual([(s.nazev, s.typ_bloku, len(s.bloky)) for s in p], [("[1] man TEST", "Text (EDIS)", 2)])
        self.assertIn("začátek řádku", text_potas(p[0].bloky[-1].data))
        vystup = POTAS().zapis(p[0], tmp / "man")
        self.assertIn("výmaz posledního", (tmp / "man.txt").read_text(encoding="utf-8"))
        self.assertEqual([f.suffix for f in vystup], [".bin", ".txt"])

    def test_vypis_basic(self):
        from sakra.platformy.potas import vypis_basic
        prog = (b"SKLAD\x00" + b"\x10\x41\x0a\x00\x8e UDRZBA SKLADU\x00"
                + b"\x20\x41\x14\x00\x81I\xc01\xb210:\x95\"P\x93IKLAD\":\x82I\x00" + b"\x00\x00")
        self.assertEqual(vypis_basic(prog), '10 REM UDRZBA SKLADU\n20 FOR I=1 TO 10: PRINT "PŘIKLAD": NEXT I')

    @unittest.skipUnless((ADR / "emgeton_c60_A.wav").exists(), "chybí nahrávka POTAS")
    def test_skutecna_nahravka(self):
        v = analyzuj_stranu(ADR / "emgeton_c60_A.wav", 1)
        jmena = {s.nazev for s in v.soubory if s.platforma == "potas"}
        for j in ("viCALC", "PHMKOHUT", "EKV", "RP", "PHMR", "SKLAD", "ZTRSKO", "MUNI", "TVMAT", "SKODYSP",
                  "[4] man PASCAL"):
            self.assertIn(j, jmena)
        vicalc = [s for s in v.soubory if s.nazev == "viCALC"]
        self.assertEqual(len(vicalc), 3)
        self.assertEqual(vicalc[0].info["spusteni"], "startIA800,GEFE0,G6020")


if __name__ == "__main__":
    unittest.main()
