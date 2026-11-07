"""Archivní balíček (dump) kazety: složka pojmenovaná inventárním číslem.

    HH08518/
      HH08518.xlsx  HH08518.json  protokol.html  SHA1SUMS
      zdroj/HH08518-1.flac (nebo .wav, je-li zdroj v plovoucí řádové čárce)
      1-01 Název.csw|tap|tzx  1-01 Název.wav  (+ .bin s daty)
      nerozpoznane/…   nahledy/ (fotky kazety)   protokol.pdf
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf

from . import AUTOR, AUTORSTVI, PODPIS, PREZDIVKA, ROK, URCENI, WEB, __version__
from .formaty import csw
from .jadro.analyza import VysledekStrany, popis_stavu
from .jadro.model import Kazeta, cas_text, kazeta_do_json
from .metadata import excel
from .platformy import podle_id

OKRAJ_S = 0.5     # kolik přidat před a za program při výřezu WAV
ZAKAZANE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def bezpecne_jmeno(s: str, nejvic: int = 80) -> str:
    s = ZAKAZANE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s[:nejvic] or "bez jména"


def sha1(cesta: Path) -> str:
    h = hashlib.sha1()
    with open(cesta, "rb") as f:
        for kus in iter(lambda: f.read(1 << 20), b""):
            h.update(kus)
    return h.hexdigest()


def _vyrez_wav(zdroj: Path, cil: Path, od: float, do: float) -> None:
    info = sf.info(str(zdroj))
    a = max(0, int((od - OKRAJ_S) * info.samplerate))
    b = min(info.frames, int((do + OKRAJ_S) * info.samplerate))
    data, rate = sf.read(str(zdroj), start=a, stop=b, dtype="float32" if "FLOAT" in info.subtype else "int32",
                         always_2d=True)
    subtype = info.subtype if info.subtype in sf.available_subtypes("WAV") else "PCM_16"
    sf.write(str(cil), data, rate, subtype=subtype, format="WAV")


def _zdroj(zdroj: Path, cil_bez_pripony: Path) -> Path:
    """Bezztrátová kopie nahrávky: FLAC, pokud to formát dovolí (FLAC neumí float), jinak kopie WAV."""
    info = sf.info(str(zdroj))
    if info.subtype in ("PCM_16", "PCM_24", "PCM_S8", "PCM_U8") and info.channels <= 8:
        cil = cil_bez_pripony.with_suffix(".flac")
        with sf.SoundFile(str(zdroj)) as f, sf.SoundFile(str(cil), "w", info.samplerate, info.channels,
                                                          subtype=info.subtype if info.subtype != "PCM_U8" else "PCM_S8",
                                                          format="FLAC") as g:
            for blok in f.blocks(blocksize=1 << 18, dtype="int32", always_2d=True):
                g.write(blok)
        return cil
    cil = cil_bez_pripony.with_suffix(zdroj.suffix.lower() or ".wav")
    shutil.copyfile(zdroj, cil)
    return cil


def _cisty_wav(cil: Path, rate: int, runy: list[int], uroven: int) -> None:
    """Čistý obdélníkový signál z délek pulzů; dlouhé pulzy (pauzy) jsou ticho."""
    mez = rate // 200
    kusy = []
    u = 1 if uroven else -1
    for n in runy:
        kusy.append(np.full(int(n), 0 if n > mez else u * 0.7, np.float32))
        u = -u
    sf.write(str(cil), np.concatenate(kusy) if kusy else np.zeros(1, np.float32), rate, subtype="PCM_16")


def exportuj(kazeta: Kazeta, kam: Path, vysledky: dict[int, VysledekStrany] | None = None,
             prubeh=None, kopirovat_zdroj: bool = True, cisty_wav: bool = False, pdf: bool = True,
             snimky: bool = True, sbalit_7z: bool = False) -> Path:
    """`cisty_wav`: WAV programů jako čistý signál (kde ho platforma umí vytvořit); u opravených programů
    se čistý signál použije vždy a výřez nahrávky se uloží vedle jako „(původní)“.
    `snimky`: u ZX Spectra spustit program v emulátoru a uložit obrazovku po spuštění (a nahrávací obrazovku).
    `sbalit_7z`: výsledkem je jeden soubor <inventární číslo>.7z (uvnitř stejná složka), složka se pak smaže.
    Vrací složku balíčku, nebo soubor .7z."""
    pr_cely = prubeh or (lambda x, t="": None)
    # se 7z zabere balení (LZMA2) většinu času – průběh: export 0–40 %, balení 40–100 %
    pr = (lambda x, t="": pr_cely(0.4 * x, t)) if sbalit_7z else pr_cely
    vysledky = vysledky or {}
    inv = bezpecne_jmeno(kazeta.inventar.cislo or "kazeta")
    d = Path(kam) / inv
    d.mkdir(parents=True, exist_ok=True)
    (d / "zdroj").mkdir(exist_ok=True)
    celkem = sum(len(s.zaznamy) for s in kazeta.strany) + len(kazeta.strany) + 1
    hotovo = 0

    for s in kazeta.strany:
        zdroj = Path(s.nahravka) if s.nahravka else None
        if kopirovat_zdroj and zdroj and zdroj.exists():
            pr(hotovo / celkem, f"Kopie nahrávky strany {s.cislo}")
            _zdroj(zdroj, d / "zdroj" / f"{inv}-{s.cislo}")
        hotovo += 1
        for i, z in enumerate(s.zaznamy, 1):
            pr(hotovo / celkem, f"Strana {s.cislo}: {z.nazev}")
            hotovo += 1
            zaklad = f"{s.cislo}-{i:02d} {bezpecne_jmeno(z.nazev)}"
            if z.soubor is not None:
                if z.funkcni_edit == "Ne":     # podle vzoru: nefunkční program nemá v dumpu vlastní soubory
                    continue
                pl = podle_id(z.soubor.platforma)
                vystupy = pl.zapis(z.soubor, d / zaklad) if pl else []
                if snimky and pl is not None and hasattr(pl, "snimky") and z.soubor.ok:
                    pr(hotovo / celkem, f"Strana {s.cislo}: {z.nazev} – spouštím v emulátoru")
                    try:
                        from .platformy.zx import zapis_snimky
                        vystupy += zapis_snimky(z.soubor, d / zaklad)
                    except Exception as e:  # noqa: BLE001 – snímek je doplněk
                        z.soubor.info["poznamka_emulace"] = f"emulace selhala: {e}"
                cisty = pl is not None and hasattr(pl, "runy") and (cisty_wav or z.soubor.opraveno)
                if cisty:
                    runy, uroven = pl.runy(z.soubor)
                    w = d / (zaklad + ".wav")
                    _cisty_wav(w, pl.RATE, runy, uroven)
                    vystupy.append(w)
                if zdroj and zdroj.exists() and z.cas_od is not None and z.cas_do is not None:
                    w = d / (zaklad + (" (původní).wav" if cisty else ".wav"))
                    _vyrez_wav(zdroj, w, min(z.cas_od, z.soubor.zacatek_signalu), z.cas_do)
                    vystupy.append(w)
                z.soubor.vystup = {p.name: sha1(p) for p in vystupy}
            elif z.nerozpoznano and z.cas_od is not None and z.cas_do is not None:
                n = d / "nerozpoznane"
                n.mkdir(exist_ok=True)
                jm = f"{s.cislo}-{i:02d} ({'zvuk' if z.typ == 'Audio' else 'nerozpoznáno'}) " \
                     f"{int(z.cas_od // 60)}m{int(z.cas_od % 60):02d}s"
                v = vysledky.get(s.cislo)
                if z.typ != "Audio":
                    if v is not None:
                        _csw_useku(v, n / f"{jm}.csw", z.cas_od, z.cas_do)
                    elif zdroj and zdroj.exists():       # projekt bez analýzy v paměti – pulzy z nahrávky
                        _csw_z_nahravky(zdroj, s.kanal, n / f"{jm}.csw", z.cas_od, z.cas_do)
                if zdroj and zdroj.exists():
                    _vyrez_wav(zdroj, n / f"{jm}.wav", z.cas_od, z.cas_do)

    fotky = []
    if kazeta.fotky:
        (d / "nahledy").mkdir(exist_ok=True)
        for i, f in enumerate(kazeta.fotky, 1):
            f = Path(f)
            if f.exists():
                cil = d / "nahledy" / f"{inv}-foto-{i}{f.suffix.lower()}"
                shutil.copyfile(f, cil)
                fotky.append(cil.relative_to(d).as_posix())
    pr(hotovo / celkem, "Metadata")
    excel.exportuj(kazeta, d / f"{inv}.xlsx")
    meta = kazeta_do_json(kazeta)
    meta["sakra"] = {"verze": __version__, "autor": f"{AUTOR} ({PREZDIVKA})", "rok": ROK,
                     "urceni": URCENI, "web": WEB}
    (d / f"{inv}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "protokol.html").write_text(protokol(kazeta, fotky), encoding="utf-8")
    if pdf:
        try:
            protokol_pdf(kazeta, fotky, d / "protokol.pdf", d)
        except Exception as e:  # noqa: BLE001 – PDF je doplněk, balíček je hotový i bez něj
            (d / "protokol.pdf.chyba.txt").write_text(f"PDF protokol se nepodařilo vytvořit: {e}\n", encoding="utf-8")
    soubory = sorted(p for p in d.rglob("*") if p.is_file() and p.name != "SHA1SUMS")
    (d / "SHA1SUMS").write_text("".join(f"{sha1(p)}  {p.relative_to(d).as_posix()}\n" for p in soubory),
                                encoding="utf-8")
    if sbalit_7z:
        d = sbal_7z(d, lambda x, t="": pr_cely(0.4 + 0.6 * x, t))
    pr_cely(1.0, "Hotovo")
    return d


def sbal_7z(slozka: Path, prubeh=None) -> Path:
    """Složku zabalí do <jméno>.7z vedle ní (uvnitř je složka i s cestami, komprese LZMA2) a složku smaže.
    Archiv se píše do dočasného souboru a přejmenuje až hotový – nepovedené balení nic nepřepíše ani nesmaže.
    Průběh podle objemu zabalených dat."""
    import py7zr
    pr = prubeh or (lambda x, t="": None)
    cil = slozka.parent / f"{slozka.name}.7z"
    docasny = slozka.parent / f".{slozka.name}.7z.tmp"
    polozky = sorted(slozka.rglob("*"))
    celkem = max(1, sum(p.stat().st_size for p in polozky if p.is_file()))
    hotovo = 0
    try:
        with py7zr.SevenZipFile(docasny, "w") as z:
            z.write(slozka, slozka.name)
            for p in polozky:
                pr(hotovo / celkem, f"Balím do 7z: {hotovo * 100 // celkem} %")
                z.write(p, f"{slozka.name}/{p.relative_to(slozka).as_posix()}")
                if p.is_file():
                    hotovo += p.stat().st_size
        docasny.replace(cil)
    finally:
        docasny.unlink(missing_ok=True)
    shutil.rmtree(slozka)
    return cil


def _csw_useku(v: VysledekStrany, cil: Path, od: float, do: float) -> None:
    p = v.pulzy
    a, b = np.searchsorted(p.hrany, [od * p.rate, do * p.rate])
    if b - a < 2:
        return
    csw.zapis(cil, p.rate, np.diff(p.hrany[a:b]).tolist(), 1 if p.urovne[a] > 0 else 0)


def _csw_z_nahravky(zdroj: Path, kanal: int, cil: Path, od: float, do: float) -> None:
    from .jadro.pulzy import najdi_pulzy
    info = sf.info(str(zdroj))
    a, b = int(od * info.samplerate), int(do * info.samplerate)
    x, rate = sf.read(str(zdroj), start=max(0, a), stop=min(info.frames, b), dtype="float32", always_2d=True)
    x = x.mean(axis=1) if kanal < 0 else x[:, min(kanal, x.shape[1] - 1)]     # -1 = součet stop
    x = x - float(np.mean(x)) if len(x) else x
    m = float(np.max(np.abs(x))) if len(x) else 0.0
    p = najdi_pulzy((x / m * 30000).astype(np.int16) if m else x.astype(np.int16), rate)
    if len(p.hrany) >= 2:
        csw.zapis(cil, rate, np.diff(p.hrany).tolist(), 1 if p.urovne[0] > 0 else 0)


def protokol(k: Kazeta, fotky: list[str] | None = None, pro_tisk: bool = False) -> str:
    """Čitelný protokol (HTML); `pro_tisk` = jednodušší styl pro převod do PDF."""
    e = html.escape
    i, d = k.inventar, k.digitalizace
    radky = []
    for s in k.strany:
        zdroj = (f"{e(Path(s.nahravka).name)} · {e(s.vzorkovani)} · {e(s.format)} · {cas_text(s.delka)}"
                 if s.nahravka else "bez nahrávky (údaje z tabulky)")
        radky.append(f"<h2>Obsah ({s.cislo})</h2><p class=m>{zdroj}</p>"
                     f"<table class=o cellspacing=0 cellpadding=3 width='100%'>"
                     "<tr><th>Od</th><th>Do</th><th>Platforma</th><th>Název</th><th>Obsah</th>"
                     "<th>Funkční (Orig./Edit)</th><th>Stav SAKRA</th><th>Poznámky</th></tr>")
        for z in s.zaznamy:
            stav = z.stav
            barva = {"ok": "ok", "opraveno": "op", "neověřeno": "nv", "chyba": "ch", "žádná data": "nv"}.get(stav, "")
            tech = popis_stavu(z.soubor) if z.soubor else ""
            radky.append(f"<tr><td>{cas_text(z.cas_od)}</td><td>{cas_text(z.cas_do)}</td><td>{e(z.platforma)}</td>"
                         f"<td><b>{e(z.nazev)}</b></td><td>{e(z.obsah)}</td><td>{e(z.funkcni_orig)} / "
                         f"{e(z.funkcni_edit)}</td><td class={barva}>{e(stav)}</td>"
                         f"<td>{e(z.poznamky or tech)}</td></tr>")
        radky.append("</table>")
    datum = f"{d.datum.day}. {d.datum.month}. {d.datum.year}" if d.datum else ""
    hlav = [("Tape-deck", f"{d.tape_deck} {d.tape_deck_model}"), ("Pův. transakce", i.puv_transakce),
            ("Sound-card", d.sound_card), ("Verze dumpu", str(i.verze_dumpu)),
            ("DI-Box", d.di_box), ("Výrobce", i.vyrobce),
            ("Vzorkování", f"{d.vzorkovani}, {d.format}"), ("Délka strany", i.delka_strany),
            ("Datum", datum), ("Materiál", i.material), ("Autor", d.autor), ("", "")]
    hl = "".join(f"<tr><td class=k>{e(a)}</td><td>{e(b)}</td><td class=k>{e(c)}</td><td>{e(dd)}</td></tr>"
                 for (a, b), (c, dd) in zip(hlav[0::2], hlav[1::2]))
    obr = "".join(f"<img src='{e(f)}' height=180 style='margin:0 8px 8px 0'>" for f in (fotky or []))
    styl = """body{font:13px/1.45 Arial,sans-serif;margin:24px;color:#222}h1{margin:0 0 4px}.m{color:#666;margin:2px 0 8px}
table.o{border-collapse:collapse;width:100%;margin-bottom:18px}table.o th,table.o td{border:1px solid #bbb;padding:3px 6px;
text-align:left;vertical-align:top}table.o th{background:#F6B26B}table.o td{background:#FCE5CD}.ok{color:#1b7a3d}
.op{color:#a86400}.ch{color:#b3261e;font-weight:bold}.nv{color:#3a6ea5}table.h{margin:12px 0 18px}
table.h td{padding:1px 14px 1px 0}td.k{color:#666}.pata{color:#888;font-size:11px;margin-top:14px}"""
    if pro_tisk:
        styl = styl.replace("13px", "9pt").replace("margin:24px", "margin:0")
    return f"""<!doctype html><html lang="cs"><head><meta charset="utf-8"><title>Protokol {e(i.cislo)}</title>
<style>{styl}</style></head><body><h1>Kazeta {e(i.cislo)}</h1><p class=m>Protokol digitalizace · SAKRA {__version__}</p>
<table class=h cellspacing=0>{hl}</table>{('<p>' + obr + '</p>') if obr else ''}
{''.join(radky)}<p class=pata>{e(PODPIS)}</p></body></html>"""


def protokol_pdf(k: Kazeta, fotky: list[str], cil: Path, zaklad: Path) -> None:
    """PDF z protokolu přes Qt (QTextDocument + QPdfWriter, A4 na šířku)."""
    import os

    from PySide6.QtCore import QMarginsF, QUrl
    from PySide6.QtGui import QGuiApplication, QPageLayout, QPageSize, QPdfWriter, QTextDocument

    if QGuiApplication.instance() is None:           # příkazová řádka bez okna
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        protokol_pdf._app = QGuiApplication(["sakra"])  # type: ignore[attr-defined]
    w = QPdfWriter(str(cil))
    w.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Landscape,
                                QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter))
    w.setResolution(150)
    w.setTitle(f"Protokol {k.inventar.cislo}")
    w.setCreator(f"SAKRA {__version__} – {AUTORSTVI}, pro Herní archiv ({WEB})")
    doc = QTextDocument()
    doc.setBaseUrl(QUrl.fromLocalFile(str(Path(zaklad).resolve()) + "/"))
    doc.setHtml(protokol(k, fotky, pro_tisk=True))
    doc.print_(w)
