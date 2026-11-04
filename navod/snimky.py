"""Snímky obrazovky pro návod: aplikace běží bez okna (offscreen) nad testovacími nahrávkami.

Spuštění z kořene projektu:  python navod/snimky.py
Potřebuje skills/testdata/RH07860_v1 (ZX Spectrum) a HH08518 (2)_44kHz.wav (Ondra); nastavení uživatele nemění.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
KOREN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOREN))

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

OBRAZKY = Path(__file__).resolve().parent / "obrazky"
RH = KOREN / "skills" / "testdata" / "RH07860_v1" / "RH07860"
HH = KOREN / "HH08518 (2)_44kHz.wav"
SIRKA, VYSKA = 1360, 860


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="sakra-navod-"))
    for f in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):     # nastavení uživatele zůstane netknuté
        QSettings.setPath(f, QSettings.Scope.UserScope, str(tmp / "nastaveni"))
    app = QApplication.instance() or QApplication(["sakra"])
    from sakra.gui import vzhled
    from sakra.gui.aplikace import _preklad_qt, ikona
    from sakra.gui.okno import HlavniOkno
    from sakra.gui.zahlavi import DialogNastaveni
    app.setWindowIcon(ikona())
    _preklad_qt(app)                              # tlačítka Qt (Storno…) česky jako v aplikaci
    n = vzhled.Nastaveni("svetle", "navrh", False)
    vzhled.pouzij(app, n)
    OBRAZKY.mkdir(exist_ok=True)

    def cekej(podminka, limit=300):
        konec = time.time() + limit
        while not podminka() and time.time() < konec:
            app.processEvents()
            time.sleep(0.02)
        for _ in range(30):
            app.processEvents()

    def uloz(w, jmeno):
        cekej(lambda: True)
        w.grab().save(str(OBRAZKY / f"{jmeno}.png"))
        print("  ", jmeno)

    ikona().pixmap(256, 256).save(str(OBRAZKY / "ikona.png"))

    # ---------------------------------------------------------------- průvodce
    o = HlavniOkno()
    o.pouzij_vzhled(n)
    o.resize(SIRKA, VYSKA)
    o.show()
    o.prepni_rezim("pruvodce")
    p = o.pruvodce
    p.pridej_soubory([RH / "RH07860 (A).wav", RH / "RH07860 (B).wav"])
    uloz(o, "pruvodce1")
    p.jdi(1)
    uloz(o, "pruvodce2")
    p.jdi(2)
    cekej(lambda: p._analyzovano is not None)
    uloz(o, "pruvodce3")
    p.jdi(3)
    uloz(o, "pruvodce4")
    p.jdi(4)
    uloz(o, "pruvodce5")
    p.jdi(5)
    p.kam.setText(str(Path.home() / "Archiv"))
    uloz(o, "pruvodce6")

    # ---------------------------------------------------------------- pracovní stůl
    o.prepni_rezim("stul")
    from sakra.platformy.zx import snimky_programu
    radek = next(i for i, (_, z) in enumerate(o.model.radky) if z.soubor is not None)
    snimky_programu(o.model.radky[radek][1].soubor)          # obrazovka po spuštění v detailu
    o.tabulka.selectRow(radek)
    uloz(o.detail, "detail")
    o.osa._nastav_rozsah(8.5, 16.5)
    uloz(o.osa, "osa")
    o.osa._nastav_rozsah(15.200, 15.215)
    uloz(o.osa, "osa_vzorky")
    o.zalozky.setCurrentIndex(1)
    uloz(o.zalozky, "karta")
    o.zalozky.setCurrentIndex(0)
    o.close()

    # ---------------------------------------------------------------- pracovní stůl s vadným blokem (Ondra)
    o = HlavniOkno()
    o.pouzij_vzhled(n)
    o.resize(SIRKA, VYSKA)
    o.show()
    o.prepni_rezim("stul")
    o.otevri_nahravky([str(HH)])
    cekej(lambda: not (o.ukol and o.ukol.isRunning()))
    radek = next(i for i, (_, z) in enumerate(o.model.radky)
                 if z.soubor is not None and any(not b.ok for b in z.soubor.bloky))
    o.tabulka.selectRow(radek)
    uloz(o, "stul")
    w = o.pulzy.parentWidget().parentWidget()                      # řádek Pulzy + Histogram délek
    uloz(w, "pulzy")
    o.close()

    # ---------------------------------------------------------------- ruční úprava (blok s výpadkem přechodu)
    sys.path.insert(0, str(KOREN))
    import numpy as np

    from sakra.jadro.analyza import analyzuj_stranu
    from testy.signal import pulzy_tesla, signal_z_pulzu, soubor_tesla, uloz_wav
    pulzy = pulzy_tesla(soubor_tesla(b"KORAB", np.random.default_rng(6).integers(0, 256, 700, np.uint8).tobytes()),
                        44100)
    uloz_wav(tmp / "cista.wav", signal_z_pulzu(pulzy, 44100), 44100)
    b3 = next(b for b in analyzuj_stranu(tmp / "cista.wav", 1).soubory[0].bloky if b.cislo == 3)
    konce = np.cumsum([int(x) for x in pulzy])
    k = int(np.searchsorted(konce, (b3.zacatek + 0.6 * (b3.konec - b3.zacatek)) * 44100))
    t = konce[k] / 44100
    uloz_wav(tmp / "HH00077 (1).wav", signal_z_pulzu(pulzy[:k] + [pulzy[k] + pulzy[k + 1]] + pulzy[k + 2:], 44100),
             44100)
    o = HlavniOkno()
    o.pouzij_vzhled(n)
    o.resize(SIRKA, VYSKA)
    o.show()
    o.prepni_rezim("stul")
    o.otevri_nahravky([str(tmp / "HH00077 (1).wav")])
    cekej(lambda: not (o.ukol and o.ukol.isRunning()))
    o.tabulka.selectRow(0)
    o.akce_uprava.setChecked(True)
    o.osa._nastav_rozsah(t - 0.004, t + 0.004)
    uloz(o, "uprava_pred")
    o._uprava_signalu(t, False)
    uloz(o, "uprava_po")
    o.akce_uprava.setChecked(False)
    o.close()

    # ---------------------------------------------------------------- dávky
    o = HlavniOkno()
    o.pouzij_vzhled(n)
    o.resize(SIRKA, VYSKA)
    o.show()
    o.prepni_rezim("davky")
    d = o.davky
    d.vystup.setText(str(tmp / "archiv"))
    d.auto_export.setChecked(False)
    d.pridej([RH / "RH07860 (A).wav", RH / "RH07860 (B).wav", HH])
    d.spust()
    cekej(lambda: not d.bezi(), 900)
    d.tabulka.selectRow(1)
    uloz(o, "davky")
    o.close()

    # ---------------------------------------------------------------- o aplikaci
    from sakra.gui.o_aplikaci import DialogOAplikaci
    da = DialogOAplikaci(None, lambda: None)
    da.show()
    uloz(da, "o_aplikaci")
    da.close()

    # ---------------------------------------------------------------- nastavení
    dn = DialogNastaveni(n)
    dn.show()
    uloz(dn, "nastaveni")
    dn.close()
    print("Snímky:", OBRAZKY)
    os._exit(0)                                   # bez úklidu Qt (offscreen občas spadne při ukončení)


if __name__ == "__main__":
    main()
