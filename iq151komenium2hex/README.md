# Převodník magnetofonových záznamů IQ-151 (Komenium) na HEX

Tento skript slouží k převodu digitalizovaných magnetofonových nahrávek (ve formátu `.wav`) z počítače **IQ-151** (určeno pro kazety **Komenium**) do formátu **HEX** a ***WAV***. 

Výsledný `.hex` soubor je optimalizován pro přímé použití v emulátorech nebo moderních hardwarových doplňcích, jako je modul **SD-ROM**, přičemž plně zachovává původní načítací obrazovku (load screen). Skript navíc dokáže vygenerovat vyčištěný a rekonstruovaný `.wav` soubor zpět.

## Hlavní funkce
*   **Automatická detekce a oprava polarity:** Pokud napoprvé selže čtení, skript automaticky invertuje polaritu signálu a zkusí to znovu.
*   **Pokročilé metody analýzy:** Kromě klasické detekce průchodů nulou nabízí amplitudovou analýzu špiček a derivační analýzu trendu.
*   **Pásmová filtrace:** Integrovaný Butterworthův filtr pro odstranění síťového brumu (300 Hz) a vysokofrekvenčního šumu (5 kHz).
*   **Dávkové zpracování:** Možnost zpracovat buď jeden soubor, nebo rovnou celý adresář plný nahrávek.
*   **Vizualizace:** Generování přehledného `.png` grafu s časovou osou a barevně vyznačenými datovými bloky.
*   **Generování reportů:** Export metadat kompatibilních s textovými reporty (tab-delimited).

## Požadavky a instalace

Skript vyžaduje Python 3 a několik externích knihoven pro zpracování signálu a matematické výpočty.

numpy>=1.20.0
scipy>=1.7.0
matplotlib>=3.4.0
tqdm>=4.60.0
