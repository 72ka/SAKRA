import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from sakra.formaty import tzx
from sakra.jadro.analyza import analyzuj_stranu
from sakra.platformy.zx import ZXSpectrum, pulzy_z_bloku
from testy.signal import signal_z_pulzu, uloz_wav


def blok(flag: int, data: bytes) -> bytes:
    b = bytes([flag]) + data
    x = 0
    for v in b:
        x ^= v
    return b + bytes([x])


class ZX(unittest.TestCase):
    def test_hlavicka_a_data(self):
        tmp = Path(tempfile.mkdtemp())
        data = np.random.default_rng(7).integers(0, 256, 1500, dtype=np.uint8).tobytes()
        hl = blok(0, bytes([3]) + b"MANIC     " + struct.pack("<HHH", len(data), 32768, 32768))
        dat = blok(255, data)
        for r in (0.92, 1.0, 1.08):
            with self.subTest(rychlost=r):
                uloz_wav(tmp / "zx.wav", signal_z_pulzu(pulzy_z_bloku([hl, dat], 44100, r), 44100), 44100)
                v = analyzuj_stranu(tmp / "zx.wav", 1)
                self.assertEqual(len(v.soubory), 1)
                s = v.soubory[0]
                self.assertEqual((s.nazev, s.stav, s.typ_bloku), ("MANIC", "ok", "Bytes"))
                self.assertEqual(s.info["adresa"], 32768)
                ZXSpectrum().zapis(s, tmp / "manic")
                self.assertEqual(tzx.nacti_tzx(tmp / "manic.tzx"), [hl, dat])
                self.assertEqual(tzx.nacti_tap(tmp / "manic.tap"), [hl, dat])

    def test_plovouci_nula_a_vypadek_pilotu(self):
        """Střed signálu se posouvá (průchody nulou se ztrácejí) a úvodní tón má těsně před koncem
        zkreslenou půlvlnu – jako na skutečné kazetě RH07860."""
        tmp = Path(tempfile.mkdtemp())
        rate = 44100
        data = np.random.default_rng(7).integers(0, 256, 3000, dtype=np.uint8).tobytes()
        hl = blok(0, bytes([3]) + b"PLAVE     " + struct.pack("<HHH", len(data), 32768, 32768))
        dat = blok(255, data)
        pz = pulzy_z_bloku([hl, dat], rate)
        i = 1 + 8063 - 150                        # 150 půlvln před koncem tónu (zbytek je kratší než MIN_PILOT)
        pz[i] = int(pz[i] * 0.7)
        x = signal_z_pulzu(pz, rate)
        t = np.arange(len(x)) / rate
        x += (0.7 * np.sin(2 * np.pi * 7 * t) * (np.abs(x) > 0.05)).astype(np.float32)
        uloz_wav(tmp / "zx.wav", x, rate)
        v = analyzuj_stranu(tmp / "zx.wav", 1)
        self.assertEqual([(s.nazev, s.stav) for s in v.soubory], [("PLAVE", "opraveno")])
        self.assertEqual([b.data for b in v.soubory[0].bloky], [hl, dat])
        self.assertIn("plovoucí střed", v.soubory[0].bloky[1].oprava)

    def test_ondra_neni_zx(self):
        from testy.signal import pulzy_tesla, soubor_tesla
        tmp = Path(tempfile.mkdtemp())
        uloz_wav(tmp / "o.wav", signal_z_pulzu(pulzy_tesla(soubor_tesla(b"X", b"\xf6" * 300), 44100), 44100), 44100)
        v = analyzuj_stranu(tmp / "o.wav", 1)
        self.assertEqual([s.platforma for s in v.soubory], ["ondra-tesla"])


if __name__ == "__main__":
    unittest.main()


def basic_radek(n: int, telo: bytes) -> bytes:
    return struct.pack(">H", n) + struct.pack("<H", len(telo) + 1) + telo + b"\r"


class Program(unittest.TestCase):
    """Zavaděč v BASICu + obrazovka + kód bez hlavičky + turbo blok = jeden program."""

    def test_cely_program(self):
        from sakra.platformy import podle_id
        from testy.signal2 import pulzy_pwm
        tmp = Path(tempfile.mkdtemp())
        prg = (basic_radek(10, b"\xfd24999\x0e\x00\x00\xa7\x61\x00") + basic_radek(20, b"\xef\"\"\xaa")
               + basic_radek(30, b"\xf9\xc025000\x0e\x00\x00\xa8\x61\x00"))
        obr = np.random.default_rng(3).integers(0, 256, 6912, dtype=np.uint8).tobytes()
        kod = np.random.default_rng(4).integers(0, 256, 3000, dtype=np.uint8).tobytes()
        turbo = np.random.default_rng(5).integers(0, 256, 4000, dtype=np.uint8).tobytes()
        bloky_rom = [blok(0, bytes([0]) + b"HRA       " + struct.pack("<HHH", len(prg), 10, len(prg))), blok(255, prg),
                     blok(0, bytes([3]) + b"obrazovka " + struct.pack("<HHH", 6912, 16384, 32768)), blok(255, obr),
                     blok(255, kod)]
        dalsi = [blok(0, bytes([0]) + b"DALSI     " + struct.pack("<HHH", len(prg), 0x8000, len(prg))), blok(255, prg)]
        pulzy = (pulzy_z_bloku(bloky_rom) + pulzy_pwm([blok(255, turbo)], 420, 2000, [150, 160], 140, 280)
                 + pulzy_z_bloku(dalsi))
        uloz_wav(tmp / "zx.wav", signal_z_pulzu(pulzy, 44100), 44100)
        v = analyzuj_stranu(tmp / "zx.wav", 1)
        self.assertEqual([(s.nazev, s.platforma, len(s.bloky), s.stav) for s in v.soubory],
                         [("HRA", "zx-turbo", 6, "ok"), ("DALSI", "zx-rom", 2, "ok")])
        s = v.soubory[0]
        self.assertEqual(len(s.info["casti"]), 4)
        self.assertEqual(len(v.strana.zaznamy), 2)                  # v tabulce jeden řádek na program
        vystup = podle_id(s.platforma).zapis(s, tmp / "hra")
        self.assertEqual([p.suffix for p in vystup], [".tzx", ".png"])  # s turbo blokem TAP nevznikne
        d = vystup[0].read_bytes()
        self.assertEqual(tzx.nacti_tzx(vystup[0]), bloky_rom + [blok(255, turbo)])
        self.assertEqual(d.count(b"\x10\xe8\x03"), 5)                 # 5 standardních bloků (pauza 1000 ms)
        n = podle_id(s.platforma).nahled(s)
        self.assertEqual(len(n["obrazky"]), 1)
        self.assertEqual(n["texty"][0][1].splitlines(),
                         ["  10 CLEAR 24999", '  20 LOAD "" SCREEN$', "  30 RANDOMIZE USR 25000"])
