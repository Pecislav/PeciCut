# PeciCut 🎬✂️

> **Automatický střihač dlouhých záznamů (2–6 hodin) s Facecam AI a detekcí hype reakcí z mikrofonu.**  
> Multiplatformní desktopová aplikace pro macOS i Windows v moderním Twitch/YouTube Creator stylu (oranžovo-černý design) postavená na CustomTkinter, OpenCV YuNet AI a bezztrátovém FFmpeg enginu.

---

## 📋 Klíčové funkce

1. **🤖 Facecam Computer Vision AI (Reakce z webkamery)**:
   - **Analýza výrazu obličeje**: Detekuje otevřená ústa při výkřiku, leknutí či údivu a široký úsměv při záchvatu smíchu.
   - **Kinetický pohyb hlavy a těla**: Měří zrychlení a pohyb (když streamer nadskočí leknutím, hází hlavou či slaví).
   - **Dvoufázová hybridní AI architektura**: Fáze 1 bleskově otestuje zvuk a vytyčí kandidáty, Fáze 2 vzorkuje pouze tyto momenty (cca 5–10 sekund na 4h záznam).
   - Momenty s velkou vizuální reakcí dostávají nejvyšší prioritu, zatímco náhodné herní rány bez reakce streamera jsou odfiltrovány!
2. **Cílová maximální délka sestřihu (YouTube / Shorts optimalizace)**:
   - Možnost zvolit cílovou stopáž: **Bez limitu**, **5 minut**, **10 minut**, **15 minut**, **20 minut** nebo **30 minut**.
   - PeciCut ohodnotí zachycené momenty podle AI skóre a hlasitosti a **vybere nejzábavnější reakce**, které se přesně vejdou do zadaného limitu, a seřadí je zpět do přirozeného toku streamu.
3. **Doporučené hodnoty a nápověda s otazníky (?)**:
   - U každého nastavení je jasně vypsané **doporučení pro začátek** (práh -14 dBFS, kontext 4s/2s, sloučení 2s).
   - Vedle každého parametru je klikací tlačítko **(?)**, které otevře přímo v aplikaci srozumitelné vysvětlení funkce.
4. **Dokonale vycentrovaný PRO CREATOR design**:
   - Vertikálně centrovaný oranžový štítek `PRO CREATOR` sladěný s typografií.
   - Možnost vložit vlastní logo do `assets/logo.png`.
5. **1-Click Automatické stažení FFmpeg**:
   - Pokud FFmpeg chybí, svítí tlačítko `❌ FFmpeg chybí (Klikni pro stažení)`.
   - Jedním kliknutím PeciCut sám stáhne a zprovozní oficiální statické binárky do `bin/` a indikátor se rozsvítí zeleně: `✓ FFmpeg & FFprobe: Připraveno`.
6. **Plynulé ovládání sliderů**:
   - Kolečko myši plynule posouvá celou stránku, slidery se mění výhradně přímým kliknutím a tažením myší do stran.
7. **Podpora multi-track audia z OBS**:
   - Výběr samostatné stopy mikrofonu, analýza probíhá proudově přes paměť (< 50 MB RAM i pro 6h 4K záznamy).
8. **Bleskový export (Single Choice)**:
   - 🎥 **Hotové MP4 video**: Bezztrátový střih přes FFmpeg stream copy (`-c copy` concat demuxer) během 1–2 minut.
   - 📋 **EDL Timeline**: CMX 3600 standard pro DaVinci Resolve a Adobe Premiere Pro.

---

## 🏗️ Struktura projektu

```text
autoclip_highlight_cutter/
├── assets/               # Složka pro logo (logo.png) a ikonu aplikace
├── bin/                  # Lokální složka pro přibalené binárky FFmpeg
├── models/               # AI modely (YuNet ONNX, Haar Cascades pro obličej a smích)
├── facecam_ai.py         # Facecam AI engine (detekce obličeje, úst, smíchu a pohybu)
├── ffmpeg_utils.py       # Detekce a 1-click automatické stažení FFmpeg
├── audio_analyzer.py     # Proudová extrakce audia a záznam peak dBFS
├── edl_generator.py      # CMX 3600 standard EDL generátor s timecode matematikou
├── video_cutter.py       # Slučování segmentů, AI řazení na cílovou délku a concat demuxer
├── main_gui.py           # Hlavní PeciCut CustomTkinter GUI
├── requirements.txt      # Seznam závislostí
└── README.md             # Kompletní dokumentace
```

---

## 🚀 Spuštění aplikace

```bash
cd /Users/matejpesek/.gemini/antigravity/scratch/autoclip_highlight_cutter
python3 -m pip install -r requirements.txt
python3 main_gui.py
```

---

## 📦 Zabalení do samostatné aplikace (.app / .exe)

### macOS (.app bundle)
```bash
pyinstaller --noconfirm --onedir --windowed \
  --name "PeciCut" \
  --add-data "models:models" \
  --add-data "assets:assets" \
  main_gui.py
```

### Windows (.exe soubor)
```bash
pyinstaller --noconfirm --onedir --windowed ^
  --name "PeciCut" ^
  --add-data "models;models" ^
  --add-data "assets;assets" ^
  main_gui.py
```
Výsledný spustitelný program najdete ve složce `dist/PeciCut`.
