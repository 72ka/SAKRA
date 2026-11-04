"""Školský mikropočítačový systém ŠMS VÚVT Žilina (8080) – kazetopáskový modem Kansas City.

Podle Příručky operátora (Datasystém 1982, kap. 2.11.1): „1“ = 2400 Hz, „0“ = 1200 Hz, standardně 300 Bd
(bit 0 = 4 periody 1200 Hz, bit 1 = 8 period 2400 Hz). Každý bajt: start bit 0, 8 bitů od LSB, 3 stop bity 1
(25 B/s). Každý záznam začíná „referenčním hvizdem“ (2400 Hz). Na pásce není jméno, adresa ani kontrolní
součet – adresy se namlouvaly do mikrofonu před záznamem. Programy se proto obvykle ukládaly dvakrát:
shodná kopie záznam ověří, rozdílné bajty se opraví z kopie, kde je rámec v pořádku.
"""
from __future__ import annotations

import difflib
from pathlib import Path

import numpy as np

from ..jadro.model import Blok, Soubor
from ..jadro.pulzy import Usek
from ..jadro.signaly import behy_us
from ..jadro.texty import hex_vypis, texty
from .zaklad import Kontext, Platforma, podil_v_pasmu, pripona

PUL_1 = 1e6 / 2400 / 2       # půlvlna 2400 Hz: 208 µs
BIT_PULVLN = 16              # bit = 16 půlvln 2400 Hz (8 period) = 8 půlvln 1200 Hz (4 periody) při 300 Bd
STOP_BITU = 3
MIN_HVIZD = 60               # bitů „1“ před záznamem (0,2 s referenčního hvizdu)
MIN_BAJTU = 4
MAX_VYPADEK_S = 0.3         # kratší mezera v signálu je výpadek uvnitř záznamu


def bity_kcs(r: np.ndarray) -> tuple[str, np.ndarray, float]:
    """Půlvlny (µs) -> bity podle doby úseků stejného kmitočtu. Vrací (bity, čas začátku bitu v µs od
    začátku úseku, délka bitu µs). Doba místo počtu půlvln: přechodové půlvlny mezi kmitočty nevadí."""
    kratke = r[(r > 0.5 * PUL_1) & (r < 1.4 * PUL_1)]
    s = float(np.median(kratke)) if len(kratke) > 50 else PUL_1           # skutečná rychlost pásky
    trida = (r < 1.5 * s).astype(np.int8)                                  # 1 = 2400 Hz, 0 = 1200 Hz
    dlouhe = r[(r >= 1.5 * s) & (r < 3 * s)]
    # délka bitu zvlášť pro každý kmitočet (1200 Hz na pásce nebývá přesně polovina 2400 Hz)
    T1 = BIT_PULVLN * s
    T0 = BIT_PULVLN / 2 * float(np.median(dlouhe)) if len(dlouhe) > 50 else T1
    hrany = np.flatnonzero(np.diff(trida)) + 1
    zac = np.concatenate(([0], hrany))
    kon = np.concatenate((hrany, [len(r)]))
    cas = np.concatenate(([0.0], np.cumsum(r)))
    bity: list[str] = []
    casy: list[float] = []
    for a, b in zip(zac, kon):
        T = T1 if trida[a] else T0
        n = int((cas[b] - cas[a]) / T + 0.5)
        if n > 0:
            bity.append(("1" if trida[a] else "0") * n)
            casy.extend(cas[a] + (cas[b] - cas[a]) / n * np.arange(n))
    T = (T0 + T1) / 2
    return "".join(bity), np.array(casy), T


def _je_300bd(r: np.ndarray) -> bool:
    """Rozlišení od MSX/Acorn (stejné kmitočty): tam je bit 0 jediná perioda 1200 Hz (2 půlvlny),
    při 300 Bd čtyři periody – úseky 1200 Hz mají typicky 8, 16, 24… půlvln."""
    kratke = r[(r > 0.5 * PUL_1) & (r < 1.4 * PUL_1)]
    s = float(np.median(kratke)) if len(kratke) > 50 else PUL_1
    trida = (r < 1.5 * s).astype(np.int8)
    hrany = np.flatnonzero(np.diff(trida)) + 1
    delky = np.diff(np.concatenate(([0], hrany, [len(r)])))
    nizke = delky[[trida[i] == 0 for i in np.concatenate(([0], hrany))]]
    return len(nizke) > 20 and float(np.median(nizke)) >= 6


def zaznamy_kcs(bity: str) -> list[tuple[int, list[int], list[bool], bool]]:
    """Záznamy = bajty za referenčním hvizdem. Vrací [(index bitu začátku, bajty, rámec v pořádku, celý)];
    celý = False, když záznam skončil sérií chybných rámců (výpadek, poškozená páska)."""
    out = []
    i, n = 0, len(bity)
    hvizd = "1" * MIN_HVIZD
    while True:
        k = bity.find(hvizd, i)
        if k < 0:
            break
        i = k + MIN_HVIZD
        while i < n and bity[i] == "1":                                    # konec hvizdu
            i += 1
        zac = i
        hod: list[int] = []
        ok: list[bool] = []
        chyb_po_sobe = 0
        cely = True
        while i + 9 < n:
            if bity[i] != "0":                                             # klid mezi bajty
                j = i
                while j < n and bity[j] == "1":
                    j += 1
                if j - i >= MIN_HVIZD:                                     # další záznam
                    break
                i = j
                continue
            v = int(bity[i + 1:i + 9][::-1], 2)
            stop = bity[i + 9:i + 9 + STOP_BITU]
            dobry = stop[:1] == "1"                                        # aspoň první stop bit
            hod.append(v)
            ok.append(dobry)
            chyb_po_sobe = 0 if dobry else chyb_po_sobe + 1
            if chyb_po_sobe >= 4:                                          # šum, řeč – konec záznamu
                del hod[-4:], ok[-4:]
                cely = False
                break
            i += 9 + (1 if dobry else 0)
        if len(hod) >= MIN_BAJTU and sum(ok) >= 0.9 * len(ok):
            out.append((zac, hod, ok, cely))
    return out


class SMS(Platforma):
    id = "sms-vuvt"
    pocitac = "ŠMS VÚVT"
    varianta = ""
    barva = "#B07CC6"
    pripona = "bin"
    poradi = 44                  # před MSX (stejné kmitočty, jiná rychlost)

    def skore(self, usek: Usek, rate: int) -> float:
        h = usek.histogram
        return 0.7 if podil_v_pasmu(h, 150, 500) > 0.8 and podil_v_pasmu(h, 150, 280) > 0.3 else 0.0

    def dekoduj(self, ktx: Kontext, useky: list[Usek]) -> list[Soubor]:
        p = ktx.pulzy
        zaznamy: list[Soubor] = []
        # úseky oddělené krátkým výpadkem (do 0,3 s) patří k jednomu záznamu
        skupiny: list[list[Usek]] = []
        for u in sorted(useky, key=lambda x: x.zacatek):
            if skupiny and u.zacatek - skupiny[-1][-1].konec < MAX_VYPADEK_S:
                skupiny[-1].append(u)
            else:
                skupiny.append([u])
        for sk in skupiny:
            u = Usek(sk[0].i0, sk[-1].i1, sk[0].zacatek, sk[-1].konec)
            r = behy_us(p, u.i0, u.i1)
            if len(r) < 2000:
                continue
            if not _je_300bd(r):
                continue
            bity, casy, T = bity_kcs(r)
            t0 = p.cas(u.i0)
            for zac, hod, ok, cely in zaznamy_kcs(bity):
                konec_bitu = zac + len(hod) * (9 + STOP_BITU)
                a = t0 + casy[min(zac, len(casy) - 1)] / 1e6
                b = t0 + casy[min(konec_bitu, len(casy) - 1)] / 1e6 + T / 1e6
                blok = Blok(a, b, "data", None, bytes(hod), all(ok) and cely,
                            chybne_bajty=[i for i, x in enumerate(ok) if not x])
                blok.useknuto = not cely  # type: ignore[attr-defined]
                blok.info_rychlost = 300 * (BIT_PULVLN * PUL_1) / T  # type: ignore[attr-defined]
                s = Soubor(self.id, "", "", "Data", bloky=[blok], overeno=False)
                zaznamy.append(s)
        _over_kopiemi(zaznamy)
        for s in zaznamy:
            self.dokonci(s)
        return zaznamy

    def dokonci(self, s: Soubor) -> None:
        b = s.bloky[0]
        n = len(b.data)
        s.nazev = s.nazev or f"(záznam {n} B)"
        s.typ_bloku = "Data (Kansas City)"
        s.kompletni = b.ok
        s.chybi = []
        s.info.update({"delka_dat": n, "bloku": 1, "texty": texty(b.data),
                       "rychlost_bd": round(getattr(b, "info_rychlost", 300)),
                       "poznamka": "Adresa ukládání a spuštění není na pásce – bývá namluvená před záznamem."})
        if s.overeno:
            s.info["kopie"] = "shodná kopie na pásce"

    def zapis(self, s: Soubor, cil: Path) -> list[Path]:
        out = pripona(cil, ".bin")
        out.write_bytes(s.bloky[0].data)
        return [out]

    def nahled(self, s: Soubor) -> dict:
        d = s.bloky[0].data
        return {"obrazky": [], "texty": [("Začátek dat", hex_vypis(d[:256]) + (f"\n… celkem {len(d)} B"
                                                                              if len(d) > 256 else ""))]}


def _oprav_z(blok: Blok, druhy: Blok) -> bool:
    """Opraví chybné rámce bloku podle druhé kopie (zarovnání – výpadek mohl bajt přidat nebo ubrat).
    Mění blok jen tam, kde má chybný rámec a druhá kopie je v pořádku. Vrací True, pokud něco opravil."""
    chyby, chyby2 = set(blok.chybne_bajty), set(druhy.chybne_bajty)
    if not chyby:
        return False
    sm = difflib.SequenceMatcher(None, blok.data, druhy.data, autojunk=False)
    vysledek = bytearray()
    zbyvajici: list[int] = []
    opraveno = 0
    for op, a0, a1, b0, b1 in sm.get_opcodes():
        if op == "equal":
            vysledek += blok.data[a0:a1]
            for i in range(a0, a1):
                if i in chyby:
                    if b0 + (i - a0) in chyby2:
                        zbyvajici.append(len(vysledek) - (a1 - i))
                    else:
                        opraveno += 1                  # chybný rámec, ale hodnotu potvrzuje druhá kopie
            continue
        moje_chybne = any(i in chyby for i in range(a0, a1)) or a0 == a1 and (a0 - 1 in chyby or a0 in chyby)
        jeho_dobre = not any(i in chyby2 for i in range(b0, b1))
        if op in ("replace", "delete", "insert") and moje_chybne and jeho_dobre and a1 < len(blok.data) + 1 \
                and not (op == "insert" and a0 == len(blok.data)):
            vysledek += druhy.data[b0:b1]
            opraveno += max(a1 - a0, b1 - b0)
        else:
            vysledek += blok.data[a0:a1]
            zbyvajici += [len(vysledek) - (a1 - i) for i in range(a0, a1) if i in chyby]
    if not opraveno:
        return False
    blok.data = bytes(vysledek)
    blok.chybne_bajty = zbyvajici
    blok.ok = not zbyvajici and not getattr(blok, "useknuto", False)
    blok.oprava = f"{opraveno} B z druhé kopie na pásce"
    return True


def _over_kopiemi(zaznamy: list[Soubor]) -> None:
    """Sousední záznamy jsou obvykle dvě kopie téhož programu: chybné rámce se opraví z druhé kopie (zarovnání
    podle obsahu) a po opravě shodné kopie se označí jako ověřené (formát sám kontrolní součet nemá)."""
    for a, b in zip(zaznamy, zaznamy[1:]):
        ba, bb = a.bloky[0], b.bloky[0]
        m = min(len(ba.data), len(bb.data))
        if m < MIN_BAJTU:
            continue
        # jen opravdu kopie: velká část obsahu stejná
        if difflib.SequenceMatcher(None, ba.data[:4096], bb.data[:4096], autojunk=False).ratio() < 0.8:
            continue
        _oprav_z(ba, bb)
        _oprav_z(bb, ba)
        if ba.data == bb.data and ba.ok and bb.ok:
            a.overeno = b.overeno = True
        elif len(ba.data) == len(bb.data):
            rozdil = [i for i in range(m) if ba.data[i] != bb.data[i]]
            if rozdil:                                     # bez součtu nejde rozhodnout, která kopie je správně
                text = (f"liší se od sousední kopie v {len(rozdil)} B (pozice "
                        + ", ".join(str(i) for i in rozdil[:8]) + (" …" if len(rozdil) > 8 else "") + ")")
                a.info["kopie"] = b.info["kopie"] = text
