"""Snímek z kamery: OpenCV je podvržené (v testech není kamera ani nutně OpenCV)."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from sakra.jadro import kamera

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class FalesneCv2:
    """Napodobí to, co SAKRA z OpenCV používá: VideoCapture (BGR snímky 320×240), cvtColor."""
    CAP_DSHOW = CAP_AVFOUNDATION = CAP_V4L2 = CAP_ANY = 0
    CAP_PROP_FRAME_WIDTH, CAP_PROP_FRAME_HEIGHT, COLOR_BGR2RGB = 3, 4, 4

    class VideoCapture:
        def __init__(self, index, backend=0):
            self.index, self.n = index, 0

        def isOpened(self):
            return self.index == 0

        def set(self, *_):
            return True

        def read(self):
            time.sleep(0.005)
            self.n += 1
            bgr = np.zeros((240, 320, 3), np.uint8)
            bgr[:, :, 0] = 200                        # modrý kanál (BGR) -> modrý obraz
            bgr[:20, :20] = 255
            return True, bgr

        def release(self):
            pass

    @staticmethod
    def cvtColor(bgr, _):
        return bgr[:, :, ::-1].copy()


def cekej(podminka, app=None, limit=10):
    konec = time.time() + limit
    while not podminka() and time.time() < konec:
        if app:
            app.processEvents()
        time.sleep(0.01)


class Kamera(unittest.TestCase):
    def test_kamera_ve_vlakne_a_jpeg(self):
        with mock.patch.object(kamera, "_cv2", lambda: FalesneCv2):
            k = kamera.Kamera(0)
            cekej(lambda: k.posledni() is not None)
            rgb = k.posledni()
            k.zavri()
            self.assertEqual(rgb.shape, (240, 320, 3))
            self.assertEqual(tuple(rgb[100, 100]), (0, 0, 200))          # převedeno na RGB
            with self.assertRaises(RuntimeError):
                kamera.Kamera(3)                                          # neexistuje
        try:
            from PySide6.QtGui import QImage
        except ImportError:
            self.skipTest("PySide6 není k dispozici")
        slozka = Path(tempfile.mkdtemp())
        c1 = kamera.uloz_jpeg(rgb, kamera.dalsi_jmeno(slozka, "HH00099"))
        c2 = kamera.uloz_jpeg(rgb, kamera.dalsi_jmeno(slozka, "HH00099"))
        self.assertEqual([c1.name, c2.name], ["HH00099 foto 1.jpg", "HH00099 foto 2.jpg"])
        img = QImage(str(c1))
        self.assertEqual((img.width(), img.height()), (320, 240))
        self.assertGreater(img.pixelColor(100, 100).blue(), 150)

    def test_dialog_a_karta(self):
        try:
            from PySide6.QtWidgets import QApplication
            from sakra.gui.kamera import DialogKamera
            from sakra.gui.karta import KartaKazety
        except ImportError:
            self.skipTest("PySide6 není k dispozici")
        from sakra.jadro.model import Kazeta
        app = QApplication.instance() or QApplication([])
        slozka = Path(tempfile.mkdtemp())
        with mock.patch.object(kamera, "_cv2", lambda: FalesneCv2):
            d = DialogKamera("HH00099", str(slozka), zarizeni=[kamera.Zarizeni(0, "Testovací kamera")],
                             otevri=kamera.Kamera)
            d.slozka.setText(str(slozka))
            cekej(lambda: d.nahled.pixmap() is not None and not d.nahled.pixmap().isNull(), app)
            self.assertIn("320 × 240", d.stav.text())
            d.vyfotit.click()
            d.vyfotit.click()
            d.accept()
        self.assertEqual([Path(c).name for c in d.snimky], ["HH00099 foto 1.jpg", "HH00099 foto 2.jpg"])
        self.assertIsNone(d.kam)                                         # kamera po zavření uvolněná
        k = Kazeta()
        karta = KartaKazety()
        karta.nastav(k)
        karta.pridej_fotky(d.snimky)
        self.assertEqual(k.fotky, d.snimky)
        self.assertEqual(karta.fotky.count(), 2)

    def test_bez_opencv(self):
        try:
            from PySide6.QtWidgets import QApplication
            from sakra.gui.kamera import DialogKamera
        except ImportError:
            self.skipTest("PySide6 není k dispozici")
        app = QApplication.instance() or QApplication([])  # noqa: F841
        with mock.patch.object(kamera, "_cv2", lambda: None):
            self.assertEqual(kamera.kamery(), [])
            d = DialogKamera("HH00099", tempfile.mkdtemp())
        self.assertFalse(d.vyfotit.isEnabled())
        self.assertIn("opencv-python-headless", d.nahled.text())


if __name__ == "__main__":
    unittest.main()
