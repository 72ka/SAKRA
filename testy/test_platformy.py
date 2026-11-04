"""Dekódování syntetických nahrávek všech platforem a kontrola výstupních souborů."""
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from sakra.formaty import ptp, tzx
from sakra.jadro.analyza import analyzuj_stranu
from sakra.platformy import podle_id
from testy import signal2 as g
from testy.signal import blok_tesla, pulzy_tesla, signal_z_pulzu, uloz_wav


def nahodna(n: int, seed: int = 5, nejvic: int = 256) -> bytes:
    return np.random.default_rng(seed).integers(0, nejvic, n, dtype=np.uint8).tobytes()


class Zaklad(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def analyzuj(self, pulzy, rate=44100, sum_=0.02):
        uloz_wav(self.tmp / "t.wav", signal_z_pulzu(pulzy, rate, sum_=sum_), rate)
        return analyzuj_stranu(self.tmp / "t.wav", 1)

    def jeden(self, v, platforma: str):
        self.assertEqual([s.platforma for s in v.soubory], [platforma], [(s.platforma, s.nazev) for s in v.soubory])
        return v.soubory[0]

    def zapis(self, s):
        return podle_id(s.platforma).zapis(s, self.tmp / "vystup")


class PMD(Zaklad):
    def test_pmd85(self):
        data = nahodna(700)
        hl, telo = g.pmd_hlavicka(0, ">", 0x2401, data, b"HRA"), g.pmd_telo(data)
        for r in (0.93, 1.0, 1.07):
            with self.subTest(rychlost=r):
                s = self.jeden(self.analyzuj(g.pulzy_pmd([hl, telo], rychlost=r)), "pmd85")
                self.assertEqual((s.nazev, s.stav, s.info["adresa"]), ("HRA", "ok", 0x2401))
                self.assertTrue(s.typ_bloku.startswith("> BASIC"))
                vystup = self.zapis(s)
                self.assertEqual(ptp.nacti(vystup[0]), [hl, telo])
                self.assertEqual(vystup[1].read_bytes(), data)

    def test_pmd85_posunute_nabehy(self):
        """Kazeta goldstar_HD90: náběžné hrany po dlouhé nule přicházejí o ~0,55 půlbitu dřív (pomalý náběh
        po pásce), dlouhá půlvlna vypadá jako krátká. Sestupné hrany drží mřížku -> náběžné se dopočtou."""
        data = nahodna(700, seed=4)
        hl, telo = g.pmd_hlavicka(1, ">", 0x2401, data, b"KVAD.FUN"), g.pmd_telo(data)
        pulzy = list(g.pulzy_pmd([hl, telo]))
        T = 44100 / 2400
        for i in range(2, len(pulzy) - 1, 2):            # liché běhy = horní úroveň, sudé = dolní
            if 1.6 * T < pulzy[i] < 2.4 * T:
                posun = int(0.55 * T)
                pulzy[i] -= posun
                pulzy[i + 1] += posun
        s = self.jeden(self.analyzuj(pulzy), "pmd85")
        self.assertEqual((s.nazev, s.stav), ("KVAD.FUN", "ok"))
        self.assertEqual(self.zapis(s)[1].read_bytes(), data)

    def test_pmd85_nestandardni_blok(self):
        data = nahodna(300)
        dohravka = nahodna(500, seed=9)
        s = self.jeden(self.analyzuj(g.pulzy_pmd([g.pmd_hlavicka(1, "?", 0x8000, data, b"LOADER"),
                                                   g.pmd_telo(data), dohravka])), "pmd85")
        self.assertEqual([b.typ for b in s.bloky], ["hlavička", "data", "nestandardní"])
        self.assertEqual(s.bloky[2].data, dohravka)
        self.assertEqual(s.stav, "neověřeno")

    def test_mato(self):
        data = bytes([0x12]) + nahodna(400)
        s = self.jeden(self.analyzuj(g.pulzy_mato(3, b"MATO", data)), "mato")
        self.assertEqual((s.nazev, s.stav), ("MATO", "ok"))
        bloky = ptp.nacti(self.zapis(s)[0])
        self.assertEqual(len(bloky[0]), 63)
        self.assertEqual(bloky[0][:47], bytes([0xFF] * 16 + [0] * 16 + [0x55] * 15))
        self.assertEqual(bloky[1][:-1], data)


class IQ(Zaklad):
    def test_standardni(self):
        data = nahodna(64)
        radky = [g.iq_radek(0x0400 + i, 0, data[i:i + 16]) for i in range(0, 64, 16)] + [g.iq_radek(0x0400, 1, b"")]
        s = self.jeden(self.analyzuj(g.pulzy_iq151(radky)), "iq151")
        self.assertEqual((s.stav, s.typ_bloku), ("ok", "Intel HEX"))
        self.assertEqual(self.zapis(s)[0].read_bytes().decode("ascii").split("\r\n")[:-1], radky)

    def test_komenium(self):
        zavadec = [g.iq_radek(0x7934, 0, b"\x31\x00\x80\xc3\x34\x79"), g.iq_radek(0x7934, 1, b"")]
        obr, prg = nahodna(300, 1), nahodna(900, 2)
        s = self.jeden(self.analyzuj(g.pulzy_iq151(zavadec, [(0xEC00, obr, 0x0000), (0x0300, prg, 0x0300)])),
                       "iq151")
        self.assertEqual((s.stav, s.typ_bloku, s.info["typ_komenia"]), ("ok", "Komenium", 1))
        hexy = self.zapis(s)[0].read_text().splitlines()
        self.assertEqual(hexy[-1], ":00030001FC")          # konec se startovní adresou 0300h
        obsah = b"".join(bytes.fromhex(r[9:-2]) for r in hexy[:-1])
        self.assertEqual(obsah, obr + bytes([0xED, 0x2C, 0, 0]) + prg + bytes([0x06, 0x84, 0x03, 0x00]))


class SAPI(Zaklad):
    def test_sapi1_text(self):
        jm = bytes(c - 0x40 if 0x41 <= c <= 0x5A else c for c in b"PROGRAM")      # kód MHB2501
        text = b"10 PRINT 'AHOJ'\r\n" * 30
        bloky = [blok_tesla(0x01, jm + b" DLOUHY NAZEV", jm, 1, 7)]
        kusy = [text[i:i + 255] for i in range(0, len(text), 255)]
        for i, k in enumerate(kusy):
            bloky.append(blok_tesla(0x41, k + (b"\x1a" if i == len(kusy) - 1 else b""), jm, i + 2, 7))
        bloky.append(blok_tesla(0x04, b"\x1a", jm, len(kusy) + 2, 7))
        s = self.jeden(self.analyzuj(pulzy_tesla(bloky)), "sapi1-mikos")
        self.assertEqual((s.nazev_bloku, s.stav, s.typ_bloku, s.info["cislo_souboru"]),
                         ("PROGRAM", "ok", "Text (ASCII)", 7))
        vystup = self.zapis(s)
        self.assertEqual(vystup[1].suffix, ".txt")
        self.assertEqual(vystup[1].read_bytes(), text)


class ZX81(Zaklad):
    def test_rom(self):
        data = g.zx81_p(600)
        s = self.jeden(self.analyzuj(g.pulzy_zx81(b"\x38\x2a\x37", data)), "zx81")
        self.assertEqual((s.nazev, s.stav), ("SER", "neověřeno"))
        self.assertEqual(self.zapis(s)[0].read_bytes(), data)

    def test_fastsaver(self):
        data = g.zx81_p(900, seed=8)
        s = self.jeden(self.analyzuj(g.pulzy_zx81_fast(data)), "zx81")
        self.assertEqual((s.stav, s.info["turbo"]), ("neověřeno", "FASTSAVER"))
        self.assertEqual(self.zapis(s)[0].read_bytes(), data)


class C64(Zaklad):
    def test_prg(self):
        data = nahodna(1000)
        hl = g.c64_hlavicka(3, 0x0801, data, b"GAME")
        for r in (0.95, 1.0, 1.05):
            with self.subTest(rychlost=r):
                s = self.jeden(self.analyzuj(g.pulzy_c64(hl, data, rychlost=r)), "c64-rom")
                self.assertEqual((s.nazev, s.stav, s.info["adresa"]), ("GAME", "ok", 0x0801))
                vystup = self.zapis(s)
                self.assertEqual(vystup[0].read_bytes()[:12], b"C64-TAPE-RAW")
                self.assertEqual(vystup[1].read_bytes(), b"\x01\x08" + data)


class FSK(Zaklad):
    def test_msx_binarni(self):
        data = struct.pack("<HHH", 0xC000, 0xC000 + 499, 0xC000) + nahodna(500)
        s = self.jeden(self.analyzuj(g.pulzy_msx([b"\xd0" * 10 + b"GAME  ", data])), "msx")
        self.assertEqual((s.nazev, s.stav, s.typ_bloku), ("GAME", "neověřeno", "Binární"))
        cas = self.zapis(s)[0].read_bytes()
        self.assertEqual(cas[:8], bytes([0x1F, 0xA6, 0xDE, 0xBA, 0xCC, 0x13, 0x7D, 0x74]))
        self.assertEqual(cas.count(cas[:8]), 2)
        self.assertTrue(cas.endswith(data))

    def test_acorn(self):
        data = nahodna(600)
        bloky = [g.acorn_blok(b"ELITE", i, data[i * 256:(i + 1) * 256], i == 2) for i in range(3)]
        s = self.jeden(self.analyzuj(g.pulzy_acorn(bloky)), "acorn")
        self.assertEqual((s.nazev, s.stav, len(s.bloky)), ("ELITE", "ok", 3))
        uef, binar = self.zapis(s)
        self.assertTrue(uef.read_bytes().startswith(b"UEF File!\0"))
        self.assertEqual(binar.read_bytes(), data)

    def test_oric(self):
        data = nahodna(400)
        obsah = g.oric_tap(0x80, 0x0500, data, b"ZORGON")
        s = self.jeden(self.analyzuj(g.pulzy_oric(obsah)), "oric")
        self.assertEqual((s.nazev, s.stav, s.info["adresa"]), ("ZORGON", "neověřeno", 0x0500))
        self.assertEqual(self.zapis(s)[0].read_bytes(), b"\x16\x16\x16\x24" + obsah)


class Atari(Zaklad):
    def test_standardni(self):
        data = b"\xff\xff\x00\x20\x7f\x21" + nahodna(300)
        for rate in (44100, 96000):
            with self.subTest(rate=rate):
                s = self.jeden(self.analyzuj(g.signal_atari(g.atari_zaznamy(data), rate), rate), "atari-rom")
                self.assertEqual((s.stav, s.typ_bloku), ("ok", "Binární (XEX)"))
                cas, xex = self.zapis(s)
                self.assertEqual(cas.read_bytes()[:4], b"FUJI")
                self.assertEqual(xex.read_bytes(), data)


class PWM(Zaklad):
    @staticmethod
    def _xor(b: bytes) -> bytes:
        x = 0
        for v in b:
            x ^= v
        return b + bytes([x])

    def test_zx_turbo(self):
        data = nahodna(2000)
        hl = self._xor(b"\x00\x03" + b"TURBOHRA  " + struct.pack("<HHH", len(data), 40000, 32768))
        dat = self._xor(b"\xff" + data)
        s = self.jeden(self.analyzuj(g.pulzy_pwm([hl, dat], 420, 2000, [150, 160], 140, 280)), "zx-turbo")
        self.assertEqual((s.nazev, s.stav, s.info["adresa"]), ("TURBOHRA", "ok", 40000))
        vystup = self.zapis(s)
        self.assertEqual(tzx.nacti_tzx(vystup[0]), [hl, dat])

    def test_turbo2000(self):
        data = nahodna(1500)
        hl = self._xor(b"\x00\x04" + b"FRED      " + struct.pack("<HHH", 0x2000, 0x2000, len(data)))
        dat = self._xor(b"\xff" + data)
        s = self.jeden(self.analyzuj(g.pulzy_pwm([hl, dat], 600, 600, [100, 100], 147, 293)), "atari-t2k")
        self.assertEqual((s.nazev, s.stav, s.typ_bloku), ("FRED", "ok", "Binární soubor"))
        self.assertEqual(podle_id(s.platforma).turbo(s), "T2K")
        cas, binar = self.zapis(s)
        self.assertEqual(cas.read_bytes()[:4], b"FUJI")
        self.assertEqual(binar.read_bytes(), data)

    def test_cpc(self):
        data = nahodna(700)
        h = (b"DIZZY".ljust(16, b"\0") + bytes([1, 0xFF, 2]) + struct.pack("<HH", len(data), 0x4000)
             + bytes([0xFF]) + struct.pack("<HH", len(data), 0x4000)).ljust(64, b"\0")
        bloky = [g.cpc_zaznam(0x2C, h), g.cpc_zaznam(0x16, data)]
        s = self.jeden(self.analyzuj(g.pulzy_pwm(bloky, 667, 4096, [333, 333], 333, 667, trailer=32)), "cpc")
        self.assertEqual((s.nazev, s.stav, s.typ_bloku), ("DIZZY", "ok", "Binární"))
        cdt, binar = self.zapis(s)
        self.assertEqual([b[:-4] for b in tzx.nacti_tzx(cdt)], bloky)
        self.assertEqual(binar.read_bytes(), data)


class Sharp(Zaklad):
    def test_mzf(self):
        data = nahodna(800)
        h = (bytes([1]) + b"SHARPGAME\r".ljust(17, b"\r") + struct.pack("<HHH", len(data), 0x1200, 0x1200)).ljust(128, b"\0")
        s = self.jeden(self.analyzuj(g.pulzy_mz(h, data)), "sharp-mz")
        self.assertEqual((s.nazev, s.stav, s.info["adresa"]), ("SHARPGAME", "ok", 0x1200))
        self.assertEqual(self.zapis(s)[0].read_bytes(), h + data)


if __name__ == "__main__":
    unittest.main()
