import json
import tempfile
import unittest
from pathlib import Path

import openpyxl

from sakra.balicek import exportuj, sha1
from sakra.jadro.model import Kazeta, kazeta_do_json, kazeta_z_json
from sakra.metadata import excel
from sakra.projekt import cislo_strany, zpracuj
from testy.signal import pulzy_tesla, signal_z_pulzu, soubor_tesla, uloz_wav

KOREN = Path(__file__).resolve().parents[1]
VZOR = KOREN / "HH08518.xlsx"


@unittest.skipUnless(VZOR.exists(), "chybí vzorová tabulka HH08518.xlsx")
class ExcelPodleVzoru(unittest.TestCase):
    def test_export_odpovida_vzoru(self):
        k = excel.importuj(VZOR)
        self.assertEqual(k.inventar.cislo, "HH08518")
        self.assertEqual(k.digitalizace.tape_deck_model, "RS-BX707")
        self.assertEqual([len(s.zaznamy) for s in k.strany], [9, 18])
        cil = Path(tempfile.mkdtemp()) / "e.xlsx"
        excel.exportuj(k, cil)
        a = openpyxl.load_workbook(VZOR).active
        b = openpyxl.load_workbook(cil)["List 1"]
        rozdily = []
        for r in range(1, 42):
            for c in "ABCDEFGHIJKL":
                x, y = a[f"{c}{r}"], b[f"{c}{r}"]
                vx, vy = x.value, y.value
                if c == "J" and isinstance(vx, str) and vx.startswith("="):
                    vx = a[f"E{r}"].value                    # vzorec =E13 -> hodnota
                vx = vx.strip() if isinstance(vx, str) else vx
                fx = x.fill.fgColor.rgb if x.fill.fill_type else None
                fy = y.fill.fgColor.rgb if y.fill.fill_type else None
                if vx != vy or fx != fy or bool(x.font.b) != bool(y.font.b) or x.number_format != y.number_format:
                    rozdily.append((f"{c}{r}", vx, vy, fx, fy))
        self.assertEqual(rozdily, [])
        self.assertEqual(str(b.data_validations.dataValidation[0].sqref), "I13:I21 I24:I41")
        self.assertTrue(all(b[c].comment for c in ("C12", "F12", "G12", "H12", "I12", "C23", "I23")))
        self.assertIn("SAKRA", openpyxl.load_workbook(cil).sheetnames)


class Projekt(unittest.TestCase):
    def test_cislo_strany(self):
        self.assertEqual(cislo_strany("HH08518 (2)_44kHz.wav"), 2)
        self.assertEqual(cislo_strany("kazeta strana B.wav"), 2)
        self.assertEqual(cislo_strany("hry-A.flac"), 1)
        self.assertEqual(cislo_strany("nahravka.wav", 1), 1)

    def test_json_a_balicek(self):
        tmp = Path(tempfile.mkdtemp())
        bloky = soubor_tesla(b"BAJKONUR/2", b"\xf6\xf6\xf6\x42" + bytes(700))
        uloz_wav(tmp / "HH01234 (1).wav", signal_z_pulzu(pulzy_tesla(bloky, 44100), 44100), 44100)
        k = Kazeta()
        vysl = zpracuj(k, {1: tmp / "HH01234 (1).wav"})
        self.assertEqual(k.inventar.cislo, "HH01234")
        z = k.strany[0].zaznamy[0]
        z.obsah, z.poznamky = "Program", "kresba"
        k2 = kazeta_z_json(json.loads(json.dumps(kazeta_do_json(k))))
        self.assertEqual(k2.strany[0].zaznamy[0].soubor.bloky[1].data, bloky[1])
        self.assertEqual(k2.strany[0].zaznamy[0].obsah, "Program")

        d = exportuj(k, tmp / "vystup", vysl)
        jmena = sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file())
        self.assertIn("1-01 BAJKONUR 2.csw", jmena)
        self.assertIn("1-01 BAJKONUR 2.wav", jmena)
        self.assertIn("zdroj/HH01234-1.flac", jmena)
        for n in ("HH01234.xlsx", "HH01234.json", "protokol.html", "SHA1SUMS"):
            self.assertIn(n, jmena)
        for radek in (d / "SHA1SUMS").read_text(encoding="utf-8").splitlines():
            h, jm = radek.split("  ", 1)
            self.assertEqual(sha1(d / jm), h, jm)
        k3 = excel.importuj(d / "HH01234.xlsx")
        self.assertEqual(k3.strany[0].zaznamy[0].poznamky, "kresba")


if __name__ == "__main__":
    unittest.main()
