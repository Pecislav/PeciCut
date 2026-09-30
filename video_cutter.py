"""
video_cutter.py - Segment merging logic, target duration limitation, and high-speed lossless FFmpeg video cutting.

Features:
- Intelligent segment merging (combines nearby clips within min_gap threshold).
- Target duration limitation (ranks clips by loudness/hype score and selects the best moments).
- Fast lossless stream-copy video export using FFmpeg concat demuxer (-c copy).
- Preserves all multi-track audio channels (-map 0).
- Progress callbacks and graceful cancellation.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ffmpeg_utils import find_binary


def merge_overlapping_segments(
    segments: List[Tuple],
    min_gap: float = 2.0,
    min_duration: float = 0.5
) -> List[Tuple]:
    """
    Sorts and merges segments that overlap or are separated by less than min_gap seconds.
    Filters out any segment shorter than min_duration seconds.
    Handles both 2-tuples (start, end) and 3-tuples (start, end, peak_dbfs).

    Args:
        segments: Raw list of (start_seconds, end_seconds, [peak_dbfs]).
        min_gap: Maximum gap in seconds between segments to merge into one continuous clip.
        min_duration: Minimum duration of a segment in seconds to keep.

    Returns:
        Consolidated and sorted list of tuples (retaining peak_dbfs if provided).
    """
    if not segments:
        return []

    sorted_segs = sorted(segments, key=lambda s: s[0])
    merged: List[List[float]] = []

    for item in sorted_segs:
        start, end = item[0], item[1]
        peak = item[2] if len(item) >= 3 else 0.0

        if end <= start:
            continue

        if not merged:
            merged.append([start, end, peak])
        else:
            prev_start, prev_end, prev_peak = merged[-1]
            if start <= (prev_end + min_gap):
                merged[-1][1] = max(prev_end, end)
                merged[-1][2] = max(prev_peak, peak)
            else:
                merged.append([start, end, peak])

    filtered_results = []
    for m in merged:
        s, e, p = m[0], m[1], m[2]
        if (e - s) >= min_duration:
            if any(len(item) >= 3 for item in segments):
                filtered_results.append((round(s, 2), round(e, 2), round(p, 1)))
            else:
                filtered_results.append((round(s, 2), round(e, 2)))

    return filtered_results


def limit_segments_to_target_duration(
    segments: List[Tuple],
    max_duration_sec: Optional[float] = None
) -> List[Tuple]:
    """
    Limits the total duration of highlight segments to max_duration_sec by prioritizing
    the most energetic / loudest hype moments (highest peak dBFS).

    Args:
        segments: List of (start, end, [peak_dbfs]) tuples.
        max_duration_sec: Target maximum duration in seconds (or None / <= 0 for unlimited).

    Returns:
        Filtered and chronologically sorted list of (start, end) tuples.
    """
    if not segments or not max_duration_sec or max_duration_sec <= 0:
        return [(round(s[0], 2), round(s[1], 2)) for s in segments]

    total_current = sum(s[1] - s[0] for s in segments)
    if total_current <= max_duration_sec:
        return [(round(s[0], 2), round(s[1], 2)) for s in segments]

    # Rank segments by composite AI hype score (index 4) or loudness (peak dBFS, index 2) descending
    def rank_key(s):
        if len(s) >= 5:
            return s[4]  # composite_score (AI Facecam + Audio Hype)
        if len(s) >= 3:
            return s[2]  # peak dBFS (higher is louder)
        return s[1] - s[0]  # fallback to duration

    ranked = sorted(segments, key=rank_key, reverse=True)

    selected: List[Tuple[float, float]] = []
    accumulated_sec = 0.0

    for item in ranked:
        s, e = item[0], item[1]
        dur = e - s
        if accumulated_sec + dur <= max_duration_sec:
            selected.append((s, e))
            accumulated_sec += dur
        elif accumulated_sec < max_duration_sec:
            remaining = max_duration_sec - accumulated_sec
            if remaining >= 2.0:
                selected.append((s, s + remaining))
                accumulated_sec += remaining
            break

    # Re-sort chronologically by start timestamp so timeline flows naturally
    selected_chronological = sorted(selected, key=lambda s: s[0])

    # Merge any segments that might now touch or overlap
    return merge_overlapping_segments(selected_chronological, min_gap=1.5, min_duration=0.5)


def calculate_cut_statistics(
    original_duration: float,
    segments: List[Tuple]
) -> Dict[str, Any]:
    """
    Calculates summary statistics of the cut segments.
    """
    total_kept = sum(seg[1] - seg[0] for seg in segments)
    total_removed = max(0.0, original_duration - total_kept)
    percent_reduced = (total_removed / original_duration * 100.0) if original_duration > 0 else 0.0

    def format_sec(sec: float) -> str:
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        if h > 0:
            return f"{h}h {m:02d}m {s:02d}s"
        return f"{m}m {s:02d}s"

    return {
        "original_duration_sec": original_duration,
        "kept_duration_sec": total_kept,
        "removed_duration_sec": total_removed,
        "percent_reduced": percent_reduced,
        "segment_count": len(segments),
        "original_str": format_sec(original_duration),
        "kept_str": format_sec(total_kept),
        "removed_str": format_sec(total_removed),
    }


def cut_video_lossless(
    input_video_path: Path | str,
    segments: List[Tuple],
    output_video_path: Path | str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    threads: int = 0,
) -> Optional[Path]:
    """
    Losslessly cuts and concatenates video segments using FFmpeg concat demuxer.
    Preserves all video and audio tracks without re-encoding (-c copy).

    Args:
        input_video_path: Path to the original video file.
        segments: Merged list of (start_sec, end_sec) tuples.
        output_video_path: Final destination for the merged video file.
        progress_callback: Callback reporting (percentage [0.0 - 1.0], message [str]).
        cancel_event: Threading event to support immediate cancellation.
        threads: Number of CPU threads for FFmpeg (0 = automatic/all cores).

    Returns:
        Path to output file if successful, or None if cancelled or empty.
    """
    input_path = Path(input_video_path)
    output_path = Path(output_video_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not segments:
        raise ValueError("Žádné segmenty ke střihu nebyly nalezeny.")

    ffmpeg = find_binary("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg nebyl nalezen v systému ani ve složce aplikace.")

    total_segments = len(segments)
    ext = input_path.suffix if input_path.suffix else ".mp4"

    # Create temporary directory for chunks
    temp_dir = Path(tempfile.mkdtemp(prefix="autoclip_chunks_"))
    temp_files: List[Path] = []
    concat_list_file = temp_dir / "concat_list.txt"

    startupinfo = None
    if platform.system().lower() == "windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    try:
        # Step 1: Losslessly extract each segment chunk
        for idx, seg in enumerate(segments, start=1):
            if cancel_event and cancel_event.is_set():
                return None

            start_sec, end_sec = seg[0], seg[1]
            chunk_filename = f"chunk_{idx:04d}{ext}"
            chunk_path = temp_dir / chunk_filename
            temp_files.append(chunk_path)

            duration = end_sec - start_sec

            cut_cmd = [
                str(ffmpeg),
                "-y",
            ]
            if threads > 0:
                cut_cmd.extend(["-threads", str(threads)])
            cut_cmd.extend([
                "-ss", f"{start_sec:.3f}",
                "-i", str(input_path),
                "-t", f"{duration:.3f}",
                "-c", "copy",
                "-map", "0",
                "-avoid_negative_ts", "make_zero",
                str(chunk_path)
            ])

            process = subprocess.Popen(
                cut_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo
            )

            while process.poll() is None:
                if cancel_event and cancel_event.is_set():
                    process.kill()
                    process.wait()
                    return None
                time.sleep(0.05)

            if process.returncode != 0:
                stderr_text = process.stderr.read().decode("utf-8", errors="ignore")
                fallback_cmd = [
                    str(ffmpeg),
                    "-y",
                ]
                if threads > 0:
                    fallback_cmd.extend(["-threads", str(threads)])
                fallback_cmd.extend([
                    "-ss", f"{start_sec:.3f}",
                    "-i", str(input_path),
                    "-t", f"{duration:.3f}",
                    "-c:v", "copy",
                    "-c:a", "copy",
                    "-avoid_negative_ts", "make_zero",
                    str(chunk_path)
                ])
                fb_process = subprocess.run(fallback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
                if fb_process.returncode != 0:
                    raise RuntimeError(f"Chyba při bezztrátovém střihu segmentu {idx}/{total_segments}:\n{stderr_text}")

            if progress_callback:
                fraction = 0.85 * (idx / total_segments)
                progress_callback(
                    fraction,
                    f"Rychlý bezztrátový střih: segment {idx}/{total_segments} ({int(fraction * 100)}%)"
                )

        if cancel_event and cancel_event.is_set():
            return None

        # Step 2: Write concat list with relative paths
        with open(concat_list_file, "w", encoding="utf-8") as f:
            for chunk_path in temp_files:
                f.write(f"file '{chunk_path.name}'\n")

        if progress_callback:
            progress_callback(0.88, "Spojování segmentů do finálního videa (FFmpeg concat)...")

        # Step 3: Concat chunks losslessly
        concat_cmd = [
            str(ffmpeg),
            "-y",
        ]
        if threads > 0:
            concat_cmd.extend(["-threads", str(threads)])
        concat_cmd.extend([
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list_file.name),
            "-c", "copy",
            "-movflags", "+faststart",
            str(output_path.resolve())
        ])

        concat_process = subprocess.Popen(
            concat_cmd,
            cwd=str(temp_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo
        )

        while concat_process.poll() is None:
            if cancel_event and cancel_event.is_set():
                concat_process.kill()
                concat_process.wait()
                return None
            time.sleep(0.05)

        if concat_process.returncode != 0:
            err_msg = concat_process.stderr.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Chyba při spojování segmentů:\n{err_msg}")

        if progress_callback:
            progress_callback(1.0, f"Hotovo! Video uloženo: {output_path.name}")

        return output_path

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
