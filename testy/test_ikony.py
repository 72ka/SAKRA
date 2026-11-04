"""Ikony platforem: každý počítač, ruční volby i zvláštní stavy mají ikonu; klíče se odvodí z id i názvů."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    from sakra.gui import ikony
    QT = True
except ImportError:
    QT = False

from sakra.jadro.model import ZADNA_DATA, Zaznam
from sakra.platformy import POCITACE, RUCNI, VSECHNY


@unittest.skipUnless(QT, "PySide6 není k dispozici")
class Ikony(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_klice(self):
        self.assertEqual(ikony.klic("zx-turbo"), "ZX Spectrum")
        self.assertEqual(ikony.klic("Ondra SPO 186 – ViLi ROM"), "Ondra SPO 186")
        self.assertEqual(ikony.klic("?"), ikony.NEROZPOZNANO)
        self.assertEqual(ikony.klic(ZADNA_DATA), ikony.ZADNA)
        self.assertEqual(ikony.klic_zaznamu(Zaznam(typ="Audio")), ikony.ZADNA)
        self.assertEqual(ikony.klic_zaznamu(Zaznam(platforma="PMD 85")), "PMD 85")

    def test_vse_se_vykresli(self):
        hodnoty = [ikony.AUTO, ikony.NEROZPOZNANO, ikony.ZADNA] + POCITACE + RUCNI + [p.id for p in VSECHNY]
        for h in hodnoty:
            for n in (16, 32, 64):
                pm = ikony.pixmapa(h, n)
                self.assertFalse(pm.isNull(), h)
                self.assertEqual(pm.width(), n)
                img = pm.toImage()
                self.assertGreater(img.pixelColor(n // 2, n // 8).alpha(), 0, h)      # vybarvený čtverec
        # barva podle modulu platformy (stejná jako na časové ose)
        zx = next(p for p in VSECHNY if p.id == "zx-rom")
        self.assertEqual(ikony._barva_pocitace("ZX Spectrum"), zx.barva)

    def test_ikona_aplikace(self):
        """Ikona okna z data/ikona.png ve všech velikostech (malé = výřez kazety), čtvercová; záhlaví široké."""
        from sakra.gui.aplikace import ikona, ikona_zahlavi
        ik = ikona()
        self.assertFalse(ik.isNull())
        for n in (16, 32, 48, 256):
            pm = ik.pixmap(n, n)
            self.assertEqual((pm.width(), pm.height()), (n, n))
            img = pm.toImage()
            self.assertGreater(img.pixelColor(n // 2, n // 2).alpha(), 0)     # uprostřed kazeta, ne průhledno
        z = ikona_zahlavi(26)
        self.assertEqual(z.height(), 26)
        self.assertGreater(z.width(), 2 * z.height())

    def test_soubor_pro_html(self):
        cesta = ikony.soubor("MSX", 16)
        self.assertTrue(os.path.exists(cesta))
        self.assertIn(cesta, ikony.html("msx", 16))


if __name__ == "__main__":
    unittest.main()
