# SAKRA - a Swiss Army Knife for Retrogaming Archaeologists

<p align="center">
  <img src="sakra.png" alt="SAKRA Project - Digitalization and Data Rescue" width="100%">
</p>

**SAKRA** is a specialized suite of software tools designed for retro-computing archeology, data preservation, and digital archiving. It enables direct, high-precision processing and conversion of digitized analog audio recordings (`.wav`) from legacy computer systems into clean, emulator-ready binary formats and audio tracks.

---

## Supported Platforms & Tools

The project currently provides specialized decoders and converters for the following historical computer platforms and tape formats:

* **PMD 85** (including **Didaktik Alfa** and **Consul 2717**)
* **IQ 151** (BASIC / Komenium tape formats)
* **SAPI-1** (MIKOS system tape formats)
* **Maťo** (Standard format)
* **ZX81 Fastsaver** (High-speed homebrew tape routine "fastsave" for Sinclair ZX81)

---

## Key Features

* **Advanced Signal Processing**: Emulates hardware edge detection, Biphase/Manchester decoding, and automatic phase polarity detection.
* **Smart Stereo Handling**: Automatically analyzes stereo tracks and isolates the channel with the highest signal quality, avoiding mono-downmix degradation.
* **Filtering & Denoising**: Optional band-pass filtering (300 Hz – 5 kHz) to eliminate mains hum (DC offset) and high-frequency tape hiss.
* **CRC & Integrity Verification**: Validates block headers, data payloads, and identifies non-standard or custom loaders.
* **Multi-Format Export**:
  * **Digital Tape Images**: Platform-native tape files (e.g., `.ptp`).
  * **Clean Audio (`.wav`)**: Mathematically synthesized square-wave audio files ready for playback to real hardware.
  * **Analytical Reports (`.txt`)**: Detailed block structures, timestamps, and CRC status reports compatible with historical archiving databases.
  * **Visual Inspection (`.png`)**: Waveform visualizer showing identified data blocks and timing markers.

---

## Getting Started

### Prerequisites

* Python 3.8 or higher
* Required dependencies:

```bash
pip install numpy scipy matplotlib tqdm
