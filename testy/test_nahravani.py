"""Nahrávání ze zvukového vstupu (s náhradním zdrojem zvuku – v testech není zvuková karta)."""
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from sakra.jadro import zaznam
from testy.signal import pulzy_tesla, signal_z_pulzu, soubor_tesla

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RATE = 44100


def magnetofon(signal: np.ndarray):
    """Náhradní zdroj: „přehraje“ signál (float ±1) po blocích jako zvuková karta, rychleji než v reálném čase."""
    class Zdroj:
        def __init__(self, vstup, rate, kanaly, pri_datech):
            self.kanaly, self.pri_datech, self.bezi = kanaly, pri_datech, False

        def start(self):
            self.bezi = True
            threading.Thread(target=self._hraj, daemon=True).start()

        def _hraj(self):
            x = (np.clip(signal.astype(np.float64), -1, 1) * (2 ** 31 - 1)).astype(np.int32)
            for i in range(0, len(x), 4410):
                if not self.bezi:
                    return
                kus = x[i:i + 4410]
                self.pri_datech(np.repeat(kus[:, None], self.kanaly, axis=1))
                time.sleep(0.001)
            while self.bezi:                                   # pak ticho
                self.pri_datech(np.zeros((4410, self.kanaly), np.int32))
                time.sleep(0.01)

        def stop(self):
            self.bezi = False
    return Zdroj


def program() -> np.ndarray:
    data = np.random.default_rng(9).integers(0, 256, 300, np.uint8).tobytes()
    return signal_z_pulzu(pulzy_tesla(soubor_tesla(b"NAHRANO", data), RATE), RATE)


def cekej(podminka, limit=30):
    konec = time.time() + limit
    while not podminka() and time.time() < konec:
        time.sleep(0.02)


class Nahravani(unittest.TestCase):
    def test_zapis_wav_a_uroven(self):
        x = program()
        cesta = Path(tempfile.mkdtemp()) / "HH00095 (1).wav"
        n = zaznam.Nahravac(zaznam.Vstup("test", "test"), RATE, 2, 24, zdroj=magnetofon(x))
        n.start(cesta)
        cekej(lambda: n.delka >= len(x) / RATE)
        self.assertGreater(max(n.uroven()), 0.4)
        self.assertFalse(n.prebuzeno)
        self.assertEqual(n.stop(), cesta)
        info = sf.info(str(cesta))
        self.assertEqual((info.samplerate, info.channels, info.subtype), (RATE, 2, "PCM_24"))
        self.assertGreaterEqual(info.frames, len(x))

    def test_prebuzeni_a_sledovani_bez_souboru(self):
        x = np.sign(np.sin(np.arange(RATE) / 10.0)).astype(np.float32)      # plná úroveň = přebuzeno
        n = zaznam.Nahravac(zaznam.Vstup("test", "test"), RATE, 1, 16, zdroj=magnetofon(x))
        n.start(None)
        cekej(lambda: n.prebuzeno)
        self.assertTrue(n.prebuzeno)
        self.assertIsNone(n.stop())
        self.assertEqual(n.snimku, 0)

    def test_systemovy_nahravac(self):
        """Linux bez PortAudio: surový zvuk s16le z parecord/arecord na stdout."""
        import sys
        from unittest import mock
        vzor = (np.arange(RATE // 2, dtype=np.int64) * 37 % 20000 - 10000).astype("<i2")
        tmp = Path(tempfile.mkdtemp())
        (tmp / "surove.raw").write_bytes(np.repeat(vzor, 2).tobytes())        # stereo, prokládané
        skript = ("import sys,time; sys.stdout.buffer.write(open(sys.argv[1],'rb').read()); "
                  "sys.stdout.flush(); time.sleep(30)")
        prikazy = {"testrec": lambda r, c: [sys.executable, "-c", skript, str(tmp / "surove.raw")]}
        cesta = tmp / "HH00097 (1).wav"
        with mock.patch.dict(zaznam.PRIKAZY, prikazy):
            n = zaznam.Nahravac(zaznam.Vstup("testrec", "test"), RATE, 2, 16)
            n.start(cesta)
            cekej(lambda: n.snimku >= len(vzor))
            n.stop()
        y, rate = sf.read(str(cesta), dtype="int16")
        self.assertEqual(rate, RATE)
        self.assertTrue(np.array_equal(y[:len(vzor), 0], vzor))
        self.assertTrue(np.array_equal(y[:len(vzor), 1], vzor))

    def test_ladeni_hlavy(self):
        """Stereo zdroj s pravým kanálem zpožděným o 4 vzorky: panel ukáže posun ~83 µs a špičku pulzů."""
        try:
            from PySide6.QtWidgets import QApplication
            from sakra import i18n
            from sakra.gui.nahravani import DialogNahravani
        except ImportError:
            self.skipTest("PySide6 není k dispozici")
        app = QApplication.instance() or QApplication([])
        i18n.nastav("cs")
        x = program()
        signal = (np.clip(x.astype(np.float64), -1, 1) * 2 ** 30).astype(np.int32)

        class Stereo:
            def __init__(self, vstup, rate, kanaly, pri_datech):
                self.cb, self.bezi = pri_datech, False

            def start(self):
                self.bezi = True
                threading.Thread(target=self._hraj, daemon=True).start()

            def _hraj(self):
                for i in range(RATE, len(signal) - 4410, 4410):
                    if not self.bezi:
                        return
                    kus = signal[i:i + 4410]
                    self.cb(np.stack([kus, signal[i - 4:i + 4410 - 4]], axis=1))
                    time.sleep(0.02)

            def stop(self):
                self.bezi = False
        d = DialogNahravani("HH00098", tempfile.mkdtemp(), zdroj=Stereo)
        d.vzorkovani.setCurrentIndex(d.vzorkovani.findData(RATE))
        d.sledovat.setChecked(True)
        konec = time.time() + 10
        while (d.ladeni.v is None or d.ladeni.v.posun_us is None) and time.time() < konec:
            app.processEvents()
            time.sleep(0.02)
        v = d.ladeni.v
        self.assertAlmostEqual(v.posun_us, 4 * 1e6 / RATE, delta=10)
        self.assertGreater(v.korelace, 0.9)
        self.assertIsNotNone(v.rozptyl)
        prvni, druhy = d.ladeni.texty()
        self.assertIn("Délky pulzů: špička", prvni)
        self.assertIn("Posun kanálů L/R: +9", druhy)
        self.assertFalse(d.ladeni.grab().isNull())
        d.sledovat.setChecked(False)
        self.assertIsNone(d.nahravac)

    def test_dialog_a_otevreni_v_sakra(self):
        try:
            from PySide6.QtWidgets import QApplication
            from sakra.gui.nahravani import DialogNahravani
            from sakra.gui.okno import HlavniOkno
        except ImportError:
            self.skipTest("PySide6 není k dispozici")
        app = QApplication.instance() or QApplication([])
        tmp = Path(tempfile.mkdtemp())
        x = program()
        d = DialogNahravani("HH00096", str(tmp), zdroj=magnetofon(x))
        d.slozka.setText(str(tmp))
        d.vzorkovani.setCurrentIndex(d.vzorkovani.findData(RATE))
        self.assertTrue(d.soubor.text().endswith("HH00096 (1).wav"))
        d.nahravat.click()                                   # ● Nahrávat
        self.assertIsNotNone(d.nahravac)
        cekej(lambda: (app.processEvents() or True) and d.nahravac.delka >= len(x) / RATE + 0.5)
        d.nahravat.click()                                   # ■ Zastavit
        self.assertEqual(d.hotove, [tmp / "HH00096 (1).wav"])
        self.assertEqual(d.strana.value(), 2)                # připraveno na další stranu
        self.assertTrue(d.otevrit.isEnabled())
        o = HlavniOkno()
        o.show()
        o.otevri_nahravky([str(c) for c in d.hotove])
        konec = time.time() + 60
        while o.ukol and o.ukol.isRunning() and time.time() < konec:
            app.processEvents()
            time.sleep(0.01)
        for _ in range(20):
            app.processEvents()
        self.assertIn("NAHRANO", [z.nazev for _, z in o.model.radky])
        self.assertEqual(o.kazeta.inventar.cislo, "HH00096")
        o.close()


if __name__ == "__main__":
    unittest.main()
