"""
segment_editor.py - Interactive Segment Review & Embedded Video Preview Editor for Pecislav Studio.

Provides an integrated, high-performance editor with:
1. In-App Embedded Video Player (no external popup windows!).
2. Instant frame preview and synchronized video/audio playback directly on Tkinter Canvas.
3. Smooth, optimized 60+ FPS scrolling list of all detected moments.
4. Correct Czech plural declension (1 moment, 2-4 momenty, 5+ momentů).
5. Live target duration statistics, progress bar, and bulk selection tools.
"""

from __future__ import annotations

import io
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

import customtkinter as ctk
from PIL import Image, ImageTk

from ffmpeg_utils import find_binary


# -----------------------------------------------------------------------------
# Color Palette & Theme Constants (Pecislav Studio Design System)
# -----------------------------------------------------------------------------
BG_WINDOW = ("#F8F9FA", "#14151B")
BG_CARD = ("#FFFFFF", "#181A22")
BG_CARD_INNER = ("#F3F4F6", "#1E2028")
BG_PLAYER_SCREEN = "#0B0C10"
BORDER_CARD = ("#E5E7EB", "#2B2E3B")
BORDER_ACTIVE = ("#EA580C", "#FF6B00")
ORANGE_PRIMARY = "#FF6B00"
ORANGE_HOVER = "#E05D00"
ORANGE_SUBTLE = ("#FFF7ED", "#26170E")
ORANGE_ACCENT_TEXT = ("#EA580C", "#FF8533")
TEXT_TITLE = ("#111827", "#F9FAFB")
TEXT_BODY = ("#4B5563", "#9CA3AF")
TEXT_MUTED = ("#6B7280", "#6B7280")
BADGE_AI_BG = ("#FEF3C7", "#2D2411")
BADGE_AI_FG = ("#D97706", "#FBBF24")
BADGE_TAG_BG = ("#E5E7EB", "#252834")


def format_moments_count(count: int, lang: str = "cs") -> str:
    """Correct plural declension for 'moment' / 'clip' (1 moment, 2-4 momenty, 5+ momentů)."""
    if lang == "en":
        return f"{count} clip" if count == 1 else f"{count} clips"

    n = abs(count)
    if n % 100 in (11, 12, 13, 14):
        return f"{count} momentů"
    rem = n % 10
    if rem == 1:
        return f"{count} moment"
    elif rem in (2, 3, 4):
        return f"{count} momenty"
    else:
        return f"{count} momentů"


def format_time_hms(seconds: float) -> str:
    """Formats seconds into HH:MM:SS or MM:SS string."""
    seconds = max(0.0, seconds)
    total_sec = int(round(seconds))
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def extract_preview_frame(video_path: Path, timestamp: float, width=480, height=270) -> Optional[Image.Image]:
    """Rapidly extracts a single frame at the given timestamp using FFmpeg."""
    ffmpeg_bin = find_binary("ffmpeg")
    if not ffmpeg_bin or not video_path.is_file():
        return None

    cmd = [
        str(ffmpeg_bin),
        "-ss", f"{timestamp:.2f}",
        "-i", str(video_path),
        "-vframes", "1",
        "-vf", f"scale={width}:{height}",
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "pipe:1"
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        out, _ = proc.communicate(timeout=3.0)
        if out:
            return Image.open(io.BytesIO(out))
    except Exception:
        pass
    return None


class SegmentReviewDialog(ctk.CTkToplevel):
    """
    Modern modal dialog with an embedded in-app video player and
    a high-performance, fluid list of all detected segments.
    """

    def __init__(
        self,
        parent: ctk.CTk,
        video_path: Path,
        all_segments: List[Tuple],
        recommended_segments: List[Tuple],
        target_duration_sec: Optional[float] = None,
        current_lang: str = "cs",
        on_confirm: Optional[Callable[[List[Tuple]], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent)

        self.parent_app = parent
        self.video_path = video_path
        self.all_segments = list(all_segments)
        self.recommended_segments = list(recommended_segments)
        self.target_duration_sec = target_duration_sec
        self.current_lang = current_lang if current_lang in ["cs", "en"] else "cs"
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel

        self.recommended_set: Set[Tuple[float, float]] = {
            (round(s[0], 2), round(s[1], 2)) for s in self.recommended_segments
        }

        # Active state
        self._selected_idx: int = 0
        self._closing: bool = False
        self._is_playing: bool = False

        # Playback subprocesses & thread
        self._audio_proc: Optional[subprocess.Popen] = None
        self._video_proc: Optional[subprocess.Popen] = None
        self._playback_thread: Optional[threading.Thread] = None
        self._stop_playback_event = threading.Event()
        self._current_photo_ref: Optional[ImageTk.PhotoImage] = None

        # Data & widget maps
        self._segment_vars: List[ctk.BooleanVar] = []
        self._row_frames: List[ctk.CTkFrame] = []
        self._row_labels: List[ctk.CTkLabel] = []

        # Modal Setup
        title_text = "Pecislav Studio • Editor nalezených momentů" if self.current_lang == "cs" else "Pecislav Studio • Segment Review & Editor"
        self.title(title_text)
        self.geometry("1120x750")
        self.minsize(920, 580)
        self.configure(fg_color=BG_WINDOW)

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel_click)

        self._center_window()
        self._build_ui()
        self._update_summary()

        # Select first segment by default & display initial frame
        if self.all_segments:
            self.after(50, lambda: self._select_segment(0))

    def _center_window(self):
        self.update_idletasks()
        try:
            pw = self.parent_app.winfo_width()
            ph = self.parent_app.winfo_height()
            px = self.parent_app.winfo_x()
            py = self.parent_app.winfo_y()

            w = 1120
            h = 750
            x = px + max(0, (pw - w) // 2)
            y = py + max(0, (ph - h) // 2)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # UI Layout Construction
    # -------------------------------------------------------------------------

    def _build_ui(self):
        # 1. Top Header (Branding & Live Summary)
        self._build_header()

        # 2. Main Split Area: Left Player, Right List
        split_frame = ctk.CTkFrame(self, fg_color="transparent")
        split_frame.pack(fill="both", expand=True, padx=18, pady=(0, 10))

        # Left Column: In-App Embedded Video Player
        self._build_left_player(split_frame)

        # Right Column: Smooth Moments Checklist
        self._build_right_list(split_frame)

        # 3. Bottom Action Footer
        self._build_footer()

    def _build_header(self):
        header_card = ctk.CTkFrame(
            self,
            corner_radius=10,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD
        )
        header_card.pack(fill="x", padx=18, pady=(14, 10))

        inner = ctk.CTkFrame(header_card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=10)

        left_col = ctk.CTkFrame(inner, fg_color="transparent")
        left_col.pack(side="left", fill="x", expand=True)

        t_title = "🎬 Editor nalezených momentů & Náhledy" if self.current_lang == "cs" else "🎬 Moments Editor & In-App Preview"
        t_sub = (
            "Kliknutím na moment si jej ihned přehrajte přímo v integrovaném přehrávači. Zaškrtněte momenty pro export."
            if self.current_lang == "cs"
            else "Click any moment to immediately preview it in the embedded player. Check clips to include in the cut."
        )

        lbl_title = ctk.CTkLabel(
            left_col,
            text=t_title,
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=TEXT_TITLE
        )
        lbl_title.pack(anchor="w")

        lbl_sub = ctk.CTkLabel(
            left_col,
            text=t_sub,
            font=ctk.CTkFont(size=12),
            text_color=TEXT_BODY
        )
        lbl_sub.pack(anchor="w", pady=(2, 0))

        # Right: Live Stats Counter Pill
        self.stats_pill = ctk.CTkFrame(
            inner,
            fg_color=BG_CARD_INNER,
            corner_radius=8,
            border_width=1,
            border_color=BORDER_CARD
        )
        self.stats_pill.pack(side="right", padx=(12, 0))

        sp_inner = ctk.CTkFrame(self.stats_pill, fg_color="transparent")
        sp_inner.pack(padx=14, pady=6)

        self.lbl_stats_count = ctk.CTkLabel(
            sp_inner,
            text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=ORANGE_ACCENT_TEXT
        )
        self.lbl_stats_count.pack(anchor="e")

        self.lbl_stats_duration = ctk.CTkLabel(
            sp_inner,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_BODY
        )
        self.lbl_stats_duration.pack(anchor="e")

    def _build_left_player(self, parent):
        """Constructs the left panel with embedded video screen, controls, and details."""
        player_container = ctk.CTkFrame(
            parent,
            width=500,
            corner_radius=10,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD
        )
        player_container.pack(side="left", fill="y", padx=(0, 10))
        player_container.pack_propagate(False)

        p_inner = ctk.CTkFrame(player_container, fg_color="transparent")
        p_inner.pack(fill="both", expand=True, padx=12, pady=12)

        # 1. Selected Moment Header
        sel_hdr = ctk.CTkFrame(p_inner, fg_color="transparent")
        sel_hdr.pack(fill="x", pady=(0, 8))

        self.lbl_player_title = ctk.CTkLabel(
            sel_hdr,
            text="Moment #01",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_player_title.pack(side="left")

        self.lbl_player_timecode = ctk.CTkLabel(
            sel_hdr,
            text="00:00:00 ➔ 00:00:00",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=ORANGE_ACCENT_TEXT
        )
        self.lbl_player_timecode.pack(side="right")

        # 2. Embedded Video Screen (Tkinter Canvas)
        screen_frame = ctk.CTkFrame(
            p_inner,
            fg_color=BG_PLAYER_SCREEN,
            corner_radius=8,
            border_width=1,
            border_color=BORDER_CARD
        )
        screen_frame.pack(fill="x", pady=(0, 8))

        self.video_canvas = ctk.CTkCanvas(
            screen_frame,
            width=476,
            height=268,
            bg="#000000",
            highlightthickness=0,
            cursor="hand2"
        )
        self.video_canvas.pack(padx=2, pady=2)
        self.video_canvas.bind("<Button-1>", lambda e: self._toggle_playback())

        # 3. Scrubber & Time Bar
        scrub_row = ctk.CTkFrame(p_inner, fg_color="transparent")
        scrub_row.pack(fill="x", pady=(0, 8))

        self.lbl_current_play_time = ctk.CTkLabel(
            scrub_row,
            text="00:00",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_TITLE,
            width=40
        )
        self.lbl_current_play_time.pack(side="left")

        self.play_progress = ctk.CTkProgressBar(
            scrub_row,
            height=8,
            progress_color=ORANGE_PRIMARY,
            fg_color=BG_CARD_INNER
        )
        self.play_progress.pack(side="left", fill="x", expand=True, padx=8)
        self.play_progress.set(0.0)

        self.lbl_total_play_time = ctk.CTkLabel(
            scrub_row,
            text="00:00",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
            width=40
        )
        self.lbl_total_play_time.pack(side="right")

        # 4. Player Control Buttons
        ctrl_bar = ctk.CTkFrame(p_inner, fg_color="transparent")
        ctrl_bar.pack(fill="x", pady=(0, 10))

        self.btn_play_pause = ctk.CTkButton(
            ctrl_bar,
            text="▶ Přehrát náhled" if self.current_lang == "cs" else "▶ Play Preview",
            command=self._toggle_playback,
            height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ORANGE_PRIMARY,
            hover_color=ORANGE_HOVER,
            text_color="#FFFFFF",
            corner_radius=6
        )
        self.btn_play_pause.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_stop = ctk.CTkButton(
            ctrl_bar,
            text="⏹",
            command=self._stop_playback,
            height=34,
            width=42,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=BG_CARD_INNER,
            hover_color=("#E5E7EB", "#252834"),
            text_color=TEXT_TITLE,
            border_width=1,
            border_color=BORDER_CARD,
            corner_radius=6
        )
        self.btn_stop.pack(side="left", padx=(0, 6))

        # External OS Window Fallback Button
        self.btn_ext_window = ctk.CTkButton(
            ctrl_bar,
            text="⤢",
            command=self._open_external_ffplay,
            height=34,
            width=42,
            font=ctk.CTkFont(size=14),
            fg_color=BG_CARD_INNER,
            hover_color=("#E5E7EB", "#252834"),
            text_color=TEXT_TITLE,
            border_width=1,
            border_color=BORDER_CARD,
            corner_radius=6
        )
        self.btn_ext_window.pack(side="right")

        # 5. Big Inclusion Toggle Button for Selected Segment
        self.btn_toggle_include = ctk.CTkButton(
            p_inner,
            text="✓ Vybráno do sestřihu",
            command=self._toggle_current_segment_selection,
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=("#E8F5E9", "#1B3320"),
            hover_color=("#C8E6C9", "#23472B"),
            text_color=("#2E7D32", "#4ADE80"),
            border_width=1,
            border_color=("#A5D6A7", "#2D5A37"),
            corner_radius=6
        )
        self.btn_toggle_include.pack(fill="x", pady=(0, 10))

        # 6. Clip Metadata & Hype Details Card
        info_box = ctk.CTkFrame(
            p_inner,
            fg_color=BG_CARD_INNER,
            corner_radius=8,
            border_width=1,
            border_color=BORDER_CARD
        )
        info_box.pack(fill="both", expand=True)

        ib_inner = ctk.CTkFrame(info_box, fg_color="transparent")
        ib_inner.pack(fill="both", expand=True, padx=12, pady=10)

        self.lbl_info_loudness = ctk.CTkLabel(
            ib_inner,
            text="🔥 Hlasitost: -14.0 dBFS",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_TITLE
        )
        self.lbl_info_loudness.pack(anchor="w", pady=(0, 4))

        self.lbl_info_facecam = ctk.CTkLabel(
            ib_inner,
            text="🤖 Facecam reakce: N/A",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_BODY
        )
        self.lbl_info_facecam.pack(anchor="w", pady=(0, 4))

        self.lbl_info_ai_rec = ctk.CTkLabel(
            ib_inner,
            text="⭐ AI Doporučení pro cílovou délku",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=BADGE_AI_FG
        )
        self.lbl_info_ai_rec.pack(anchor="w")

    def _build_right_list(self, parent):
        """Constructs the right panel with smooth, lightweight segment list and toolbar."""
        list_container = ctk.CTkFrame(
            parent,
            corner_radius=10,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD
        )
        list_container.pack(side="right", fill="both", expand=True)

        # Toolbar Frame
        toolbar = ctk.CTkFrame(list_container, fg_color="transparent")
        toolbar.pack(fill="x", padx=14, pady=(12, 6))

        t_reset = "⭐ Obnovit AI výběr" if self.current_lang == "cs" else "⭐ Reset AI Picks"
        t_sel_all = "☑️ Vybrat vše" if self.current_lang == "cs" else "☑️ Select All"
        t_desel_all = "⬜ Zrušit vše" if self.current_lang == "cs" else "⬜ Deselect All"

        btn_reset_ai = ctk.CTkButton(
            toolbar,
            text=t_reset,
            command=self._reset_ai_selection,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=BADGE_AI_BG,
            hover_color=("#FDE68A", "#3D3016"),
            text_color=BADGE_AI_FG,
            border_width=1,
            border_color=("#F59E0B", "#B45309"),
            corner_radius=5
        )
        btn_reset_ai.pack(side="left", padx=(0, 6))

        btn_select_all = ctk.CTkButton(
            toolbar,
            text=t_sel_all,
            command=self._select_all,
            height=28,
            width=90,
            font=ctk.CTkFont(size=11),
            fg_color=BG_CARD_INNER,
            hover_color=("#E5E7EB", "#252834"),
            text_color=TEXT_TITLE,
            border_width=1,
            border_color=BORDER_CARD,
            corner_radius=5
        )
        btn_select_all.pack(side="left", padx=(0, 6))

        btn_deselect_all = ctk.CTkButton(
            toolbar,
            text=t_desel_all,
            command=self._deselect_all,
            height=28,
            width=90,
            font=ctk.CTkFont(size=11),
            fg_color=BG_CARD_INNER,
            hover_color=("#E5E7EB", "#252834"),
            text_color=TEXT_TITLE,
            border_width=1,
            border_color=BORDER_CARD,
            corner_radius=5
        )
        btn_deselect_all.pack(side="left")

        # Target Progress Indicator
        if self.target_duration_sec and self.target_duration_sec > 0:
            tp_box = ctk.CTkFrame(toolbar, fg_color="transparent")
            tp_box.pack(side="right")

            self.target_prog_bar = ctk.CTkProgressBar(
                tp_box,
                width=120,
                height=8,
                progress_color=ORANGE_PRIMARY,
                fg_color=BG_CARD_INNER
            )
            self.target_prog_bar.pack(side="right", padx=(6, 0))

            self.lbl_target_pct = ctk.CTkLabel(
                tp_box,
                text="0%",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=TEXT_TITLE
            )
            self.lbl_target_pct.pack(side="right")
        else:
            self.target_prog_bar = None
            self.lbl_target_pct = None

        # Scrollable Frame for moments
        self.scroll_frame = ctk.CTkScrollableFrame(
            list_container,
            fg_color="transparent",
            corner_radius=0
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._setup_smooth_scrolling()

        # Render lightweight, fast rows
        for idx, seg in enumerate(self.all_segments):
            start_sec = seg[0]
            end_sec = seg[1]
            dur = max(0.1, end_sec - start_sec)
            peak_dbfs = seg[2] if len(seg) >= 3 else -14.0
            face_score = seg[3] if len(seg) >= 4 else 0.0

            is_recommended = (round(start_sec, 2), round(end_sec, 2)) in self.recommended_set
            var = ctk.BooleanVar(value=is_recommended)
            self._segment_vars.append(var)

            # Row Container
            row = ctk.CTkFrame(
                self.scroll_frame,
                corner_radius=6,
                fg_color=BG_CARD_INNER,
                border_width=1,
                border_color=BORDER_ACTIVE if (idx == 0) else BORDER_CARD,
                height=42
            )
            row.pack(fill="x", pady=2)
            self._row_frames.append(row)

            # Clicking anywhere on the row selects it in the left player
            row.bind("<Button-1>", lambda e, i=idx: self._select_segment(i))

            inner = ctk.CTkFrame(row, fg_color="transparent")
            inner.pack(fill="x", padx=8, pady=6)
            inner.bind("<Button-1>", lambda e, i=idx: self._select_segment(i))

            # 1. Checkbox
            chk = ctk.CTkCheckBox(
                inner,
                text="",
                variable=var,
                width=22,
                checkbox_width=18,
                checkbox_height=18,
                corner_radius=4,
                fg_color=ORANGE_PRIMARY,
                hover_color=ORANGE_HOVER,
                border_color=("#9CA3AF", "#4B5563"),
                command=lambda i=idx: self._on_checkbox_toggle(i)
            )
            chk.pack(side="left", padx=(0, 6))

            # 2. Index Badge
            lbl_idx = ctk.CTkLabel(
                inner,
                text=f"#{idx + 1:02d}",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=TEXT_MUTED,
                width=30
            )
            lbl_idx.pack(side="left", padx=(0, 4))
            lbl_idx.bind("<Button-1>", lambda e, i=idx: self._select_segment(i))

            # 3. Timecodes & Duration
            time_str = f"{format_time_hms(start_sec)}  ➔  {format_time_hms(end_sec)}"
            lbl_time = ctk.CTkLabel(
                inner,
                text=f"{time_str}  ({dur:.1f}s)",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=TEXT_TITLE
            )
            lbl_time.pack(side="left", padx=(0, 6))
            lbl_time.bind("<Button-1>", lambda e, i=idx: self._select_segment(i))
            self._row_labels.append(lbl_time)

            # 4. Badges (AI & Loudness)
            if is_recommended:
                b_ai = ctk.CTkLabel(
                    inner,
                    text="⭐ AI",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color=BADGE_AI_FG,
                    fg_color=BADGE_AI_BG,
                    corner_radius=4,
                    padx=5,
                    pady=1
                )
                b_ai.pack(side="left", padx=(0, 4))
                b_ai.bind("<Button-1>", lambda e, i=idx: self._select_segment(i))

            b_loud = ctk.CTkLabel(
                inner,
                text=f"🔥 {peak_dbfs:.1f} dBFS",
                font=ctk.CTkFont(size=10),
                text_color=TEXT_TITLE,
                fg_color=BADGE_TAG_BG,
                corner_radius=4,
                padx=5,
                pady=1
            )
            b_loud.pack(side="left")
            b_loud.bind("<Button-1>", lambda e, i=idx: self._select_segment(i))

            # 5. Play Icon Button
            btn_play_row = ctk.CTkButton(
                inner,
                text="▶",
                command=lambda i=idx: self._select_and_play_segment(i),
                width=28,
                height=26,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=BG_CARD,
                hover_color=ORANGE_PRIMARY,
                text_color=TEXT_TITLE,
                border_width=1,
                border_color=BORDER_CARD,
                corner_radius=4
            )
            btn_play_row.pack(side="right")

    def _setup_smooth_scrolling(self):
        """Enables smooth, hardware-accelerated mousewheel scrolling on canvas."""
        try:
            canvas = self.scroll_frame._parent_canvas
            orig_yview = canvas.yview

            def safe_yview(*args):
                if not args:
                    return orig_yview()
                return orig_yview(*args)

            canvas.yview = safe_yview

            def custom_check_valid_scroll(widget):
                try:
                    if isinstance(widget, ctk.windows.widgets.ctk_scrollbar.CTkScrollbar):
                        return False
                except Exception:
                    pass
                return True

            self.scroll_frame._check_if_valid_scroll = custom_check_valid_scroll
        except Exception:
            pass

    def _build_footer(self):
        footer_card = ctk.CTkFrame(
            self,
            corner_radius=10,
            fg_color=BG_CARD,
            border_width=1,
            border_color=BORDER_CARD
        )
        footer_card.pack(fill="x", side="bottom", padx=18, pady=(0, 14))

        inner = ctk.CTkFrame(footer_card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=10)

        self.lbl_footer_summary = ctk.CTkLabel(
            inner,
            text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.lbl_footer_summary.pack(side="left")

        # Action Buttons
        self.btn_confirm = ctk.CTkButton(
            inner,
            text="",
            command=self._on_confirm_click,
            height=38,
            width=220,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ORANGE_PRIMARY,
            hover_color=ORANGE_HOVER,
            text_color="#FFFFFF",
            corner_radius=6
        )
        self.btn_confirm.pack(side="right", padx=(10, 0))

        t_cancel = "Zrušit export" if self.current_lang == "cs" else "Cancel Export"
        self.btn_cancel = ctk.CTkButton(
            inner,
            text=t_cancel,
            command=self._on_cancel_click,
            height=38,
            width=110,
            font=ctk.CTkFont(size=12),
            fg_color=BG_CARD_INNER,
            hover_color=("#E5E7EB", "#2B2E3B"),
            text_color=TEXT_TITLE,
            border_width=1,
            border_color=BORDER_CARD,
            corner_radius=6
        )
        self.btn_cancel.pack(side="right")

    # -------------------------------------------------------------------------
    # Segment Selection & Navigation
    # -------------------------------------------------------------------------

    def _select_segment(self, idx: int):
        """Highlights row, updates embedded player info and displays preview frame."""
        if not (0 <= idx < len(self.all_segments)):
            return

        self._stop_playback()
        self._selected_idx = idx

        # Update row highlight borders
        for i, row in enumerate(self._row_frames):
            if i == idx:
                row.configure(border_color=BORDER_ACTIVE, fg_color=("#FFF7ED", "#231B15"))
            else:
                row.configure(border_color=BORDER_CARD, fg_color=BG_CARD_INNER)

        seg = self.all_segments[idx]
        start_sec, end_sec = seg[0], seg[1]
        dur = max(0.1, end_sec - start_sec)
        peak_dbfs = seg[2] if len(seg) >= 3 else -14.0
        face_score = seg[3] if len(seg) >= 4 else 0.0
        is_rec = (round(start_sec, 2), round(end_sec, 2)) in self.recommended_set

        # Update Player Header
        t_moment = f"Moment #{idx + 1:02d}"
        self.lbl_player_title.configure(text=t_moment)
        self.lbl_player_timecode.configure(
            text=f"{format_time_hms(start_sec)} ➔ {format_time_hms(end_sec)} ({dur:.1f}s)"
        )

        # Update Player Controls
        self.lbl_current_play_time.configure(text="00:00")
        self.lbl_total_play_time.configure(text=format_time_hms(dur))
        self.play_progress.set(0.0)

        t_play = "▶ Přehrát náhled" if self.current_lang == "cs" else "▶ Play Preview"
        self.btn_play_pause.configure(text=t_play, fg_color=ORANGE_PRIMARY)

        # Update Inclusion Button
        self._update_inclusion_button_ui(self._segment_vars[idx].get())

        # Update Metadata Box
        self.lbl_info_loudness.configure(text=f"🔥 Hlasitost špičky: {peak_dbfs:.1f} dBFS")
        if face_score > 0.05:
            self.lbl_info_facecam.configure(text=f"🤖 Facecam reakce: {int(face_score * 100)}% (výraz obličeje)")
        else:
            self.lbl_info_facecam.configure(text="🤖 Facecam reakce: Bez výrazné reakce / kamera nevypozorována")

        if is_rec:
            t_rec = "⭐ AI Doporučení pro cílovou délku" if self.current_lang == "cs" else "⭐ Recommended by AI"
            self.lbl_info_ai_rec.configure(text=t_rec, text_color=BADGE_AI_FG)
        else:
            t_rec = "ℹ️ Doplňkový moment (můžete zahrnout)" if self.current_lang == "cs" else "ℹ️ Optional moment"
            self.lbl_info_ai_rec.configure(text=t_rec, text_color=TEXT_MUTED)

        # Asynchronously fetch single frame for the player canvas
        threading.Thread(target=self._load_player_frame_worker, args=(start_sec,), daemon=True).start()

    def _select_and_play_segment(self, idx: int):
        self._select_segment(idx)
        self.after(50, self._start_playback)

    def _load_player_frame_worker(self, timestamp: float):
        img = extract_preview_frame(self.video_path, timestamp, width=476, height=268)
        if img:
            self.after(0, lambda: self._draw_canvas_image(img))

    def _draw_canvas_image(self, pil_image: Image.Image):
        if not self.winfo_exists() or self._closing:
            return
        photo = ImageTk.PhotoImage(pil_image)
        self._current_photo_ref = photo
        self.video_canvas.delete("all")
        self.video_canvas.create_image(0, 0, image=photo, anchor="nw")

        # Draw subtle centered play triangle overlay if not playing
        if not self._is_playing:
            cx, cy = 476 // 2, 268 // 2
            self.video_canvas.create_oval(cx - 24, cy - 24, cx + 24, cy + 24, fill="#000000", outline="#FFFFFF", width=2)
            self.video_canvas.create_polygon(cx - 7, cy - 12, cx + 13, cy, cx - 7, cy + 12, fill="#FFFFFF")

    # -------------------------------------------------------------------------
    # Embedded Video & Audio Playback Engine
    # -------------------------------------------------------------------------

    def _toggle_playback(self):
        if self._is_playing:
            self._stop_playback()
        else:
            self._start_playback()

    def _start_playback(self):
        self._stop_playback()
        if not self.all_segments:
            return

        seg = self.all_segments[self._selected_idx]
        start_sec, end_sec = seg[0], seg[1]
        dur_sec = max(0.5, end_sec - start_sec)

        ffplay_bin = find_binary("ffplay")
        ffmpeg_bin = find_binary("ffmpeg")
        if not ffplay_bin or not ffmpeg_bin:
            return

        self._is_playing = True
        self._stop_playback_event.clear()

        t_pause = "⏸ Pozastavit" if self.current_lang == "cs" else "⏸ Pause"
        self.btn_play_pause.configure(text=t_pause, fg_color="#DC2626")

        # Start Playback Thread
        self._playback_thread = threading.Thread(
            target=self._playback_worker,
            args=(ffplay_bin, ffmpeg_bin, start_sec, dur_sec),
            daemon=True
        )
        self._playback_thread.start()

    def _playback_worker(self, ffplay_bin: Path, ffmpeg_bin: Path, start_sec: float, dur_sec: float):
        # 1. Background hardware audio stream (ffplay with NO display window)
        cmd_audio = [
            str(ffplay_bin),
            "-nodisp",
            "-ss", f"{start_sec:.2f}",
            "-t", f"{dur_sec:.2f}",
            "-autoexit",
            str(self.video_path)
        ]
        # 2. Direct RGB video frame stream
        cmd_video = [
            str(ffmpeg_bin),
            "-ss", f"{start_sec:.2f}",
            "-t", f"{dur_sec:.2f}",
            "-i", str(self.video_path),
            "-vf", "scale=476:268",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "pipe:1"
        ]

        try:
            self._audio_proc = subprocess.Popen(cmd_audio, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._video_proc = subprocess.Popen(cmd_video, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

            frame_size = 476 * 268 * 3
            fps = 25.0
            frame_delay = 1.0 / fps
            start_wall = time.time()
            frame_idx = 0

            while not self._stop_playback_event.is_set():
                raw = self._video_proc.stdout.read(frame_size)
                if len(raw) < frame_size:
                    break

                img = Image.frombytes("RGB", (476, 268), raw)
                cur_offset = frame_idx / fps

                self.after(0, lambda im=img, off=cur_offset, total=dur_sec: self._update_playback_ui(im, off, total))
                frame_idx += 1

                target_time = start_wall + (frame_idx * frame_delay)
                sleep_dur = target_time - time.time()
                if sleep_dur > 0.005:
                    time.sleep(sleep_dur)

        except Exception as e:
            print(f"[Player] Playback error: {e}")
        finally:
            self.after(0, self._on_playback_finished)

    def _update_playback_ui(self, pil_image: Image.Image, current_sec: float, total_sec: float):
        if not self.winfo_exists() or self._closing or not self._is_playing:
            return
        photo = ImageTk.PhotoImage(pil_image)
        self._current_photo_ref = photo
        self.video_canvas.delete("all")
        self.video_canvas.create_image(0, 0, image=photo, anchor="nw")

        self.lbl_current_play_time.configure(text=format_time_hms(current_sec))
        if total_sec > 0:
            self.play_progress.set(min(1.0, current_sec / total_sec))

    def _on_playback_finished(self):
        self._stop_playback()

    def _stop_playback(self):
        self._is_playing = False
        self._stop_playback_event.set()

        if self._audio_proc:
            try:
                if self._audio_proc.poll() is None:
                    self._audio_proc.terminate()
                    self._audio_proc.wait(timeout=0.2)
            except Exception:
                pass
            self._audio_proc = None

        if self._video_proc:
            try:
                if self._video_proc.poll() is None:
                    self._video_proc.terminate()
                    self._video_proc.wait(timeout=0.2)
            except Exception:
                pass
            self._video_proc = None

        t_play = "▶ Přehrát náhled" if self.current_lang == "cs" else "▶ Play Preview"
        if hasattr(self, "btn_play_pause") and self.btn_play_pause.winfo_exists():
            self.btn_play_pause.configure(text=t_play, fg_color=ORANGE_PRIMARY)

    def _open_external_ffplay(self):
        """Fallback option to launch full external player window if explicitly requested."""
        if not self.all_segments:
            return
        seg = self.all_segments[self._selected_idx]
        start_sec, end_sec = seg[0], seg[1]
        dur = max(0.5, end_sec - start_sec)

        ffplay_bin = find_binary("ffplay")
        if not ffplay_bin:
            return

        cmd = [
            str(ffplay_bin),
            "-ss", f"{start_sec:.2f}",
            "-t", f"{dur:.2f}",
            "-autoexit",
            "-window_title", f"Pecislav Studio • Náhled klipu ({format_time_hms(start_sec)} - {format_time_hms(end_sec)})",
            "-x", "640",
            "-y", "360",
            str(self.video_path)
        ]
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"[Preview] Error: {e}")

    # -------------------------------------------------------------------------
    # Checkbox & State Management
    # -------------------------------------------------------------------------

    def _on_checkbox_toggle(self, idx: int):
        if idx == self._selected_idx:
            self._update_inclusion_button_ui(self._segment_vars[idx].get())
        self._update_summary()

    def _toggle_current_segment_selection(self):
        idx = self._selected_idx
        if 0 <= idx < len(self._segment_vars):
            new_val = not self._segment_vars[idx].get()
            self._segment_vars[idx].set(new_val)
            self._update_inclusion_button_ui(new_val)
            self._update_summary()

    def _update_inclusion_button_ui(self, is_included: bool):
        if is_included:
            t = "✓ Zahrnuto do výsledného videa" if self.current_lang == "cs" else "✓ Included in Cut"
            self.btn_toggle_include.configure(
                text=t,
                fg_color=("#E8F5E9", "#1B3320"),
                hover_color=("#C8E6C9", "#23472B"),
                text_color=("#2E7D32", "#4ADE80"),
                border_color=("#A5D6A7", "#2D5A37")
            )
        else:
            t = "＋ Vynecháno (kliknutím zahrnout)" if self.current_lang == "cs" else "＋ Excluded (click to include)"
            self.btn_toggle_include.configure(
                text=t,
                fg_color=BG_CARD_INNER,
                hover_color=("#E5E7EB", "#252834"),
                text_color=TEXT_MUTED,
                border_color=BORDER_CARD
            )

    def _select_all(self):
        for var in self._segment_vars:
            var.set(True)
        if 0 <= self._selected_idx < len(self._segment_vars):
            self._update_inclusion_button_ui(True)
        self._update_summary()

    def _deselect_all(self):
        for var in self._segment_vars:
            var.set(False)
        if 0 <= self._selected_idx < len(self._segment_vars):
            self._update_inclusion_button_ui(False)
        self._update_summary()

    def _reset_ai_selection(self):
        for idx, seg in enumerate(self.all_segments):
            is_rec = (round(seg[0], 2), round(seg[1], 2)) in self.recommended_set
            self._segment_vars[idx].set(is_rec)
        if 0 <= self._selected_idx < len(self._segment_vars):
            self._update_inclusion_button_ui(self._segment_vars[self._selected_idx].get())
        self._update_summary()

    def _update_summary(self):
        """Recalculates total selected count and duration with correct Czech plural declension."""
        sel_count = 0
        total_duration = 0.0

        for idx, var in enumerate(self._segment_vars):
            if var.get():
                sel_count += 1
                seg = self.all_segments[idx]
                total_duration += (seg[1] - seg[0])

        total_clips = len(self.all_segments)
        cur_dur_str = format_time_hms(total_duration)

        # Correct Czech declension (1 moment, 2-4 momenty, 5+ momentů)
        c_str = format_moments_count(sel_count, self.current_lang)
        tot_str = format_moments_count(total_clips, self.current_lang)

        # Header Counter
        if self.current_lang == "cs":
            self.lbl_stats_count.configure(text=f"Vybráno: {c_str} (celkem: {total_clips})")
        else:
            self.lbl_stats_count.configure(text=f"Selected: {sel_count} of {total_clips} clips")

        if self.target_duration_sec and self.target_duration_sec > 0:
            target_str = format_time_hms(self.target_duration_sec)
            t_dur = f"Délka: {cur_dur_str} / Cíl: {target_str}" if self.current_lang == "cs" else f"Duration: {cur_dur_str} / Target: {target_str}"
            self.lbl_stats_duration.configure(text=t_dur)

            pct = min(1.0, max(0.0, total_duration / self.target_duration_sec))
            if self.target_prog_bar:
                self.target_prog_bar.set(pct)
            if self.lbl_target_pct:
                self.lbl_target_pct.configure(text=f"{int(pct * 100)}%")
        else:
            t_dur = f"Celková délka: {cur_dur_str}" if self.current_lang == "cs" else f"Total duration: {cur_dur_str}"
            self.lbl_stats_duration.configure(text=t_dur)

        # Footer Summary & Confirm button
        if self.current_lang == "cs":
            self.lbl_footer_summary.configure(text=f"Celkem vybráno {c_str} ({cur_dur_str})")
            self.btn_confirm.configure(text=f"🚀 Sestříhat {c_str}")
        else:
            self.lbl_footer_summary.configure(text=f"Total {sel_count} clips selected ({cur_dur_str})")
            self.btn_confirm.configure(text=f"🚀 Export {sel_count} clips")

    # -------------------------------------------------------------------------
    # Confirmation & Cancellation
    # -------------------------------------------------------------------------

    def _on_confirm_click(self):
        selected_segments = [
            self.all_segments[idx]
            for idx, var in enumerate(self._segment_vars)
            if var.get()
        ]

        if not selected_segments:
            from tkinter import messagebox
            t_w = "Žádný výběr" if self.current_lang == "cs" else "No Selection"
            m_w = "Vyberte prosím alespoň 1 moment pro sestříhání videa." if self.current_lang == "cs" else "Please select at least 1 moment to export."
            messagebox.showwarning(t_w, m_w)
            return

        self._cleanup()
        if self.on_confirm:
            self.on_confirm(selected_segments)
        self.destroy()

    def _on_cancel_click(self):
        self._cleanup()
        if self.on_cancel:
            self.on_cancel()
        self.destroy()

    def _cleanup(self):
        self._closing = True
        self._stop_playback()
