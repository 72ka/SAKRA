"""Nastavení: umístění (proměnná, přenosné, vlastní soubor, systém), profily a výchozí profil, složky,
export a import, dialog Nastavení."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QSettings
    from sakra import nastaveni
except ImportError:  # pragma: no cover
    nastaveni = None

PROFIL = {"tape_deck": "Tesla", "tape_deck_model": "B 115", "sound_card": "Focusrite 2i2", "di_box": "",
          "autor": "Jan Novák"}


@unittest.skipIf(nastaveni is None, "PySide6 není k dispozici")
class Nastaveni(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict(os.environ, {"SAKRA_NASTAVENI": str(self.tmp / "test.ini")})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_vychozi_profil(self):
        from sakra.jadro.model import Kazeta
        nastaveni.uloz_profily({"Pracoviště 1": PROFIL, "Doma": {"autor": "J. N."}}, "Pracoviště 1")
        self.assertEqual(nastaveni.vychozi_profil(), "Pracoviště 1")
        k = Kazeta()
        k.digitalizace.autor = "Někdo jiný"
        self.assertTrue(nastaveni.pouzij_vychozi_profil(k))
        self.assertEqual(k.digitalizace.tape_deck_model, "B 115")
        self.assertEqual(k.digitalizace.autor, "Někdo jiný")          # vyplněné se nepřepíše
        nastaveni.uloz_profily({"Doma": {"autor": "J. N."}})           # smazaný výchozí přestane platit
        self.assertEqual(nastaveni.vychozi_profil(), "")
        self.assertFalse(nastaveni.pouzij_vychozi_profil(Kazeta()))

    def test_export_import(self):
        nastaveni.uloz_profily({"Pracoviště 1": PROFIL}, "Pracoviště 1")
        n = nastaveni.nastaveni()
        n.setValue("archiv", "/data/archiv")
        n.setValue("okno/geometrie", b"\x01\x02")                        # vázané na počítač – neexportuje se
        soubor = self.tmp / "export.json"
        self.assertGreaterEqual(nastaveni.exportuj(soubor), 3)
        d = json.loads(soubor.read_text(encoding="utf-8"))
        self.assertNotIn("okno/geometrie", d["hodnoty"])
        with mock.patch.dict(os.environ, {"SAKRA_NASTAVENI": str(self.tmp / "jine.ini")}):
            self.assertEqual(nastaveni.profily(), {})
            nastaveni.importuj(soubor)
            self.assertEqual(nastaveni.nastaveni().value("archiv"), "/data/archiv")
            self.assertEqual(nastaveni.vychozi_profil(), "Pracoviště 1")
        # profily zvlášť: sloučí se, výchozí se nepřebírá, když už nějaký je
        p = self.tmp / "profily.json"
        nastaveni.zapis_profily(p, {"Studio": dict(PROFIL, autor="Studio")}, "Studio")
        self.assertEqual(nastaveni.importuj(p), 1)                      # importuj pozná export profilů
        self.assertEqual(sorted(nastaveni.profily()), ["Pracoviště 1", "Studio"])
        self.assertEqual(nastaveni.vychozi_profil(), "Pracoviště 1")
        self.assertEqual(nastaveni.precti_profily(soubor)[1], "Pracoviště 1")   # i z exportu nastavení
        (self.tmp / "spatny.json").write_text('{"neco": 1}', encoding="utf-8")
        with self.assertRaises(ValueError):
            nastaveni.importuj(self.tmp / "spatny.json")

    def test_umisteni_a_presun(self):
        system = self.tmp / "system.ini"
        prenosny = self.tmp / "program" / "sakra.ini"
        with mock.patch.dict(os.environ, {"SAKRA_NASTAVENI": ""}), \
                mock.patch.object(nastaveni, "_systemove", lambda: QSettings(str(system), QSettings.Format.IniFormat)), \
                mock.patch.object(nastaveni, "prenosny_soubor", lambda: prenosny):
            self.assertEqual(nastaveni.umisteni()[0], "system")
            nastaveni.nastaveni().setValue("jazyk", "en")
            cil = self.tmp / "sdileny" / "SAKRA.ini"
            nastaveni.presun(cil)
            self.assertEqual(nastaveni.umisteni(), ("soubor", str(cil)))
            self.assertEqual(nastaveni.nastaveni().value("jazyk"), "en")
            nastaveni.nastaveni().setValue("archiv", "/x")
            nastaveni.presun(None)                                         # zpět do systému i s novými údaji
            self.assertEqual(nastaveni.umisteni()[0], "system")
            self.assertEqual(nastaveni.nastaveni().value("archiv"), "/x")
            prenosny.parent.mkdir(parents=True)
            prenosny.write_text("", encoding="utf-8")
            self.assertEqual(nastaveni.umisteni(), ("prenosne", str(prenosny)))

    def test_pamatovat_slozku(self):
        nastaveni.zapamatuj_slozku("archiv", "/a")
        nastaveni.zapamatuj_slozku("archiv", "/b")
        self.assertEqual(nastaveni.nastaveni().value("archiv"), "/b")
        nastaveni.nastaveni().setValue(nastaveni.PAMATOVAT, False)
        nastaveni.zapamatuj_slozku("archiv", "/c")                         # pevná složka zůstane
        self.assertEqual(nastaveni.nastaveni().value("archiv"), "/b")
        nastaveni.zapamatuj_slozku("kamera/slozka", "/foto")               # ještě žádná: uloží se
        self.assertEqual(nastaveni.nastaveni().value("kamera/slozka"), "/foto")

    def test_mezipamet_slozka(self):
        from sakra.jadro import mezipamet
        nastaveni.nastaveni().setValue("mezipamet/slozka", str(self.tmp / "analyzy"))
        with mock.patch.dict(os.environ, {"SAKRA_CACHE": ""}):
            self.assertEqual(mezipamet.slozka(), self.tmp / "analyzy")

    def test_dialog_a_okno(self):
        from PySide6.QtWidgets import QApplication, QInputDialog
        from sakra.gui import vzhled
        from sakra.gui.okno import HlavniOkno
        from sakra.gui.zahlavi import DialogNastaveni
        QApplication.instance() or QApplication([])
        nastaveni.uloz_profily({"Doma": {"autor": "J. N."}})
        d = DialogNastaveni(vzhled.Nastaveni(), zalozka="profily")
        self.assertEqual(d.zalozky.currentIndex(), 1)
        with mock.patch.object(QInputDialog, "getText", return_value=("Pracoviště 1", True)):
            d._novy_profil()
        for k, v in PROFIL.items():
            d.pole_profilu[k].setText(v)
            d.pole_profilu[k].textEdited.emit(v)
        d.je_vychozi.setChecked(True)
        self.assertTrue(d.seznam_profilu.currentItem().text().startswith("★"))
        d.slozky["archiv"].setText("/data/archiv")
        d.pamatovat.setChecked(False)
        d.uloz()
        self.assertEqual(nastaveni.profily()["Pracoviště 1"], PROFIL)
        self.assertEqual(nastaveni.vychozi_profil(), "Pracoviště 1")
        self.assertEqual(nastaveni.nastaveni().value("archiv"), "/data/archiv")
        self.assertFalse(nastaveni.pamatovat())
        with mock.patch.object(QInputDialog, "getText", return_value=("Dílna", True)):
            d._prejmenuj_profil()
        d.uloz()
        self.assertEqual(nastaveni.vychozi_profil(), "Dílna")              # výchozí jde s přejmenováním
        o = HlavniOkno()
        o.nova()
        self.assertEqual(o.kazeta.digitalizace.sound_card, "Focusrite 2i2")
        self.assertEqual(o.karta.sound_card.text(), "Focusrite 2i2")
        self.assertEqual(o.karta.profil.currentData(), "Dílna")
        self.assertIn("(", o.karta.profil.currentText())                  # „(výchozí)“
        o.close()


if __name__ == "__main__":
    unittest.main()
