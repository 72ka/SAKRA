"""Export a import metadat v Excelu podle vzoru Herního archivu.

List „List 1“ má přesně rozložení vzoru (HH08518.xlsx). Technické údaje SAKRA jsou na listu „SAKRA“.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

from .. import AUTORSTVI, __version__
from ..jadro.analyza import popis_stavu
from ..jadro.model import TURBA, Kazeta, Strana, Zaznam, cas_text, cas_z_textu
from . import sablona as S

TENKA = Side(style="thin")
RAMECEK = Border(left=TENKA, right=TENKA, top=TENKA, bottom=TENKA)
RAMECEK_ZAHLAVI = Border(left=TENKA, right=TENKA, top=TENKA)


def _vypln(barva: str) -> PatternFill:
    return PatternFill("solid", fgColor="FF" + barva)


def _bunka(ws, adresa, hodnota=None, tucne=False, barva=None, ramecek=None, format_=None, zarovnani=None):
    c = ws[adresa]
    if hodnota is not None:
        c.value = hodnota
    c.font = Font(name=S.FONT, size=S.VELIKOST, bold=tucne)
    if barva:
        c.fill = _vypln(barva)
    if ramecek:
        c.border = ramecek
    if format_:
        c.number_format = format_
    if zarovnani:
        c.alignment = Alignment(horizontal=zarovnani)
    return c


def _cislo_nebo_text(s: str):
    s = (s or "").strip()
    return int(s) if s.isdigit() else (s or None)


def exportuj(kazeta: Kazeta, cesta: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = S.LIST
    for sl, w in S.SIRKY.items():
        ws.column_dimensions[sl].width = w
    d, inv = kazeta.digitalizace, kazeta.inventar

    _bunka(ws, "A1", "Digitalizace", tucne=True)
    _bunka(ws, "D1", "Inventář", tucne=True)
    hodnoty_digi = {2: d.tape_deck, 4: d.sound_card, 5: d.di_box, 6: d.vzorkovani, 7: d.format,
                    8: d.datum, 9: d.autor}
    for radek, popisek in S.DIGITALIZACE:
        _bunka(ws, f"A{radek}", popisek, tucne=True, barva=S.BARVA_DIGITALIZACE, ramecek=RAMECEK)
        hod = hodnoty_digi[radek]
        _bunka(ws, f"B{radek}", hod or None, barva=S.BARVA_DIGI_HODNOTA if radek >= 8 else None,
               ramecek=RAMECEK, format_="d/m/yyyy" if radek == 8 else None, zarovnani="left" if radek == 8 else None)
    _bunka(ws, "A3", barva=S.BARVA_DIGITALIZACE, ramecek=RAMECEK, tucne=True)        # druhý řádek Tape-decku
    _bunka(ws, "B3", d.tape_deck_model or None, ramecek=Border(right=TENKA))

    hodnoty_inv = {2: _cislo_nebo_text(inv.puv_transakce), 3: inv.verze_dumpu, 4: inv.verze_metadat}
    for radek, popisek in S.INVENTAR:
        _bunka(ws, f"D{radek}", popisek, tucne=True, barva=S.BARVA_INVENTAR, ramecek=RAMECEK)
        _bunka(ws, f"E{radek}", hodnoty_inv[radek], barva=S.BARVA_INV_HODNOTA, ramecek=RAMECEK,
               format_="d/m" if radek == 4 else None, zarovnani="right")
    _bunka(ws, "D5", "Popis kazety", tucne=True)
    hodnoty_popis = {6: inv.vyrobce, 7: inv.delka_strany, 8: inv.material}
    for radek, popisek in S.POPIS_KAZETY:
        _bunka(ws, f"D{radek}", popisek, tucne=True, barva=S.BARVA_POPIS, ramecek=RAMECEK)
        _bunka(ws, f"E{radek}", hodnoty_popis[radek] or None, ramecek=RAMECEK)

    radek = S.PRVNI_OBSAH
    rozsahy_turba = []
    strany = kazeta.strany or [Strana(1)]
    for strana in strany:
        _bunka(ws, f"A{radek}", f"Obsah ({strana.cislo})", tucne=True)
        radek += 1
        for sl, zahlavi, _ in S.SLOUPCE:
            c = _bunka(ws, f"{sl}{radek}", zahlavi, tucne=True, barva=S.BARVA_HLAVICKA, ramecek=RAMECEK_ZAHLAVI)
            if sl in S.NAPOVEDY:
                c.comment = Comment(S.NAPOVEDY[sl], "SAKRA", width=420, height=260)
        radek += 1
        prvni = radek
        for z in strana.zaznamy:
            for sl, _, pole in S.SLOUPCE:
                hod = getattr(z, pole)
                if pole in ("cas_od", "cas_do"):
                    hod = cas_text(hod)
                barva = S.BARVA_ZVYRAZNENI if sl in z.zvyrazneni else S.BARVA_RADEK
                _bunka(ws, f"{sl}{radek}", hod if hod != "" else None, tucne=(sl == "E"), barva=barva,
                       ramecek=RAMECEK)
            radek += 1
        if radek > prvni:
            rozsahy_turba.append(f"I{prvni}:I{radek - 1}")
    for r in range(1, radek):
        ws.row_dimensions[r].height = S.VYSKA_RADKU
    if rozsahy_turba:
        dv = DataValidation(type="list", formula1='"' + ",".join(TURBA) + '"', allow_blank=True)
        for r in rozsahy_turba:
            dv.add(r)
        ws.add_data_validation(dv)

    _list_sakra(wb.create_sheet("SAKRA"), kazeta)
    wb.properties.creator = f"SAKRA {__version__} ({AUTORSTVI}, Herní archiv)"
    cesta = Path(cesta)
    wb.save(cesta)
    return cesta


def _list_sakra(ws, kazeta: Kazeta) -> None:
    """Technické údaje, které ve vzoru nejsou."""
    zahlavi = ["Strana", "Čas Od", "Čas Do", "Název", "Platforma", "Stav SAKRA", "Bloků", "Chybějící bloky",
               "Opravy", "Rychlost pásky", "Údaje z hlavičky", "Texty v datech", "Výstupní soubory (SHA-1)"]
    ws.append(zahlavi)
    for c in ws[1]:
        c.font = Font(name=S.FONT, bold=True)
        c.fill = _vypln(S.BARVA_HLAVICKA)
    for s in kazeta.strany:
        ws.append([f"Nahrávka strany {s.cislo}: {Path(s.nahravka).name}", None, None,
                   f"{s.vzorkovani}, {s.format}, délka {cas_text(s.delka)}, kanál {s.kanal + 1}"])
        for z in s.zaznamy:
            f = z.soubor
            info = {k: v for k, v in (f.info if f else {}).items() if k not in ("texty", "rychlost")}
            ws.append([s.cislo, cas_text(z.cas_od), cas_text(z.cas_do), z.nazev, z.platforma, z.stav,
                       len(f.bloky) if f else None, ", ".join(map(str, f.chybi)) if f else None,
                       popis_stavu(f) if f else None, f.info.get("rychlost") if f else None,
                       ", ".join(f"{k}={v}" for k, v in info.items()) or None,
                       " | ".join(f.info.get("texty", [])[:8]) if f else None,
                       " ".join(f"{k}:{v}" for k, v in f.vystup.items()) if f else None])
    for sl, w in zip("ABCDEFGHIJKLM", (14, 10, 10, 30, 28, 12, 7, 16, 50, 10, 40, 60, 60)):
        ws.column_dimensions[sl].width = w


# ------------------------------------------------------------------ import

def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _datum(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return None


def importuj(cesta: Path, kazeta: Kazeta | None = None) -> Kazeta:
    """Načte tabulku podle vzoru (i ručně vyplněnou starší). Pole se hledají podle popisků."""
    cesta = Path(cesta)
    wb = load_workbook(cesta)
    ws = wb[S.LIST] if S.LIST in wb.sheetnames else wb.worksheets[0]
    k = kazeta or Kazeta()
    k.inventar.cislo = k.inventar.cislo or cesta.stem
    popisky: dict[str, tuple[int, int]] = {}
    for row in ws.iter_rows(min_row=1, max_row=12):
        for c in row:
            if isinstance(c.value, str):
                popisky.setdefault(c.value.strip(), (c.row, c.column))

    def vedle(popisek, dolu=0):
        if popisek not in popisky:
            return None
        r, s = popisky[popisek]
        return ws.cell(r + dolu, s + 1).value

    d, inv = k.digitalizace, k.inventar
    d.tape_deck, d.tape_deck_model = _text(vedle("Tape-deck")), _text(vedle("Tape-deck", 1))
    d.sound_card, d.di_box = _text(vedle("Sound-card")), _text(vedle("DI-Box"))
    d.vzorkovani, d.format = _text(vedle("Vzorkování")), _text(vedle("Formát"))
    d.datum, d.autor = _datum(vedle("Datum")), _text(vedle("Autor"))
    inv.puv_transakce = _text(vedle("Pův. transakce"))
    try:
        inv.verze_dumpu = int(vedle("Verze dumpu") or 1)
    except (TypeError, ValueError):
        inv.verze_dumpu = 1
    inv.verze_metadat = _datum(vedle("Verze metadat")) or inv.verze_metadat
    inv.vyrobce, inv.delka_strany = _text(vedle("Výrobce")), _text(vedle("Délka strany"))
    inv.material = _text(vedle("Materiál"))

    strana: Strana | None = None
    sloupce: dict[int, str] = {}
    podle_zahlavi = {z.lower(): pole for _, z, pole in S.SLOUPCE}
    for row in ws.iter_rows(min_row=S.PRVNI_OBSAH - 1):
        prvni = row[0].value
        if isinstance(prvni, str) and prvni.strip().lower().startswith("obsah ("):
            try:
                cislo = int(prvni.strip()[7:].rstrip(")"))
            except ValueError:
                cislo = len(k.strany) + 1
            strana = k.strana(cislo)
            strana.zaznamy = []
            sloupce = {}
            continue
        if strana is None:
            continue
        if not sloupce:
            sloupce = {c.column: podle_zahlavi[str(c.value).strip().lower()] for c in row
                       if c.value is not None and str(c.value).strip().lower() in podle_zahlavi}
            continue
        hodnoty = {sloupce[c.column]: c.value for c in row if c.column in sloupce}
        if all(v in (None, "") for v in hodnoty.values()):
            continue
        z = Zaznam()
        for pole, v in hodnoty.items():
            if pole in ("cas_od", "cas_do"):
                setattr(z, pole, cas_z_textu(v))
            else:
                setattr(z, pole, _text(v))
        if z.nazev_bloku.startswith("="):            # ve vzoru vzorec „=E13“
            z.nazev_bloku = z.nazev
        z.zvyrazneni = "".join(c.column_letter for c in row if c.column in sloupce and c.fill is not None
                               and c.fill.fill_type == "solid"
                               and str(c.fill.fgColor.rgb).upper().endswith(S.BARVA_ZVYRAZNENI))
        strana.zaznamy.append(z)
    return k
