"""
segment_editor.py - Optimalizovaný editor nalezených momentů (Pecislav Studio).

Architektura pro maximální výkon na notebooku:
- SEZNAM: Tkinter Canvas s textem (ne CTk widgety na každý řádek).
  Canvas.coords/itemconfig jsou ~100× rychlejší než CTk Frame.configure().
  Scrollování je okamžité - jen posun yview.
- PŘEHRÁVAČ: konverze PIL->PhotoImage proběhne v background threadu.
  Main thread dostane hotový PhotoImage objekt a jen zavolá itemconfig() -> nulová práce.
- Žádné pack_forget/pack při scrollu, žádné CTkFrame.configure na každý řádek.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional, Set, Tuple

import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
from ffmpeg_utils import find_binary, get_base_dir


# ---------------------------------------------------------------------------
# Barvy (hex stringy, ne tuple - rychlejší pro Canvas)
# ---------------------------------------------------------------------------
_MODE = ctk.get_appearance_mode()  # "Dark" nebo "Light"

def _c(light: str, dark: str) -> str:
    return dark if ctk.get_appearance_mode() == "Dark" else light

BG_WIN       = _c("#F8F9FA", "#14151B")
BG_CARD      = _c("#FFFFFF", "#181A22")
BG_ROW       = _c("#F3F4F6", "#1E2028")
BG_ROW_SEL   = _c("#FFF7ED", "#231B15")
BD_ROW       = _c("#E5E7EB", "#2B2E3B")
BD_ROW_SEL   = _c("#EA580C", "#FF6B00")
ORANGE       = "#FF6B00"
ORANGE_HV    = "#E05D00"
TXT_MAIN     = _c("#111827", "#F9FAFB")
TXT_MUTED    = _c("#6B7280", "#9CA3AF")
TXT_BODY     = _c("#4B5563", "#9CA3AF")
TXT_ORANGE   = _c("#EA580C", "#FF8533")
BADGE_AI_BG  = _c("#FEF3C7", "#2D2411")
BADGE_AI_FG  = _c("#D97706", "#FBBF24")
BG_PLAYER    = "#0B0C10"

# CTkFrame-kompatibilní tuple barvy pro widgety mimo Canvas
BG_CARD_T    = ("#FFFFFF", "#181A22")
BG_INNER_T   = ("#F3F4F6", "#1E2028")
BD_CARD_T    = ("#E5E7EB", "#2B2E3B")
BD_ACT_T     = ("#EA580C", "#FF6B00")
TXT_TITLE_T  = ("#111827", "#F9FAFB")
TXT_BODY_T   = ("#4B5563", "#9CA3AF")
TXT_MUTED_T  = ("#6B7280", "#6B7280")
OBG_T        = ("#FFF7ED", "#26170E")
BADGE_BG_T   = ("#FEF3C7", "#2D2411")
BADGE_FG_T   = ("#D97706", "#FBBF24")

# ---------------------------------------------------------------------------
# Video přehrávač - rozlišení
# ---------------------------------------------------------------------------
PREV_W = 448
PREV_H = 252
PLAY_FPS = 18          # Snímky za sekundu (notebook-friendly)
DISP_MS  = 50          # Display timer interval (~20 Hz) - volný pro UI

# ---------------------------------------------------------------------------
# Canvas seznam - geometrie jednoho řádku
# ---------------------------------------------------------------------------
ROW_H     = 44          # výška jednoho řádku v px
ROW_PAD_X = 10
ROW_PAD_Y = 3


# ---------------------------------------------------------------------------
# Pomocné funkce
# ---------------------------------------------------------------------------

def format_moments_count(count: int, lang: str = "cs") -> str:
    if lang == "en":
        return f"{count} clip" if count == 1 else f"{count} clips"
    n = abs(count)
    if n % 100 in (11, 12, 13, 14):
        return f"{count} momentů"
    r = n % 10
    if r == 1:
        return f"{count} moment"
    if r in (2, 3, 4):
        return f"{count} momenty"
    return f"{count} momentů"


def fmt_t(sec: float) -> str:
    sec = max(0.0, sec)
    s = int(round(sec))
    h, rem = divmod(s, 3600)
    m, s2 = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s2:02d}" if h else f"{m:02d}:{s2:02d}"


def _grab_frame(video_path: Path, ts: float, w: int = PREV_W, h: int = PREV_H) -> Optional[Image.Image]:
    """Extrahuje jeden snímek jako čistý PIL Image (bezpečné volat z background threadu)."""
    ffmpeg = find_binary("ffmpeg")
    if not ffmpeg or not video_path.is_file():
        return None
    cmd = [
        str(ffmpeg), "-ss", f"{ts:.2f}", "-i", str(video_path),
        "-vframes", "1", "-vf", f"scale={w}:{h}",
        "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
    ]
    try:
        cflags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
        sinfo = None
        if sys.platform.startswith("win"):
            sinfo = subprocess.STARTUPINFO()
            sinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            sinfo.wShowWindow = 0
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            startupinfo=sinfo,
            creationflags=cflags,
        )
        data, _ = p.communicate(timeout=4.0)
        if data:
            return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        pass
    return None


def _load_ctk_icon(name: str, size: Tuple[int, int] = (16, 16)) -> Optional[ctk.CTkImage]:
    """Loads a PNG icon from assets/icons/ as CTkImage."""
    icon_path = Path(__file__).parent / "assets" / "icons" / f"{name}.png"
    if icon_path.is_file():
        try:
            im = Image.open(icon_path)
            return ctk.CTkImage(light_image=im, dark_image=im, size=size)
        except Exception:
            pass
    return None


# ===========================================================================
# Dialog
# ===========================================================================

class SegmentReviewDialog(ctk.CTkToplevel):

    def __init__(
        self,
        parent: ctk.CTk,
        video_path: Path,
        all_segments: List[Tuple],
        recommended_segments: List[Tuple],
        target_duration_sec: Optional[float] = None,
        current_lang: str = "cs",
        on_confirm: Optional[Callable[[List[Tuple]], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)

        self._parent = parent
        self.video_path = video_path
        self.segs = list(all_segments)
        self._rec_set: Set[Tuple[float, float]] = {
            (round(s[0], 2), round(s[1], 2)) for s in recommended_segments
        }
        self.target_dur = target_duration_sec
        self.lang = current_lang if current_lang in ("cs", "en") else "cs"
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel

        # Stav zahrnutí: prostý bool list (bez BooleanVar - rychlejší)
        self._inc: List[bool] = [
            (round(s[0], 2), round(s[1], 2)) in self._rec_set for s in self.segs
        ]

        # UI stav
        self._sel: int = 0           # aktuálně vybraný index
        self._closing = False

        # Přehrávač
        self._playing = False
        self._stop_ev = threading.Event()
        self._ended_ev = threading.Event()
        self._aud_proc: Optional[subprocess.Popen] = None
        self._frame_lock = threading.Lock()
        self._next_frame: Optional[Tuple[Image.Image, float]] = None  # (PIL Image, ft) předávané z bg threadu
        self._cur_photo: Optional[ImageTk.PhotoImage] = None          # reference bránící GC (VÝHRADNĚ na main threadu)
        self._play_session_id: int = 0                                # ochrana proti překrývání přehrávacích vláken
        self._still_req_id: int = 0                                   # ochrana proti zastaralým požadavkům na statický náhled
        self._pending_play_id: Optional[str] = None
        self._play_dur: float = 0.0
        self._cur_play_offset: float = 0.0                             # aktuální pozice pro pauzu / pokračování
        self._canvas_img: Optional[int] = None
        self._disp_id: Optional[str] = None

        # Canvas seznam - stav scrollu
        self._list_canvas: Optional[tk.Canvas] = None
        self._row_items: List[dict] = []  # canvas item IDs pro každý řádek
        self._chk_vars: List[tk.BooleanVar] = []
        self._chk_widgets: List[tk.Checkbutton] = []
        self._chk_windows: List[int] = []  # canvas window IDs pro checkboxy

        # Ikony pro ovládací prvky přehrávače
        self._icon_play = _load_ctk_icon("play", (14, 14))
        self._icon_pause = _load_ctk_icon("pause", (14, 14))
        self._icon_stop = _load_ctk_icon("stop", (14, 14))
        self._icon_expand = _load_ctk_icon("expand", (14, 14))
        self._icon_check = _load_ctk_icon("check", (15, 15))
        self._icon_plus = _load_ctk_icon("plus", (15, 15))

        # Okno
        title = ("Pecislav Studio • Editor"
                 if self.lang == "cs" else "Pecislav Studio • Editor")
        self.title(title)
        self.geometry("1120x750")
        self.minsize(900, 560)
        self.configure(fg_color=BG_CARD_T)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._center()
        self._set_app_icon()
        self.after(50, self._apply_windows_titlebar_theme)
        self._build()
        self._update_summary()

        if self.segs:
            self.after(80, lambda: self._select(0))

    # ------------------------------------------------------------------
    def _set_app_icon(self):
        """Loads and sets the window icon."""
        try:
            assets_dir = get_base_dir() / "assets"
            ico_file = assets_dir / "app_icon.ico"
            png_file = assets_dir / "app_icon.png"
            logo_file = assets_dir / "logo.png"

            if sys.platform.startswith("win") and ico_file.is_file():
                try:
                    self.iconbitmap(str(ico_file))
                    return
                except Exception:
                    pass

            target_png = png_file if png_file.is_file() else (logo_file if logo_file.is_file() else None)
            if target_png:
                try:
                    pil_icon = Image.open(target_png)
                    self._app_window_icon = ImageTk.PhotoImage(pil_icon)
                    self.wm_iconphoto(True, self._app_window_icon)  # type: ignore
                except Exception:
                    pass
        except Exception:
            pass

    def _apply_windows_titlebar_theme(self):
        """Sets immersive dark mode or light mode for the Windows title bar via DwmSetWindowAttribute."""
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes
            from ctypes import c_int, byref, sizeof
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd:
                hwnd = self.winfo_id()
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            mode = ctk.get_appearance_mode().lower()
            dark_flag = c_int(1 if mode == "dark" else 0)
            res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, byref(dark_flag), sizeof(dark_flag)
            )
            if res != 0:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 19, byref(dark_flag), sizeof(dark_flag)
                )
            if mode == "dark":
                caption_color = c_int(0x00181211)  # #111218
                text_color = c_int(0x00FFFFFF)
            else:
                caption_color = c_int(0x00FAFAF8)
                text_color = c_int(0x0010181A)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 35, byref(caption_color), sizeof(caption_color)
            )
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 36, byref(text_color), sizeof(text_color)
            )
        except Exception:
            pass

    def _center(self):
        self.update_idletasks()
        try:
            w, h = 1120, 750
            px, py = self._parent.winfo_x(), self._parent.winfo_y()
            pw, ph = self._parent.winfo_width(), self._parent.winfo_height()
            self.geometry(f"{w}x{h}+{px + (pw-w)//2}+{py + (ph-h)//2}")
        except Exception:
            pass

    # ==================================================================
    # Stavba UI
    # ==================================================================

    def _build(self):
        self._build_header()
        split = ctk.CTkFrame(self, fg_color="transparent")
        split.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self._build_player(split)
        self._build_list(split)
        self._build_footer()

    # --- Hlavička ---

    def _build_header(self):
        hdr = ctk.CTkFrame(self, corner_radius=10, fg_color=BG_CARD_T,
                           border_width=1, border_color=BD_CARD_T)
        hdr.pack(fill="x", padx=16, pady=(12, 8))

        row = ctk.CTkFrame(hdr, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=8)

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)

        t = "Editor"
        ctk.CTkLabel(left, text=t, font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=TXT_TITLE_T).pack(anchor="w")

        s = ("Kontrola a výběr nejlepších momentů pro finální sestřih videa"
             if self.lang == "cs"
             else "Review and select the best moments for the final video cut")
        ctk.CTkLabel(left, text=s, font=ctk.CTkFont(size=11), text_color=TXT_BODY_T).pack(anchor="w")

        pill = ctk.CTkFrame(row, fg_color=BG_INNER_T, corner_radius=8,
                            border_width=1, border_color=BD_CARD_T)
        pill.pack(side="right")

        pi = ctk.CTkFrame(pill, fg_color="transparent")
        pi.pack(padx=12, pady=6)

        self._lbl_count = ctk.CTkLabel(pi, text="", font=ctk.CTkFont(size=12, weight="bold"),
                                        text_color=("EA580C", "#FF8533"))
        self._lbl_count.pack(anchor="e")
        self._lbl_dur = ctk.CTkLabel(pi, text="", font=ctk.CTkFont(size=11), text_color=TXT_BODY_T)
        self._lbl_dur.pack(anchor="e")

    # --- Levý panel: Přehrávač ---

    def _build_player(self, parent):
        box = ctk.CTkFrame(parent, width=488, corner_radius=10, fg_color=BG_CARD_T,
                           border_width=1, border_color=BD_CARD_T)
        box.pack(side="left", fill="y", padx=(0, 8))
        box.pack_propagate(False)

        p = ctk.CTkFrame(box, fg_color="transparent")
        p.pack(fill="both", expand=True, padx=10, pady=10)

        # Titulek
        th = ctk.CTkFrame(p, fg_color="transparent")
        th.pack(fill="x", pady=(0, 6))

        self._lbl_ptitle = ctk.CTkLabel(th, text="Moment #01",
                                         font=ctk.CTkFont(size=14, weight="bold"),
                                         text_color=TXT_TITLE_T)
        self._lbl_ptitle.pack(side="left")

        self._lbl_ptc = ctk.CTkLabel(th, text="00:00 -> 00:00",
                                      font=ctk.CTkFont(size=11, weight="bold"),
                                      text_color=("EA580C", "#FF8533"))
        self._lbl_ptc.pack(side="right")

        # Video canvas
        sc = ctk.CTkFrame(p, fg_color=BG_PLAYER, corner_radius=6,
                          border_width=1, border_color=BD_CARD_T)
        sc.pack(fill="x", pady=(0, 6))

        self._vcanvas = ctk.CTkCanvas(sc, width=PREV_W, height=PREV_H,
                                       bg="#000000", highlightthickness=0, cursor="hand2")
        self._vcanvas.pack(padx=2, pady=2)
        self._vcanvas.bind("<Button-1>", lambda _: self._toggle_play())

        # Scrubber
        sb = ctk.CTkFrame(p, fg_color="transparent")
        sb.pack(fill="x", pady=(0, 6))

        self._lbl_ct = ctk.CTkLabel(sb, text="00:00", font=ctk.CTkFont(size=10, weight="bold"),
                                     text_color=TXT_TITLE_T, width=42)
        self._lbl_ct.pack(side="left")

        self._pbar = ctk.CTkProgressBar(sb, height=6, progress_color=ORANGE,
                                         fg_color=BG_INNER_T)
        self._pbar.pack(side="left", fill="x", expand=True, padx=6)
        self._pbar.set(0.0)

        self._lbl_tt = ctk.CTkLabel(sb, text="00:00", font=ctk.CTkFont(size=10),
                                     text_color=TXT_MUTED_T, width=42)
        self._lbl_tt.pack(side="right")

        # Tlačítka přehrávače: velké Play/Pause vlevo + zvětšit vpravo
        cb = ctk.CTkFrame(p, fg_color="transparent")
        cb.pack(fill="x", pady=(0, 8))

        self._btn_pp = ctk.CTkButton(
            cb, text="Přehrát náhled" if self.lang == "cs" else "Play Preview",
            image=self._icon_play, compound="left",
            command=self._toggle_play, height=36, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ORANGE, hover_color=ORANGE_HV, text_color="#FFF", corner_radius=6)
        self._btn_pp.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._btn_ext = ctk.CTkButton(
            cb, text="", image=self._icon_expand, command=self._ext_player, height=36, width=42,
            fg_color=BG_INNER_T, hover_color=("#E5E7EB", "#252834"),
            border_width=1, border_color=BD_CARD_T, corner_radius=6)
        self._btn_ext.pack(side="right")

        # Velké tlačítko zahrnutí/vynechání
        self._btn_inc = ctk.CTkButton(
            p, text="Zahrnuto do výsledného videa" if self.lang == "cs" else "Included in Cut",
            image=self._icon_check, compound="left",
            command=self._toggle_inc,
            height=36, font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#E8F5E9", "#1B3320"), hover_color=("#C8E6C9", "#23472B"),
            text_color=("#2E7D32", "#4ADE80"), border_width=1,
            border_color=("#A5D6A7", "#2D5A37"), corner_radius=6)
        self._btn_inc.pack(fill="x", pady=(0, 8))

        # Info box
        ib = ctk.CTkFrame(p, fg_color=BG_INNER_T, corner_radius=6,
                          border_width=1, border_color=BD_CARD_T)
        ib.pack(fill="both", expand=True)

        ibi = ctk.CTkFrame(ib, fg_color="transparent")
        ibi.pack(fill="both", padx=10, pady=8)

        self._lbl_loud = ctk.CTkLabel(ibi, text="Hlasitost: -",
                                       font=ctk.CTkFont(size=12), text_color=TXT_TITLE_T)
        self._lbl_loud.pack(anchor="w", pady=(0, 3))

        self._lbl_face = ctk.CTkLabel(ibi, text="Facecam: N/A",
                                       font=ctk.CTkFont(size=12), text_color=TXT_BODY_T)
        self._lbl_face.pack(anchor="w", pady=(0, 3))

        self._lbl_ai = ctk.CTkLabel(ibi, text="",
                                     font=ctk.CTkFont(size=12, weight="bold"),
                                     text_color=BADGE_FG_T)
        self._lbl_ai.pack(anchor="w")

    # --- Pravý panel: Canvas seznam ---

    def _build_list(self, parent):
        box = ctk.CTkFrame(parent, corner_radius=10, fg_color=BG_CARD_T,
                           border_width=1, border_color=BD_CARD_T)
        box.pack(side="right", fill="both", expand=True)

        # Toolbar
        self._build_toolbar(box)

        # Rámeček pro Canvas + scrollbar
        lf = ctk.CTkFrame(box, fg_color="transparent")
        lf.pack(fill="both", expand=True, padx=6, pady=(0, 4))

        self._list_canvas = tk.Canvas(
            lf,
            bg=BG_CARD,
            highlightthickness=0,
        )
        self._list_canvas.pack(side="left", fill="both", expand=True)

        sb_v = ctk.CTkScrollbar(
            lf,
            orientation="vertical",
            command=self._list_canvas.yview,
            fg_color=BG_INNER_T,
            button_color=("#9CA3AF", "#3A3D4D"),
            button_hover_color=("#6B7280", "#FF6B00"),
        )
        sb_v.pack(side="right", fill="y")
        self._list_canvas.configure(yscrollcommand=sb_v.set)

        # Vnější frame uvnitř canvasu (pro embed checkboxů)
        self._inner_frame = tk.Frame(self._list_canvas, bg=BG_CARD)
        self._inner_frame_id = self._list_canvas.create_window(
            0, 0, window=self._inner_frame, anchor="nw")

        # Naplnění řádky
        self._build_canvas_rows()

        # Aktualizace scroll region po vykreslení
        if self._list_canvas is not None and self._inner_frame is not None:
            canvas = self._list_canvas
            inner = self._inner_frame
            inner_id = self._inner_frame_id
            inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>", lambda e: canvas.itemconfig(inner_id, width=e.width))

            # Mousewheel - nad listcanvas i celým dialogem
            canvas.bind("<MouseWheel>", self._on_wheel)
            inner.bind("<MouseWheel>", self._on_wheel)

        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", self._on_wheel)
        self.bind("<Button-5>", self._on_wheel)

        # Klávesové šipky
        self.bind("<Up>", lambda _: self._kb_nav(-1))
        self.bind("<Down>", lambda _: self._kb_nav(1))

    def _build_canvas_rows(self):
        """Vytvoří Tk widgety pro každý řádek (ne CTk - je to rychlejší)."""
        for i, seg in enumerate(self.segs):
            start, end = seg[0], seg[1]
            dur = max(0.1, end - start)
            peak = seg[2] if len(seg) >= 3 else -14.0
            is_rec = (round(start, 2), round(end, 2)) in self._rec_set

            # Řádkový frame (tk.Frame = nativní, bez CTk overhead)
            row_f = tk.Frame(self._inner_frame, bg=BG_ROW, bd=1, relief="flat",
                             highlightbackground=BD_ROW, highlightthickness=1, height=ROW_H)
            row_f.pack(fill="x", padx=4, pady=2)
            row_f.pack_propagate(False)

            inner = tk.Frame(row_f, bg=BG_ROW)
            inner.pack(fill="both", expand=True, padx=6, pady=4)

            # Checkbox
            var = tk.BooleanVar(value=self._inc[i])
            self._chk_vars.append(var)

            chk = tk.Checkbutton(
                inner, variable=var, bg=BG_ROW, activebackground=BG_ROW,
                selectcolor=BG_ROW,
                fg=ORANGE, activeforeground=ORANGE,
                command=lambda idx=i: self._on_chk(idx),
                relief="flat", bd=0, highlightthickness=0, cursor="hand2")
            chk.pack(side="left", padx=(0, 4))
            self._chk_widgets.append(chk)

            # Text label
            ai_tag = "  AI" if is_rec else ""
            txt = (f"#{i+1:02d}  {fmt_t(start)} -> {fmt_t(end)}  "
                   f"({dur:.1f}s)  {peak:.1f}dB{ai_tag}")
            lbl = tk.Label(inner, text=txt, bg=BG_ROW, fg=TXT_MAIN,
                           font=("Helvetica", 11), anchor="w", cursor="hand2")
            lbl.pack(side="left", fill="x", expand=True)

            # Play tlačítko – tk.Label místo tk.Button, aby na macOS/Windows nebyla bílá systémová kapsle
            pbtn = tk.Label(
                inner, text=" ▶ ", bg="#242632", fg=ORANGE,
                font=("Helvetica", 10, "bold"), relief="flat", bd=0,
                cursor="hand2", padx=6, pady=2
            )
            pbtn.pack(side="right", padx=(4, 0))
            pbtn.bind("<Button-1>", lambda _, idx=i: self._sel_and_play(idx))
            pbtn.bind("<Enter>", lambda _, b=pbtn: b.configure(bg=ORANGE, fg="#FFFFFF"))
            pbtn.bind("<Leave>", lambda _, b=pbtn, idx=i: b.configure(
                bg="#302620" if idx == self._sel else "#242632",
                fg=ORANGE
            ))

            # Kliknutí na řádek -> výběr a plynulý scroll
            for w in (row_f, inner, lbl):
                w.bind("<Button-1>", lambda _, idx=i: self._select(idx))
            for w in (row_f, inner, lbl, chk, pbtn):
                w.bind("<MouseWheel>", self._on_wheel)

            self._row_items.append({
                "frame": row_f, "inner": inner, "lbl": lbl, "chk": chk,
                "var": var, "pbtn": pbtn
            })

    def _highlight_row(self, idx: int, selected: bool):
        row = self._row_items[idx]
        bg = BG_ROW_SEL if selected else BG_ROW
        bd = BD_ROW_SEL if selected else BD_ROW
        row["frame"].configure(bg=bg, highlightbackground=bd)
        row["inner"].configure(bg=bg)
        row["lbl"].configure(bg=bg)
        row["chk"].configure(bg=bg, activebackground=bg, selectcolor=bg)
        btn_bg = "#302620" if selected else "#242632"
        row["pbtn"].configure(bg=btn_bg, fg=ORANGE)

    def _build_toolbar(self, parent):
        tb = ctk.CTkFrame(parent, fg_color="transparent")
        tb.pack(fill="x", padx=12, pady=(10, 4))

        def _b(txt, cmd, **kw):
            return ctk.CTkButton(tb, text=txt, command=cmd, height=26,
                                 font=ctk.CTkFont(size=11),
                                 border_width=1, corner_radius=5, **kw)

        t_ai = "AI výběr" if self.lang == "cs" else "AI Picks"
        _b(t_ai, self._reset_ai,
           fg_color=BADGE_BG_T, hover_color=("#FDE68A", "#3D3016"),
           text_color=BADGE_FG_T, border_color=("#F59E0B", "#B45309")
           ).pack(side="left", padx=(0, 4))

        _b("Vše" if self.lang == "cs" else "All", self._sel_all,
           fg_color=BG_INNER_T, hover_color=("#E5E7EB", "#252834"),
           text_color=TXT_TITLE_T, border_color=BD_CARD_T
           ).pack(side="left", padx=(0, 4))

        _b("Nic" if self.lang == "cs" else "None", self._desel_all,
           fg_color=BG_INNER_T, hover_color=("#E5E7EB", "#252834"),
           text_color=TXT_TITLE_T, border_color=BD_CARD_T
           ).pack(side="left")

        if self.target_dur and self.target_dur > 0:
            tp = ctk.CTkFrame(tb, fg_color="transparent")
            tp.pack(side="right")
            self._tpbar = ctk.CTkProgressBar(tp, width=110, height=6,
                                              progress_color=ORANGE, fg_color=BG_INNER_T)
            self._tpbar.pack(side="right", padx=(4, 0))
            self._lbl_tpct = ctk.CTkLabel(tp, text="0%",
                                           font=ctk.CTkFont(size=11, weight="bold"),
                                           text_color=TXT_TITLE_T)
            self._lbl_tpct.pack(side="right")
        else:
            self._tpbar = None
            self._lbl_tpct = None

    # --- Patička ---

    def _build_footer(self):
        f = ctk.CTkFrame(self, corner_radius=10, fg_color=BG_CARD_T,
                         border_width=1, border_color=BD_CARD_T)
        f.pack(fill="x", side="bottom", padx=16, pady=(0, 12))

        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=8)

        self._lbl_foot = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=12, weight="bold"),
                                       text_color=TXT_TITLE_T)
        self._lbl_foot.pack(side="left")

        self._btn_conf = ctk.CTkButton(
            row, text="", command=self._on_confirm,
            height=36, width=210, font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=ORANGE, hover_color=ORANGE_HV, text_color="#FFF", corner_radius=6)
        self._btn_conf.pack(side="right", padx=(8, 0))

        t_c = "Zrušit" if self.lang == "cs" else "Cancel"
        ctk.CTkButton(row, text=t_c, command=self._on_cancel,
                      height=36, width=90, font=ctk.CTkFont(size=11),
                      fg_color=BG_INNER_T, hover_color=("#E5E7EB", "#2B2E3B"),
                      text_color=TXT_TITLE_T, border_width=1, border_color=BD_CARD_T,
                      corner_radius=6).pack(side="right")

    # ==================================================================
    # Výběr segmentu
    # ==================================================================

    def _select(self, idx: int):
        if not (0 <= idx < len(self.segs)):
            return

        self._stop_play()
        self._cur_play_offset = 0.0

        old = self._sel
        self._sel = idx

        # Zvýraznění řádků (pouze aktualizujeme starý a nový)
        if 0 <= old < len(self._row_items):
            self._highlight_row(old, False)
        self._highlight_row(idx, True)

        # Scroll řádku do pohledu
        self._scroll_into_view(idx)

        seg = self.segs[idx]
        start, end = seg[0], seg[1]
        dur = max(0.1, end - start)
        peak = seg[2] if len(seg) >= 3 else -14.0
        face = seg[3] if len(seg) >= 4 else 0.0
        is_rec = (round(start, 2), round(end, 2)) in self._rec_set

        self._lbl_ptitle.configure(text=f"Moment #{idx+1:02d}")
        self._lbl_ptc.configure(text=f"{fmt_t(start)} -> {fmt_t(end)} ({dur:.1f}s)")
        self._lbl_ct.configure(text="00:00")
        self._lbl_tt.configure(text=fmt_t(dur))
        self._pbar.set(0.0)

        t = "Přehrát náhled" if self.lang == "cs" else "Play Preview"
        self._btn_pp.configure(text=t, image=self._icon_play, fg_color=ORANGE)

        self._update_inc_btn(self._inc[idx])

        self._lbl_loud.configure(text=f"Hlasitost spicky: {peak:.1f} dBFS")
        fc = (f"Facecam reakce: {int(face*100)}%" if face > 0.05
              else ("Facecam: Bez reakce" if self.lang == "cs"
                    else "Facecam: No reaction"))
        self._lbl_face.configure(text=fc)

        if is_rec:
            ai = "AI doporuceni pro cilovou delku" if self.lang == "cs" else "AI Pick"
            self._lbl_ai.configure(text=ai, text_color=BADGE_FG_T)
        else:
            ai = "Doplnkovy moment (muzete zahrnout)" if self.lang == "cs" else "Optional moment"
            self._lbl_ai.configure(text=ai, text_color=TXT_MUTED_T)

        # Načti náhledový snímek v bg threadu (s unikátním ID požadavku)
        self._still_req_id += 1
        req_id = self._still_req_id
        threading.Thread(target=self._load_still, args=(req_id, start), daemon=True).start()

    def _sel_and_play(self, idx: int):
        self._select(idx)
        if self._pending_play_id:
            try:
                self.after_cancel(self._pending_play_id)
            except Exception:
                pass
        self._pending_play_id = self.after(80, self._start_play)

    def _scroll_into_view(self, idx: int):
        """Scrolluje canvas seznam tak, aby byl řádek idx viditelný."""
        if not self._row_items or idx >= len(self._row_items):
            return
        try:
            if self._list_canvas is None or self._inner_frame is None:
                return
            canvas = self._list_canvas
            inner = self._inner_frame
            row_f = self._row_items[idx]["frame"]
            row_f.update_idletasks()
            y = row_f.winfo_y()
            vh = canvas.winfo_height()
            total_h = inner.winfo_height()
            if total_h <= vh:
                return
            # Scroll tak, aby byl řádek uprostřed
            center = y + ROW_H // 2
            new_top = max(0, center - vh // 2)
            frac = new_top / total_h
            canvas.yview_moveto(frac)
        except Exception:
            pass

    def _on_wheel(self, event):
        """Scrolluje Canvas seznam pomocí kolečka myši."""
        try:
            if self._list_canvas is None:
                return
            canvas = self._list_canvas
            if sys.platform.startswith("win"):
                units = -int(event.delta / 40)
            elif sys.platform == "darwin":
                units = -int(event.delta)
            else:
                units = -1 if event.delta > 0 else 1
            canvas.yview_scroll(units, "units")
            return "break"
        except Exception:
            pass

    def _kb_nav(self, delta: int):
        new = max(0, min(self._sel + delta, len(self.segs) - 1))
        self._select(new)

    # ==================================================================
    # Přehrávač
    # ==================================================================

    def _load_still(self, req_id: int, ts: float):
        """Volat z bg threadu: načte snímek jako PIL Image bez volání Tcl/Tk."""
        img = _grab_frame(self.video_path, ts)
        if img and not self._closing:
            # Bezpečně předat čistý PIL Image do main threadu
            self.after(0, lambda im=img, rid=req_id: self._show_still(im, rid))

    def _show_still(self, img: Image.Image, req_id: int):
        if self._closing or not self.winfo_exists():
            return
        if req_id != self._still_req_id:
            return
        try:
            photo = ImageTk.PhotoImage(img)
            self._cur_photo = photo
            self._vcanvas.delete("all")
            self._canvas_img = self._vcanvas.create_image(0, 0, image=photo, anchor="nw")
            # Play overlay
            cx, cy = PREV_W // 2, PREV_H // 2
            self._vcanvas.create_oval(cx-26, cy-26, cx+26, cy+26,
                                       fill="#00000088", outline="#FFFFFF", width=2)
            self._vcanvas.create_polygon(cx-8, cy-13, cx+14, cy, cx-8, cy+13, fill="#FFFFFF")
        except Exception:
            pass

    def _toggle_play(self):
        if self._playing:
            self._pause_play()
        else:
            self._start_play()

    def _pause_play(self):
        """Pozastaví přehrávání na aktuálním čase a zachová zobrazený snímek."""
        self._playing = False
        self._stop_ev.set()

        if self._disp_id:
            try:
                self.after_cancel(self._disp_id)
            except Exception:
                pass
            self._disp_id = None

        self._kill_playback_procs()

        with self._frame_lock:
            self._next_frame = None

        try:
            if self._btn_pp.winfo_exists():
                t = "Pokračovat v přehrávání" if self.lang == "cs" else "Resume Preview"
                self._btn_pp.configure(text=t, image=self._icon_play, fg_color=ORANGE)
        except Exception:
            pass

    def _start_play(self):
        """Spustí přehrávání od aktuálního času (buď od začátku, nebo naváže po pauze)."""
        if self._pending_play_id:
            try:
                self.after_cancel(self._pending_play_id)
            except Exception:
                pass
            self._pending_play_id = None

        self._play_session_id += 1
        curr_session = self._play_session_id

        self._stop_ev.set()
        self._kill_playback_procs()
        if not self.segs:
            return

        seg = self.segs[self._sel]
        s0, s1 = seg[0], seg[1]
        self._play_dur = max(0.5, s1 - s0)

        # Pokud jsme na konci nebo těsně před ním, začneme od začátku
        if self._cur_play_offset >= (self._play_dur - 0.25):
            self._cur_play_offset = 0.0
            self._vcanvas.delete("all")
            self._canvas_img = None

        resume_start = s0 + self._cur_play_offset
        resume_dur = max(0.2, self._play_dur - self._cur_play_offset)

        ffplay = find_binary("ffplay")
        ffmpeg = find_binary("ffmpeg")
        if not ffplay or not ffmpeg:
            return

        self._playing = True
        self._stop_ev.clear()
        self._ended_ev.clear()
        with self._frame_lock:
            self._next_frame = None

        t = "Pozastavit" if self.lang == "cs" else "Pause"
        self._btn_pp.configure(text=t, image=self._icon_pause, fg_color="#DC2626")

        cflags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
        sinfo = None
        if sys.platform.startswith("win"):
            sinfo = subprocess.STARTUPINFO()
            sinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            sinfo.wShowWindow = 0

        # Audio: ffplay od navázané pozice
        self._aud_proc = subprocess.Popen(
            [str(ffplay), "-nodisp",
             "-ss", f"{resume_start:.3f}", "-t", f"{resume_dur:.3f}",
             "-autoexit", str(self.video_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            startupinfo=sinfo, creationflags=cflags)

        # Video: ffmpeg raw RGB pipe od navázané pozice
        self._vid_proc = subprocess.Popen(
            [str(ffmpeg),
             "-ss", f"{resume_start:.3f}", "-t", f"{resume_dur:.3f}",
             "-i", str(self.video_path),
             "-vf", f"scale={PREV_W}:{PREV_H},fps={PLAY_FPS}",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            startupinfo=sinfo, creationflags=cflags)

        # Reader thread s počátečním offsetem a session ID
        base_offset = self._cur_play_offset
        threading.Thread(target=self._reader, args=(curr_session, base_offset), daemon=True).start()
        # Display timer
        self._disp_id = self.after(DISP_MS, self._disp_tick)

    def _reader(self, session_id: int, base_offset: float = 0.0):
        """Čte snímky z ffmpeg jako čisté PIL Images v bg threadu (žádný PhotoImage v threadu!)."""
        fsize = PREV_W * PREV_H * 3
        fi = 0
        wall0 = time.monotonic()

        try:
            while not self._stop_ev.is_set() and session_id == self._play_session_id:
                if not self._vid_proc or not self._vid_proc.stdout:
                    break
                raw = self._vid_proc.stdout.read(fsize)
                if len(raw) < fsize:
                    break

                fi += 1
                ft = base_offset + (fi / PLAY_FPS)

                try:
                    img = Image.frombytes("RGB", (PREV_W, PREV_H), raw)
                except Exception:
                    continue

                with self._frame_lock:
                    self._next_frame = (img, ft)

                # Pacing - čekej na správný čas
                target = wall0 + (fi / PLAY_FPS)
                wait = target - time.monotonic()
                if wait > 0.003:
                    time.sleep(wait)

        except Exception:
            pass
        finally:
            if session_id == self._play_session_id:
                self._ended_ev.set()

    def _disp_tick(self):
        """Tick v main threadu: převezme PIL Image, vytvoří PhotoImage a vykreslí ho."""
        if not self._playing or self._closing:
            return

        if self._ended_ev.is_set():
            self._on_play_end()
            return

        with self._frame_lock:
            item = self._next_frame
            self._next_frame = None

        if item is not None:
            img, ft = item
            try:
                photo = ImageTk.PhotoImage(img)
                self._cur_photo = photo  # GC reference na main threadu
                self._cur_play_offset = ft

                if self._canvas_img is None:
                    self._canvas_img = self._vcanvas.create_image(0, 0, image=photo, anchor="nw")
                else:
                    self._vcanvas.itemconfig(self._canvas_img, image=photo)

                self._lbl_ct.configure(text=fmt_t(ft))
                if self._play_dur > 0:
                    self._pbar.set(min(1.0, ft / self._play_dur))
            except Exception:
                pass

        # Naplánuj další tick
        self._disp_id = self.after(DISP_MS, self._disp_tick)

    def _on_play_end(self):
        self._stop_play()
        self._cur_play_offset = 0.0
        self._lbl_ct.configure(text="00:00")
        self._pbar.set(0.0)
        t = "Přehrát náhled" if self.lang == "cs" else "Play Preview"
        self._btn_pp.configure(text=t, image=self._icon_play, fg_color=ORANGE)
        if 0 <= self._sel < len(self.segs):
            self._still_req_id += 1
            req_id = self._still_req_id
            threading.Thread(target=self._load_still, args=(req_id, self.segs[self._sel][0]),
                             daemon=True).start()

    def _kill_playback_procs(self):
        for attr in ("_aud_proc", "_vid_proc"):
            proc = getattr(self, attr, None)
            if proc:
                try:
                    if hasattr(proc, "stdout") and proc.stdout:
                        try:
                            proc.stdout.close()
                        except Exception:
                            pass
                    if proc.poll() is None:
                        proc.terminate()
                        proc.wait(timeout=0.15)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            setattr(self, attr, None)

    def _stop_play(self):
        """Úplné zastavení přehrávání a reset pozice."""
        was = self._playing
        self._playing = False
        self._stop_ev.set()

        if self._disp_id:
            try:
                self.after_cancel(self._disp_id)
            except Exception:
                pass
            self._disp_id = None

        self._kill_playback_procs()

        with self._frame_lock:
            self._next_frame = None
        self._canvas_img = None

        if was:
            try:
                if self._btn_pp.winfo_exists():
                    t = "Přehrát náhled" if self.lang == "cs" else "Play Preview"
                    self._btn_pp.configure(text=t, image=self._icon_play, fg_color=ORANGE)
            except Exception:
                pass

    def _ext_player(self):
        if not self.segs:
            return
        seg = self.segs[self._sel]
        s0, s1 = seg[0], seg[1]
        ffplay = find_binary("ffplay")
        if not ffplay:
            return
        try:
            cflags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
            sinfo = None
            if sys.platform.startswith("win"):
                sinfo = subprocess.STARTUPINFO()
                sinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                sinfo.wShowWindow = 0
            subprocess.Popen(
                [str(ffplay), "-ss", f"{s0:.2f}", "-t", f"{s1-s0:.2f}",
                 "-autoexit", "-x", "640", "-y", "360", str(self.video_path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                startupinfo=sinfo, creationflags=cflags)
        except Exception:
            pass

    # ==================================================================
    # Zahrnutí / vyloučení
    # ==================================================================

    def _toggle_inc(self):
        idx = self._sel
        if 0 <= idx < len(self._inc):
            self._inc[idx] = not self._inc[idx]
            self._chk_vars[idx].set(self._inc[idx])
            self._update_inc_btn(self._inc[idx])
            self._update_summary()

    def _update_inc_btn(self, inc: bool):
        if inc:
            t = "Zahrnuto do výsledného videa" if self.lang == "cs" else "Included in Cut"
            self._btn_inc.configure(text=t,
                                    image=self._icon_check,
                                    compound="left",
                                    fg_color=("#E8F5E9", "#1B3320"),
                                    hover_color=("#C8E6C9", "#23472B"),
                                    text_color=("#2E7D32", "#4ADE80"),
                                    border_color=("#A5D6A7", "#2D5A37"))
        else:
            t = "Vynecháno (klikni pro zahrnutí)" if self.lang == "cs" else "Excluded (click to include)"
            self._btn_inc.configure(text=t,
                                    image=self._icon_plus,
                                    compound="left",
                                    fg_color=BG_INNER_T,
                                    hover_color=("#E5E7EB", "#252834"),
                                    text_color=TXT_MUTED_T,
                                    border_color=BD_CARD_T)

    def _on_chk(self, idx: int):
        self._inc[idx] = self._chk_vars[idx].get()
        if idx == self._sel:
            self._update_inc_btn(self._inc[idx])
        self._update_summary()

    def _sel_all(self):
        self._inc = [True] * len(self._inc)
        for v in self._chk_vars:
            v.set(True)
        self._update_inc_btn(True)
        self._update_summary()

    def _desel_all(self):
        self._inc = [False] * len(self._inc)
        for v in self._chk_vars:
            v.set(False)
        self._update_inc_btn(False)
        self._update_summary()

    def _reset_ai(self):
        for i, seg in enumerate(self.segs):
            val = (round(seg[0], 2), round(seg[1], 2)) in self._rec_set
            self._inc[i] = val
            self._chk_vars[i].set(val)
        self._update_inc_btn(self._inc[self._sel] if self.segs else False)
        self._update_summary()

    # ==================================================================
    # Live souhrn
    # ==================================================================

    def _update_summary(self):
        sc = sum(1 for x in self._inc if x)
        sd = sum((self.segs[i][1] - self.segs[i][0]) for i, x in enumerate(self._inc) if x)
        total = len(self.segs)
        d_str = fmt_t(sd)
        c_str = format_moments_count(sc, self.lang)

        if self.lang == "cs":
            self._lbl_count.configure(text=f"Vybráno: {c_str} (celkem: {total})")
        else:
            self._lbl_count.configure(text=f"Selected: {sc} of {total} clips")

        if self.target_dur and self.target_dur > 0:
            t_str = fmt_t(self.target_dur)
            if sd < self.target_dur * 0.9:
                # Celkova delka mensi nez cil - informuj uzivatele
                note = " (video kratsi nez cilova delka)" if self.lang == "cs" else " (video shorter than target)"
            else:
                note = ""
            dt = f"Délka: {d_str} / Cíl: {t_str}{note}" if self.lang == "cs" else f"Duration: {d_str} / Target: {t_str}{note}"
            self._lbl_dur.configure(text=dt)
            pct = min(1.0, sd / self.target_dur)
            if self._tpbar:
                self._tpbar.set(pct)
            if self._lbl_tpct:
                self._lbl_tpct.configure(text=f"{int(pct*100)}%")
        else:
            dt = f"Celková délka: {d_str}" if self.lang == "cs" else f"Total duration: {d_str}"
            self._lbl_dur.configure(text=dt)

        if self.lang == "cs":
            self._lbl_foot.configure(text=f"Celkem vybráno {c_str} ({d_str})")
            self._btn_conf.configure(text=f"Sestříhat {c_str}")
        else:
            self._lbl_foot.configure(text=f"{sc} clips selected ({d_str})")
            self._btn_conf.configure(text=f"Export {sc} clips")

    # ==================================================================
    # Potvrzení / Zrušení
    # ==================================================================

    def _on_confirm(self):
        chosen = [self.segs[i] for i, x in enumerate(self._inc) if x]
        if not chosen:
            from tkinter import messagebox
            t = "Žádný výběr" if self.lang == "cs" else "No Selection"
            m = ("Vyber alespoň 1 moment." if self.lang == "cs"
                 else "Please select at least 1 moment.")
            messagebox.showwarning(t, m)
            return
        self._cleanup()
        if self.on_confirm:
            self.on_confirm(chosen)
        self.destroy()

    def _on_cancel(self):
        self._cleanup()
        if self.on_cancel:
            self.on_cancel()
        self.destroy()

    def _cleanup(self):
        self._closing = True
        self._play_session_id += 1
        self._still_req_id += 1
        if self._pending_play_id:
            try:
                self.after_cancel(self._pending_play_id)
            except Exception:
                pass
            self._pending_play_id = None
        self._stop_play()
