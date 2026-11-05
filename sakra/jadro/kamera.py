"""Snímek z připojené kamery (typicky USB webkamera) – fotky kazety a obalu.

Používá OpenCV (balík opencv-python-headless, volitelný doplněk „kamera“): Windows DirectShow / Media
Foundation, Linux V4L2, macOS AVFoundation. Snímání běží ve vlákně, drží se vždy poslední snímek (RGB).
Bez OpenCV aplikace funguje, jen kamera není k dispozici (dostupna() == False).
"""
from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

MAX_KAMER = 6
ROZLISENI = (1920, 1080)       # požadované; kamera dá nejbližší, které umí
INSTALACE = "pip install opencv-python-headless"


def _cv2():
    try:
        import cv2
        return cv2
    except ImportError:
        return None


def dostupna() -> bool:
    return _cv2() is not None


@dataclass
class Zarizeni:
    index: int
    nazev: str


def _nazev_linux(i: int) -> str | None:
    try:
        return Path(f"/sys/class/video4linux/video{i}/name").read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _backend(cv2):
    if sys.platform == "win32":
        return cv2.CAP_DSHOW          # rychlé otevření, umí vyšší rozlišení
    if sys.platform == "darwin":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY


def kamery() -> list[Zarizeni]:
    """Připojené kamery (zkouší indexy 0..MAX_KAMER-1)."""
    cv2 = _cv2()
    if cv2 is None:
        return []
    out = []
    for i in range(MAX_KAMER):
        if sys.platform.startswith("linux") and not Path(f"/dev/video{i}").exists():
            continue
        c = cv2.VideoCapture(i, _backend(cv2))
        try:
            if c.isOpened() and c.read()[0]:
                out.append(Zarizeni(i, _nazev_linux(i) or f"Kamera {i + 1}"))
        finally:
            c.release()
    return out


class Kamera:
    """Otevřená kamera; posledni() vrací poslední snímek (výška × šířka × 3, RGB) nebo None."""

    def __init__(self, index: int, rozliseni: tuple[int, int] = ROZLISENI):
        cv2 = _cv2()
        if cv2 is None:
            raise RuntimeError(f"Kamera potřebuje OpenCV ({INSTALACE})")
        self._cv2 = cv2
        self._cap = cv2.VideoCapture(index, _backend(cv2))
        if not self._cap.isOpened():
            raise RuntimeError(f"Kameru {index + 1} nejde otevřít (je připojená, nepoužívá ji jiný program?)")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, rozliseni[0])
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, rozliseni[1])
        self._snimek: np.ndarray | None = None
        self._zamek = threading.Lock()
        self._bezi = True
        self.chyba = ""
        self._vlakno = threading.Thread(target=self._cti, daemon=True)
        self._vlakno.start()

    def _cti(self):
        chyb = 0
        while self._bezi:
            ok, bgr = self._cap.read()
            if not ok:
                chyb += 1
                if chyb > 50:
                    self.chyba = "Kamera přestala posílat obraz"
                    return
                continue
            chyb = 0
            rgb = self._cv2.cvtColor(bgr, self._cv2.COLOR_BGR2RGB)
            with self._zamek:
                self._snimek = rgb

    def posledni(self) -> np.ndarray | None:
        with self._zamek:
            return None if self._snimek is None else self._snimek.copy()

    def zavri(self):
        self._bezi = False
        self._vlakno.join(2)
        self._cap.release()


def uloz_jpeg(rgb: np.ndarray, cesta: Path, kvalita: int = 92) -> Path:
    """RGB snímek do JPEG (přes Qt, bez dalších knihoven)."""
    from PySide6.QtGui import QImage
    rgb = np.ascontiguousarray(rgb)
    h, w, _ = rgb.shape
    img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
    cesta = Path(cesta)
    cesta.parent.mkdir(parents=True, exist_ok=True)
    if not img.save(str(cesta), "JPG", kvalita):
        raise OSError(f"Snímek nejde uložit: {cesta}")
    return cesta


def dalsi_jmeno(slozka: Path, inv: str) -> Path:
    """„<inventární číslo> foto <n>.jpg“ s prvním volným n."""
    zaklad = inv.strip() or "kazeta"
    n = 1
    while (Path(slozka) / f"{zaklad} foto {n}.jpg").exists():
        n += 1
    return Path(slozka) / f"{zaklad} foto {n}.jpg"
