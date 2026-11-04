"""ŠMS VÚVT Žilina: Kansas City 300 Bd (2400 Hz = 1, 1200 Hz = 0), 1 start + 8 bitů LSB + 3 stop bity."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from sakra.jadro.analyza import analyzuj_stranu
from testy.signal import uloz_wav

RATE = 44100
ADR = Path(__file__).resolve().parents[1] / "skills" / "testdata" / "nezname_kazety_pwramp"


def kcs(data: bytes, hvizd_s: float = 1.5) -> np.ndarray:
    """Signál modemu ŠMS: hvizd 2400 Hz, pak bajty (bit 0 = 4 periody 1200 Hz, bit 1 = 8 period 2400 Hz)."""
    bity = [1] * int(hvizd_s * 300)
    for b in data:
        bity += [0] + [(b >> i) & 1 for i in range(8)] + [1, 1, 1]
    bity += [1] * 30
    kusy, faze = [], 0.0
    for bit in bity:
        f = 2400 if bit else 1200
        n = RATE / 300
        t = np.arange(int(round(n))) / RATE
        kusy.append(np.sign(np.sin(2 * np.pi * f * t + faze)))
        faze += 2 * np.pi * f * len(t) / RATE
    return (0.6 * np.concatenate(kusy)).astype(np.float32)


class SMS(unittest.TestCase):
    def test_dve_kopie_s_vypadkem(self):
        tmp = Path(tempfile.mkdtemp())
        program = bytes([0xEB, 0x11, 0x76, 0x83]) + np.random.default_rng(4).integers(0, 256, 300, np.uint8).tobytes()
        k1, k2 = kcs(program), kcs(program)
        a = int(len(k1) * 0.6)
        k1[a:a + int(0.02 * RATE)] = 0                               # výpadek 20 ms v první kopii
        ticho = np.zeros(RATE, np.float32)
        uloz_wav(tmp / "sms.wav", np.concatenate([ticho, k1, ticho, k2, ticho]), RATE)
        v = analyzuj_stranu(tmp / "sms.wav", 1, polarita="normalni")
        sms = [s for s in v.soubory if s.platforma == "sms-vuvt"]
        self.assertEqual(len(sms), 2, [(s.platforma, s.nazev) for s in v.soubory])
        self.assertEqual([s.bloky[0].data for s in sms], [program, program])
        self.assertTrue(all(s.overeno for s in sms))                 # shodné kopie
        self.assertIn("druhé kopie", sms[0].bloky[0].oprava)
        self.assertEqual(sms[0].stav, "opraveno")
        self.assertEqual(sms[1].stav, "ok")

    def test_jedna_kopie_neovereno(self):
        tmp = Path(tempfile.mkdtemp())
        uloz_wav(tmp / "j.wav", np.concatenate([np.zeros(RATE, np.float32), kcs(b"ABCDEFGH" * 10)]), RATE)
        v = analyzuj_stranu(tmp / "j.wav", 1, polarita="normalni")
        self.assertEqual([(s.platforma, s.bloky[0].data, s.stav) for s in v.soubory],
                         [("sms-vuvt", b"ABCDEFGH" * 10, "neověřeno")])

    @unittest.skipUnless((ADR / "brg_c90_B.wav").exists(), "chybí testovací nahrávka ŠMS")
    def test_skutecna_nahravka(self):
        v = analyzuj_stranu(ADR / "brg_c90_B.wav", 2)
        sms = [s for s in v.soubory if s.platforma == "sms-vuvt"]
        self.assertGreaterEqual(len(sms), 2)
        self.assertEqual([len(s.bloky[0].data) for s in sms[:2]], [881, 1025])
        self.assertTrue(all(s.bloky[0].data.startswith(bytes.fromhex("eb117683")) for s in sms[:2]))
        self.assertEqual(sms[0].bloky[0].data, sms[1].bloky[0].data[:881])  # stejný program, kratší úsek paměti


if __name__ == "__main__":
    unittest.main()
