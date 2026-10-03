<div align="center">

# Pecislav Studio 🎬
### *The Ultimate Desktop Creator Suite with SnapCut AI*

[![Version](https://img.shields.io/badge/Version-1.0.0--beta-FF6D00?style=for-the-badge&logo=rocket)](https://github.com/Pecislav/PecislavStudio)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS-22C55E?style=for-the-badge&logo=windows)](https://github.com/Pecislav/PecislavStudio)
[![Design](https://img.shields.io/badge/Design-Logi%20Options%2B%20Style-FF6D00?style=for-the-badge)](https://github.com/Pecislav/PecislavStudio)
[![Typography](https://img.shields.io/badge/Typography-Poppins-0284C7?style=for-the-badge)](https://fonts.google.com/specimen/Poppins)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)

<p align="center">
  <b>Comprehensive All-in-One ecosystem engineered for streamers, YouTubers, and content creators.</b><br>
  Automated highlight cutting for long Twitch and YouTube recordings (2–6 hours), hybrid Facecam AI reaction detection, and lightning-fast lossless FFmpeg stream-copy export without quality loss.
</p>

---

</div>

## 🧭 About Pecislav Studio

**Pecislav Studio** is a modern desktop suite built from the ground up to solve the most tedious task in content creation: turning multi-hour raw VODs into concise, high-energy videos.

Featuring a sleek visual design inspired by **Logi Options+**, refined **Google Fonts Poppins** typography, floating rounded cards, and the signature `#FF6D00` warm accent, Pecislav Studio replaces dozens of fragile one-off command-line scripts with a cohesive, professional workstation that looks stunning in both **Dark** and **Light** modes.

---

## 🧩 Key Features & Modules

### 🎬 1. SnapCut — Highlight Cutter & Reaction Engine
- **🤖 Facecam Computer Vision AI**: Real-time neural face analysis powered by OpenCV YuNet ONNX. Detects open mouth moments (screams, gasps, awe), broad smiles, laughter fits, and kinetic head/body movement.
- **⚡ Two-Phase Hybrid Analysis Pipeline**:
  - *Phase 1*: Lightning-fast streaming audio waveform analysis of the creator's microphone track (flags candidate excitement spikes in seconds with minimal RAM footprint).
  - *Phase 2*: Visual AI scans candidate timestamps to verify genuine creator face reactions—filtering out deceptive in-game explosions or gunshots.
- **⏱️ Target Duration Limiter**: Cap your final highlight video to **5, 10, 15, 20, 30 minutes** or **Unlimited**. SnapCut automatically ranks all captured moments by hype intensity and selects the best reactions that fit within your target duration.
- **✂️ Interactive Segment Review Editor**: Visually review, scrub, trim, toggle, or full-screen preview every captured clip before finalizing the export.
- **🎞️ Lossless FFmpeg Stream Copy**: Exports via FFmpeg concat demuxer (`-c copy`) without re-encoding—a 4-hour stream is sliced and stitched in **1 to 2 minutes** with 100% original visual and audio quality preserved.
- **📋 CMX 3600 EDL Export**: Instant timeline export compatible with DaVinci Resolve and Adobe Premiere Pro for seamless multi-track finishing and music mastering.

---

### ⚙️ 2. Studio Settings & System Diagnostics
- **🎨 Theme Customization**: Native support for Dark, Light, and System themes with live preview and tuned contrast ratios.
- **🌐 Multilingual Interface**: Full bilingual support in English and Czech.
- **💾 Persistent Settings**: All threshold parameters, sliders, preferred export paths, and module configs persist automatically in `%APPDATA%/PecislavStudio/config.json`.
- **⬇️ 1-Click Component Installer**: Automated in-app download and setup of FFmpeg, FFprobe, and Facecam AI ONNX models with real-time percentage indicators (`XX %`) and byte counters.
- **🧹 Cache Manager**: Safely reclaim disk space by purging temporary audio renders with a single click.
- **🚀 Integrated Update Checker**: Direct release verification from GitHub with automatic notifications.

---

## 🛠️ System Requirements & Quick Start

### Requirements:
- **Windows 10 / 11** or **macOS** (Apple Silicon & Intel)
- **Python 3.10** or higher
- **FFmpeg** (installed automatically via the Settings tab if missing)

### Running from source:
```bash
# 1. Clone repository
git clone https://github.com/Pecislav/PecislavStudio.git
cd PecislavStudio

# 2. Install dependencies
python -m pip install -r requirements.txt

# 3. Launch Pecislav Studio
python main_gui.py
```

---

## 📦 Building Standalone Executable (.exe / .app)

You can build a standalone binary distribution package without external Python dependencies:

### Windows (.exe):
Run the automated build script:
```cmd
build_exe.bat
```
Or run PyInstaller directly:
```cmd
py -m PyInstaller --noconfirm PecislavStudio.spec
```
The compiled executable will be placed in `dist/Pecislav Studio/`.

---

## 👤 Author

Created by **Pecislav** for creators worldwide.
- GitHub: [@Pecislav](https://github.com/Pecislav)
- Project: **Pecislav Studio (Pro Creator Edition)**
