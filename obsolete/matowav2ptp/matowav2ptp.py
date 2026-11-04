#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
matowav2ptp.py
==================

Nástroj pro dekódování Maťo programů z audio záznamu (.wav).

Autor: Jan Heřman (72ka)
Licence: MIT
Repozitář: https://github.com/72ka/matowav2ptp

Použití:
    python zx81fastwav2p.py vstupnisoubor.wav

Výstup:
    vytvoří soubor .ptp s dekódovanými Maťo programy
    
"""

import wave
import numpy as np
import argparse
import struct
import re
import sys

ap = argparse.ArgumentParser(description="Maťo převodník WAW->PTP, (c) 2025 Jan Heřman, github.com/72ka, 2hp@seznam.cz")
ap.add_argument("in_wav", help="vstupní WAV soubor nejlépe 22.5kHz mono")
ap.add_argument("out_file", help="výstupní PTP soubor")

# signál
ap.add_argument("--invert", action="store_true", help="invertovat logickou polaritu signálu")

# rozlišení bitů
ap.add_argument("--samples-thresh", type=int, default=26, help="hranice (v počtu vzorků mezi nul. přechody) pro rozlišení 0/1, normálně 26")

# formát bloků
ap.add_argument("--start-bits", type=int, default=1, help="počet start bitů před KAŽDÝM bajtem, snad standard 1")
ap.add_argument("--start-bit-value", type=int, default=1, choices=[0,1], help="hodnota start bitu, normálně 1")

# výstup
ap.add_argument("--debug", action="store_true")

args = ap.parse_args()

print(f"********************************************")
print(f"Maťo převodník WAW->PTP, (c) 2025 Jan Heřman")
print(f"********************************************")

# --- načtení WAV ---
with wave.open(args.in_wav, "rb") as wf:
    ch = wf.getnchannels()
    sr = wf.getframerate()
    n = wf.getnframes()
    sw = wf.getsampwidth()
    raw = wf.readframes(n)

if sw == 1:
    sig = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
    sig = (sig - 128.0) / 128.0
elif sw == 2:
    sig = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
else:
    raise ValueError("Nepodporovaná šířka vzorku (jen 8/16 bit)")

if ch > 1:
    sig = sig.reshape(-1, ch).mean(axis=1)

N = len(sig)

# --- najdi nulové přechody ---
zc = []
for i in range(1, N):
    if sig[i-1] >= 0 > sig[i]:
        zc.append(i)
        
    # progress info
    if i % 1000 == 0 or i == N-1:
        progress = (i / (N-1)) * 100
        sys.stdout.write(f"\rAnalyzuji záznam: {i}/{N-1} ({progress:.1f}%)")
        sys.stdout.flush()

print()  # odřádkujeme po dokončení

if args.debug:
    print(f"Nulových přechodů: {len(zc)}")

# --- měření period ---
periods = []
for i in range(1, len(zc), 1):  # bereme vždy dvě půlperiody
    p = zc[i] - zc[i-1]
    periods.append(p)

# --- dekódování na bity ---
bits = []
for p in periods:
    bit = 0 if p <= args.samples_thresh else 1
    if args.invert:
        bit ^= 1
    # --- vyloučení extrémních dob ---
    if p < args.samples_thresh*2:
        bits.append(bit)

if args.debug:
    print(f"Detekováno {len(bits)} bitů, průměrná perioda={np.mean(periods):.2f} vzorků")
# --- skládání bajtů se start/stop bity ---
bytes_out = []
i = 0
while True:
    # start bity
    if args.start_bits:
        if i + args.start_bits > len(bits):
            break
        if bits[i] != args.start_bit_value:
            i += 1
            continue
        i += args.start_bits

    # datové bity
    if i + 8 > len(bits):
        break
        
    data_bits = bits[i:i+8]
    i += 8

    # složení bajtu
    val = sum((b & 1) << k for k, b in enumerate(data_bits))
    bytes_out.append(val)


# --- uložit raw bin---
if args.debug:
    with open(args.out_file, "wb") as f:
        f.write(bytearray(bytes_out))    
                
    print(f"WAV: sr={sr} Hz, kanály={ch}, sampwidth={sw*8}b, samples={len(sig)})")
    print(f"Výstup: {len(bits)} bitů -> {len(bytes_out)} bajtů")
    print("Bytes[0:16]:", [f"{b:02X}" for b in bytes_out[:16]])
    print("Uloženo do:", args.out_file)

# pevná sekvence bajtů, doplní to co je normálně v PTP
prefix = bytes.fromhex(
    "3F 00 "
    "FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF "
    "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
    "55 55 55 55 55 55 55 55 55 55 55 55 55 55 55"
)

def sanitize_filename(name: str) -> str:
    # odstraní znaky nepovolené v názvech programů
    return re.sub(r'[\\/*?:"<>|]', "_", name.strip())
    
def shr8(value: int) -> int:
    """Posun doprava o 1 bit pro 8bit číslo (bez rotace)."""
    return (value >> 1) & 0x7F  # horní bit se vždy vyplní nulou
   
def process_bytes(data: bytes):
    i = 0
    file_counter = 0
    all_blocks = bytearray()  # zde budeme skládat všechny bloky
    while i < len(data) - 5:
        # hledej vzor 55 ?? 3E 01 24
        if data[i] == 0x55 and i + 4 < len(data):
            if data[i+2] == 0x3E and data[i+3] == 0x01 and data[i+4] == 0x24:
                any_byte = data[i+1]

                # načti délku
                if i + 7 >= len(data):
                    break
                length = data[i+5] | (data[i+6] << 8)

                # načti jméno bloku
                if i + 15 >= len(data):
                    break
                name_bytes = data[i+7:i+15]
                name = name_bytes.decode("ascii", errors="replace")
                name = sanitize_filename(name)

                # CRC hlavičky (od "cokoliv" po poslední byte jména)
                crc_header = data[i+15]
                crc_calc = sum(data[i+1:i+15]) % 256
                if args.debug:
                    print("Hlavicka CRC:", [f"{b:02X}" for b in data[i+1:i+15]])
                if crc_calc != crc_header:
                    print(f"[!] CRC hlavičky nesouhlasí u bloku {name} (oček. {crc_header}, spoč. {crc_calc})")
                    i += 1
                    continue

                # načti data bloku
                block_start = i + 16
                block_end = block_start + length+1
                if block_end >= len(data):
                    break
                block = bytearray(data[block_start:block_start+length+2])
                crc_block = data[block_start+length+1]
                
                # tady rotuju bity v prvnim byte po hlavicce, Mato dava navic jeden startbit pred zacatkem tela coz jsem zjistil pozde a
                # je to spatne reseni, prichazim o info o MSB, ale temer jiste to nevadi, protoze by delka prvniho
                # radku v BASICu musela mit vetsi delku nez 128 bajtu. Cely program je treba prepsat, ale to uz se mi
                # nechtelo
                block[0] = shr8(block[0])
                
                if args.debug:
                    print("Začátek bloku CRC:", [f"{b:02X}" for b in block[:5]])
                    print("Konec bloku CRC:", [f"{b:02X}" for b in block[len(block)-5:len(block)]])
                crc_block_calc = (sum(block[:len(block)-1])) % 256
                if args.debug:
                    print("Očekávám CRC:", [f"{crc_block:02X}"])
                    print("Vypočítané CRC:", [f"{crc_block_calc:02X}"])
                if crc_block_calc != crc_block:
                    print(f"[!] CRC bloku '{name}' nesouhlasí!")
                    crc_diff = crc_block_calc - crc_block

                # původní hlavička (od 0x55 po CRC hlavičky)
                header = data[i:i+16]
                
                # vypočítám novou délku = původní + 2
                new_length = length + 2
                new_length_bytes = new_length.to_bytes(2, "little")

                # spoj 
                final_data = prefix + header + new_length_bytes + block
                
                # přidej do společného souboru
                all_blocks.extend(final_data)
                
                # ulož do souboru
                filename = f"blok_{file_counter}_{name.strip()}.ptp"
                with open(filename, "wb") as f:
                    f.write(final_data)
                print(f"[+] Blok {name} uložen do {filename}, délka {len(block)} bajtů")

                file_counter += 1
                i = block_end + 1
                continue
        i += 1
    
    
    # nakonec ulož všechny bloky do jednoho souboru
    if all_blocks:
        with open("all_blocks.ptp", "wb") as f:
            f.write(all_blocks)
        print(f"[+] Všechny bloky spojeny do souboru all_blocks.ptp, celková délka {len(all_blocks)} bajtů")


# převest na bajty:
process_bytes(bytes(bytes_out))
