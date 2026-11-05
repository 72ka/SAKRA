"""Nahrávání strany kazety ze zvukového vstupu přímo do WAV.

Zdroj: knihovna sounddevice (PortAudio; ve Windows a macOS je v balíčku), na Linuxu bez PortAudio
systémový nahrávač (parecord, arecord) se surovým zvukem na výstupu. Data se průběžně zapisují na disk
(i dlouhá strana nezaplní paměť); k tomu špičková úroveň po kanálech a příznak přebuzení.
"""
from __future__ import annotations

import queue
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

PLNA = 2 ** 31            # vzorky int32
PREBUZENI = 0.999         # špička nad tímto podílem = přebuzeno (ořez)
VZORKOVANI = (44100, 48000, 96000)
POSLEDNI_S = 0.5          # kolik posledního zvuku držet pro ladění hlavy
BITU = {16: "PCM_16", 24: "PCM_24"}
PRIKAZY = {               # surový zvuk s16le na stdout
    "parecord": lambda r, c: ["parecord", "--raw", "--format=s16le", f"--rate={r}", f"--channels={c}"],
    "arecord": lambda r, c: ["arecord", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(r), "-c", str(c)],
}


@dataclass
class Vstup:
    id: object                 # zařízení pro zdroj (index sounddevice, název příkazu)
    nazev: str
    kanaly: int = 2


def _sounddevice():
    try:
        import sounddevice as sd
        return sd
    except (ImportError, OSError):    # balík chybí nebo není knihovna PortAudio
        return None


def vstupy() -> list[Vstup]:
    """Dostupné zvukové vstupy (výchozí první)."""
    sd = _sounddevice()
    if sd is not None:
        try:
            vychozi = sd.default.device[0]
            out = [Vstup(i, d["name"], min(2, d["max_input_channels"]))
                   for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
            out.sort(key=lambda v: v.id != vychozi)
            if out:
                return out
        except Exception:  # noqa: BLE001 – rozbitý ovladač: zkusit systémový nahrávač
            pass
    return [Vstup(p, f"výchozí vstup ({p})") for p in PRIKAZY if shutil.which(p)]


class _ZdrojSD:
    def __init__(self, vstup: Vstup, rate: int, kanaly: int, pri_datech):
        sd = _sounddevice()
        self.stream = sd.InputStream(device=vstup.id, channels=kanaly, samplerate=rate, dtype="int32",
                                     callback=lambda d, n, t, stav: pri_datech(d.copy()))

    def start(self):
        self.stream.start()

    def stop(self):
        self.stream.stop()
        self.stream.close()


class _ZdrojProces:
    def __init__(self, vstup: Vstup, rate: int, kanaly: int, pri_datech):
        self.prikaz = PRIKAZY[vstup.id](rate, kanaly)
        self.kanaly, self.blok = kanaly, max(1, rate // 20) * kanaly * 2
        self.pri_datech = pri_datech
        self.proces: subprocess.Popen | None = None

    def start(self):
        self.proces = subprocess.Popen(self.prikaz, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        threading.Thread(target=self._cti, daemon=True).start()

    def _cti(self):
        zbytek = b""
        while self.proces and self.proces.poll() is None:
            kus = zbytek + self.proces.stdout.read(self.blok)
            if not kus:
                break
            n = len(kus) // (2 * self.kanaly) * 2 * self.kanaly
            kus, zbytek = kus[:n], kus[n:]
            if kus:
                d = np.frombuffer(kus, "<i2").astype(np.int32).reshape(-1, self.kanaly) << 16
                self.pri_datech(d)

    def stop(self):
        if self.proces:
            self.proces.terminate()
            try:
                self.proces.wait(2)
            except subprocess.TimeoutExpired:
                self.proces.kill()
            if self.proces.stdout:
                self.proces.stdout.close()
            self.proces = None


class Nahravac:
    """start(cesta) nahrává do WAV (cesta None = jen sledovat úroveň), stop() zavře soubor."""

    def __init__(self, vstup: Vstup, rate: int = 48000, kanaly: int = 2, bitu: int = 16, zdroj=None):
        self.vstup, self.rate, self.kanaly, self.bitu = vstup, rate, kanaly, bitu
        self._zdroj_trida = zdroj or (_ZdrojProces if isinstance(vstup.id, str) and vstup.id in PRIKAZY
                                      else _ZdrojSD)
        self._zdroj = None
        self._fronta: queue.Queue = queue.Queue()
        self._zapis: threading.Thread | None = None
        self._spicky = np.zeros(kanaly)
        self._zamek = threading.Lock()
        self.prebuzeno = False
        self._posledni: list[np.ndarray] = []      # posledních POSLEDNI_S zvuku (ladění hlavy)
        self._posledni_n = 0
        self.snimku = 0
        self.cesta: Path | None = None
        self.chyba = ""

    # ---- data ze zdroje (vlákno zdroje) ----
    def _pri_datech(self, d: np.ndarray) -> None:
        spicka = np.abs(d.astype(np.int64)).max(axis=0) / PLNA
        with self._zamek:
            self._spicky = np.maximum(self._spicky, spicka)
            if spicka.max() >= PREBUZENI:
                self.prebuzeno = True
            self._posledni.append(d)
            self._posledni_n += len(d)
            while self._posledni_n - len(self._posledni[0]) >= POSLEDNI_S * self.rate:
                self._posledni_n -= len(self._posledni.pop(0))
        if self.cesta is not None:
            self._fronta.put(d)

    def _zapisuj(self, f: sf.SoundFile) -> None:
        try:
            while True:
                d = self._fronta.get()
                if d is None:
                    break
                f.write(d)
                self.snimku += len(d)
        except Exception as e:  # noqa: BLE001 – plný disk apod.: nahrávání skončí s chybou
            self.chyba = str(e)
        finally:
            f.close()

    # ---- ovládání ----
    def start(self, cesta: Path | None = None) -> None:
        self.cesta = Path(cesta) if cesta else None
        self.snimku, self.prebuzeno, self.chyba = 0, False, ""
        if self.cesta is not None:
            self.cesta.parent.mkdir(parents=True, exist_ok=True)
            f = sf.SoundFile(str(self.cesta), "w", self.rate, self.kanaly, BITU.get(self.bitu, "PCM_16"), format="WAV")
            self._zapis = threading.Thread(target=self._zapisuj, args=(f,), daemon=True)
            self._zapis.start()
        self._zdroj = self._zdroj_trida(self.vstup, self.rate, self.kanaly, self._pri_datech)
        try:
            self._zdroj.start()
        except Exception as e:  # noqa: BLE001 – zařízení nejde otevřít (obsazené, nepodporuje vzorkování…)
            self.chyba = str(e)
            self._zdroj = None
            self.stop()
            raise

    def stop(self) -> Path | None:
        if self._zdroj is not None:
            self._zdroj.stop()
            self._zdroj = None
        if self._zapis is not None:
            self._fronta.put(None)
            self._zapis.join(10)
            self._zapis = None
        cesta, self.cesta = self.cesta, None
        return cesta

    @property
    def bezi(self) -> bool:
        return self._zdroj is not None

    @property
    def delka(self) -> float:
        return self.snimku / self.rate

    def posledni(self) -> np.ndarray:
        """Posledních POSLEDNI_S zvuku (int32, snímky × kanály) – pro ladění hlavy."""
        with self._zamek:
            kusy = list(self._posledni)
        return np.concatenate(kusy) if kusy else np.zeros((0, self.kanaly), np.int32)

    def uroven(self) -> list[float]:
        """Špičky po kanálech (0..1) od posledního dotazu."""
        with self._zamek:
            s, self._spicky = self._spicky, np.zeros(self.kanaly)
        return [float(x) for x in s]
