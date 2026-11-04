#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Převodník magnetofonových záznamů počítače PMD 85 na čisté WAV a PTP.

Nástroj analyzuje digitalizované nahrávky z kazet, provádí hardwarovou emulaci čtení hran signálu 
(Biphase/Manchester dekódování), kontroluje integritu bloků pomocí CRC, rekonstruuje signál 
do ideální obdélníkové podoby a extrahuje data do souoru digitální pásky PTP.

Autor: (c) Jan Heřman 2026 <2hp@seznam.cz>
"""

import os
import sys
import warnings
import glob
import traceback
import numpy as np
import matplotlib.pyplot as plt
from scipy.io import wavfile
from scipy.io.wavfile import WavFileWarning
from scipy.signal import butter, filtfilt
from tqdm import tqdm

__version__ = "1.0"
__author__ = "Jan Heřman"

# Globalni práh pro rozhodovani
prah = 0.75

# Přesměrování logování i do souboru
class Tee(object):
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()
    def flush(self):
        for f in self.files:
            f.flush()

# Ignorování specifických varování knihovny SciPy ohledně nestandardních chunků ve WAV souborech
warnings.simplefilter("ignore", WavFileWarning)

# Globální příznak integrity nahrávky (počet chyb CRC)
chyba_crc_pocet = 0


def log(text):
    """
    Pomocná funkce pro barevné formátování výpisu zpráv do terminálu.
    """
    CLR_RED = "\033[31m"
    CLR_YELLOW = "\033[33m"
    CLR_GREEN = "\033[32m"
    CLR_RESET = "\033[0m"
    
    if "[ERROR]" in text:
        print(f"{CLR_RED}{text}{CLR_RESET}")
    elif "[INFO]" in text:
        print(f"{CLR_YELLOW}{text}{CLR_RESET}")
    elif "[OK]" in text:
        print(text.replace("[OK]", f"{CLR_GREEN}[OK]{CLR_RESET}"))
    else:
        print(text)


def process_wav(input_path):
    """
    Načte vstupní audiosoubor WAV, v případě stereo nahrávky vybere 
    hlasitější kanál a provede špičkovou amplitudovou normalizaci.
    """
    sr, data = wavfile.read(input_path)
    
    if data.ndim > 1:
        data = data.astype(float)
        # Zjistíme špičkovou hlasitost pro levý (index 0) a pravý (index 1) kanál
        max_left = np.max(np.abs(data[:, 0]))
        max_right = np.max(np.abs(data[:, 1]))
        
        # Vybereme ten, který má větší amplitudu
        if max_left > max_right:
            data = data[:, 0]
            print("[INFO] Vstup je stereo. Vybrán LEVÝ kanál (je hlasitější).")
        else:
            data = data[:, 1]
            print("[INFO] Vstup je stereo. Vybrán PRAVÝ kanál (je hlasitější).")
    else:
        data = data.astype(float)
    
    max_val = np.max(np.abs(data))
    if max_val > 0:
        data /= max_val
    
    # Centrovaná normalizace pro vnitřní logiku dekodéru
    orig_centered = data - np.mean(data)
    max_orig = np.max(np.abs(orig_centered))
    orig_normalized = (orig_centered / max_orig * 30000) if max_orig > 0 else orig_centered
    
    return orig_normalized, sr


def filtr(data, sr):
    """
    Aplikuje Butterworthův pásmový filtr (Band-pass).
    Odřízne nízkofrekvenční brum pod 300 Hz (způsobující DC posun) 
    a vysokofrekvenční šum nad 5000 Hz.
    """
    low_cutoff = 300    # Hz
    high_cutoff = 5000  # Hz
    order = 4           
    
    nyq = sr / 2
    b, a = butter(order, [low_cutoff / nyq, high_cutoff / nyq], btype='band')

    print("[OK] Aplikuji pásmový filtr (300 Hz - 5 kHz)...")
    filtered = filtfilt(b, a, data)
    return filtered


def detect_crossings(data):
    """
    Klasická detekce průchodů signálu nulou.
    Zaznamenává indexy vzorků a směr přechodu (1 = stoupající, 0 = klesající).
    """
    crossings = []
    for i in tqdm(range(1, len(data)), desc="[OK] Analyzuji signál"):
        if data[i-1] < 0 <= data[i]:
            crossings.append({'index': i, 'dir': 1})
        elif data[i-1] > 0 >= data[i]:
            crossings.append({'index': i, 'dir': 0})
    return crossings

    
def analyze(crossings):
    """
    Statistická analýza periodicity hran. Počítá medián délky pulsu,
    který definuje základní časovou jednotku (T) nahrávky PMD 85.
    """
    diffs = np.diff([item['index'] for item in crossings])
    T = np.median(diffs[(diffs > 9) & (diffs < 27)])

    print("-" * 40)
    print(f"Analýza signálu:")
    print(f"  Detekovaný puls (T):  {T:.2f} vzorků")
    print(f"  Počet hran (změn):    {len(crossings)}")
    print("-" * 40)
    return T


def crossings_to_byte(crossings, T, start_crossing, cbit):
    """
    Čte proud surových biphase dat z průchodů hran a skládá je posuvem do bajtů.
    """
    len_1 = int(2 * T)
    threshold = len_1 * prah
    
    bits = []
    byte_val = 0
    current_bit = cbit
    i = start_crossing
    
    if (i + 22) > len(crossings):
        return False, False, i, False, False
    
    pred = i
    # posuneme se k dalšímu start bitu, protože u PMD jsou pilotní tóny mezi hlavičkou a daty
    while (crossings[i+1]['index'] - crossings[i]['index'] < threshold):
        i += 2

    next_crossing = i + 1
     
    while len(bits) < 11:
        dt = crossings[i+1]['index'] - crossings[i]['index']
        if dt > threshold:
            current_bit ^= 1
            bits.append({'index': crossings[i+1]['index'], 'bit': current_bit})
            i += 1
        else:
            bits.append({'index': crossings[i+1]['index'], 'bit': current_bit})
            i += 2 
            
    for bit_entry in bits[1:9]:  
        byte_val = (byte_val >> 1) | (bit_entry['bit'] << 7)
    
    end_byte_crossing = i
    end_data_sample = bits[-1]['index']

    if (bits[0]['bit'] == 0) and (bits[9]['bit'] == 1) and (bits[10]['bit'] == 1): #validní start bit a dva stop bity  
        return byte_val, next_crossing, end_byte_crossing, current_bit, end_data_sample
    else:
        return False, False, end_byte_crossing, False, False


def check_crc(byte_data, stored_checksum):
    """
    Ověřuje kontrolní součet (8-bitový aditivní checksum).
    """
    calculated_sum = sum(byte_data) & 0xFF
    return calculated_sum == stored_checksum


def find_sync(crossings, T, start_crossing):
    """
    Hledá na kazetě začátek hlavičky.
    Využívá posuvný registr a vrací index nálezu a zjištěnou polaritu fáze.
    """
    cbit = 1
    syncbits = "11111111111111111111110111111111101111111111"
    syncbits_inv = "".join('1' if b == '0' else '0' for b in syncbits)
    
    len_1 = int(2 * T)
    threshold = len_1 * prah
    
    with tqdm(total=len(crossings), initial=start_crossing, desc="Hledám bloky: ", leave=False) as pbar:
        while (start_crossing + 2*len(syncbits)) < len(crossings):
            i = start_crossing
            bits = []
            current_bit = cbit
            
            while len(bits) < len(syncbits):
                dt = crossings[i+1]['index'] - crossings[i]['index']
                if dt > threshold:
                    current_bit ^= 1
                    bits.append({'index': crossings[i+1]['index'], 'bit': current_bit})
                    i += 1
                else:
                    bits.append({'index': crossings[i+1]['index'], 'bit': current_bit})
                    i += 2 

            bits_string = "".join(str(b['bit']) for b in bits)

            if bits_string == syncbits:
                return i-40, 1 #o 40 mene je zacatek prvni sync byte
            elif bits_string == syncbits_inv:
                return i-40, 0
            else:
                start_crossing += 1
                pbar.update(1)
                
    print("[INFO] Do konce nahrávky žádný další blok... Konec")
    return False, False


def cti_blok(crossings, T, crossing_index, blocks, current_block):
    """
    Načte a extrahuje jeden blok z nahrávky.
    """
            
    crossing_index, cbit = find_sync(crossings, T, crossing_index)
    if not crossing_index:
        return blocks, False, False
            
    start_sample = crossings[crossing_index]['index']
    start_index = crossing_index
        
    print("[OK] Nalezen začátek bloku, sample:", start_sample)
    blocks.append({'id': current_block, 'start_index': crossing_index, 'start_sample': start_sample})
    
    data = []
    for b in range(63): #délka hlavičky PMD 85
        current_byte, next_crossing, end_byte_crossing, cbit, sample = crossings_to_byte(crossings, T, crossing_index, cbit)
        if current_byte is False:
            return blocks, end_byte_crossing, False
        crossing_index = end_byte_crossing
        data.append(current_byte)

    # Definice očekávaných vzorků v hlavičče (16x 0xFF, 16x 0x00, 16x 0x55)
    ocekavano_ff = [0xFF] * 16
    ocekavano_00 = [0x00] * 16
    ocekavano_55 = [0x55] * 16
    
    # Kontrola jednotlivých úseků v poli data
    if (data[0:16] == ocekavano_ff and 
        data[16:32] == ocekavano_00 and 
        data[32:48] == ocekavano_55):

        # Vytvořím PTP data pro tento začátek bloku a budu přidávat
        ptp_length = len(data).to_bytes(2, byteorder='little')
        blocks[-1]['ptp_data'] = bytearray(ptp_length)
        blocks[-1]['ptp_data'].extend(data) 
            
        # Parsování metadat hlavičky podle PMD 85 PTP specifikace
        blocks[-1]['cislo_souboru'] = data[48]
        blocks[-1]['typ_souboru'] = data[49]
        
        blocks[-1]['adresa'] = data[50:52]
        blocks[-1]['delka'] = data[52:54]
        blocks[-1]['nazev'] = bytes(data[54:62]).decode('ascii', errors='ignore').strip()
        
        header_valid = check_crc(data[48:62], data[-1])       
        blocks[-1]['header_crc'] = header_valid
        
        if header_valid:
            ptp_data = []
            # a načtu datový blok pokud je hlavička OK
            delka_dat = int.from_bytes(data[52:54], byteorder='little') + 2
        
            for b in range(delka_dat): #délka dat
                current_byte, next_crossing, end_byte_crossing, cbit, sample = crossings_to_byte(crossings, T, crossing_index, cbit)
                crossing_index = end_byte_crossing
                data.append(current_byte)
                ptp_data.append(current_byte)
            
            data_valid = check_crc(data[63:62+delka_dat], data[62+delka_dat])
        else:
            data_valid = False
        
        blocks[-1]['data_crc'] = data_valid
        blocks[-1]['data'] = data
        blocks[-1]['end_sample'] = crossings[crossing_index]['index']
        blocks[-1]['end_index'] = crossing_index
        
        # Vytvořím PTP data pro tento datový blok
        ptp_length = len(ptp_data).to_bytes(2, byteorder='little')
        blocks[-1]['ptp_data'].extend(ptp_length)
        blocks[-1]['ptp_data'].extend(ptp_data)

        if data_valid and header_valid:
            print(f"[OK] Konec bloku {blocks[-1]['cislo_souboru']}/{chr(blocks[-1]['typ_souboru'])}, "
                  f"název: {blocks[-1]['nazev']}, CRC OK")
        elif data_valid:
            log(f"[ERROR] Konec bloku, pravděpodobný název: {blocks[-1]['nazev']} - Chyba kontrolního součtu HLAVIČKY!")
        elif header_valid:
            log(f"[ERROR] Konec bloku, název: {blocks[-1]['nazev']} - Chyba kontrolního součtu DAT!")
        else:
            log(f"[ERROR] Konec bloku, Chyba kontrolního součtu HLAVIČKY i DAT!")
        
        # Odtud pokračuji dál, kvůli nepodporovaným blokům je třeba načítat další data, dokud
        # je platný rámec bajtu (1x start bit, 2x stop bit)
        start_index = crossing_index
        data2 = []
        while crossing_index < len(crossings)-44: #čti dokud číst lze - neznámý blok tu může být, na základě start a stop bitů
                current_byte, next_crossing, end_byte_crossing, cbit, sample = crossings_to_byte(crossings, T, crossing_index, cbit)
                if current_byte is False:
                    break
                crossing_index = end_byte_crossing
                data2.append(current_byte)
        
        if len(data2) > 2: #pokud tam skutečně něco je bude to asi delší než dva bajty

            print("[OK] Nalezen začátek nestandardního bloku, sample:", crossings[start_index]['index'])
            blocks.append({'id': current_block+1, 'start_index': start_index, 'start_sample': crossings[start_index]['index']})
                
            # U neznámého typu si prostě budu teď vymýšlet
            blocks[-1]['data_crc'] = "n/a"
            blocks[-1]['header_crc'] = "n/a"
            blocks[-1]['data'] = data2
            blocks[-1]['end_sample'] = crossings[crossing_index]['index']
            blocks[-1]['end_index'] = crossing_index
            blocks[-1]['cislo_souboru'] = 0
            blocks[-1]['typ_souboru'] = 46 #neznamy blok bude třeba tečka
            blocks[-1]['delka'] = len(data2)
            
            # Vytvořím PTP data pro tento neznámý datový blok
            ptp_length = len(data2).to_bytes(2, byteorder='little')
            blocks[-1]['ptp_data'] = bytearray(ptp_length)
            blocks[-1]['ptp_data'].extend(data2)
                      
            # Tady to je hack, aby se vysledny wav generoval s predchozim standard blokem a nazvem
            # což je v praxi takto udělané, pře neznámým blokem musí být nějaký loader
            blocks[-1]['start_index'] = blocks[-2]['start_index']
            blocks[-1]['nazev'] = "n/a"
        
        return blocks, end_byte_crossing, (data_valid and header_valid)

def index_time(crossing_index, samplerate):
    """
    Přepočítává vzorkový index pozice na pásce do lidsky čitelného formátu času MM:SS.mmm.
    """
    total_seconds = crossing_index / samplerate
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60
    total_minutes = (hours * 60) + minutes
    return f"{total_minutes:02d}:{seconds:06.3f}"


def export_to_report(blocks, sr, vystupni_txt):
    """
    Generuje textový analytický report struktury kazety kompatibilní s databází historických nahrávek Rudolfa Jana Suchého.
    """
    try:
        print(f"[INFO] Generuji textový report do: {vystupni_txt}")
        hlavicka = "Čas Od\tČas Do\tTyp\tPlatforma\tNázev\tObsah\tFunkční (Orig.)\tFunkční (Edit)\tTurbo\tNázev bloku\tTyp Bloku\tDélka\tPoznámky\n"
        
        with open(vystupni_txt, "w", encoding="utf-8") as f:
            f.write(hlavicka)
            for idx, block in enumerate(blocks):
                cas_od = index_time(block.get('start_sample', 0), sr)
                cas_do = index_time(block.get('end_sample', 0), sr)
                delka = len(block.get('data', []))
                
                crc_bloku = "Ano" if (block.get('data_crc') and block.get('header_crc')) else "Ne"
                cislo_bloku = f"{block.get('cislo_souboru', idx)}"
                typ_bloku = f"{chr(block.get('typ_souboru', idx))}"
                nazev_bloku = f"{block.get('nazev', idx)}".strip() if block.get('header_crc', idx) else ""
                poznamky_bloku = f"".strip()
                
                radek = (
                    f"{cas_od}\t{cas_do}\tData\tPMD-85\t{nazev_bloku}\t\t"
                    f"{crc_bloku}\t\tNení v Turbo\t{nazev_bloku}\t"
                    f"{typ_bloku}\t{delka}\t{poznamky_bloku}\n"
                )
                f.write(radek)
        print(f"[OK] Report úspěšně uložen.")
        return True
    except Exception as e:
        log(f"[ERROR] Nepodařilo se zapsat report: {e}")
        return False
        

def export_to_wav(crossings, start, end, T, vystupni_wav, samplerate=44100):
    """
    Vygeneruje novou, matematicky vyčištěnou obdélníkovou WAV nahrávku bloku 
    (vhodné pro bezproblémové načítání v reálném hardwaru).
    """
    AMP_HIGH = 24000
    AMP_LOW = -24000
    AMP_SILENCE = 0
    
    audio_samples = []
    audio_samples.extend([AMP_SILENCE] * int(samplerate * 1.0))
    
    vybrane_crossings = crossings[start:end+1]
    aktualni_amplituda = AMP_HIGH
    
    len_1 = int(2 * T)   
    threshold = len_1 * prah
    
    # Rekonstrukce pilotního tónu (1.5 sekundy)
    for i in range(int(samplerate / T * 1.5)):
        audio_samples.extend([aktualni_amplituda] * int(T))
        aktualni_amplituda = AMP_LOW if aktualni_amplituda == AMP_HIGH else AMP_HIGH
        
    # Výplň samotných datových period
    for i in range(len(vybrane_crossings) - 1):
        if (vybrane_crossings[i+1]['index'] - vybrane_crossings[i]['index'] > threshold):
            delka_pulsu = int(2 * T)
        else:
            delka_pulsu = int(T)
        
        audio_samples.extend([aktualni_amplituda] * delka_pulsu)
        aktualni_amplituda = AMP_LOW if aktualni_amplituda == AMP_HIGH else AMP_HIGH
        
    audio_samples.extend([AMP_SILENCE] * int(samplerate * 1.5))
    audio_data = np.array(audio_samples, dtype=np.int16)
    wavfile.write(vystupni_wav, samplerate, audio_data)
    
    print(f"[OK] Vyčištěný WAV úspěšně uložen ({len(audio_data)} vzorků).")
    return True

def export_to_ptp(blocks, vystupni_ptp):
    """
    Sestaví soubor formátu PTP. 
    """
    
    try:
        ptp_obsah = bytearray()
        
        for block in blocks:
            # Získání dat z bloku
            surova_data = block.get('ptp_data', [])

            # Pojistka, pokud by data byla ve tvaru listu čísel
            if isinstance(surova_data, list):
                surova_data = bytes(surova_data)
            elif not isinstance(surova_data, bytes):
                surova_data = bytes(surova_data)

            ptp_obsah.extend(surova_data)
            
        # Zápis do binárního souboru
        with open(vystupni_ptp, "wb") as f:
            f.write(ptp_obsah)
            
        print(f"[OK] PTP soubor úspěšně uložen: {vystupni_ptp} ({len(ptp_obsah)} bajtů)")
        return True

    except Exception as e:
        print(f"[CHYBA] Nepodařilo se vyexportovat PTP soubor: {e}")
        return False
                
def vizualizuj_wav_a_bloky(data, sr, blocks, wav_filename, base_name):
    """
    Vykreslí waveform WAV souboru s kaskádovým vyznačením a popisem detekovaných bloků.
    """
    pngfilename = f"{base_name}.png"
    print(f"[OK] Generuji grafickou vizualizaci do {pngfilename}...")
    
    delka_vzorku = len(data)
    casova_osa = np.arange(delka_vzorku) / sr
    celkovy_cas = delka_vzorku / sr
    
    if len(data.shape) == 1:
        kanaly = 1
        stops = [data]
    else:
        kanaly = data.shape[1]
        stops = [data[:, 0], data[:, 1]]
        
    fig, axes = plt.subplots(kanaly, 1, figsize=(16, 9), sharex=True, squeeze=False)
    fig.suptitle(f"Analýza záznamu: {os.path.basename(wav_filename)}\n({sr} Hz, {celkovy_cas:.2f} s)", 
                 fontsize=15, fontweight='bold', color='#1a252f', y=0.96)
    
    nazvy_kanalu = ["Levý kanál", "Pravý kanál"] if kanaly == 2 else ["Audio stopa"]
    pocet_bloku = max(len(blocks), 1)
    barvy_palety = plt.colormaps['tab20b'](np.linspace(0, 1, pocet_bloku))
    
    for ch in range(kanaly):
        ax = axes[ch, 0]
        ax.plot(casova_osa, stops[ch], color='#4a6984', alpha=0.35, linewidth=0.5)
        ax.set_title(nazvy_kanalu[ch], fontsize=11, fontweight='semibold', color='#34495e', loc='left', pad=12)
        ax.grid(True, linestyle=':', alpha=0.5, color='#bdc3c7')
        ax.set_xlim(0, celkovy_cas)
        
        ax.get_yaxis().set_visible(False)
        for spine in ['top', 'left', 'right']:
            ax.spines[spine].set_visible(False)
        ax.spines['bottom'].set_color('#7f8c8d')
        
        max_val = np.max(np.abs(data)) if np.max(np.abs(data)) > 0 else 1
        obsazeny_prostor = []
        
        for idx, block in enumerate(blocks):
            start_idx = block.get('start_sample', 0)
            end_idx = block.get('end_sample', len(data))

            t_start = start_idx / sr
            t_end = end_idx / sr
            t_stred = t_start + ((t_end - t_start) / 2)
            
            barva_bloku = barvy_palety[idx]
            ax.axvspan(t_start, t_end, color=barva_bloku, alpha=0.12)
            ax.axvline(t_start, color=barva_bloku, linestyle='--', linewidth=0.8, alpha=0.5)
            ax.axvline(t_end, color=barva_bloku, linestyle='--', linewidth=0.8, alpha=0.5)
            
            nazev = str(block.get('nazev') or 'n/a').strip()
            info_text = f"{nazev} | start: {t_start:.1f}s"
            vyska_start = max_val * 1.2
            krok_patra = max_val * 4.9  
            odhad_sirky_textu_s = celkovy_cas * 0.02
            
            kolize = True
            while kolize:
                kolize = False
                text_x_start = t_stred - (odhad_sirky_textu_s / 2)
                text_x_end = t_stred + (odhad_sirky_textu_s / 2)
                
                for predchozi_x_start, predchozi_x_end, predchozi_y in obsazeny_prostor:
                    if abs(vyska_start - predchozi_y) < (krok_patra * 0.8):
                        if not (text_x_end < predchozi_x_start or text_x_start > predchozi_x_end):
                            vyska_start += krok_patra  
                            kolize = True
                            break
            
            obsazeny_prostor.append((text_x_start, text_x_end, vyska_start))

            ax.annotate(
                info_text, xy=(t_stred, max_val * 0.2), xytext=(t_stred, vyska_start),
                ha='center', va='bottom', fontsize=10, rotation=90,
                bbox=dict(boxstyle="square,pad=0.4", fc="#ffffff", ec=barva_bloku, alpha=0.95, lw=1.5),
                arrowprops=dict(arrowstyle="-", color=barva_bloku, lw=1.0, alpha=0.7)
            )

        if obsazeny_prostor:
            nejvyssi_bod = max([pos[2] for pos in obsazeny_prostor])
            ax.set_ylim(-max_val * 1.1, nejvyssi_bod + (max_val * 2.5))
        else:
            ax.set_ylim(-max_val * 1.1, max_val * 4.0)

    axes[-1, 0].set_xlabel("Čas (sekundy)", fontsize=11, fontweight='semibold', color='#34495e', labelpad=8)
    plt.tight_layout(rect=[0, 0, 1, 0.72])
    plt.savefig(pngfilename, dpi=200, format='png')
    plt.close()
    print(f"[OK] Graf uložen.")


def convert_pmd85(input_path, filt=False, visu=False):
    """
    Hlavní funkce analýzy jednoho WAV souboru.
    """
    blocks = []
    global chyba_crc_pocet

    # Příprava signálu
    data, sr_local = process_wav(input_path)
    
    # Volitelná filtrace
    if filt:
        data = filtr(data, sr_local)       

    # Detekce změn/hran
    crossings = detect_crossings(data)
    
    if not crossings:
        print("[INFO] V signálu nebyly detekovány žádné hrany.")
        return

    crossing_index = 0 
    T = analyze(crossings)
    chyba_crc_pocet = 0
    
    adresar_vstupu = os.path.dirname(input_path)              
    if not adresar_vstupu:
        adresar_vstupu = os.getcwd()

    try:
        while crossing_index < len(crossings) - 128:
            program_start = crossing_index
            current_block = 0 
            blk_valid = True 
            chyba_crc_pocet = 0
            blocks, crossing_index, blk_valid = cti_blok(crossings, T, crossing_index, blocks, current_block)
            
            if not crossing_index:
                #Konec
                break
                    
            if not blk_valid:
                chyba_crc_pocet += 1
                continue

            if not blocks:
                print("[INFO] Na nahrávce nebyly nalezeny žádné platné datové bloky.")
                break
                
            crossing_index = blocks[-1]['end_index']
            
            # Export vyčištěného WAVu (pouze pokud je celistvost a CRC souboru stoprocentní)
            # WAV v případě nestandard bloku bude mít název jako normální blok před ním
            if chyba_crc_pocet == 0:
                if blocks[-1]['nazev'] == "n/a":
                    cisty_nazev = blocks[-2]['nazev'].replace('/', '_') 
                else:
                    cisty_nazev = blocks[-1]['nazev'].replace('/', '_')
                clean_wav_filename = os.path.join(adresar_vstupu, cisty_nazev + ".wav")
                print("[OK] Generuji novou rekonstruovanou WAV nahrávku:", clean_wav_filename)
                export_to_wav(crossings, blocks[-1]['start_index'] - 200, blocks[-1]['end_index'] + 2, sr_local / 2400, clean_wav_filename)
    
    except Exception as e:
        if blocks: 
            blocks.pop()
        print(f"[INFO] Přerušení nebo konec platného záznamu")
        #traceback.print_exc()
        
    # Export všech bloků do PTP   
    export_to_ptp(blocks, os.path.splitext(input_path)[0]+".ptp")
      
    if visu:
        vizualizuj_wav_a_bloky(data, sr_local, blocks, input_path, os.path.splitext(input_path)[0])
        
    report_filename = os.path.splitext(input_path)[0] + ".txt"
    export_to_report(blocks, sr_local, report_filename)
    print(f"[OK] Zpracování souboru dokončeno.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("-------------------------------------------------------------")
        print("         Převodník PMD 85 kazetových záznamů")
        print(f"            (c) {__author__} 2026, 2hp@seznam.cz")
        print(f"                      verze {__version__}")
        print("-------------------------------------------------------------")
        print("Použití pro jeden soubor: python pmd2ptp.py vstup.wav [-f -v]")
        print("Použití pro celou složku: python pmd2ptp.py cesta/složka/ [-f -v]")
        print("")
        print("-f    Aplikace pásmového filtru (odstraní síťový brum a VF šum).")
        print("-v    Generuje PNG obrázek s vizuálním přehledem bloků.")
        print("-------------------------------------------------------------")
    else:
        print("=" * 60)
        print(f"        Převodník PMD 85 kazetových záznamů")
        print(f"           (SAKRA Project) v{__version__} by {__author__}")
        print("=" * 60)
        filt_flag = "-f" in sys.argv
        visu_flag = "-v" in sys.argv
        
        vstupni_cesta = sys.argv[1]
        wav_soubory = []

        if os.path.isdir(vstupni_cesta):
            print(f"[INFO] Detekován adresář složky: {vstupni_cesta}")
            wav_soubory = glob.glob(os.path.join(vstupni_cesta, "*.wav")) + glob.glob(os.path.join(vstupni_cesta, "*.WAV"))
            wav_soubory.sort()
        elif os.path.isfile(vstupni_cesta):
            wav_soubory = [vstupni_cesta]
        else:
            log(f"[ERROR] Cesta '{vstupni_cesta}' neexistuje.")
            sys.exit(1)

        if not wav_soubory:
            print("[INFO] V zadaném umístění nebyly nalezeny žádné soubory typu WAV.")
            sys.exit(0)

        print(f"[INFO] Nalezeno souborů ke zpracování: {len(wav_soubory)}")
        print("=" * 60)

        for index, aktualni_wav in enumerate(wav_soubory, start=1):
            print(f"\n[{index}/{len(wav_soubory)}] Zpracovávám soubor: {os.path.basename(aktualni_wav)}")
            print("-" * 60)
            chyba_crc_pocet = 0
            
            puvodni_stdout = sys.stdout
            log_file = None
            
            try:
                log_filename = os.path.splitext(aktualni_wav)[0] + ".log"               
                # Otevřu log
                log_file = open(log_filename, "w", encoding="utf-8")
                sys.stdout = Tee(puvodni_stdout, log_file)
                next_index = 0
                next_index = convert_pmd85(aktualni_wav, filt=filt_flag, visu=visu_flag)
            except Exception as e:
                #print(f"[INFO] Záznam nahrávky ukončen nebo neočekávaná chyba: {e}")
                print("Pokračuji na další soubor v pořadí...")
            finally:
                if log_file is not None:
                    sys.stdout = puvodni_stdout
                    log_file.close()
                
        print("\n=============================================================")
        print("[OK] Hromadné zpracování kazet kompletně dokončeno.")
        print("=============================================================")
