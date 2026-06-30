#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Převodník magnetofonových záznamů počítače IQ-151 (systém Komenium) na formát HEX a WAv.
Výsledný .hex soubor slouží pro přímé použití v modulu SD-ROM se zachováním load obrazovky

verze 1.6

Autor: (c) Jan Heřman 2026 <2hp@seznam.cz>
"""

import os
import sys
import warnings
import matplotlib.pyplot as plt
import numpy as np
import glob
from scipy.io import wavfile
from scipy.io.wavfile import WavFileWarning
from scipy.signal import butter, filtfilt
from tqdm import tqdm

# Ignorování specifických varování knihovny SciPy ohledně nestandardních chunků ve WAV souborech
warnings.simplefilter("ignore", WavFileWarning)

# ANSI kódy pro barvy v terminálu
CLR_RED = "\033[31m"
CLR_YELLOW = "\033[33m"
CLR_GREEN = "\033[32m"
CLR_RESET = "\033[0m"

# Globální příznak integrity nahrávky (počet chyb CRC)
chyba_crc_pocet = 0

#Globální polarita signálu
polarita = 0

#Globální proměnné pro průběžnou tvorbu wav
AMP_HIGH = 24000
AMP_LOW = -24000
AMP_SILENCE = 0
stav = AMP_SILENCE
        
audio_samples = []

def log(text):
    """Pomocná funkce pro barevné printování do terminálu podle typu hlášky."""
    CLR_RED = "\033[31m"
    CLR_YELLOW = "\033[33m"
    CLR_GREEN = "\033[32m"
    CLR_RESET = "\033[0m"
    
    if "[ERROR]" in text:
        print(f"{CLR_RED}{text}{CLR_RESET}")
    elif "[INFO]" in text or "[INFO]" in text:
        print(f"{CLR_YELLOW}{text}{CLR_RESET}")
    elif "[OK]" in text:
        # Aby zelená nebyla moc agresivní
        print(text.replace("[OK]", f"{CLR_GREEN}[OK]{CLR_RESET}"))
    else:
        print(text)
        
def vizualizuj_wav_a_bloky(data, sr, blocks, wav_filename, base_name):
    """
    Vykreslí waveform WAV s popisky bloků
    """
    pngfilename = f"{base_name}.png"
    print(f"[OK] Generuji vizualizaci do {pngfilename}...")
    
    delka_vzorku = len(data)
    casova_osa = np.arange(delka_vzorku) / sr
    celkovy_cas = delka_vzorku / sr
    
    if len(data.shape) == 1:
        kanaly = 1
        stops = [data]
    else:
        kanaly = data.shape[1]
        stops = [data[:, 0], data[:, 1]]
        
    sirka_inch = 16
    vyska_inch = 9
    
    # Použití čistého stylu
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['text.color'] = '#2c3e50'
    
    fig, axes = plt.subplots(kanaly, 1, figsize=(sirka_inch, vyska_inch), sharex=True, squeeze=False)
    
    fig.suptitle(f"Analýza záznamu: {os.path.basename(wav_filename)}\n({sr} Hz, {celkovy_cas:.2f} s)", 
                 fontsize=15, fontweight='bold', color='#1a252f', y=0.96)
    
    nazvy_kanalu = ["Levý kanál", "Pravý kanál"] if kanaly == 2 else ["Audio stopa"]
    
    pocet_bloku = max(len(blocks), 1)
    barvy_palety = plt.colormaps['tab20b'](np.linspace(0, 1, pocet_bloku))
    
    for ch in range(kanaly):
        ax = axes[ch, 0]
        
        # Vykreslení signálu v jemné břidlicové barvě
        ax.plot(casova_osa, stops[ch], color='#4a6984', alpha=0.35, linewidth=0.5)
        ax.set_title(nazvy_kanalu[ch], fontsize=11, fontweight='semibold', color='#34495e', loc='left', pad=12)
        
        # Minimalistická mřížka
        ax.grid(True, linestyle=':', alpha=0.5, color='#bdc3c7')
        ax.set_xlim(0, celkovy_cas)
        
        # Skrytí osy Y a odstranění zbytečných okrajových linek grafu (Spines)
        ax.get_yaxis().set_visible(False)
        for spine in ['top', 'left', 'right']:
            ax.spines[spine].set_visible(False)
        ax.spines['bottom'].set_color('#7f8c8d')
        ax.spines['bottom'].set_linewidth(0.8)
        
        max_val = np.max(np.abs(data)) if np.max(np.abs(data)) > 0 else 1
        obsazeny_prostor = []
        
        # Vyznačení všech nalezených bloků do grafu
        for idx, block in enumerate(blocks):
            start_idx = block.get('start_sample', 0)
            end_idx = block.get('end_sample', len(data))
            
            t_start = start_idx / sr
            t_end = end_idx / sr
            t_delka = t_end - t_start
            t_stred = t_start + (t_delka / 2)
            
            barva_bloku = barvy_palety[idx]
            
            # Výpočet reálné velikosti datového bloku v kB
            pocet_bajtu = len(block.get('data', []))
            velikost_kb = pocet_bajtu / 1024.0
            
            # Decentní podbarvení plochy bloku a jeho vertikální ohraničení
            ax.axvspan(t_start, t_end, color=barva_bloku, alpha=0.12)
            ax.axvline(t_start, color=barva_bloku, linestyle='--', linewidth=0.8, alpha=0.5)
            ax.axvline(t_end, color=barva_bloku, linestyle='--', linewidth=0.8, alpha=0.5)
            
            info_text = f"Blok {idx} ({velikost_kb:.2f} kB) | {t_start:.1f}s - {t_end:.1f}s"
            
            # Výpočet výšky kaskády (patra) pro vertikální popisky
            vyska_start = max_val * 1.2
            krok_patra = max_val * 4.9  # Zvětšený krok pro vertikální texty (jsou vyšší na výšku)
            
            # Odhad šířky, kterou zabere vertikální popisek na ose X (velmi úzký, cca 2% délky nahrávky)
            odhad_sirky_textu_s = celkovy_cas * 0.02
            
            kolize = True
            while kolize:
                kolize = False
                text_x_start = t_stred - (odhad_sirky_textu_s / 2)
                text_x_end = t_stred + (odhad_sirky_textu_s / 2)
                
                for predchozi_x_start, predchozi_x_end, predchozi_y in obsazeny_prostor:
                    # Pokud by texty v dané výškové hladině kolidovaly horizontálně
                    if abs(vyska_start - predchozi_y) < (krok_patra * 0.8):
                        if not (text_x_end < predchozi_x_start or text_x_start > predchozi_x_end):
                            vyska_start += krok_patra  
                            kolize = True
                            break
            
            obsazeny_prostor.append((t_stred - (odhad_sirky_textu_s / 2), t_stred + (odhad_sirky_textu_s / 2), vyska_start))
            
            # Čisté vykreslení vertikálního popisku (rotation=90)
            ax.annotate(
                info_text,
                xy=(t_stred, max_val * 0.2),
                xytext=(t_stred, vyska_start),
                ha='center', va='bottom',
                fontsize=10, fontweight='medium', color='#2c3e50',
                rotation=90,
                bbox=dict(boxstyle="square,pad=0.4", fc="#ffffff", ec=barva_bloku, alpha=0.95, lw=1.5),
                arrowprops=dict(
                    arrowstyle="-",
                    color=barva_bloku,
                    lw=1.0,
                    alpha=0.7,
                    connectionstyle="arc3,rad=0"
                )
            )

        # Přizpůsobení horního okraje grafu podle nejvyšší vertikální kaskády
        if obsazeny_prostor:
            nejvyssi_bod = max([pos[2] for pos in obsazeny_prostor])
            # Vertikální text potřebuje dodatečný prostor nad bodem xytext, proto max_val * 2.5
            ax.set_ylim(-max_val * 1.1, nejvyssi_bod + (max_val * 2.5))
        else:
            ax.set_ylim(-max_val * 1.1, max_val * 4.0)

    axes[-1, 0].set_xlabel("Čas (sekundy)", fontsize=11, fontweight='semibold', color='#34495e', labelpad=8)
    
    # Rezerva nahoře pro dlouhé vertikální popisky
    plt.tight_layout(rect=[0, 0, 1, 0.72])
    plt.savefig(pngfilename, dpi=200, format='png')  # Zvýšeno DPI na 200 pro ostré texty
    plt.close()
    print(f"[OK] Vizualizace úspěšně uložena.")


def process_wav(input_path):
    """
    Načte vstupní audiosoubor WAV, v případě potřeby provede downmix stereo kanálů 
    do čistého mono signálu a provede špičkovou amplitudovou normalizaci na hodnotu 1.0.
    """
    sr, data = wavfile.read(input_path)
    
    if data.ndim > 1:
        data = data.astype(float)
        data = (data[:, 0] + data[:, 1]) / 2.0
    else:
        data = data.astype(float)
    
    data /= np.max(np.abs(data))
    
    # Normalizace originálu pro vnitřní zpracování a vizuální stabilitu
    orig_centered = data - np.mean(data)
    max_orig = np.max(np.abs(orig_centered))
    orig_normalized = (orig_centered / max_orig * 30000) if max_orig > 0 else orig_centered
    
    return orig_normalized, sr


def filtr(data, sr):
    """
    Aplikuje Butterworthův pásmový filtr (Band-pass).
    Odřízne nízkofrekvenční brum pod 300 Hz (který tahá signál pod nulu)
    a vysokofrekvenční šum nad 5000 Hz.
    """
    low_cutoff = 300    # Hz (odstraní DC posun a brum)
    high_cutoff = 5000  # Hz (odstraní VF šum)
    order = 4           # Stačí menší řád, abychom nerozhasili fázi
    
    # Návrh pásmového filtru
    nyq = sr / 2
    b, a = butter(order, [low_cutoff / nyq, high_cutoff / nyq], btype='band')

    print("[OK] Aplikuji pásmový filtr (300 Hz - 5 kHz) .....")
    filtered = filtfilt(b, a, data)
        
    return filtered


def detect_crossings(data):
    """
    Klasická hardwarová detekce průchodů signálu nulovou linií.
    Zaznamenává indexy vzorků a směr přechodu (1 = stoupající, 0 = klesající).
    """
    crossings = []
    for i in tqdm(range(1, len(data)), desc="[OK] Analyzuji signál"):
        if data[i-1] < 0 <= data[i]:
            crossings.append({'index': i, 'dir': 1})
        if data[i-1] > 0 >= data[i]:
            crossings.append({'index': i, 'dir': 0})

    return crossings


def detect_crossings_amplitude(data):
    """
    Pokročilá detekce lokálních extrémů (špiček a údolí) vln s adaptivním oknem.
    Zabraňuje chybám při nesymetrickém signálu a DC posunu typickém pro staré kazety.
    """
    global sr
    
    current_sr = sr if 'sr' in globals() else 44100
    window_size = max(3, int(current_sr * 0.00063 / 4))
    threshold = 0.05  
    crossings = []
    
    print(f"[Analýza] Hledám vrcholy amplitud (Dynamické okno: {window_size} vzorků)...")
    
    for i in tqdm(range(window_size, len(data) - window_size), desc="Hledám vrcholy"):
        aktualni_hodnota = data[i]
        
        # --- DETEKCE MAXIMA (VRCHOL NAHOŘE) ---
        if aktualni_hodnota > threshold:
            if aktualni_hodnota >= np.max(data[i - window_size : i]) and \
               aktualni_hodnota > data[i + window_size]:
                
                if not crossings or (i - crossings[-1]['index'] > (window_size * 2)):
                    if crossings and crossings[-1]['dir'] == 1:
                        if aktualni_hodnota > data[crossings[-1]['index']]:
                            crossings[-1]['index'] = i
                    else:
                        crossings.append({'index': i, 'dir': 1})
                        
        # --- DETEKCE MINIMA (VRCHOL DOLE) ---
        elif aktualni_hodnota < -threshold:
            if aktualni_hodnota <= np.min(data[i - window_size : i]) and \
               aktualni_hodnota < data[i + window_size]:
                
                if not crossings or (i - crossings[-1]['index'] > (window_size * 2)):
                    if crossings and crossings[-1]['dir'] == 0:
                        if aktualni_hodnota < data[crossings[-1]['index']]:
                            crossings[-1]['index'] = i
                    else:
                        crossings.append({'index': i, 'dir': 0})

    return crossings

def detect_crossings_dynamic_derivative(data):
    """
    Detekuje vrcholy (crossings) čistě na základě změny směru signálu.
    Ignoruje absolutní hodnoty i nulu, funguje i hluboko v záporných hodnotách.
    """
    global sr
    current_sr = sr if 'sr' in globals() else 44100
    window_size = 4*max(2, int(current_sr * 0.00063 / 6)) # Menší okno pro citlivost
    
    crossings = []
    print("[Analýza] Hledám lokální extrémy pomocí derivace trendu...")

    for i in tqdm(range(window_size, len(data) - window_size), desc="Hledám vrcholy"):
        # Sleduju trend před vzorkem 'i' a po něm
        
        # Jednoduchý test: je bod i větší než jeho sousedi?
        if data[i] > data[i - 1] and data[i] >= data[i + 1]:
            # Ověřím v širším okně, zda to není jen drobný šum
            if data[i] == np.max(data[i - window_size : i + window_size + 1]):
                if not crossings or (i - crossings[-1]['index'] > window_size):
                    crossings.append({'index': i, 'dir': 1}) # Lokální maximum
                    
        # Je bod i menší než jeho sousedi? (Minimum)
        elif data[i] < data[i - 1] and data[i] <= data[i + 1]:
            if data[i] == np.min(data[i - window_size : i + window_size + 1]):
                if not crossings or (i - crossings[-1]['index'] > window_size):
                    crossings.append({'index': i, 'dir': 0}) # Lokální minimum

    return crossings
    
def analyze(crossings):
    """
    Statistická analýza periodicity hran. Počítá medián délky pulsu, 
    který definuje základní taktovací jednotku (clock T) nahrávky pro dekódování bitů.
    """
    diffs = np.diff([item['index'] for item in crossings])
    T = np.median(diffs[(diffs > 10) & (diffs < 30)])
    
    print("-" * 40)
    print(f"Analýza signálu:")
    print(f"  Detekovaný puls:      {T:.2f} vzorků")
    print(f"  Počet změn:           {len(crossings)}")
    print("-" * 40)
    
    return T


def crossings_to_char(crossings, T, start_crossing, cbit):
    """
    Převádí intervaly mezi hranami na printické bity a sestavuje z nich
    standardní 7-bitové znaky s doprovodnými start/stop bity (Zavaděč / Loader).
    """
    len_1 = int(2 * T)   # 2kHz (printická 1)
    threshold = len_1 * 0.75
    
    bits = []
    byte_val = 0
    current_bit = cbit
    i = start_crossing

    if (crossings[i+1]['index'] - crossings[i]['index'] > threshold):
        next_crossing = i + 4
    else:
        next_crossing = i + 2
        
    if (i + 18) > len(crossings):
        print("[OK] Konec nahrávky")
        return False, False, i, False, False
        
    while len(bits) < 9:
        dt = crossings[i+1]['index'] - crossings[i]['index']
        if dt > threshold:
            current_bit ^= 1
            bits.append({'index': crossings[i+1]['index'], 'bit': current_bit})
            i += 1
        else:
            bits.append({'index': crossings[i+1]['index'], 'bit': current_bit})
            i += 2 
            
    if bits[0]['bit'] == 0:  
        for bit_pos in range(7):
            if bits[bit_pos+1]['bit'] == 1:
                byte_val |= (1 << bit_pos) 
    
    byte_val = byte_val & 0x7F
    end_byte_crossing = i
    end_data_sample = bits[-1]['index']
          
    return byte_val, next_crossing, end_byte_crossing, current_bit, end_data_sample
    

def kcrossings_to_char(crossings, T, start_crossing, cbit):
    """
    Speciální varianta bitové rekonstrukce pro čisté Komenium bloky (8-bit MSB).
    Čte proud dat bez standardních stop bitů, bity skládá posuvem doleva.
    """
    len_1 = int(2 * T)   # 2kHz
    threshold = len_1 * 0.75
    
    bits = []
    byte_val = 0
    current_bit = cbit
    i = start_crossing

    if (crossings[i+1]['index'] - crossings[i]['index'] > threshold):
        next_crossing = i + 1
    else:
        next_crossing = i + 2
        
    if (i + 18) > len(crossings):
        print("[OK] Konec nahrávky")
        return False, False, i, False, False
        
    while len(bits) < 8:
        dt = crossings[i+1]['index'] - crossings[i]['index']
        if dt > threshold:
            current_bit ^= 1
            bits.append({'index': crossings[i+1]['index'], 'bit': current_bit})
            i += 1
        else:
            bits.append({'index': crossings[i+1]['index'], 'bit': current_bit})
            i += 2 
            
    for bit_entry in bits[:8]:  
        byte_val = (byte_val << 1) | bit_entry['bit']
    
    end_byte_crossing = i
    end_data_sample = bits[-1]['index']
          
    return byte_val, next_crossing, end_byte_crossing, current_bit, end_data_sample
    

def get_length_type(header):
    """
    Parsovací rutina pro Intel HEX hlavičku ze Standardního bloku.
    Zjišťuje délku datové oblasti a typ záznamu.
    """
    try:
        header = "".join(header)
        length_hex = header[0:2]
        type_hex = header[7:9]
        
        return int(length_hex, 16), int(type_hex, 16), True
        
    except (ValueError, IndexError):
        log("[INFO] Neplatný formát INTEL HEX hlavičky.")
        return 0, 0, False
        

def get_length_address(header):
    """
    Parsovací rutina pro binární hlavičku Komenia (Big-Endian).
    Extrahuje cílovou délku bajtů a zaváděcí adresu v paměti IQ-151.
    """
    try:
        if len(header) < 4:
            raise IndexError

        b0 = header[0]
        b1 = header[1]
        b2 = header[2]
        b3 = header[3]

        length = (b0 << 8) | b1 
        address = (b2 << 8) | b3

        print(f"  Délka:   0x{length:04X} ({length} bytů -> {length // 1024} kB)")
        print(f"  Adresa:  0x{address:04X} ({address})")

        return length, address, True
        
    except (ValueError, IndexError, TypeError):
        log("[ERROR] Neplatný formát Komenium hlavičky.")
        return 0, 0, False


def check_crc(hex_data):
    """
    Validátor kontrolního součtu pro standardní řádky Intel HEX zavaděče.
    Využívá algoritmus CheckSum8 2's Complement.
    """
    hex_data = hex_data.strip()
    header_crc = int(hex_data[-2:], 16)
    
    try:
        bytes_list = [int(hex_data[i:i+2], 16) for i in range(0, len(hex_data) - 2, 2)]
    except ValueError:
        log(f"[ERROR] CRC kontrola: Neplatný hex formát v bloku: {hex_data}")
        return False
    
    sum_of_bytes = sum(bytes_list) & 0xFF
    checksum = (0x100 - sum_of_bytes) & 0xFF
    
    if checksum == header_crc:
        print(f"[OK] CRC OK (Vypočteno: {checksum:02X} == Uloženo: {header_crc:02X})")
        return True
    else:
        log(f"[ERROR] CRC: Nesouhlasí kontrolní součet řádku!")
        print(f"  -> Suma bajtů:       0x{sum_of_bytes:02X}")
        print(f"  -> Vypočtené CRC (2s): 0x{checksum:02X}")
        print(f"  -> Uložené CRC:      0x{header_crc:02X}")
        return False
        
# Pomocná funkce pro vygenerování hrany ve wav
def hrana(T):
    global stav
    global AMP_LOW
    global AMP_HIGH
    audio_samples.extend([stav] * int(T))
    stav = AMP_LOW if stav == AMP_HIGH else AMP_HIGH

def najdi_pilotni_ton(crossings, T, crossing_index, pocet):
    """
    Vyhledává synchronizační pilotní tón pásky. Jakmile identifikuje 
    minimální stabilní počet period, pokračuje v čtení až na samotný 
    konec tónu, kde se opře o první start bit.
    """
    threshold = T * 1.5
    min_limit = T * 0.75
    
    pocitadlo_pulsu = 0
    start_pilot_index = None
    pilot_nalezen_faze1 = False

    i = crossing_index
                
    while i < len(crossings) - 1:
        delka_pulsu = crossings[i+1]['index'] - crossings[i]['index']
        
        if min_limit <= delka_pulsu < threshold:
            if pocitadlo_pulsu == 0:
                start_pilot_index = i
            
            #generuj zaroven do wav
            hrana(T)
            pocitadlo_pulsu += 1
            
            if pocitadlo_pulsu >= pocet and not pilot_nalezen_faze1:
                pilot_nalezen_faze1 = True
                print(f"[OK] Detekován pilotní tón")
        
        else:
            if pilot_nalezen_faze1:
                print(f"[OK] Nalezen konec pilotního tónu. Sample: {crossings[i]['index']}")
                return i-20, True
            else:
                pocitadlo_pulsu = 0
                start_pilot_index = None
            
        i += 1
        
    if pilot_nalezen_faze1:
        print("[INFO] Pilotní tón na konci pásky.")
        return i, False

    print("[INFO] Pilotní tón nebyl nalezen.")
    return crossing_index, False
    

def cti_blok(crossings, T, crossing_index, blocks, current_block):
    """
    Kompletní stavový automat pro přečtení jednoho Standardního bloku (ID 0).
    Čeká na pilot, zachytí startovní znak ':' (0x3A), načte hlavičku a čte data do konce řádku CR.
    """
    
    global polarita
    
    current_byte = 0
    crossing_index, ispilot = najdi_pilotni_ton(crossings, T, crossing_index, 20)
    
    startcbit = polarita
    
    while current_byte != 0x3A: #detekce znaku ":"
        cbit = startcbit
        current_byte, next_crossing, end_byte_crossing, cbit, sample = crossings_to_char(crossings, T, crossing_index, cbit)
        if current_byte is False:
            return blocks, crossing_index, False
        start_sample = crossings[crossing_index]['index']
        crossing_index = next_crossing
        
    print("[OK] Nalezen začátek Standard HEX bloku dat")

    blocks.append({'id': current_block, 'typ': 0, 'header': [], 'data': [], 'start_index': crossing_index, 'start_sample': start_sample})
    crossing_index = end_byte_crossing
    
    current_byte = 0 
    header = []
    for b in range(8): #prvnich 8 je hlavicka
        current_byte, next_crossing, end_byte_crossing, cbit, sample = crossings_to_char(crossings, T, crossing_index, cbit)
        if current_byte is False:
            blocks.pop()
            return blocks, crossing_index, False
        char = chr(current_byte)
        crossing_index = end_byte_crossing
        header.append(char)
        blocks[current_block]['header'].append(char)
        
    bl_length, bl_type, valid = get_length_type(header)

    if bl_type == 1:
        blocks[current_block]['end_index'] = end_byte_crossing
        blocks[current_block]['end_sample'] = crossings[end_byte_crossing]['index']
        return blocks, crossing_index, False
    
    if not valid:
        blocks.pop()
        return blocks, crossing_index, False
        
    blocks[current_block]['size'] = bl_length
    blocks[current_block]['type'] = bl_type
    
    current_byte = 0 
    blk_data = []
    while current_byte != 0x0D: #čti všechny bajty dokud není ukončeno znakem CR
        current_byte, next_crossing, end_byte_crossing, cbit, sample = crossings_to_char(crossings, T, crossing_index, cbit)
        if current_byte is False:
            return blocks, crossing_index, False
        char = chr(current_byte)
        crossing_index = end_byte_crossing
        blk_data.append(char)
    
    blocks[current_block]['data'] = blk_data
    blocks[current_block]['end_index'] = end_byte_crossing
    blocks[current_block]['end_sample'] = crossings[end_byte_crossing]['index']
    
    block = "".join(header + blk_data)
    check_crc(block)
    
    return blocks, end_byte_crossing, True
    

def cti_komenium_blok(crossings, T, crossing_index, blocks, current_block, typ):
    """
    Kompletní stavový automat pro extrakci čistého Komenium bloku (ID 1).
    Odpovídá loaderu začínajícího na 7934h
    Vyhledává synchronizační znak 'L' (0x4C) a parsuje binární payload programu včetně CRC.
    """
    global polarita
    current_byte = 0
    crossing_index, ispilot = najdi_pilotni_ton(crossings, T, crossing_index, 20)
    if ispilot is False:
            return blocks, crossing_index, False
    cbit = polarita 
    
    while current_byte != 0x4C:
        current_byte, next_crossing, end_byte_crossing, cbit, sample = kcrossings_to_char(crossings, T, crossing_index, cbit)
        if current_byte is False:
            return blocks, end_byte_crossing, False
        char = chr(current_byte)
        start_sample = crossings[crossing_index]['index']
        crossing_index = next_crossing
        
    if typ != 999:    
        print("[OK] Nalezen začátek bloku Komenium dat typ ", typ)
    else:
        print("[OK] Nalezen začátek NEZNAMEHO typu bloku Komenium dat")

    blocks.append({'id': current_block, 'typ': typ, 'header': [], 'data': [], 'start_index': crossing_index, 'start_sample': start_sample})
    crossing_index = end_byte_crossing
    
    current_byte = 0 
    header = []
    delkahlavy = 5
    
    if typ == 1:
        delkahlavy = 4
    
    for b in range(delkahlavy):
        current_byte, next_crossing, end_byte_crossing, cbit, sample = kcrossings_to_char(crossings, T, crossing_index, cbit)
        if current_byte is False:
            return blocks, end_byte_crossing, False
        crossing_index = end_byte_crossing
        header.append(current_byte)
        
    blocks[-1]['header'].append(header)
    bl_length, bl_address, valid = get_length_address(header)
    
    if not valid:
        return blocks, end_byte_crossing, False
        
    blocks[-1]['size'] = bl_length
    blocks[-1]['address'] = bl_address
    
    kblk_data = []
    for b in range(blocks[-1]['size'] + 4):
        current_byte, next_crossing, end_byte_crossing, cbit, sample = kcrossings_to_char(crossings, T, crossing_index, cbit)
        if current_byte is False:
            return blocks, end_byte_crossing, False
        crossing_index = end_byte_crossing
        kblk_data.append(f"{current_byte:02X}")
    
    blocks[-1]['data'] = kblk_data
    blocks[-1]['end_index'] = end_byte_crossing
    blocks[-1]['end_sample'] = crossings[end_byte_crossing]['index']
    
    #if typ == 2:
    #    kblk_valid = kontrola_crc_komenium_typ2(kblk_data)
    #else: 
    kblk_valid = kontrola_crc_komenium(kblk_data, header)
    
    return blocks, end_byte_crossing, kblk_valid

def kontrola_crc_komenium(kblk_data, header):
    """
    Ověří binární integritu Komenium bloku porovnáním očekávané koncové adresy 
    vypočtené z hlavičky se skutečnou hodnotou zapsanou na konci datového toku.
    """
    
    global chyba_crc_pocet
    
    try:
        if len(header) < 4:
            log("[ERROR] Neplatný formát hlavičky (příliš krátká).")
            chyba_crc_pocet += 1
            return False

        length = (header[0] << 8) | header[1]
        address = (header[2] << 8) | header[3]
        
        ocekavane_crc = (address + length) & 0xFFFF
        
        if len(kblk_data) < 2:
            log("[ERROR] Blok dat je příliš krátký pro kontrolu CRC.")
            chyba_crc_pocet += 1
            return False
            
        skutecne_hi = int(kblk_data[-4], 16)
        skutecne_lo = int(kblk_data[-3], 16)
        skutecne_crc = (skutecne_hi << 8) | skutecne_lo
        
        if ocekavane_crc == skutecne_crc:
            print(f"[OK] Kontrolní součet souhlasí: 0x{skutecne_crc:04X}")
            return True
        else:
            log(f"[ERROR] CRC ERROR Nesouhlasí koncová adresa!")
            print(f"  -> Očekáváno podle hlavičky: 0x{ocekavane_crc:04X}")
            print(f"  -> Skutečně zapsáno v bloku: 0x{skutecne_crc:04X}")
            chyba_crc_pocet += 1
            return False
            
    except (ValueError, IndexError, TypeError) as e:
        log(f"[ERROR] Chyba při zpracování CRC: {e}")
        chyba_crc_pocet += 1
        return False
        
def kontrola_crc_komenium_typ2(byte_data):

    
    pbyte_data = "".join(byte_data)
    print(pbyte_data)
    # Vypočítáme čistý 8-bitový součet všech bajtů kromě posledního
    # Každý prvek (kromě posledního) se nejdřív převede z HEX stringu na int a pak se sečte
    calculated_sum = sum(int(b, 16) for b in byte_data[:-2]) & 0xFF
        
    # Načteme uložený checksum z pozice 268
    stored_checksum = int(byte_data[-1], 16)
    print("Stored", hex(stored_checksum))
    print("Calc", hex(calculated_sum))
    
    # Porovnáme vypočtenou sumu s uloženou
    return calculated_sum == stored_checksum    

def index_time(crossing_index, samplerate):

    total_seconds = crossing_index / samplerate

    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60  # včetně milisekund

    total_minutes = (hours * 60) + minutes

    return f"{total_minutes:02d}:{seconds:06.3f}"
    

def export_to_intel_hex(blocks, vystupni_soubor, bajtu_na_radek):
    """
    Vyexportuje shromážděná Komenium data do textového souboru standardu Intel HEX.
    Kód automaticky dopočítává kontrolní součty řádků a generuje správný EOF záznam.
    """
    try:
        posledni_komenium_data = None
        
        with open(vystupni_soubor, "w", encoding="utf-8") as f:
            print(f"Zahajuji export Komenium bloků do: {vystupni_soubor}")
            
            for index, block in enumerate(blocks):
                if block.get('typ') < 1:
                    continue
                
                if 'data' not in block or not block['data']:
                    print(f" -> Komenium blok {index} nemá žádná data, přeskakuji.")
                    continue
                
                start_adresa = block['address']
                data = block['data']
                posledni_komenium_data = data
                
                print(f" -> Exportuji Komenium blok {index}: Adresa 0x{start_adresa:04X}, Délka {len(data)} bajtů")
                
                for i in range(0, len(data), bajtu_na_radek):
                    radek_data = data[i:i + bajtu_na_radek]
                    aktualni_adresa = start_adresa + i
                    pocet_bajtu = len(radek_data)
                    typ_zaznamu = 0
                    
                    hex_radek = f"{pocet_bajtu:02X}{aktualni_adresa:04X}{typ_zaznamu:02X}"
                    hex_radek += "".join(radek_data)
                    
                    bytes_list = [int(hex_radek[j:j+2], 16) for j in range(0, len(hex_radek), 2)]
                    sum_of_bytes = sum(bytes_list) & 0xFF
                    checksum = (0x100 - sum_of_bytes) & 0xFF
                    
                    f.write(f":{hex_radek}{checksum:02X}\n")
            
            # --- ZAKONČENÍ SOUBORU PODLE STRUKTURY KOMENIA ---
            if posledni_komenium_data and len(posledni_komenium_data) >= 2:
                start_hi = int(posledni_komenium_data[-2], 16)
                start_lo = int(posledni_komenium_data[-1], 16)
                
                ukoncovaci_adresa = (start_hi << 8) | start_lo
                typ_ukonceni = 1  
                
                hex_konec = f"00{ukoncovaci_adresa:04X}{typ_ukonceni:02X}"
                
                bytes_list_konec = [int(hex_konec[j:j+2], 16) for j in range(0, len(hex_konec), 2)]
                sum_of_konec = sum(bytes_list_konec) & 0xFF
                checksum_konec = (0x100 - sum_of_konec) & 0xFF
                
                f.write(f":{hex_konec}{checksum_konec:02X}\n")
                print(f"[OK] Soubor zakončen startovní adresou programu: 0x{ukoncovaci_adresa:04X}")
            else:
                f.write(":00000001FF\n")
                log("[ERROR] Nebyla nalezena data pro určení startovní adresy, použit vymyšlený konec.")
                return False
            
        print(f"[OK] Export úspěšně dokončen do {vystupni_soubor}.")
        return True
        
    except Exception as e:
        log(f"[ERROR] Nepodařilo se zapsat Intel HEX: {e}")
        return False

def export_to_report(blocks, kblocks, sr, vystupni_txt):
    """
    Vytvoří tab-delimited textový soubor Rudolf Jan Suchý kompatibilní.
    Sloučí standardní bloky i Komenium bloky a zapíše jejich časy a délky.
    """
    global polarita
    
    text_polarita = "Normal" if polarita == 1 else "Invert"
    
    try:
        print(f"[INFO] Generuji textový report do: {vystupni_txt}")
        
        #nazev = vystupni_txt[:-4]
        nazev = ""
        
        # Hlavička přesně podle poslaného vzoru (oddělená tabulátory)
        hlavicka = "Čas Od\tČas Do\tTyp\tPlatforma\tNázev\tObsah\tFunkční (Orig.)\tFunkční (Edit)\tTurbo\tNázev bloku\tTyp Bloku\tDélka\tPoznámky\n"
        
        with open(vystupni_txt, "w", encoding="utf-8") as f:
            f.write(hlavicka)
            
            # Sloučíme oba seznamy bloků do jednoho pro postupné zpracování
            vsechny_bloky = blocks + kblocks
            
            for idx, block in enumerate(vsechny_bloky):
                # Výpočet časů pomocí tvé stávající funkce
                cas_od = index_time(block.get('start_sample', 0), sr)
                cas_do = index_time(block.get('end_sample', 0), sr)
                
                # Zjištění reálné délky dat
                delka = len(block.get('data', []))
                
                # Rozlišení typu bloku podle tvého klíče 'typ'
                if block.get('typ') == 0:
                    #nazev_bloku = f"Blok {block.get('id', idx)}"
                    nazev_bloku = f""
                    if delka == 0:
                        typ_bloku = "HEX Header"
                    else:
                        typ_bloku = "HEX Header/Data"
                else:
                    #nazev_bloku = f"Blok {block.get('id', idx)}"
                    nazev_bloku = f""
                    typ_bloku = f"Komenium Bin typ {block.get('typ')}"
                
                # Sestavení řádku - fixní hodnoty upraveny pro IQ-151 Komenium
                radek = (
                    f"{cas_od}\t"         # Čas Od
                    f"{cas_do}\t"         # Čas Do
                    f"Data\t"              # Typ
                    f"IQ151\t"             # Platforma
                    f"{nazev}\t"          # Název
                    f"Program\t"           # Obsah
                    f"\t"               # Funkční (Orig.)
                    f"\t"               # Funkční (Edit)
                    f"Není v Turbo\t"      # Turbo
                    f"{nazev_bloku}\t"     # Název bloku (Požadavek: dává se sem typ bloku)
                    f"{typ_bloku}\t"       # Typ Bloku
                    f"{delka}\t"           # Délka
                    f"Polarita {text_polarita}\n"                 # Poznámky
                )
                f.write(radek)
                
        print(f"[OK] Report úspěšně uložen do {vystupni_txt}")
        return True
        
    except Exception as e:
        log(f"[ERROR] Nepodařilo se zapsat report: {e}")
        return False
        
import numpy as np
import scipy.io.wavfile as wav
import os

import numpy as np
import scipy.io.wavfile as wav

def export_to_wav(crossings, start, end, T, vystupni_wav, samplerate=44100):
    """
    Vygeneruje čistý WAV soubor na základě pole průchodů (crossings).
    Rekonstruuje perfektní obdélníkový signál mezi indexy start a end.
    """

    print(f"[INFO] Generuji čistý WAV z průchodů: {vystupni_wav}")
    
    # Definice amplitud pro 16-bit PCM (-32768 až 32767)
    AMP_HIGH = 24000
    AMP_LOW = -24000
    AMP_SILENCE = 0
    
    audio_samples = []
    
    # 1. Úvodní ticho před blokem (cca 1 sekunda)
    audio_samples.extend([AMP_SILENCE] * int(samplerate * 1.0))
    
    # Vytáhneme si pouze ten úsek průchodů, který nás zajímá
    vybrane_crossings = crossings[start:end+1]
    
    # Výchozí stav polarity na začátku bloku
    aktualni_amplituda = AMP_HIGH
    
    len_1 = int(2 * T)   # 2kHz (printická 1)
    threshold = len_1 * 0.75
    
    # Přidáme pilot 1.5s
    for i in range(int(samplerate/T*1.5)):

        delka_pulsu = int(T)
        
        # Vygenerujeme stabilní úroveň pro tento puls
        audio_samples.extend([aktualni_amplituda] * delka_pulsu)
        
        # Překlopíme polaritu pro následující puls (střídání HIGH / LOW)
        aktualni_amplituda = AMP_LOW if aktualni_amplituda == AMP_HIGH else AMP_HIGH
        
    
    # Projdeme dvojice po sobě jdoucích průchodů a vyplníme prostor mezi nimi
    for i in range(len(vybrane_crossings) - 1):
    
        if (vybrane_crossings[i+1]['index'] - vybrane_crossings[i]['index'] > threshold):
            delka_pulsu = int(2*T)
        else:
            delka_pulsu = int(T)
        
        # Vygenerujeme stabilní úroveň pro tento puls
        audio_samples.extend([aktualni_amplituda] * delka_pulsu)
        
        # Překlopíme polaritu pro následující puls (střídání HIGH / LOW)
        aktualni_amplituda = AMP_LOW if aktualni_amplituda == AMP_HIGH else AMP_HIGH
        
    # 2. Závěrečné ticho po bloku (cca 1.5 sekundy pro uložení v IQ-151)
    audio_samples.extend([AMP_SILENCE] * int(samplerate * 1.5))
    
    # Převod na NumPy pole se správným datovým typem (int16)
    audio_data = np.array(audio_samples, dtype=np.int16)
    
    # Zápis do WAV souboru
    wav.write(vystupni_wav, samplerate, audio_data)
    
    print(f"[OK] Soubor úspěšně uložen. Celkem vygenerováno {len(audio_data)} vzorků.")
    return True

def convert_iq151_komenium(input_path, filt=False, visu=False, ampl=False, der=False, crossing_index=0):
    """
    Hlavní orchestrátor celého převodu. Zajišťuje sekvenční průchod fázemi:
    Načtení audio signálu -> Filtrace -> Extrakce hran -> Načtení zavaděče -> Extrakce dat -> Export.
    """
    blocks = []
    kblocks = []
    current_block = 0
    global chyba_crc_pocet
    global polarita

    # 1. Načtení a příprava nahrávky
    data, sr_local = process_wav(input_path)
    
    # 2. Filtrace v případě aktivního přepínače
    if filt:
        data = filtr(data, sr_local)       
	
    # 3. Sběr hran (klasicky vs. amplitudové špičky)
    if ampl:
        crossings = detect_crossings_amplitude(data)
    elif der:
        crossings = detect_crossings_dynamic_derivative(data)
    else:
        crossings = detect_crossings(data)

    program = 0
    
    # 4. Výpočet základní periody (T)
    T = analyze(crossings)
    
    # Najeď za dlouhý pilotní tón a potlačí špatný pilot na začátku kazety
    crossing_index, ispilot = najdi_pilotni_ton(crossings, T, crossing_index, 300)
    afterpilot = crossing_index
    
    # 5. Smyčka pro čtení Standardních zaváděcích bloků
    blk_valid = True 
    while (crossing_index < len(crossings)) and blk_valid:
        print(f"[OK] Zpracovávám blok: {current_block}, index: {crossing_index}")
        blocks, crossing_index, blk_valid = cti_blok(crossings, T, crossing_index, blocks, current_block)
        current_block += 1
    
    if not blocks:
        print("[INFO] Nic jsem nanašel, obracím polaritu a zkouším znova.")
        blocks = []
        current_block = 0
        polarita ^= 1
        crossing_index = afterpilot
        blk_valid = True 
        while (crossing_index < len(crossings)) and blk_valid:
            print(f"[OK] Zpracovávám blok: {current_block}, index: {crossing_index}")
            blocks, crossing_index, blk_valid = cti_blok(crossings, T, crossing_index, blocks, current_block)
            current_block += 1
        
    if not blocks:
        print("[INFO] Na nahrávce nebyly nalezeny žádné platné datové bloky!")
        return
        
    
    cas = index_time(blocks[-1]['end_sample'], sr_local)
    print("[INFO] Konec Standardních bloků na: ", cas)
    
    crossing_index = blocks[-1]['end_index']
    
    #podle vstupni adresy loaderu rozeznám typ Komenium loaderu   
    vstupniaddr = "".join(blocks[-1]['header'])[2:6]
    
    if vstupniaddr == "7934":
        typ = 1 #delka hlavy 4
    elif vstupniaddr == "3FAE":
        typ = 1 
    elif vstupniaddr == "7934":
        typ = 2 #delka hlavy 5
    elif vstupniaddr == "7AE2":
        typ = 1
    elif vstupniaddr == "7010":
        typ = 1
    elif vstupniaddr == "0226":
        typ = 2
    elif vstupniaddr == "7A6B":
        typ = 2
    elif vstupniaddr == "024D":
        typ = 2
    else:
        typ = 999

    
    # 6. Smyčka pro čtení Komenium bloků s daty programu
    """
    Komenium ukládalo jako jeden blok loading screen a druhý blok data
    Pro zamezení načítání nesmyslů za koncem hlavního datového bloku
    tedy navíc omezím počet bloků na 2
    """

    current_kblock = current_block
    blk_valid = True
    
    while (crossing_index < len(crossings)) and blk_valid:
        print(f"[OK] Zpracovávám Komenium blok: {current_kblock}, typ: {typ}, sample: {crossings[crossing_index]['index']}")
        kblocks, crossing_index, blk_valid = cti_komenium_blok(crossings, T, crossing_index, kblocks, current_kblock, typ)
        current_kblock += 1
    
    if not kblocks:
        log("[INFO] Nebyly nalezeny žádné Komenium bloky k exportu.")
    
    elif chyba_crc_pocet > 0:
        log("\n[INFO] ZÁPIS HEX SOUBORU ZRUŠEN! Nahrávka obsahuje chybu(y) v kontrolním součtu (CRC).")
    
    else:
        # 7. Uložení výsledného souboru Intel HEX
        print("-" * 40)
        hexfilename = os.path.splitext(input_path)[0] + ".hex"
        export_to_intel_hex(kblocks, hexfilename, 80)
        program += 1

        
    # 8. Vytvoří metadata do text souboru (oddělený tabulátory)
    report_filename = os.path.splitext(input_path)[0] + ".txt"
    export_to_report(blocks, kblocks, sr_local, report_filename)
    

    # pokud tu nejsou Komenium bloky, uložíme standard HEX program, aby šel převodník použít    
    if not kblocks and blocks:
        log("[INFO] Standardní IQ151 nahrávka, takže jí uložím do HEX.")
        # 7. Uložení výsledného souboru Intel HEX pro standardní program
        print("-" * 40)
        hexfilename = os.path.splitext(input_path)[0] + ".hex"
        export_to_intel_hex(blocks, hexfilename, 80)
        
    # 9. Volitelná vizualizace do PNG grafu i v případě vadných bloků
    if visu:
        vsechny_bloky = blocks + kblocks
        vizualizuj_wav_a_bloky(data, sr_local, vsechny_bloky, sys.argv[1], os.path.splitext(input_path)[0])
        
        
        
    # 10. Export nové wav
    print("[OK] Generuji novou rekonstruovanou WAV nahrávku")
    # Vytvoření názvu pro nový vyčištěný WAV
    clean_wav_filename = os.path.splitext(input_path)[0] + "_clean.wav"
    
    print("[INFO] Skoncili jsme na indexu: ", crossing_index, "CAS: ", index_time(crossings[crossing_index]['index'], sr_local))
    
    # Spuštění exportu zvuku zpět, natvrdo dělám 44,1KHz wav
    samplerate=44100
    export_to_wav(crossings, blocks[0]['start_index']-500, kblocks[-1]['end_index']+30, samplerate/2000, clean_wav_filename)
    
    print("-" * 40)
    print("[OK] Konec")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("-------------------------------------------------------------")
        print("           Převodník IQ151 Komenium kazet na HEX a WAV")
        print("            (c) Jan Heřman 2026, 2hp@seznam.cz")
        print("                       verze 1.6")
        print("-------------------------------------------------------------")
        print("Použití: python iq151kom2hex.py vstup.wav [-f -v -a -d]")
        print("Pozn. Umí i dávkově zpracovat adresář")
        print("Použití: python iq151kom2hex.py cesta/adresář ")
        print("")
        print("-f    Aplikace pásmového filtru, odfiltruje brum, šum. Použijte v případě selhání převodu")
        print("-v    Generuje obrázek s přehledem bloků v záznamu")
        print("-a    Amplitudová analýza signálu. Pokud převod selhává zkuste ji.")
        print("-d    Derivační analýza signálu. Pokud převod selhává, zkuste ji.")
        print("-------------------------------------------------------------")
        print("Příklad: python iq151kom2hex.py nahravka.wav -v -a")
    else:
        # Načtení tvých definovaných přepínačů
        filt_flag = "-f" in sys.argv
        visu_flag = "-v" in sys.argv
        amplitude_flag = "-a" in sys.argv
        der_flag = "-d" in sys.argv
        
        # Načtení hodnoty za parametrem -i ---
        start_index_val = 0  # Výchozí hodnota, pokud -i nezadá
        if "-i" in sys.argv:
            try:
                # Najdeme, na jaké pozici v argumentech je "-i"
                idx_pos = sys.argv.index("-i")
                # Vezmeme argument hned za ním a převedeme na int
                start_index_val = int(sys.argv[idx_pos + 1])
                print(f"[INFO] Ručně nastaven počáteční index: {start_index_val}")
            except (ValueError, IndexError):
                print("[ERROR] Neplatná nebo chybějící hodnota pro parametr -i! Musí to být celé číslo.")
                print("Příklad použití: -i 23955")
                sys.exit(1)
        
        vstupni_cesta = sys.argv[1]
        wav_soubory = []

        # Analýza, zda jde o složku nebo o jeden soubor
        if os.path.isdir(vstupni_cesta):
            print(f"[INFO] Detekován adresář: {vstupni_cesta}")
            # Načte *.wav i *.WAV
            pattern_lower = os.path.join(vstupni_cesta, "*.wav")
            pattern_upper = os.path.join(vstupni_cesta, "*.WAV")
            wav_soubory = glob.glob(pattern_lower) + glob.glob(pattern_upper)
            wav_soubory.sort()  # Abecední seřazení
        elif os.path.isfile(vstupni_cesta):
            wav_soubory = [vstupni_cesta]
        else:
            log(f"[ERROR] Cesta '{vstupni_cesta}' neexistuje.")
            sys.exit(1)

        if not wav_soubory:
            print("[INFO] V zadaném umístění nebyly nalezeny žádné WAV soubory.")
            sys.exit(0)

        print(f"[INFO] Nalezeno souborů ke zpracování: {len(wav_soubory)}")
        print("=" * 60)

        # Postupné hromadné zpracování nalezených souborů
        for index, aktualni_wav in enumerate(wav_soubory, start=1):
            print(f"\n[{index}/{len(wav_soubory)}] Zpracovávám: {os.path.basename(aktualni_wav)}")
            print("-" * 60)
            
            # Reset globální proměnné pro každý soubor znovu, aby předchozí chyba nezablokovala další soubor
            chyba_crc_pocet = 0
            
            try:
                # Volání tvé funkce s předanými přepínači
                convert_iq151_komenium(
                    aktualni_wav, 
                    filt=filt_flag, 
                    visu=visu_flag, 
                    ampl=amplitude_flag, 
                    der=der_flag,
                    crossing_index=start_index_val
                )
            except Exception as e:
                log(f"[ERROR] Soubor {os.path.basename(aktualni_wav)} selhal na neošetřenou chybu: {e}")
                print("Pokračuji na další soubor v pořadí...")
                
        print("\n=============================================================")
        print("[OK] Zpracování dokončeno.")
        print("=============================================================")
