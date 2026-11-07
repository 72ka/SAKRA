"""Kontrolní součty v detailu bloku: hodnota na pásce a spočtená z dat (shoda / rozdíl)."""
import os
import unittest

from sakra.jadro.model import Blok, Soubor
from sakra.jadro.soucty import soucty_bloku
from testy.signal import blok_tesla
from testy.signal2 import acorn_blok, atari_zaznamy, cpc_zaznam, pmd_hlavicka, pmd_telo

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
DATA = bytes(range(200))


def zx_blok(data: bytes) -> bytes:
    x = 0xFF
    for v in data:
        x ^= v
    return b"\xff" + data + bytes([x])


PRIPADY = [   # (platforma, typ bloku, data bloku)
    ("ondra-tesla", "data", blok_tesla(0x42, DATA, b"TEST", 2)),
    ("zx-rom", "data", zx_blok(DATA)),
    ("pmd85", "hlavička", pmd_hlavicka(1, "P", 0, DATA, b"TEST"), 50),   # 0-47 úvod bez součtu
    ("pmd85", "data", pmd_telo(DATA)),
    ("acorn", "data", acorn_blok(b"TEST", 0, DATA, True)),
    ("cpc", "data", cpc_zaznam(0x16, DATA * 2)),
    ("atari-rom", "data", atari_zaznamy(DATA)[0]),
    ("sord-m5", "H", b"H\x1f" + bytes(range(31)) + bytes([sum(range(31)) & 255])),
    *[("sord-m5", typ, typ.encode() + bytes([len(DATA)]) + DATA + bytes([sum(DATA) & 255]))
      for typ in "DEF"],
    ("sord-m5", "D", b"D\0" + bytes(range(256)) + b"\x80"),
]


def poskod(d: bytes, i: int | None = None) -> bytes:
    """Změní bajt i (výchozí: uprostřed bloku) – musí ležet v části, kterou součet hlídá."""
    i = len(d) // 2 if i is None else i
    return d[:i] + bytes([d[i] ^ 0x5A]) + d[i + 1:]


class Soucty(unittest.TestCase):
    def test_spravny_a_poskozeny_blok(self):
        for platforma, typ, d, *kde in PRIPADY:
            with self.subTest(platforma=platforma, typ=typ):
                dobre = soucty_bloku(platforma, Blok(0, 1, typ, None, d, True))
                self.assertTrue(dobre)
                self.assertTrue(all(s.sedi for s in dobre), dobre)
                spatne = soucty_bloku(platforma, Blok(0, 1, typ, None, poskod(d, *kde), False))
                self.assertFalse(all(s.sedi for s in spatne), spatne)

    def test_formaty_bez_souctu(self):
        self.assertIsNone(soucty_bloku("zx81", Blok(0, 1, "data", None, DATA, True)))
        self.assertIsNone(soucty_bloku("pmd85", Blok(0, 1, "nestandardní", None, DATA, True)))
        self.assertEqual(soucty_bloku("ondra-tesla", Blok(0, 1, "data", None, b"\x10", False)), [])

    def test_sord_soucet_dat_a_chybejici_soucet(self):
        def soucty(d):
            return soucty_bloku("sord-m5", Blok(0, 1, "D", None, d, False))
        self.assertEqual(soucty(b"D\x02\xff\x02\x01"), [("součet", 1, 1, 2)])
        self.assertEqual(soucty(b"D\x02\xff\x02\x00"), [("součet", 0, 1, 2)])
        self.assertEqual(soucty(b"D\x02\xff\x02"), [("součet", None, 1, 2)])
        for d in (b"", b"D", b"D\x02\xff", b"D\x02\xff\x02\x01\x00", b"H\x01\xff\xff"):
            with self.subTest(data=d):
                self.assertEqual(soucty(d), [])

    def test_detail_ukaze_soucty(self):
        try:
            from PySide6.QtWidgets import QApplication
            from sakra.gui.detail import Detail
        except ImportError:
            self.skipTest("PySide6 není k dispozici")
        from sakra import i18n
        from sakra.jadro.model import Zaznam
        i18n.nastav("cs")
        app = QApplication.instance() or QApplication([])  # noqa: F841
        d = zx_blok(DATA)
        s = Soubor("zx-rom", "TEST", "TEST", "Bytes",
                   bloky=[Blok(0, 1, "data", None, d, True), Blok(1, 2, "data", None, poskod(d), False)])
        det = Detail()
        det.nastav(Zaznam(nazev="TEST", soubor=s))
        text = det.text.toPlainText()
        self.assertIn("Součet (pásek / spočteno)", text)
        self.assertIn(f"XOR: {d[-1]:02X} / {d[-1]:02X}", text)

        s = Soubor("sord-m5", "SORD", "SORD", "BASIC", bloky=[
            Blok(0, 1, "D", None, b"D\x02\xff\x02\x01", True),
            Blok(1, 2, "D", None, b"D\x02\xff\x02\x00", False),
            Blok(2, 3, "D", None, b"D\x02\xff\x02", False)])
        det.nastav(Zaznam(nazev="SORD", soubor=s))
        text = det.text.toPlainText()
        self.assertIn("součet: 01 / 01", text)
        self.assertIn("součet: 00 / 01", text)
        self.assertIn("součet: ? / 01", text)
        html = det.text.toHtml().lower()
        self.assertIn("#2ea866", html)
        self.assertIn("#e04848", html)


if __name__ == "__main__":
    unittest.main()
