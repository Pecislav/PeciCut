# PeciCut 🎬✂️

> **Automatický střihač dlouhých záznamů (2–6 hodin) s detekcí hype reakcí a křiku z mikrofonu.**  
> Multiplatformní aplikace pro macOS i Windows v moderním Twitch/YouTube Creator stylu (oranžovo-černý design) postavená na CustomTkinter a bezztrátovém FFmpeg enginu.

---

## 📋 Klíčové funkce

1. **Cílová maximální délka sestřihu (YouTube / Shorts optimalizace)**:
   - Možnost zvolit cílovou stopáž: **Bez limitu**, **5 minut**, **10 minut**, **15 minut**, **20 minut** nebo **30 minut**.
   - PeciCut ohodnotí zachycené momenty podle intenzity (hlasitosti v dBFS) a **vybere nejhlasitější a nejzábavnější reakce**, které se přesně vejdou do zadaného limitu, a seřadí je zpět do přirozeného toku streamu.
2. **Doporučené hodnoty a nápověda s otazníky (?)**:
   - U každého nastavení je jasně vypsané **doporučení pro začátek** (práh -14 dBFS, kontext 4s/2s, sloučení 2s).
   - Vedle každého parametru je klikací tlačítko **(?)**, které otevře srozumitelné vysvětlení, jak daná funkce funguje.
3. **Dokonale vycentrovaný PRO CREATOR design**:
   - Vertikálně centrovaný oranžový štítek `PRO CREATOR` sladěný s typografií.
   - Možnost vložit vlastní logo do `assets/logo.png`.
4. **1-Click Automatické stažení FFmpeg**:
   - Pokud FFmpeg chybí, svítí tlačítko `❌ FFmpeg chybí (Klikni pro stažení)`.
   - Jedním kliknutím PeciCut sám stáhne a zprovozní oficiální statické binárky do `bin/` a indikátor se rozsvítí zeleně: `✓ FFmpeg & FFprobe: Připraveno`.
5. **Plynulé ovládání sliderů**:
   - Kolečko myši plynule posouvá celou stránku, slidery se mění výhradně přímým kliknutím a tažením myší do stran.
6. **Podpora multi-track audia z OBS**:
   - Výběr samostatné stopy mikrofonu, analýza probíhá proudově přes paměť (< 50 MB RAM i pro 6h 4K záznamy).
7. **Bleskový export (Single Choice)**:
   - 🎥 **Hotové MP4 video**: Bezztrátový střih přes FFmpeg stream copy (`-c copy` concat demuxer) během 1–2 minut.
   - 📋 **EDL Timeline**: CMX 3600 standard pro DaVinci Resolve a Adobe Premiere Pro.

---

## 🏗️ Struktura projektu

```text
autoclip_highlight_cutter/
├── assets/               # Složka pro logo (logo.png) a ikonu aplikace
├── bin/                  # Lokální složka pro přibalené binárky FFmpeg
├── ffmpeg_utils.py       # Detekce a 1-click automatické stažení FFmpeg
├── audio_analyzer.py     # Proudová extrakce audia a záznam peak dBFS
├── edl_generator.py      # CMX 3600 standard EDL generátor s timecode matematikou
├── video_cutter.py       # Slučování segmentů, omezení na cílovou délku a concat demuxer
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
