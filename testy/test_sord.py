"""Sord m5: syntetický signál podle MAME/z88dk, součty, úplnost a export."""
import hashlib
import os
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from sakra.jadro.analyza import CHYBY_DEKODERU, analyzuj_stranu, znovu_dekoduj_blok
from sakra.jadro.model import Kazeta, Nosna, Strana, Zaznam, kazeta_do_json, kazeta_z_json
from sakra.jadro.pulzy import Pulzy, Usek
from sakra.platformy import POCITACE, RUCNI, bloky_pro_zobrazeni, dekodery, podle_id
from sakra.platformy.sord import bloky_sord
from testy.signal import signal_z_pulzu, uloz_wav
from testy.signal2 import pulzy_z_us


def blok(typ, data):
    return typ + bytes([len(data) & 255]) + data + bytes([sum(data) & 255])


def program(data, nazev=b"SORD", typ=3, vypln=False):
    h = bytes([typ]) + nazev.ljust(9, b"\0")[:9] + struct.pack("<HHH", 0x7300, len(data), 0x7302) + bytes(15)
    out = [blok(b"H", h)]
    for i in range(0, len(data), 256):
        d = data[i:i + 256]
        out.append(blok(b"D", d.ljust(256, b"\0") if vypln else d))
    return out


def pulzy(bloky, rate=44100, rychlost=1.0, pauzy=False, stdly=None):
    # Každý bit je jediná perioda; nejde o MSX/Kansas City se dvěma periodami pro 1.
    us = [500000.0]
    t1 = 1e6 / 3150 if stdly is None else 35.36 + stdly * 8.929
    t0 = 1e6 / 1575 if stdly is None else 49.71 + 2 * stdly * 8.929
    for b in bloky:
        if pauzy:
            us.append(250000.0)
        us += [t1 / 2 / rychlost] * (15000 if b[:1] == b"H" else 940)
        bity = []
        for v in b:
            bity += [0] + [(v >> q) & 1 for q in range(8)] + [1]
        bity += [1] * 4
        for bit in bity:
            us += [(t1 if bit else t0) / 2 / rychlost] * 2
    us.append(500000.0)
    return pulzy_z_us(us, rate)


class Sord(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.tmp = Path(self.tmpdir.name)

    def analyzuj(self, bloky, rate=44100, rychlost=1.0, platforma="Sord m5", obr=False, pauzy=False, stdly=None):
        x = signal_z_pulzu(pulzy(bloky, rate, rychlost, pauzy, stdly), rate)
        uloz_wav(self.tmp / "t.wav", -x if obr else x, rate)
        pred = len(CHYBY_DEKODERU)
        v = analyzuj_stranu(self.tmp / "t.wav", 1, platforma=platforma, polarita="normalni")
        self.assertEqual(CHYBY_DEKODERU[pred:], [])
        self.vysledek = v
        return v.soubory

    def test_standard_export(self):
        data = np.random.default_rng(15).integers(0, 256, 611, np.uint8).tobytes()
        bb = program(data, b"HRA.1")
        for rate, rychlost, obr, pauzy in ((44100, 1.0, False, False), (48000, .93, True, True),
                                         (96000, 1.07, False, False)):
            with self.subTest(rate=rate, rychlost=rychlost):
                soubory = self.analyzuj(bb, rate, rychlost, obr=obr, pauzy=pauzy)
                self.assertEqual(len(soubory), 1)
                s = soubory[0]
                self.assertEqual((s.platforma, s.nazev, s.stav), ("sord-m5", "HRA.1", "ok"))
                self.assertEqual((s.info["adresa"], s.info["spusteni"], s.info["delka_dat"]), (0x7300, 0x7302, 611))
                self.assertEqual([b.data for b in s.bloky], bb)
                out = podle_id(s.platforma).zapis(s, self.tmp / s.nazev)
                self.assertEqual([p.name for p in out], ["HRA.1.cas", "HRA.1.bin"])
                self.assertEqual(out[0].read_bytes(), b"SORDM5" + bytes(10) + b"".join(bb))
                self.assertEqual(out[1].read_bytes(), data)
                self.assertTrue(s.zacatek < s.bloky[0].konec <= s.bloky[1].zacatek < s.konec)

    def test_automatika_a_dva_programy(self):
        bb = program(bytes(range(256)), b"PRVNI") + program(b"10 PRINT\r" * 10, b"DRUHY", 0x60)
        ss = self.analyzuj(bb, platforma="")
        self.assertEqual([(s.platforma, s.nazev, s.stav) for s in ss],
                         [("sord-m5", "PRVNI", "ok"), ("sord-m5", "DRUHY", "ok")])
        self.assertEqual(ss[1].typ_bloku, "BASIC")
        self.assertFalse(any(z.nerozpoznano for z in self.vysledek.strana.zaznamy))

    def test_hranice_od_start_bitu_po_stop_bit(self):
        # Součet FFh má na konci samé jedničky splývající s další nosnou.
        bb = program(b"\xff") + program(b"\x01\xfe", b"DRUHY")
        for rate, rychlost in ((22050, 1.45), (44100, 1.0), (48000, .75)):
            with self.subTest(rate=rate, rychlost=rychlost):
                pp = pulzy(bb, rate, rychlost)
                hrany = np.concatenate(([0], np.cumsum(pp))).astype(np.int64)
                p = Pulzy(rate, hrany, np.where(np.arange(len(hrany)) % 2, 1, -1).astype(np.int8))
                u = Usek(0, len(hrany) - 1, 0.0, p.cas(len(hrany) - 1))
                bs = bloky_sord(p, u)
                self.assertEqual([b.data for b in bs], bb)
                self.assertTrue(all(b.ok for b in bs))
                i = 1
                for b, data in zip(bs, bb):
                    nosna = i
                    i += 15000 if data[:1] == b"H" else 940
                    self.assertEqual(b.zacatek, p.cas(i))
                    self.assertLessEqual(b.nosna_zacatek, p.cas(nosna))
                    self.assertLess(b.nosna_zacatek, b.zacatek)
                    self.assertEqual(len(b.hranice_bitu), len(data))
                    for j, h in enumerate(b.hranice_bitu):
                        self.assertEqual(h, [p.cas(i + 20 * j + 2 * q) for q in range(11)])
                    i += 20 * len(data)
                    self.assertEqual(b.konec, p.cas(i))
                    i += 8  # jedničky za posledním stop bitem už do bloku nepatří

    def test_konec_stop_bitu_pred_tichem(self):
        bb = program(b"\xff")
        pp = pulzy(bb)
        stop = 1 + 15000 + 20 * len(bb[0]) + 8 + 940 + 20 * len(bb[1]) - 2
        for chybi_hrana in (False, True):
            with self.subTest(chybi_hrana=chybi_hrana):
                prubeh = list(pp)
                prubeh[stop + 1] = 22050  # druhá půlvlna splývá s tichem
                hrany = np.concatenate(([0], np.cumsum(prubeh))).astype(np.int64)
                if chybi_hrana:
                    hrany = hrany[:stop + 2]  # poslední hrana je uprostřed stop bitu
                p = Pulzy(44100, hrany, np.where(np.arange(len(hrany)) % 2, 1, -1).astype(np.int8))
                bs = bloky_sord(p, Usek(0, len(hrany) - 1, 0.0, p.cas(len(hrany) - 1)))
                self.assertEqual([b.data for b in bs], bb)
                self.assertTrue(all(b.ok for b in bs))
                self.assertAlmostEqual(bs[-1].konec, p.cas(stop) + 1 / 3150, delta=1 / 44100)
                self.assertEqual(bs[-1].hranice_bitu[-1][-1], bs[-1].konec)
                self.assertEqual(bs[-1].hranice_bitu[-1][-2], p.cas(stop))

    def test_nosna_se_neoznaci_jako_nerozpoznana(self):
        s = self.analyzuj(program(b"\xff"))[0]
        self.assertFalse(any(z.nerozpoznano for z in self.vysledek.strana.zaznamy))
        self.assertGreater(s.zacatek - s.bloky[0].nosna_zacatek, 2.0)
        self.assertEqual(s.zacatek_signalu, s.bloky[0].nosna_zacatek)
        for b in s.bloky:
            znovu = znovu_dekoduj_blok(self.vysledek, s, b)
            self.assertIsNotNone(znovu)
            self.assertEqual((znovu.zacatek, znovu.konec, znovu.data), (b.zacatek, b.konec, b.data))
            self.assertEqual(znovu.hranice_bitu, b.hranice_bitu)

    def test_ibg_je_pomocny_usek_bez_dat(self):
        bb = program(bytes(range(256)) * 2)
        bb[1] = bb[1][:-1] + bytes([bb[1][-1] ^ 1])
        s = self.analyzuj(bb)[0]
        pohled = bloky_pro_zobrazeni(s)
        self.assertEqual([b.typ for b in pohled], ["IBG", "H", "IBG", "D", "IBG", "D"])
        self.assertEqual([b for b in pohled if not isinstance(b, Nosna)], s.bloky)
        self.assertEqual([b.data for b in s.bloky], bb)
        self.assertEqual(s.stav, "chyba")  # nosná nesmí maskovat vadný součet
        self.assertEqual(s.info["bloku"], 3)
        for nosna, data in zip(pohled[::2], pohled[1::2]):
            self.assertIsInstance(nosna, Nosna)
            self.assertEqual(nosna.data, b"")
            self.assertEqual(nosna.zacatek, data.nosna_zacatek)
            self.assertEqual(nosna.konec, data.zacatek)
        k = Kazeta(strany=[Strana(1, zaznamy=[Zaznam(soubor=s)])])
        obnoveny = kazeta_z_json(kazeta_do_json(k)).strany[0].zaznamy[0].soubor
        self.assertEqual([b.typ for b in obnoveny.bloky], ["H", "D", "D"])
        self.assertEqual([(b.typ, b.zacatek, b.konec) for b in bloky_pro_zobrazeni(obnoveny)],
                         [(b.typ, b.zacatek, b.konec) for b in pohled])
        out = podle_id("sord-m5").zapis(obnoveny, self.tmp / "ibg")
        self.assertEqual(out[0].read_bytes(), b"SORDM5" + bytes(10) + b"".join(bb))
        self.assertEqual(out[1].read_bytes(), bytes(range(256)) * 2)

    def test_stdly_ve_sloupci_turbo_a_po_obnove(self):
        pl = podle_id("sord-m5")
        for stdly in (21, 33, 45):
            for rate in (22050, 44100, 48000):
                with self.subTest(stdly=stdly, rate=rate):
                    s = self.analyzuj(program(bytes(range(256))), rate=rate, stdly=stdly)[0]
                    self.assertTrue(s.ok)
                    self.assertEqual(s.info["casovani"]["stdly"], stdly)
                    self.assertEqual(pl.turbo(s), f"STDLY ≈ {stdly}")
                    z = self.vysledek.strana.zaznamy[0]
                    self.assertEqual(z.turbo, f"STDLY ≈ {stdly}")
                    k = Kazeta(strany=[self.vysledek.strana])
                    obnova = kazeta_z_json(kazeta_do_json(k)).strany[0].zaznamy[0]
                    self.assertEqual(pl.turbo(obnova.soubor), z.turbo)
                    pl.zapis(obnova.soubor, self.tmp / "stdly")
                    self.assertEqual(pl.turbo(obnova.soubor), z.turbo)
        s.info.pop("casovani")
        self.assertEqual(pl.turbo(s), "STDLY ?")  # starý projekt nemá změřené časování

    def test_vypln_a_obnova_projektu(self):
        data = b"ABCDEFG" * 47
        s = self.analyzuj(program(data, vypln=True))[0]
        self.assertTrue(s.ok)
        k = Kazeta(strany=[Strana(1, zaznamy=[Zaznam(soubor=s)])])
        obnoveny = kazeta_z_json(kazeta_do_json(k)).strany[0].zaznamy[0].soubor
        self.assertEqual([(b.zacatek, b.konec, b.nosna_zacatek) for b in obnoveny.bloky],
                         [(b.zacatek, b.konec, b.nosna_zacatek) for b in s.bloky])
        self.assertEqual(obnoveny.zacatek_signalu, s.zacatek_signalu)
        self.assertEqual([b.hranice_bitu for b in obnoveny.bloky], [b.hranice_bitu for b in s.bloky])
        out = podle_id("sord-m5").zapis(obnoveny, self.tmp / "obnova")
        self.assertEqual(out[1].read_bytes(), data)
        self.assertEqual(podle_id("sord-m5").nahled(obnoveny)["texty"][0][0], "Začátek dat")

    def test_chybny_soucet(self):
        bb = program(bytes(range(256)) * 2)
        bb[1] = bb[1][:-1] + bytes([bb[1][-1] ^ 1])
        s = self.analyzuj(bb)[0]
        self.assertEqual([b.ok for b in s.bloky], [True, False, True])
        self.assertEqual(s.stav, "chyba")
        self.assertEqual(s.bloky[1].data, bb[1])  # export nesmí chybný součet potichu opravit

    def test_chybny_stop_bit(self):
        bb = program(bytes(range(64)))
        pp = pulzy(bb)
        # První datový bajt: po úvodu, hlavičce, nosné D a dvou bajtech H/D rámce.
        i = 1 + 15000 + 20 * len(bb[0]) + 8 + 940 + 2 * 20 + 18
        pp[i:i + 2] = [14, 14]  # dlouhá perioda místo krátkého stop bitu při 44,1 kHz
        uloz_wav(self.tmp / "ramec.wav", signal_z_pulzu(pp, 44100), 44100)
        v = analyzuj_stranu(self.tmp / "ramec.wav", 1, platforma="Sord m5", polarita="normalni")
        s = v.soubory[0]
        self.assertEqual(s.bloky[1].data, bb[1])  # rámec nesmí posunout všechny další bajty
        self.assertFalse(s.bloky[1].ok)
        self.assertEqual(s.bloky[1].chybne_bajty, [2])
        self.assertEqual(s.stav, "chyba")

    def test_chybna_hlavicka(self):
        bb = program(bytes(range(64)))
        bb[0] = bb[0][:-1] + bytes([bb[0][-1] ^ 1])
        s = self.analyzuj(bb)[0]
        self.assertEqual([b.ok for b in s.bloky], [False, True])
        self.assertEqual(s.stav, "chyba")

    def test_useknuty_a_chybejici_blok(self):
        bb = program(bytes(range(256)) * 2)
        for poskozene in (bb[:-1], bb[:-1] + [bb[-1][:-10]]):
            with self.subTest(delka=len(poskozene)):
                s = self.analyzuj(poskozene)[0]
                self.assertFalse(s.kompletni)
                self.assertEqual(s.stav, "chyba")
        s = self.analyzuj(bb[:1])[0]
        self.assertFalse(s.kompletni)

    def test_bez_hlavicky_a_nesouvisle_bloky(self):
        ss = self.analyzuj([blok(b"D", bytes(range(256)))])
        self.assertEqual(len(ss), 1)
        self.assertFalse(ss[0].kompletni)
        bb = program(b"ABCDEFGH")[:1] + [blok(b"E", b"ABCDEFGH"), blok(b"F", b"ijkl")]
        s = self.analyzuj(bb)[0]
        self.assertEqual([b.typ for b in s.bloky], ["H", "E", "F"])
        self.assertFalse(s.kompletni)
        out = podle_id("sord-m5").zapis(s, self.tmp / "ef")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].read_bytes()[16:], b"".join(bb))

    def test_registrace_a_cizi_signal(self):
        self.assertIn("Sord m5", POCITACE)
        self.assertIn("Sord m5", RUCNI)
        self.assertEqual([p.id for p in dekodery("Sord m5")], ["sord-m5"])
        # Platný UART se stejnými kmitočty, ale bez hlavičky/bloku Sordu.
        self.assertEqual(self.analyzuj([b"XYZ" * 40]), [])

    def test_nesoumerne_pulvlny(self):
        bb = program(bytes(range(256)) * 2)
        pp = np.array(pulzy(bb))
        # Posun průchodu nulou nemění periodu bitu. Rozdíl půlvln 6 vzorků
        # při 44,1 kHz odpovídá zkreslení ve skutečné nahrávce Victory of Mars.
        for i in range(1, len(pp) - 1, 2):
            if 12 <= pp[i] < 100 and 12 <= pp[i + 1] < 100:
                pp[i] += 3
                pp[i + 1] -= 3
        uloz_wav(self.tmp / "asymetrie.wav", signal_z_pulzu(pp, 44100, sum_=0), 44100)
        v = analyzuj_stranu(self.tmp / "asymetrie.wav", 1, platforma="Sord m5")
        self.assertEqual(len(v.soubory), 1)
        self.assertTrue(v.soubory[0].ok)
        self.assertEqual([b.data for b in v.soubory[0].bloky], bb)

    def test_casovani_podle_nosne(self):
        bb = program(bytes(range(256)) * 2)
        for rate in (22050, 44100, 48000):
            for rychlost in (.75, 1.0, 1.45, 1.65):
                with self.subTest(rate=rate, rychlost=rychlost):
                    ss = self.analyzuj(bb, rate=rate, rychlost=rychlost, platforma="")
                    self.assertEqual(len(ss), 1)
                    self.assertTrue(ss[0].ok)
                    self.assertEqual([b.data for b in ss[0].bloky], bb)

    def test_casovani_mame_a_licha_nosna(self):
        bb = program(bytes(range(256)) * 2)
        # Z dodaného WAV: krátká půlvlna ~110 µs, dlouhá ~205 µs.
        # Lichý počet půlvln nosné nesmí posunout začátek UART rámce.
        for pocet in (15934, 15935):
            with self.subTest(nosna=pocet):
                us = [500000.0]
                for b in bb:
                    us += [110.0] * pocet
                    for v in b:
                        for bit in [0] + [(v >> q) & 1 for q in range(8)] + [1]:
                            us += [110.0 if bit else 205.0] * 2
                us.append(500000.0)
                uloz_wav(self.tmp / "mame.wav", signal_z_pulzu(pulzy_z_us(us, 44100), 44100, sum_=0), 44100)
                v = analyzuj_stranu(self.tmp / "mame.wav", 1)
                self.assertEqual(len(v.soubory), 1)
                self.assertTrue(v.soubory[0].ok)
                self.assertEqual([b.data for b in v.soubory[0].bloky], bb)

    def test_zakmity_v_mezerach(self):
        bb = program(bytes(range(256)))
        x = signal_z_pulzu(pulzy(bb), 44100)
        # Krátké pulzy v mezeře nesmějí vyřadit celý souvislý úsek ze skórování.
        sum_ = np.tile(np.array([.6, .6, -.6, -.6], np.float32), 44100)
        uloz_wav(self.tmp / "zakmity.wav", np.concatenate([sum_, x, sum_]), 44100)
        v = analyzuj_stranu(self.tmp / "zakmity.wav", 1)
        self.assertEqual(len(v.soubory), 1)
        self.assertEqual(v.soubory[0].platforma, "sord-m5")
        self.assertTrue(v.soubory[0].ok)
        self.assertEqual([b.data for b in v.soubory[0].bloky], bb)
        zbytky = [z for z in v.strana.zaznamy if z.nerozpoznano]
        self.assertEqual(len(zbytky), 2)
        s = v.soubory[0]
        self.assertTrue(all(z.cas_do <= s.zacatek or z.cas_od >= s.konec for z in zbytky))


VZOREK = Path(os.environ.get("SAKRA_SORD_WAV", str(
    Path(__file__).resolve().parents[1] / "testdata" / "SSF2_Victory_of_Mars.wav")))


@unittest.skipUnless(VZOREK.is_file(), "chybí WAV Victory of Mars (SAKRA_SORD_WAV)")
class VictoryOfMars(unittest.TestCase):
    def test_skutecna_nahravka(self):
        # Otisky dat z dodaného WAV: všech 42 bloků ověřeno původními součty.
        ocekavane = [
            ("BH", 6, 1127, "e9cda5dd3c49e6586eaf23ca411f4e105a6e30ea5c8c87327d93223390cc16ec"),
            ("mars", 13, 3034, "ba4f2d34eb42ee0f70fb7c7a2a9f333aa9d1ace5f3c02b29e4744bee70fbed50"),
            ("game", 23, 5472, "0dc6efb98efab8469c92e6382357d1b7f424dbc5b7d1fe46b101b1c723c8e746"),
        ]
        for platforma in ("", "Sord m5"):
            with self.subTest(platforma=platforma):
                pred = len(CHYBY_DEKODERU)
                v = analyzuj_stranu(VZOREK, 1, platforma=platforma)
                self.assertEqual(CHYBY_DEKODERU[pred:], [])
                self.assertEqual([(s.nazev, len(s.bloky), s.info["delka_dat"],
                                   hashlib.sha256(s._data).hexdigest()) for s in v.soubory], ocekavane)
                self.assertTrue(all(s.ok for s in v.soubory))
                self.assertEqual([z.turbo for z in v.strana.zaznamy if z.soubor], ["STDLY ≈ 33"] * 3)
                self.assertTrue(all(b.ok and not b.chybne_bajty for s in v.soubory for b in s.bloky))
                zbytky = [z for z in v.strana.zaznamy if z.nerozpoznano]
                self.assertEqual(len(zbytky), 2)
                self.assertTrue(all(z.cas_do <= s.zacatek or z.cas_od >= s.konec
                                    for z in zbytky for s in v.soubory))
                with tempfile.TemporaryDirectory() as tmp:
                    for s in v.soubory:
                        out = podle_id("sord-m5").zapis(s, Path(tmp) / s.nazev)
                        self.assertEqual(out[0].read_bytes(), b"SORDM5" + bytes(10) + b"".join(b.data for b in s.bloky))
                        self.assertEqual(hashlib.sha256(out[1].read_bytes()).hexdigest(),
                                         hashlib.sha256(s._data).hexdigest())


MAME_VZOREK = Path(os.environ.get("SAKRA_SORD_MAME_WAV", str(
    Path(__file__).resolve().parents[1] / "testdata" / "sord_basic_i_mame.wav")))


@unittest.skipUnless(MAME_VZOREK.is_file(), "chybí WAV BASIC-I MAME (SAKRA_SORD_MAME_WAV)")
class BasicIMame(unittest.TestCase):
    def test_skutecna_nahravka(self):
        ocekavane = [
            ("DALNICE", 6, 1161, "97134a9ebeccc1657f58bea58be9a723feb1bbb83e5bf7e2d6124bec1c04c5c7"),
            ("dalnice", 12, 2706, "1749206cc4138c7dbf2c81ce24ce5a678dabcefc77b6796c70bc51ad428be5ce"),
            ("TANK&HELI", 11, 2461, "6e7f7ba82adff024e95da401872868ef90ab0e2826355c27b7287908f74b6b66"),
            ("PONORMINY", 11, 2495, "f9808278ee2e4ac4fff1ef853f581d71f24ebd91e4eb94687f27688a4aed5134"),
            ("JUMPMAN", 13, 2928, "7444dd375e17bd1a30ad77cd1b19a52201bfa0317fe212f7779a54ab0370d4f0"),
            ("AUTOKAMEN", 8, 1692, "97c11cc63f7806996024aa5731780b5c27d3bb6fbf81e7dbb8b394fc7d198071"),
            ("FUTBAL", 12, 2619, "556d2e9fc654a8434f8a5da7eee694e48d80da1673c42eac0642650a60a6ac7b"),
            ("KROKY", 11, 2358, "2635b55a31f54131a3114d83ff95848eb5ec1d30ee338f72057de025c40dc66a"),
        ]
        for platforma in ("", "Sord m5"):
            with self.subTest(platforma=platforma):
                pred = len(CHYBY_DEKODERU)
                v = analyzuj_stranu(MAME_VZOREK, 1, platforma=platforma)
                self.assertEqual(CHYBY_DEKODERU[pred:], [])
                self.assertEqual([(s.nazev, len(s.bloky), s.info["delka_dat"],
                                   hashlib.sha256(s._data).hexdigest()) for s in v.soubory], ocekavane)
                self.assertTrue(all(s.platforma == "sord-m5" and s.ok for s in v.soubory))
                self.assertEqual([z.turbo for z in v.strana.zaznamy], ["STDLY ≈ 21"] * 8)
                self.assertTrue(all(b.ok and not b.chybne_bajty for s in v.soubory for b in s.bloky))
                self.assertFalse(any(z.nerozpoznano for z in v.strana.zaznamy))
                with tempfile.TemporaryDirectory() as tmp:
                    for i, s in enumerate(v.soubory):
                        out = podle_id("sord-m5").zapis(s, Path(tmp) / str(i))
                        self.assertEqual(out[0].read_bytes(), b"SORDM5" + bytes(10) + b"".join(b.data for b in s.bloky))
                        self.assertEqual(out[1].read_bytes(), s._data)


if __name__ == "__main__":
    unittest.main()
