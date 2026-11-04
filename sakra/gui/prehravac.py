"""Přehrání úseku nahrávky bez dalších knihoven: Windows `winsound`, Linux pw-play/paplay/aplay, macOS afplay.

(QtMultimedia už v balíčku PySide6-Essentials není a PySide6-Addons by aplikaci zvětšil o stovky MB.)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

PREHRAVACE = [["pw-play"], ["paplay"], ["aplay", "-q"], ["afplay"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]]


class Prehravac:
    def __init__(self):
        self.proces: subprocess.Popen | None = None
        self.soubor = Path(tempfile.gettempdir()) / f"sakra-prehravani-{os.getpid()}.wav"
        self.od = 0.0
        self.zacatek = 0.0
        self.delka = 0.0

    @staticmethod
    def dostupny() -> str | None:
        """Čím se bude přehrávat (None = nejde)."""
        if sys.platform == "win32":
            return "winsound"
        for p in PREHRAVACE:
            if shutil.which(p[0]):
                return p[0]
        return None

    def prehraj(self, vzorky: np.ndarray, rate: int, od: float, do: float) -> bool:
        self.stop()
        a, b = max(0, int(od * rate)), min(len(vzorky), int(do * rate))
        if b <= a:
            return False
        kus = vzorky[a:b]
        if kus.dtype != np.int16:
            kus = np.clip(kus, -32768, 32767).astype(np.int16)
        sf.write(str(self.soubor), kus, rate, subtype="PCM_16")
        self.od, self.delka, self.zacatek = a / rate, (b - a) / rate, time.monotonic()
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(str(self.soubor), winsound.SND_FILENAME | winsound.SND_ASYNC)
            return True
        prog = next((p for p in PREHRAVACE if shutil.which(p[0])), None)
        if prog is None:
            return False
        self.proces = subprocess.Popen(prog + [str(self.soubor)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    def pozice(self) -> float | None:
        """Aktuální čas přehrávání v nahrávce, nebo None, když už nehraje."""
        if self.delka <= 0:
            return None
        uplynulo = time.monotonic() - self.zacatek
        if uplynulo > self.delka or (self.proces is not None and self.proces.poll() is not None):
            self.delka = 0
            return None
        return self.od + uplynulo

    def stop(self) -> None:
        if sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(None, 0)
            except Exception:  # noqa: BLE001
                pass
        if self.proces is not None and self.proces.poll() is None:
            self.proces.terminate()
        self.proces = None
        self.delka = 0
