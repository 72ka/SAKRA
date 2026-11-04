"""Přepínání jazyka: každý text rozhraní má anglický překlad a šablony mají stejné zástupné znaky."""
import ast
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

from sakra import i18n
from sakra.preklady import en

KOREN = Path(__file__).resolve().parents[1] / "sakra"
# vlastní jména a značky – v angličtině stejné
BEZ_PREKLADU = {"Maxell", "Philips", "Scotch", "Sony", "Tesla", "Type I", "Type II", "Type IV"}


def klice():
    for f in sorted(KOREN.rglob("*.py")):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "tr" and n.args \
                    and isinstance(n.args[0], ast.Constant):
                yield f.relative_to(KOREN.parent), n.args[0].value


class Preklady(unittest.TestCase):
    def tearDown(self):
        i18n.nastav("cs")

    def test_vse_prelozeno(self):
        chybi = sorted({f"{f}: {k!r}" for f, k in klice() if k not in en.TEXTY and k not in BEZ_PREKLADU})
        self.assertEqual(chybi, [], "\n".join(chybi))

    def test_zastupne_znaky(self):
        for k, v in en.TEXTY.items():
            with self.subTest(k=k):
                self.assertEqual(sorted(re.findall(r"\{\d+[^}]*\}", k)), sorted(re.findall(r"\{\d+[^}]*\}", v)))

    def test_preklad_a_data(self):
        i18n.nastav("en")
        self.assertEqual(i18n.tr("Pracovní stůl"), "Workbench")
        self.assertEqual(i18n.tr("neznámý text"), "neznámý text")
        self.assertEqual(i18n.tr_data("blok 3: 12 bitů podle kopií (rozhodla většina)"),
                         "block 3: 12 bits from copies (majority vote)")
        self.assertEqual(i18n.tr_data("chybí blok 2; poškozený blok 5"), "missing block 2; damaged block 5")
        self.assertEqual(i18n.tr_data("Strana 1: Obrácená polarita: Dekóduji: ZX Spectrum"),
                         "Side 1: Inverted polarity: Decoding: ZX Spectrum")
        self.assertEqual(i18n.tr_data("> Data BASICu"), "> BASIC data")
        from sakra.jadro.texty import pocet
        self.assertEqual((pocet(1, "kazeta", "kazety", "kazet"), pocet(3, "kazeta", "kazety", "kazet")),
                         ("1 cassette", "3 cassettes"))
        i18n.nastav("cs")
        self.assertEqual(i18n.tr("Pracovní stůl"), "Pracovní stůl")
        self.assertEqual(pocet(3, "kazeta", "kazety", "kazet"), "3 kazety")

    def test_okno_anglicky(self):
        """Celé okno v angličtině (v samostatném procesu – texty modulů se vyhodnotí při importu)."""
        kod = ("from sakra import i18n; i18n.nastav('en')\n"
               "from PySide6.QtWidgets import QApplication\n"
               "app = QApplication([])\n"
               "from sakra.gui.okno import HlavniOkno\n"
               "o = HlavniOkno()\n"
               "print([a.text() for a in o.menu_lista.actions()])\n"
               "print(o.akce_rezimu['stul'].text(), o.akce_rezimu['pruvodce'].text())\n")
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        r = subprocess.run([sys.executable, "-c", kod], capture_output=True, text=True, env=env, timeout=120,
                           cwd=KOREN.parent)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("&File", r.stdout)
        self.assertIn("Workbench Wizard", r.stdout)


if __name__ == "__main__":
    unittest.main()
