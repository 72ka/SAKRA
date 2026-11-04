"""TZX v1.20 (standardní bloky ID 10h, turbo bloky ID 11h – také CDT pro Amstrad CPC) a TAP pro ZX Spectrum."""
from __future__ import annotations

import struct
from pathlib import Path


def zapis_tzx(cesta: Path, bloky: list[bytes], pauza_ms: int = 1000, popis: str = "") -> None:
    out = bytearray(b"ZXTape!\x1a\x01\x14")
    if popis:
        t = popis.encode("ascii", "replace")[:255]
        out += bytes([0x30, len(t)]) + t                      # ID 30h – textový popis
    for b in bloky:
        out += bytes([0x10]) + struct.pack("<HH", pauza_ms, len(b)) + b
    Path(cesta).write_bytes(bytes(out))


def zapis_tzx_turbo(cesta: Path, bloky: list[tuple[bytes, dict | None]], popis: str = "") -> None:
    """Bloky ID 11h s vlastním časováním (v taktech 3,5 MHz): klíče pilot, pilot_pocet, sync1, sync2,
    nula, jedna, pauza_ms. Blok s časováním None se zapíše jako standardní (ID 10h)."""
    out = bytearray(b"ZXTape!\x1a\x01\x14")
    if popis:
        t = popis.encode("ascii", "replace")[:255]
        out += bytes([0x30, len(t)]) + t
    for data, c in bloky:
        if c is None:
            out += bytes([0x10]) + struct.pack("<HH", 1000, len(data)) + data
            continue
        out += bytes([0x11]) + struct.pack("<HHHHHHBH", *(min(0xFFFF, max(1, int(round(c[k])))) for k in (
            "pilot", "sync1", "sync2", "nula", "jedna", "pilot_pocet")), 8, int(c.get("pauza_ms", 1000)))
        out += struct.pack("<I", len(data))[:3] + data
    Path(cesta).write_bytes(bytes(out))


def zapis_tap(cesta: Path, bloky: list[bytes]) -> None:
    out = bytearray()
    for b in bloky:
        out += struct.pack("<H", len(b)) + b
    Path(cesta).write_bytes(bytes(out))


def nacti_tap(cesta: Path) -> list[bytes]:
    d = Path(cesta).read_bytes()
    out, p = [], 0
    while p + 2 <= len(d):
        n = struct.unpack_from("<H", d, p)[0]
        out.append(d[p + 2:p + 2 + n])
        p += 2 + n
    return out


def nacti_tzx(cesta: Path) -> list[bytes]:
    """Jen standardní bloky (10h); ostatní typy přeskočí, pokud znají délku."""
    d = Path(cesta).read_bytes()
    if not d.startswith(b"ZXTape!\x1a"):
        raise ValueError("není TZX")
    p, out = 10, []
    while p < len(d):
        i = d[p]
        p += 1
        if i == 0x10:
            n = struct.unpack_from("<H", d, p + 2)[0]
            out.append(d[p + 4:p + 4 + n])
            p += 4 + n
        elif i == 0x11:
            n = struct.unpack_from("<I", d, p + 15)[0] & 0xFFFFFF
            out.append(d[p + 18:p + 18 + n])
            p += 18 + n
        elif i == 0x30:
            p += 1 + d[p]
        elif i == 0x20:
            p += 2
        else:
            raise ValueError(f"TZX blok {i:02X} zatím neumím přeskočit")
    return out
