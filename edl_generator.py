"""
edl_generator.py - CMX 3600 standard Edit Decision List (EDL) generator.

Generates industry-standard CMX 3600 EDL files with frame-accurate timecodes
(HH:MM:SS:FF) for direct import into DaVinci Resolve, Adobe Premiere Pro,
and Final Cut Pro.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import List, Tuple


def seconds_to_timecode(seconds: float, fps: float) -> str:
    """
    Converts a timestamp in seconds to standard SMPTE timecode (HH:MM:SS:FF).
    
    Args:
        seconds: Time offset in seconds.
        fps: Video frame rate (e.g. 24, 25, 29.97, 30, 50, 59.94, 60).

    Returns:
        Formatted timecode string 'HH:MM:SS:FF'.
    """
    if seconds < 0:
        seconds = 0.0

    nominal_fps = int(round(fps))
    if nominal_fps <= 0:
        nominal_fps = 30

    total_frames = int(round(seconds * fps))
    frames_per_hour = 3600 * nominal_fps
    frames_per_minute = 60 * nominal_fps

    hours = total_frames // frames_per_hour
    remainder = total_frames % frames_per_hour

    minutes = remainder // frames_per_minute
    remainder = remainder % frames_per_minute

    secs = remainder // nominal_fps
    frame = remainder % nominal_fps

    return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frame:02d}"


def timecode_to_frames(timecode: str, fps: float) -> int:
    """
    Parses a timecode string 'HH:MM:SS:FF' into total frames.
    """
    parts = timecode.strip().split(":")
    if len(parts) != 4:
        raise ValueError(f"Neplatný formát timecode: {timecode}")

    h, m, s, f = [int(p) for p in parts]
    nominal_fps = int(round(fps))
    return (h * 3600 * nominal_fps) + (m * 60 * nominal_fps) + (s * nominal_fps) + f


def frames_to_timecode(total_frames: int, fps: float) -> str:
    """
    Converts frame count to 'HH:MM:SS:FF'.
    """
    nominal_fps = int(round(fps))
    frames_per_hour = 3600 * nominal_fps
    frames_per_minute = 60 * nominal_fps

    hours = total_frames // frames_per_hour
    remainder = total_frames % frames_per_hour

    minutes = remainder // frames_per_minute
    remainder = remainder % frames_per_minute

    secs = remainder // nominal_fps
    frame = remainder % nominal_fps

    return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frame:02d}"


def generate_cmx3600_edl(
    segments: List[Tuple[float, float]],
    video_source_path: Path | str,
    output_edl_path: Path | str,
    fps: float = 30.0,
    title: str = "AUTOCLIP_HIGHLIGHTS",
    record_start_tc: str = "01:00:00:00"
) -> Path:
    """
    Generates a CMX 3600 standard EDL file for DaVinci Resolve and Premiere Pro.

    Args:
        segments: List of (start_sec, end_sec) tuples.
        video_source_path: Path to the original video file.
        output_edl_path: Destination path for the .edl file.
        fps: Source video frame rate.
        title: Project title written in header.
        record_start_tc: Initial timecode of the timeline (default 01:00:00:00).

    Returns:
        Path to the generated EDL file.
    """
    video_source = Path(video_source_path)
    output_edl = Path(output_edl_path)
    output_edl.parent.mkdir(parents=True, exist_ok=True)

    clip_name = video_source.name

    # Header conforming to CMX 3600 standard
    lines = [
        f"TITLE:   {title[:32].upper()}",
        "FCM:     NON-DROP FRAME",
        ""
    ]

    current_record_frames = timecode_to_frames(record_start_tc, fps)

    event_index = 1
    for seg in segments:
        start_sec, end_sec = seg[0], seg[1]
        duration_sec = end_sec - start_sec
        if duration_sec <= 0.01:
            continue

        src_in_frames = int(round(start_sec * fps))
        src_out_frames = int(round(end_sec * fps))

        if src_out_frames <= src_in_frames:
            src_out_frames = src_in_frames + 1

        seg_frames = src_out_frames - src_in_frames

        src_in_tc = frames_to_timecode(src_in_frames, fps)
        src_out_tc = frames_to_timecode(src_out_frames, fps)

        rec_in_tc = frames_to_timecode(current_record_frames, fps)
        rec_out_tc = frames_to_timecode(current_record_frames + seg_frames, fps)

        current_record_frames += seg_frames

        # Standard CMX format:
        # Event Reel Track Trans SrcIn SrcOut RecIn RecOut
        # AA/V indicates both stereo audio and video cuts
        event_num_str = f"{event_index:03d}" if event_index < 1000 else f"{event_index:04d}"
        lines.append(f"{event_num_str}  AX       AA/V  C        {src_in_tc} {src_out_tc} {rec_in_tc} {rec_out_tc}")
        
        # Link comment recognized by DaVinci Resolve and Adobe Premiere Pro
        lines.append(f"* FROM CLIP NAME: {clip_name}")
        lines.append("")

        event_index += 1

    content = "\r\n".join(lines)  # CRLF for maximum NLE compatibility
    output_edl.write_text(content, encoding="utf-8")
    return output_edl
