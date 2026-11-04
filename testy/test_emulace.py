"""Snímky ZX Spectra z emulátoru (balíček zx): nahrávací obrazovka a obrazovka po spuštění."""
import struct
import tempfile
import unittest
from pathlib import Path

from sakra.jadro.model import Soubor
from sakra.platformy import zx_emulace
from sakra.platformy.zx import dokonci_program, nahled_programu, zapis_snimky
from testy.test_zx import basic_radek, blok

PRG = (basic_radek(10, b"\xef\"\"\xaa") + basic_radek(20, b"\xef\"\"\xaf")
       + basic_radek(30, b"\xf9\xc032768\x0e\x00\x00\x00\x80\x00"))
SCR = bytes((x * 7) & 0xFF for x in range(6144)) + bytes(((i % 8) | 0x38) for i in range(768))
# kód: vyplní bitmapu obrazovky vzorem 55h a zastaví se (DI, HALT)
KOD = bytes([0x21, 0x00, 0x40, 0x11, 0x01, 0x40, 0x01, 0xFF, 0x17, 0x36, 0x55, 0xED, 0xB0, 0xF3, 0x76]) + bytes(185)
BLOKY = [blok(0, bytes([0]) + b"HRA       " + struct.pack("<HHH", len(PRG), 10, len(PRG))), blok(255, PRG),
         blok(0, bytes([3]) + b"scr       " + struct.pack("<HHH", 6912, 16384, 32768)), blok(255, SCR),
         blok(0, bytes([3]) + b"kod       " + struct.pack("<HHH", len(KOD), 32768, 32768)), blok(255, KOD)]


@unittest.skipIf(zx_emulace.k_dispozici(), "emulátor ZX (balíček zx) není k dispozici")
class Emulace(unittest.TestCase):
    def test_rychle_nahrani(self):
        r = zx_emulace.spust(BLOKY, None, sekund_po=1.0)
        self.assertEqual(r["zpusob"], "rychlé nahrání (ROM)")
        self.assertEqual(r["nahravaci"], SCR)
        self.assertEqual(r["po_spusteni"][:6144], b"\x55" * 6144)

    def test_emulace_pasky(self):
        rom = {"pilot": 619, "pilot_pocet": 3223, "sync": [190, 210], "nula": 244, "jedna": 489}
        r = zx_emulace.spust(BLOKY, [None] * 5 + [rom], sekund_po=1.0)
        self.assertEqual(r["zpusob"], "emulace pásky (turbo)")
        self.assertEqual(r["nahravaci"], SCR)
        self.assertEqual(r["po_spusteni"][:6144], b"\x55" * 6144)

    def test_nahled_a_png(self):
        from sakra.jadro.model import Blok
        s = Soubor("zx-rom", "", "", "", bloky=[Blok(0, 1, "hlavička" if b[0] == 0 else "data", None, b, True)
                                               for b in BLOKY])
        dokonci_program(s)
        self.assertEqual(nahled_programu(s)["emulace"], "lze")
        tmp = Path(tempfile.mkdtemp())
        vystup = zapis_snimky(s, tmp / "hra")
        self.assertEqual([p.name for p in vystup], ["hra (po spuštění).png"])   # nahrávací je z bloku SCREEN$
        n = nahled_programu(s)
        self.assertEqual(n["emulace"], "hotovo")
        self.assertEqual([p for p, _ in n["obrazky"]][-1].split(" (")[0], "Po spuštění")


class Export(unittest.TestCase):
    """Celý balíček z nahrávky Spectra (JSON projektu musí zvládnout i data bloků ZX)."""

    def test_balicek(self):
        import json
        from sakra.balicek import exportuj
        from sakra.jadro.model import Kazeta, kazeta_do_json
        from sakra.platformy.zx import pulzy_z_bloku
        from sakra.projekt import zpracuj
        from testy.signal import signal_z_pulzu, uloz_wav
        tmp = Path(tempfile.mkdtemp())
        uloz_wav(tmp / "HH00100 (1).wav", signal_z_pulzu(pulzy_z_bloku(BLOKY), 44100), 44100)
        k = Kazeta()
        v = zpracuj(k, {1: tmp / "HH00100 (1).wav"})
        json.dumps(kazeta_do_json(k))
        d = exportuj(k, tmp / "archiv", v, kopirovat_zdroj=False, pdf=False,
                     snimky=not zx_emulace.k_dispozici())
        jmena = {p.name for p in d.iterdir()}
        self.assertTrue({"HH00100.json", "SHA1SUMS", "1-01 HRA.tzx", "1-01 HRA (nahrávací obrazovka).png"} <= jmena)
        if not zx_emulace.k_dispozici():
            self.assertIn("1-01 HRA (po spuštění).png", jmena)


if __name__ == "__main__":
    unittest.main()
