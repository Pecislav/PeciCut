"""
audio_analyzer.py - Audio track extraction, metadata inspection, and loudness/hype analysis.

This module provides high-performance, memory-efficient audio analysis for long video files
(2 to 6+ hours) using FFmpeg streaming and NumPy RMS calculation. It avoids loading gigabytes
of uncompressed PCM into RAM by streaming 16kHz mono audio in small windows.
"""

from __future__ import annotations

import json
import math
import platform
import subprocess
import threading
from fractions import Fraction
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from ffmpeg_utils import find_binary


def get_video_metadata(video_path: Path | str) -> Dict:
    """
    Inspects video and audio streams using ffprobe.
    
    Returns a dictionary containing:
      - duration: total duration in seconds (float)
      - fps: frame rate (float, e.g. 60.0, 59.94, 29.97, 24.0)
      - fps_str: string representation of fps (e.g. "60/1", "60000/1001")
      - width: video width (int)
      - height: video height (int)
      - video_codec: name of video codec (str)
      - audio_tracks: list of dicts describing each audio stream
    """
    video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(f"Video soubor nenalezen: {video_path}")

    ffprobe = find_binary("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe nebyl nalezen v systému ani ve složce aplikace.")

    cmd = [
        str(ffprobe),
        "-v", "error",
        "-show_entries", "format=duration",
        "-show_entries", (
            "stream=index,codec_type,codec_name,width,height,r_frame_rate,"
            "avg_frame_rate,channels,channel_layout,sample_rate:stream_tags=title,language,handler_name"
        ),
        "-of", "json",
        str(video_path)
    ]

    startupinfo = None
    cflags = 0
    if platform.system().lower() == "windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        cflags = subprocess.CREATE_NO_WINDOW

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        startupinfo=startupinfo,
        creationflags=cflags,
        check=True
    )

    data = json.loads(result.stdout)
    format_info = data.get("format", {})
    streams = data.get("streams", [])

    # Duration
    duration = float(format_info.get("duration", 0.0))

    # Video details
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    fps = 30.0
    fps_str = "30/1"
    width = 1920
    height = 1080
    video_codec = "unknown"

    if video_streams:
        v0 = video_streams[0]
        width = int(v0.get("width", 1920) or 1920)
        height = int(v0.get("height", 1080) or 1080)
        video_codec = v0.get("codec_name", "unknown")

        r_fps = v0.get("r_frame_rate", "30/1")
        avg_fps = v0.get("avg_frame_rate", "30/1")

        # Prefer r_frame_rate if valid, fallback to avg_frame_rate
        for cand in [r_fps, avg_fps]:
            try:
                frac = Fraction(cand)
                val = float(frac)
                if 5.0 <= val <= 240.0:
                    fps = val
                    fps_str = cand
                    break
            except Exception:
                continue

    # Audio tracks
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    audio_tracks = []

    for a_idx, s in enumerate(audio_streams):
        stream_index = s.get("index")
        codec = s.get("codec_name", "unknown")
        channels = s.get("channels", 2)
        channel_layout = s.get("channel_layout", "stereo")
        sample_rate = s.get("sample_rate", "44100")
        tags = s.get("tags", {})
        title = tags.get("title") or tags.get("handler_name") or ""
        lang = tags.get("language") or ""

        # Construct readable label
        details = []
        if title:
            details.append(title)
        if lang and lang != "und":
            details.append(f"[{lang}]")
        details.append(f"{channel_layout or f'{channels}ch'}")
        details.append(f"{codec}")
        details.append(f"{int(sample_rate)//1000}kHz")

        label = f"Stopa {a_idx + 1}: {' - '.join(details)}"

        audio_tracks.append({
            "track_index": a_idx,            # 0-based index among audio streams (-map 0:a:N)
            "stream_index": stream_index,    # absolute stream index
            "label": label,
            "channels": channels,
            "codec": codec,
            "sample_rate": sample_rate,
            "title": title,
            "language": lang
        })

    return {
        "duration": duration,
        "fps": fps,
        "fps_str": fps_str,
        "width": width,
        "height": height,
        "video_codec": video_codec,
        "audio_tracks": audio_tracks,
    }


def format_moments_count(count: int) -> str:
    """Czech plural declension for 'moment' (1 moment, 2-4 momenty, 5+ momentů)."""
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


def analyze_audio_stream(
    video_path: Path | str,
    track_index: int = 0,
    total_duration: float = 0.0,
    threshold_db: float = -14.0,
    mode: str = "highlights",  # "highlights" nebo "remove_silence"
    padding_before: float = 4.0,
    padding_after: float = 2.0,
    window_sec: float = 0.1,   # 100ms analysis window
    progress_callback: Optional[Callable[[float, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    threads: int = 0,
) -> Optional[List[Tuple[float, float, float]]]:
    """
    Streams audio from a specific track using FFmpeg as 16kHz 16-bit mono PCM.
    Calculates RMS and dBFS per window, detects loud/hype segments, expands them
    with padding before/after, and returns raw candidate intervals.

    Args:
        video_path: Path to the video file.
        track_index: 0-based index of audio track (for -map 0:a:<track_index>).
        total_duration: Duration of video in seconds (for progress estimation).
        threshold_db: Threshold in dBFS (e.g. -14 dB for hype, -35 dB for silence cut).
        mode: "highlights" (keep loud moments) or "remove_silence" (keep everything above threshold).
        padding_before: Seconds to include before a detected moment.
        padding_after: Seconds to include after a detected moment.
        window_sec: Length of analysis window in seconds (default 0.1s = 100ms).
        progress_callback: Function accepting (percentage [0.0 - 1.0], message [str]).
        cancel_event: threading.Event to signal cancellation.
        threads: Number of CPU threads for FFmpeg (0 = automatic/all cores).

    Returns:
        List of (start_sec, end_sec) tuples or None if cancelled.
    """
    video_path = Path(video_path)
    ffmpeg = find_binary("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg nebyl nalezen.")

    sample_rate = 16000  # 16 kHz is optimal for voice / hype loudness detection
    bytes_per_sample = 2  # s16le = 2 bytes per mono sample
    samples_per_window = int(sample_rate * window_sec)
    bytes_per_window = samples_per_window * bytes_per_sample

    # FFmpeg command to decode audio track into raw s16le mono stream on stdout
    cmd = [
        str(ffmpeg),
        "-v", "error",
    ]
    if threads > 0:
        cmd.extend(["-threads", str(threads)])
    cmd.extend([
        "-i", str(video_path),
        "-map", f"0:a:{track_index}",
        "-ac", "1",
        "-ar", str(sample_rate),
        "-f", "s16le",
        "-"
    ])

    startupinfo = None
    cflags = 0
    if platform.system().lower() == "windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        cflags = subprocess.CREATE_NO_WINDOW

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        startupinfo=startupinfo,
        creationflags=cflags,
        bufsize=bytes_per_window * 32
    )

    detected_moments: List[Tuple[float, float, float]] = []
    current_start: Optional[float] = None
    current_peak_dbfs: float = -120.0
    current_time = 0.0
    last_active_time = 0.0
    hangover_sec = 0.4  # vyžaduje 400ms ticha pro rozdělení momentu (spojí slabiky a slova)

    last_reported_sec = -1.0
    chunk_count = 0

    try:
        while True:
            if cancel_event and cancel_event.is_set():
                process.kill()
                process.wait()
                return None

            if not process.stdout:
                break

            raw_bytes = process.stdout.read(bytes_per_window)
            if not raw_bytes:
                break

            actual_samples = len(raw_bytes) // bytes_per_sample
            if actual_samples == 0:
                break

            # Convert to numpy int16 array
            samples = np.frombuffer(raw_bytes[: actual_samples * bytes_per_sample], dtype=np.int16)
            
            # Root Mean Square (RMS) calculation
            # Use float64 to avoid overflow with large sums of squared int16s
            sum_sq = np.sum(samples.astype(np.float64) ** 2)
            rms = math.sqrt(sum_sq / actual_samples) if actual_samples > 0 else 0.0

            # Convert RMS to dBFS (max 0 dBFS for 32768)
            # Add small epsilon to prevent log10(0)
            if rms > 0.001:
                dbfs = 20.0 * math.log10(rms / 32768.0)
            else:
                dbfs = -120.0

            # Determine whether this window passes the criterion
            is_active = (dbfs >= threshold_db)

            chunk_duration = actual_samples / sample_rate
            window_end = current_time + chunk_duration

            if is_active:
                if current_start is None:
                    current_start = current_time
                    current_peak_dbfs = dbfs
                else:
                    if dbfs > current_peak_dbfs:
                        current_peak_dbfs = dbfs
                last_active_time = window_end
            else:
                if current_start is not None:
                    # Moment se uzavře až po souvislém tichu 0.4s (zabrání rozpadu vět na tisíce mikromomentů)
                    if (window_end - last_active_time) >= hangover_sec:
                        active_dur = last_active_time - current_start
                        if active_dur >= 0.25:  # filtruje náhodná lupnutí mikrofonu pod 250ms
                            detected_moments.append((current_start, last_active_time, current_peak_dbfs))
                        current_start = None
                        current_peak_dbfs = -120.0

            current_time = window_end
            chunk_count += 1

            # Report progress roughly every 0.5s of audio processed
            if progress_callback and (current_time - last_reported_sec >= 1.0 or actual_samples < samples_per_window):
                last_reported_sec = current_time
                fraction = (current_time / total_duration) if total_duration > 0 else 0.0
                fraction = min(max(fraction, 0.0), 1.0)
                cur_min = int(current_time // 60)
                cur_sec = int(current_time % 60)
                tot_min = int(total_duration // 60)
                tot_sec = int(total_duration % 60)
                msg = (
                    f"Analýza audia ({int(fraction * 100)}%): "
                    f"{cur_min:02d}:{cur_sec:02d} / {tot_min:02d}:{tot_sec:02d} "
                    f"| Detekováno: {format_moments_count(len(detected_moments))}"
                )
                progress_callback(fraction, msg)

        # Close any open moment at the end of the stream
        if current_start is not None:
            active_dur = last_active_time - current_start
            if active_dur >= 0.25:
                detected_moments.append((current_start, last_active_time, current_peak_dbfs))

        process.wait()

    except Exception:
        process.kill()
        process.wait()
        raise

    if cancel_event and cancel_event.is_set():
        return None

    # Apply padding around detected moments
    padded_segments: List[Tuple[float, float, float]] = []
    for start, end, peak in detected_moments:
        # Extend backwards and forwards
        p_start = max(0.0, start - padding_before)
        p_end = end + padding_after
        if total_duration > 0:
            p_end = min(total_duration, p_end)
        padded_segments.append((p_start, p_end, peak))

    return padded_segments
