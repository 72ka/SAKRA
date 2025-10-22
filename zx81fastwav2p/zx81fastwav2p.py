#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zx81fastwav2p.py
==================

Nástroj pro dekódování ZX81 programů z audio záznamu (.wav).
Interaktivní rozhodování při nejistotě automatu.
Zobrazuje i BASIC interpretaci tokenů v náhledu.
Záznam je v domácím turbu FASTSAVER.p
WAV vstupní 44,1KHz mono nebo stereo 

Autor: Jan Heřman (72ka)
Licence: MIT
Repozitář: https://github.com/72ka/zx81fastwav2p

Použití:
    python zx81fastwav2p.py vstupnisoubor.wav

Výstup:
    vytvoří soubor .p s dekódovaným ZX81 programem
    
"""
import sys
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import TextBox, Button
from scipy.io import wavfile
from scipy.signal import butter, filtfilt
import os

# ---------- DEFINICE
bytespre = 120
S1 = 44100/4000
S2 = 2*S1

res = S1+(S2-S1)/2

threshold = 0
tolerance = 1

L1=S1-3
L2=S1+3
H1=S2-8
H2=S2+4

# ---------- ZX81 úplná reprezentace ----------
ZX81_TABLE = {
    **{i: "·" for i in range(32)},            # řídicí znaky
    **{i: chr(i) for i in range(32, 128)},   # ASCII
    **{i: "░█▓"[i % 3] for i in range(128, 256)}  # grafické speciální znaky
}

def Xzx81_char_full(b):
    return ZX81_TABLE.get(b, "·")

def bytes_to_zx81_string_full(byte_list):
     return ''.join(zx81_char_full(b) for b in byte_list)

ZX81_CHARSET = {
    0x00: " ",
    0x0B: '"',
    # Interpunkce
    0x10: "(", 0x11: ")", 0x12: ">", 0x13: "<",
    0x14: "=", 0x15: "+",
    # Písmena A–Z neinvert
    0x26: "A", 0x27: "B", 0x28: "C", 0x29: "D",
    0x2A: "E", 0x2B: "F", 0x2C: "G", 0x2D: "H",
    0x2E: "I", 0x2F: "J", 0x30: "K", 0x31: "L",
    0x32: "M", 0x33: "N", 0x34: "O", 0x35: "P",
    0x36: "Q", 0x37: "R", 0x38: "S", 0x39: "T",
    0x3A: "U", 0x3B: "V", 0x3C: "W", 0x3D: "X",
    0x3E: "Y", 0x3F: "Z",
    # Číslice 0–9 neinvert
    0x1C: "0", 0x1D: "1", 0x1E: "2", 0x1F: "3",
    0x20: "4", 0x21: "5", 0x25: "6", 0x23: "7",
    0x24: "8", 0x25: "9",
    
    # Písmena A–Z invert
    0xA6: "A", 0xA7: "B", 0xA8: "C", 0xA9: "D",
    0xAA: "E", 0xAB: "F", 0xAC: "G", 0xAD: "H",
    0xAE: "I", 0xAF: "J", 0xB0: "K", 0xB1: "L",
    0xB2: "M", 0xB3: "N", 0xB4: "O", 0xB5: "P",
    0xB6: "Q", 0xB7: "R", 0xB8: "S", 0xB9: "T",
    0xBA: "U", 0xBB: "V", 0xBC: "W", 0xBD: "X",
    0xBE: "Y", 0xBF: "Z",
    # Číslice 0–9 invert
    0x9C: "0", 0x9D: "1", 0x9E: "2", 0x9F: "3",
    0xA0: "4", 0xA1: "5", 0xA2: "6", 0xA3: "7",
    0xA4: "8", 0xA5: "9",
    
    # BASIC tokeny
    0xC0: '""',   0xC1: "AT",    0xC2: "TAB",   0xC3: ".",    0xC4: "CODE",
    0xC5: "VAL",  0xC6: "LEN",   0xC7: "SIN",   0xC8: "COS",   0xC9: "TAN",
    0xCA: "ASN",  0xCB: "ACS",   0xCC: "ATN",   0xCD: "LN",    0xCE: "EXP",
    0xCF: "INT",  0xD0: "SQR",   0xD1: "SGN",   0xD2: "ABS",   0xD3: "PEEK",
    0xD4: "USR",  0xD5: "STR$",  0xD6: "CHR$",  0xD7: "NOT",   0xD8: "**",
    0xD9: "OR",   0xDA: "AND",   0xDB: "<=",    0xDC: ">=",    0xDD: "<>",
    0xDE: "THEN", 0xDF: "TO",    0xE0: "STEP",  0xE1: "LPRINT",0xE2: "LLIST",
    0xE3: "STOP", 0xE4: "SLOW",  0xE5: "FAST",  0xE6: "NEW",   0xE7: "SCROLL",
    0xE8: "CONT", 0xE9: "DIM",   0xEA: "REM",   0xEB: "FOR",   0xEC: "GOTO",
    0xED: "GOSUB",0xEE: "INPUT", 0xEF: "LOAD",  0xF0: "LIST",  0xF1: "LET",
    0xF2: "PAUSE",0xF3: "NEXT",  0xF4: "POKE",  0xF5: "PRINT", 0xF6: "PLOT",
    0xF7: "RUN",  0xF8: "SAVE",  0xF9: "RAND",  0xFA: "IF",    0xFB: "CLS",
    0xFC: "UNPLOT",0xFD: "CLEAR",0xFE: "RETURN",0xFF: "COPY",
}


def zx81_char_full(b):
    if b in ZX81_CHARSET:
        result = (ZX81_CHARSET[b])
    else:
        result = "."
    return result


def Xbytes_to_zx81_string_full(data: bytes) -> str:
    """Převede bajty ZX81 RAM na Unicode znaky."""
    result = []
    for b in data:
        if b in ZX81_CHARSET:
            result.append(ZX81_CHARSET[b])
        else:
            # neznámý znak (např. BASIC keyword)
            result.append(f".")
    return "".join(result)


# ---------- převody ----------
def bits_to_bytes(bits):
    res = []
    for i in range(0, len(bits), 8):
        b = bits[i:i+8]
        if len(b) < 8 or any(x not in ("0","1") for x in b):
            break
        res.append(int("".join(b), 2))
    return res

# ---------- klasifikace pulzu ----------
def classify_pulse(length):        
    if L1 < (length) < res:
        return "0"
    elif res <= (length) < H2:
        return "1"
    return None
    
# ---------- klasifikace pulzu preview ----------
def classify_pulse_prev(length):        
    if length <= res:
        return "0"
    else:
        return "1"

# ---------- interaktivní rozhodování ----------
class InteractiveDecision:
    def __init__(self, signal, fs, pulse_center, pulse_len, bitstream, all_bits_after, progress, window=200):
        self.signal = signal
        self.fs = fs
        self.pulse_center = pulse_center
        self.pulse_len = pulse_len
        self.bitstream = bitstream
        self.all_bits_after = all_bits_after
        self.progress = progress
        self.window = window
        self.result = None

    def ask(self):
        fig, (ax_sig, ax_bits, ax_ascii) = plt.subplots(3, 1, figsize=(12, 9))
        plt.subplots_adjust(bottom=0.25, hspace=0.6)

        start = int(max(0, self.pulse_center - self.window))
        end = int(min(len(self.signal), self.pulse_center + self.window))
        ax_sig.plot(np.arange(start, end)/self.fs, self.signal[start:end], color='gray')
        ax_sig.axvspan(self.pulse_center/self.fs, (self.pulse_center+self.pulse_len)/self.fs, color='red', alpha=0.3)
        ax_sig.set_xlabel("čas [s]")
        ax_sig.set_ylabel("amplituda")

        ax_bits.axis("off")
        txt_bits = ax_bits.text(0.01, 0.5, "", fontsize=12, family="monospace")
        ax_ascii.axis("off")
        txt_ascii = ax_ascii.text(0.01, 0.5, "", fontsize=8, family="monospace")

        axbox = plt.axes([0.15, 0.1, 0.5, 0.05])
        text_box = TextBox(axbox, 'Bity:', initial="")
        axok = plt.axes([0.7, 0.1, 0.05, 0.05])
        bok = Button(axok, "OK")
        axend = plt.axes([0.8, 0.1, 0.05, 0.05])
        bend = Button(axend, "END")

        def update_preview(text):
            bits = self.bitstream.copy()
            if text.strip() == "x":
                if bits: bits.pop()
            else:
                for c in text.strip():
                    if c in ("0","1"):
                        bits.append(c)
                    if c in ("-"):
                        bits.pop()

            sim_bits = bits + self.all_bits_after
            txt_bits.set_text(f"Zadané bity: {text}\nPoslední bity: {''.join(bits[-64:])}")
            fig.suptitle(f"Pulz mimo rozsah: {self.pulse_len} vzorků – rozhodni! ({self.progress:.1f} %)", fontsize=12)

            bytes_all = bits_to_bytes(sim_bits)
            bits_after_start = len(bits)
            idx = bits_after_start // 8

            prev_bytes = bytes_all[max(0, idx-bytespre):idx]
            next_bytes = bytes_all[idx:idx+bytespre]

            # zvýraznění aktuálního bajtu
            next_bytes_display = next_bytes.copy()
            if next_bytes_display:
                next_bytes_display[0] = f"[{next_bytes_display[0]}]"

            prev_ascii = bytes_to_zx81_string_full(prev_bytes)
            next_ascii = bytes_to_zx81_string_full(next_bytes)
            txt_ascii.set_text(
                f"Předchozí znaky ({len(prev_bytes)}): {prev_ascii}\n"
                f"Následující znaky ({len(next_bytes_display)}): {next_ascii}"
            )

            fig.canvas.draw_idle()

        def accept(event):
            self.result = text_box.text.strip()
            plt.close(fig)
            
        def end(event):
            self.result = "e"
            plt.close(fig)

        text_box.on_text_change(update_preview)
        bok.on_clicked(accept)
        bend.on_clicked(end)
        update_preview("")
        plt.show()
        return self.result

# ---------- dekódování WAV ----------
def decode_wav(filename):
    fs, data = wavfile.read(filename)
    # Vezmeme pouze první kanál levý
    if data.ndim > 1:
        data = data[:,0]
    data = data.astype(float)
    
    # normalizace hlasitosti (max. absolutní hodnota = 1)
    data /= np.max(np.abs(data))
    
    # filtr potlačit vše ostře nad 5kHz
    cutoff = 5000       # Hz
    order = 8
    b, a = butter(order, cutoff / (fs / 2), btype='low')

    # aplikace filtru
    filtered = filtfilt(b, a, data)
    data = filtered
    
    # detekce pulzů pomocí průchodu nulou
    minima = []
    for i in range(1, len(data)-1):
        if data[i-1] < 0 <= data[i]:
            minima.append(i)
        
    # délky pulzů = rozdíly mezi průchody nulou
    pulses = []
    for i in range(1, len(minima)):
        length = minima[i] - minima[i-1]
        pulses.append((minima[i-1], length))

    # hledání start bitu (první log 1 po sérii krátkých pulzů - pilotní tón)
    start_index = None
    min_pilot_pulses = 50   # počet krátkých pulzů před start bitem

    for idx in range(min_pilot_pulses, len(pulses)):
        pos, length = pulses[idx]
        # start bit má být dlouhý (log 1)
        if length > res:
            # kontrola, že před tímto bitem je alespoň 50 krátkých
            previous_pulses = [l for _, l in pulses[idx - min_pilot_pulses:idx]]
            if all(l <= res for l in previous_pulses):
                start_index = idx + 1
                print(f"[*] Start bit nalezen na pozici {pos} (po {min_pilot_pulses} krátkých pulzech)")
                break

    if start_index is None:
        raise RuntimeError("Start bit nenalezen (nebyla nalezena série 50 krátkých pulzů před dlouhým pulsem)")


    # dekódování od start bitu
    bits = []
    bits_in_byte = []
    total = len(pulses[start_index:])
    time_acc = 0
    expl = False
    for i, (pos, length) in enumerate(pulses[start_index:]):
        bit = classify_pulse(length)
        if (bit is not None) and (expl is not True):
            bits.append(bit)
            bits_in_byte.append(bit)
            time_acc += length
        else:
            print("Potřeba rozhodnout")
            # zbývající bity po start bitu pro náhled
            all_bits_after = []
            for _, (pos2,l) in enumerate(pulses[start_index+i+1:]):
                fb = classify_pulse_prev(l)
                
                if fb is not None:
                    all_bits_after.append(fb)
            progress = 100.0 * i / total
            decision = InteractiveDecision(data, fs, pos, length, bits, all_bits_after, progress).ask()
            if decision == "x":
                if bits:
                    bits.pop()
                    expl = False
            if decision == "e":
                   bytes_all = bits_to_bytes(bits)
                   return bytes_all
            else:
                for c in decision:
                    if c in ("0","1"):
                        bits.append(c)
                        expl = False
                    if c in ("-"):
                        bits.pop()
                        expl = False

    bytes_all = bits_to_bytes(bits)    
    return bytes_all

# ---------- hlavní část ----------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("--------------------------------------")
        print("*** ZX81 FASTSAVER decode utility ****")
        print("     (c) 2025 Jan Heřman (72ka)")
        print("      http://github.com/72ka")
        print("--------------------------------------")
        print("Usage: python zx81fastwav2p.py vstup.wav")
        sys.exit(1)
    infile = sys.argv[1]
    outfile = infile.rsplit(".",1)[0] + ".p"
    decoded = decode_wav(infile)
    with open(outfile,"wb") as f:
        f.write(bytearray(decoded))
    print(f"Uloženo do {outfile}")

