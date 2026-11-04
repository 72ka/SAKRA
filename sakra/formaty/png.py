"""Minimální zápis PNG (RGB, bez závislostí) – náhledy obrazovek z dat."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np


def zapis(cesta: Path, rgb: np.ndarray) -> None:
    """`rgb` = pole (výška, šířka, 3) uint8."""
    v, s, _ = rgb.shape
    radky = b"".join(b"\0" + rgb[y].astype(np.uint8).tobytes() for y in range(v))

    def kus(typ: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + typ + data + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    Path(cesta).write_bytes(b"\x89PNG\r\n\x1a\n" + kus(b"IHDR", struct.pack(">IIBBBBB", s, v, 8, 2, 0, 0, 0))
                            + kus(b"IDAT", zlib.compress(radky, 9)) + kus(b"IEND", b""))
