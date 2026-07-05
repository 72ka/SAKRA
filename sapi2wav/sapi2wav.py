#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Převodník magnetofonových záznamů počítače SAPI-1 (systém MIKOS) na čisté WAV a textové soubory.

Nástroj analyzuje digitalizované nahrávky z kazet, provádí hardwarovou emulaci větvení hran signálu 
(Biphase/Manchester dekódování), kontroluje integritu bloků pomocí CRC, rekonstruuje signál 
do ideální obdélníkové podoby a extrahuje data souborů (ASCII texty/BASIC nahrávky).

Verze: 1.1
Autor: (c) Jan Heřman 2026 <2hp@seznam.cz>
"""

import os
import sys
import warnings
import glob
import numpy as np
import matplotlib.pyplot as plt
from scipy.io import wavfile
from scipy.io.wavfile import WavFileWarning
from scipy.signal import butter, filtfilt
from tqdm import tqdm

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
    Načte vstupní audiosoubor WAV, v případě stereo nahrávky provede downmix 
    kanálů do mono signálu a provede špičkovou amplitudovou normalizaci.
    
    Args:
        input_path (str): Cesta k původnímu WAV souboru.
    Returns:
        tuple: (normalizovaná audio data typu numpy array, samplerate)
    """
    sr, data = wavfile.read(input_path)
    
    if data.ndim > 1:
        data = data.astype(float)
        data = (data[:, 0] + data[:, 1]) / 2.0
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


def detect_crossings_dynamic_derivative(data, sr):
    """
    Pokročilá detekce vrcholů (extrémů) signálu na základě změny směru (derivace trendu).
    Ignoruje absolutní hodnotu amplitudy i DC posun, ideální pro silně poškozené nahrávky.
    """
    window_size = 4 * max(2, int(sr * 0.00063 / 6))
    crossings = []
    print("[Analýza] Hledám lokální extrémy pomocí derivace trendu...")

    for i in tqdm(range(window_size, len(data) - window_size), desc="Hledám vrcholy"):
        if data[i] > data[i - 1] and data[i] >= data[i + 1]:
            if data[i] == np.max(data[i - window_size : i + window_size + 1]):
                if not crossings or (i - crossings[-1]['index'] > window_size):
                    crossings.append({'index': i, 'dir': 1})  # Lokální maximum
                    
        elif data[i] < data[i - 1] and data[i] <= data[i + 1]:
            if data[i] == np.min(data[i - window_size : i + window_size + 1]):
                if not crossings or (i - crossings[-1]['index'] > window_size):
                    crossings.append({'index': i, 'dir': 0})  # Lokální minimum
    return crossings

    
def analyze(crossings):
    """
    Statistická analýza periodicity hran. Počítá medián délky pulsu,
    který definuje základní časovou jednotku (T) nahrávky.
    """
    diffs = np.diff([item['index'] for item in crossings])
    T = np.median(diffs[(diffs > 4) & (diffs < 24)])

    print("-" * 40)
    print(f"Analýza signálu:")
    print(f"  Detekovaný puls (T):  {T:.2f} vzorků")
    print(f"  Počet hran (změn):    {len(crossings)}")
    print("-" * 40)
    return T


def kcrossings_to_char(crossings, T, start_crossing, cbit):
    """
    Čte proud surových biphase dat z průchodů hran a skládá je posuvem do bajtů.
    """
    len_1 = int(2 * T)
    threshold = len_1 * 0.75
    
    bits = []
    byte_val = 0
    current_bit = cbit
    i = start_crossing

    if (crossings[i+1]['index'] - crossings[i]['index'] > threshold):
        next_crossing = i + 1
    else:
        next_crossing = i + 2

    if (i + 22) > len(crossings):
        return False, False, i, False, False
        
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
          
    return byte_val, next_crossing, end_byte_crossing, current_bit, end_data_sample


def check_crc(byte_data):
    """
    Ověřuje kontrolní součet MIKOS bloku (8-bitový aditivní checksum).
    """
    if len(byte_data) < 272:
        return False
    calculated_sum = sum(byte_data[:-3]) & 0xFF
    stored_checksum = byte_data[269]
    return calculated_sum == stored_checksum


def find_sync(crossings, T, start_crossing):
    """
    Hledá na kazetě unifikovanou synchronizační sekvenci (3x za sebou bajt 0x10).
    Využívá posuvný registr a vrací index nálezu a zjištěnou polaritu fáze.
    """
    cbit = 1
    syncbits = "000001000110000010001100000100011"
    syncbits_inv = "".join('1' if b == '0' else '0' for b in syncbits)
    
    len_1 = int(2 * T)
    threshold = len_1 * 0.75
    
    with tqdm(total=len(crossings), initial=start_crossing, desc="Hledám bloky: ", leave=False) as pbar:
        while (start_crossing + len(syncbits)) < len(crossings):
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
                return i, 0
            elif bits_string == syncbits_inv:
                return i, 1
            else:
                start_crossing += 1
                pbar.update(1)
                
    print("[INFO] Do konce nahrávky žádný další blok... Konec")
    return i, cbit


def cti_blok(crossings, T, crossing_index, blocks, current_block):
    """
    Načte a extrahuje jeden kompletní 272-bajtový MIKOS blok z nahrávky.
    """
    crossing_index, cbit = find_sync(crossings, T, crossing_index)
    start_sample = crossings[crossing_index]['index']
        
    print("[OK] Nalezen začátek bloku, sample:", start_sample)
    blocks.append({'id': current_block, 'start_index': crossing_index, 'start_sample': start_sample})
    
    data = []
    for b in range(272):
        current_byte, next_crossing, end_byte_crossing, cbit, sample = kcrossings_to_char(crossings, T, crossing_index, cbit)
        if current_byte is False:
            return blocks, end_byte_crossing, False
        crossing_index = end_byte_crossing
        data.append(current_byte)
    
    blocks[-1]['end_sample'] = crossings[crossing_index]['index']
    blocks[-1]['end_index'] = crossing_index
    blocks[-1]['data'] = data
    
    # Parsování metadat bloku podle MIKOS specifikace
    blocks[-1]['kod'] = data[0]
    blocks[-1]['poznamky'] = ""
    blocks[-1]['funkcni_data'] = data[1:255]
    
    if int(blocks[-1]['kod']) == 0x3A:  # 58 = Název kazety
        blocks[-1]['nazev'] = get_blknazev(data[1:65])
    elif int(blocks[-1]['kod']) == 0x01:  # 1 = Dlouhý název souboru
        blocks[-1]['nazev'] = get_blknazev(data[1:76])
        blocks[-1]['poznamky'] = get_blknazev(data[12:76])
    else:
        blocks[-1]['nazev'] = get_blknazev(data[256:267])
        
    blocks[-1]['cislo_bloku'] = data[-5]
    blocks[-1]['cislo_souboru'] = data[-4]
    
    kblk_valid = check_crc(data)
    blocks[-1]['crc'] = kblk_valid
    
    if kblk_valid:
        print(f"[OK] Konec bloku č. {blocks[-1]['cislo_bloku']}/{blocks[-1]['cislo_souboru']}, "
              f"kód: {hex(blocks[-1]['kod'])}, název: {blocks[-1]['nazev']}, CRC OK")
    else:
        log("[ERROR] Konec bloku - Chyba kontrolního součtu CRC!")
        
    return blocks, end_byte_crossing, kblk_valid
    
    
def get_blknazev(data):
    """
    Konvertuje surová bajtová data ze SAPI hlavičky (původně kódovaná 
    pro Tesla MHB2501 s posunutým bitovým registrem) do čitelného ASCII stringu.
    """
    data = [b | 0x40 for b in data]
    if isinstance(data, list):
        data = bytes(data)
        
    valid_chars = []
    for b in data:
        if 32 <= b <= 95:
            if b == 64: b = 32
            valid_chars.append(chr(b))
        else:
            b = b & 0xbf
            if b == 64: b = 32
            valid_chars.append(chr(b))
               
    return "".join(valid_chars).strip()

      
def extrahuj_data_z_bloku(blocks):
    """
    Sestaví kompletní soubory z jednotlivých načtených bloků pásky.
    Detekuje typy souborů (ASCII/BASIC text vs. BINARY) a kontroluje celistvost řady.
    """
    vysledky = []
    v_souboru = False
    aktualni_typ = None  
    kumulovana_data = []
    aktualni_nazev = "NEZNAMY"
    finalni_nazev = aktualni_nazev
    cislo = 1
    
    for i, block in enumerate(blocks):
        kod = block.get('kod')
        # Získání čistých dat bez režie bloku a bez koncového CRC bajtu
        data = block.get('data', [])[1:-16]
        crc = block.get('crc')
        cislo_bloku = block.get('cislo_bloku')
        
        # 1. Začátek souboru (Hlavička 0x01)
        if kod == 0x01:
            v_souboru = True
            aktualni_typ = None  
            kumulovana_data = []
            surovy_nazev = block.get('nazev', f"SAPI1_{i}").strip()
            aktualni_nazev = surovy_nazev.replace('/', '_')
            finalni_nazev = aktualni_nazev
            cislo = 1
            continue
            
        cislo += 1
        
        # Kontrola kontinuity řady bloků
        if cislo_bloku != cislo:
            finalni_nazev = "-!INCOMPLETE!-" + aktualni_nazev 
        
        if not crc:
            finalni_nazev = "-!BAD_CRC!-" + aktualni_nazev
            
        # 2. Zpracování datových bloků (0x41 / 0x0A / 0x00 = ASCII, 0x42 / 0x0B = Binární)
        if kod in [0x41, 0x0A, 0x00]:
            if aktualni_typ is None:
                aktualni_typ = 'ASCII'
            if 0x1A in data:
                data = data[:data.index(0x1A)]
            kumulovana_data.extend(data)
            
        elif kod in [0x42, 0x0B]:
            if aktualni_typ is None:
                aktualni_typ = 'BINARY'
            kumulovana_data.extend(data)
            
        # 3. Konec souboru (Marker 0x04)
        elif kod == 0x04:
            cislo = 1
            if aktualni_typ is not None:
                if 0x1A in data:
                    data = data[:data.index(0x1A)]
                kumulovana_data.extend(data)
                vysledky.append(uzavri_soubor(finalni_nazev, aktualni_typ, kumulovana_data))
            v_souboru = False
            aktualni_typ = None
            kumulovana_data = []
            aktualni_nazev = "NEZNAMY"

    if v_souboru and kumulovana_data and aktualni_typ is not None:
        print("[INFO] Soubor nebyl korektně uzavřen, exportuji surový zbytek.")
        vysledky.append(uzavri_soubor("-!INCOMPLETE!-" + aktualni_nazev, aktualni_typ, kumulovana_data))

    return vysledky


def uzavri_soubor(nazev, typ, data_list):
    """
    Pomocná funkce konvertující pole nasbíraných hodnot na finální typ (str/bytes).
    """
    surove_bajty = bytes(data_list)
    
    if typ == 'ASCII':
        try:
            text = surove_bajty.decode('ascii', errors='replace')
            text = text.replace('\x0c', '')
            text = text.rstrip('\x1a\x03')
            return {'nazev': nazev, 'typ': 'ASCII', 'data': text}
        except Exception as e:
            print(f"[CHYBA] Dekódování ASCII u souboru {nazev} selhalo: {e}")
            return {'nazev': nazev, 'typ': 'BINARY_FALLBACK', 'data': surove_bajty}
    else:
        return {'nazev': nazev, 'typ': 'BINARY', 'data': surove_bajty}


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
                
                crc_bloku = "Ano" if block.get('crc') else "Ne"
                cislo_bloku = f"{block.get('cislo_bloku', idx)}"
                typ_bloku = f"{hex(block.get('kod', idx))}"
                nazev_bloku = f"{block.get('nazev', idx)}".strip() if block.get('crc', idx) else ""
                poznamky_bloku = f"{block.get('poznamky', idx)}".strip()
                
                radek = (
                    f"{cas_od}\t{cas_do}\tData\tSAPI-1 MIKOS\t{nazev_bloku}\t\t"
                    f"{crc_bloku}\t\tNení v Turbo\t{nazev_bloku} ({cislo_bloku})\t"
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
    threshold = len_1 * 0.75
    
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

        
def vizualizuj_wav_a_bloky(data, sr, blocks, wav_filename, base_name):
    """
    Vykreslí waveform WAV souboru s kaskádovým vyznačením a popisem detekovaných MIKOS bloků.
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
            
            info_text = f"{block.get('nazev')} | start: {t_start:.1f}s"
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
            
            if int(block.get('cislo_bloku', 0)) == 1:
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


def convert_sapi(input_path, filt=False, visu=False):
    """
    Hlavní funkce analýzy jednoho WAV souboru.
    """
    blocks = []
    global chyba_crc_pocet

    # 1. Příprava signálu
    data, sr_local = process_wav(input_path)
    
    # 2. Volitelná filtrace
    if filt:
        data = filtr(data, sr_local)       

    # 3. Detekce změn/hran
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
            
            while crossing_index < len(crossings) and blk_valid:
                blocks, crossing_index, blk_valid = cti_blok(crossings, T, crossing_index, blocks, current_block)
                
                if not blk_valid:
                    chyba_crc_pocet += 1
                    continue
                
                if blocks[-1]['kod'] == 0x3A: 
                    continue
                if blocks[-1]['kod'] == 0x01: 
                    program_start = blocks[-1]['start_index']
                    current_block = 1
                    chyba_crc_pocet = 0
                    continue
                if blocks[-1]['kod'] in [0x41, 0x42, 0x0A, 0x0B, 0]:
                    current_block += 1
                    continue
                if blocks[-1]['kod'] == 4: 
                    cas = index_time(blocks[-1]['end_sample'], sr_local)
                    print("[INFO] Konec programu v čase: ", cas)
                    break
                elif current_block != blocks[-1]['cislo_bloku']:
                    log("[ERROR] Neočekávané číslo bloku!")
                    chyba_crc_pocet += 1
                    continue
                    
            if not blocks:
                print("[INFO] Na nahrávce nebyly nalezeny žádné platné datové bloky MIKOS.")
                break
    
            crossing_index = blocks[-1]['end_index']
            
            # Export vyčištěného WAVu (pouze pokud je celistvost a CRC souboru stoprocentní)
            if chyba_crc_pocet == 0:
                cisty_nazev = blocks[-1]['nazev'].replace('/', '_')
                clean_wav_filename = os.path.join(adresar_vstupu, cisty_nazev + ".wav")
                print("[OK] Generuji novou rekonstruovanou WAV nahrávku:", clean_wav_filename)
                export_to_wav(crossings, program_start - 200, blocks[-1]['end_index'] + 2, sr_local / 4000, clean_wav_filename)
    
    except Exception as e:
        if blocks: blocks.pop()
        print(f"[INFO] Přerušení nebo konec platného záznamu:", e)
    
    # Finální dolování dat z ucelených bloků
    print(f"[INFO] Doluji soubory z paměťových bloků...")   
    exportovane_soubory = extrahuj_data_z_bloku(blocks)

    for soubor in exportovane_soubory:
        cesta_souboru = os.path.join(adresar_vstupu, soubor['nazev'])
        
        if soubor['typ'] == 'ASCII':
            with open(cesta_souboru + ".txt", "w", encoding="ascii", errors="replace") as f:
                f.write(soubor['data'])
            print(f"[OK] Uložen textový soubor/BASIC: {soubor['nazev']}.txt ({len(soubor['data'])} znaků)")
        #else:
            # Možná ToDo dodělat export do INTELHEX?
            #with open(cesta_souboru + ".bin", "wb") as f:
            #    f.write(soubor['data'])
            #print(f"[OK] Uložen binární strojový kód: {soubor['nazev']}.bin ({len(soubor['data'])} bajtů)")
        
    if visu:
        vizualizuj_wav_a_bloky(data, sr_local, blocks, input_path, os.path.splitext(input_path)[0])
        
    report_filename = os.path.splitext(input_path)[0] + ".txt"
    export_to_report(blocks, sr_local, report_filename)
    print(f"[OK] Zpracování souboru dokončeno.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("-------------------------------------------------------------")
        print("         Převodník SAPI-1 MIKOS kazetových záznamů v1.1")
        print("            (c) Jan Heřman 2026, 2hp@seznam.cz")
        print("-------------------------------------------------------------")
        print("Použití pro jeden soubor: python sapi2wav.py vstup.wav [-f -v]")
        print("Použití pro celou složku: python sapi2wav.py cesta/složka/ [-f -v]")
        print("")
        print("-f    Aplikace pásmového filtru (odstraní síťový brum a VF šum).")
        print("-v    Generuje PNG obrázek s vizuálním přehledem bloků.")
        print("-------------------------------------------------------------")
    else:
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
            
            try:
                convert_sapi(aktualni_wav, filt=filt_flag, visu=visu_flag)
            except Exception as e:
                print(f"[INFO] Záznam nahrávky ukončen nebo neočekávaná chyba: {e}")
                print("Pokračuji na další soubor v pořadí...")
                
        print("\n=============================================================")
        print("[OK] Hromadné zpracování kazet kompletně dokončeno.")
        print("=============================================================")
