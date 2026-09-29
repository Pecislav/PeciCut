"""
facecam_ai.py - Computer Vision AI for streamer facecam reaction analysis.

Detects streamer facial expressions, wide-open mouth (screams/gasps/yells),
laughter/smiles, and head/body kinetic movement in video highlights.
Uses OpenCV YuNet ONNX (ultra-fast deep learning face detector) and Haar cascades,
optimized for multiplatform performance (macOS Apple Silicon/Intel & Windows).
"""

from __future__ import annotations

import os
import ssl
import sys
import time
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np


# Default paths for bundled/cached AI models
MODELS_DIR = Path(__file__).resolve().parent / "models"
YUNET_MODEL_FILE = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SMILE_CASCADE_FILE = MODELS_DIR / "haarcascade_smile.xml"
FACE_CASCADE_FILE = MODELS_DIR / "haarcascade_frontalface_default.xml"

YUNET_DOWNLOAD_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
SMILE_DOWNLOAD_URL = (
    "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_smile.xml"
)
FACE_DOWNLOAD_URL = (
    "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml"
)


def ensure_ai_models_present(progress_callback: Optional[Callable[[str], None]] = None) -> bool:
    """
    Checks if required AI models exist in the models directory.
    If missing, downloads them automatically.
    Returns True if models are ready, False on failure.
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    models_to_check = [
        (YUNET_MODEL_FILE, YUNET_DOWNLOAD_URL, 200000),  # ~232 KB
        (SMILE_CASCADE_FILE, SMILE_DOWNLOAD_URL, 100000), # ~188 KB
        (FACE_CASCADE_FILE, FACE_DOWNLOAD_URL, 500000),  # ~930 KB
    ]

    ctx = ssl._create_unverified_context()

    for file_path, url, min_size in models_to_check:
        if not file_path.exists() or file_path.stat().st_size < min_size:
            name = file_path.name
            if progress_callback:
                progress_callback(f"Stahuji AI model {name}...")
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 PeciCut/1.0"})
                with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                    data = resp.read()
                    with open(file_path, "wb") as f:
                        f.write(data)
            except Exception as e:
                print(f"[FacecamAI] Warning: Failed to download {name}: {e}")
                # If YuNet fails but Haar cascades exist, we can still fall back
                if file_path == YUNET_MODEL_FILE and FACE_CASCADE_FILE.exists():
                    continue
                return False

    return True


class FacecamAnalyzer:
    """
    Analyzes streamer video frames for face reactions:
    - Open mouth detection (screaming, gasping, excitement)
    - Smile and laughter detection
    - Kinetic head/body movement
    """

    def __init__(self, score_threshold: float = 0.6):
        self.score_threshold = score_threshold
        self.detector_yunet: Optional[cv2.FaceDetectorYN] = None
        self.face_cascade: Optional[cv2.CascadeClassifier] = None
        self.smile_cascade: Optional[cv2.CascadeClassifier] = None
        self.current_input_size = (0, 0)
        self._init_models()

    def _init_models(self) -> None:
        """Initializes OpenCV face detector and smile cascade."""
        if YUNET_MODEL_FILE.exists() and YUNET_MODEL_FILE.stat().st_size > 100000:
            try:
                self.detector_yunet = cv2.FaceDetectorYN.create(
                    model=str(YUNET_MODEL_FILE),
                    config="",
                    input_size=(640, 360),
                    score_threshold=self.score_threshold,
                    nms_threshold=0.3,
                    top_k=2000
                )
                self.current_input_size = (640, 360)
            except Exception as e:
                print(f"[FacecamAI] YuNet init error: {e}")
                self.detector_yunet = None

        if SMILE_CASCADE_FILE.exists():
            try:
                self.smile_cascade = cv2.CascadeClassifier(str(SMILE_CASCADE_FILE))
            except Exception as e:
                print(f"[FacecamAI] Smile cascade init error: {e}")

        if FACE_CASCADE_FILE.exists():
            try:
                self.face_cascade = cv2.CascadeClassifier(str(FACE_CASCADE_FILE))
            except Exception as e:
                print(f"[FacecamAI] Face cascade init error: {e}")

    def is_ready(self) -> bool:
        """Returns True if at least one detector model is ready."""
        return self.detector_yunet is not None or self.face_cascade is not None

    def detect_primary_face(
        self, frame: np.ndarray
    ) -> Optional[Tuple[int, int, int, int, Optional[Dict[str, Tuple[int, int]]]]]:
        """
        Detects the most prominent face in the frame.
        Returns:
            (x, y, w, h, landmarks) or None if no face detected.
            Landmarks dict contains 'right_eye', 'left_eye', 'nose', 'right_mouth', 'left_mouth'.
        """
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return None

        # 1. Try YuNet deep learning detector
        if self.detector_yunet is not None:
            if self.current_input_size != (w, h):
                self.detector_yunet.setInputSize((w, h))
                self.current_input_size = (w, h)

            _, faces = self.detector_yunet.detect(frame)
            if faces is not None and len(faces) > 0:
                # Find face with highest confidence or largest area
                best_face = max(faces, key=lambda f: f[2] * f[3])
                fx, fy, fw, fh = int(best_face[0]), int(best_face[1]), int(best_face[2]), int(best_face[3])
                # Clamp coordinates to frame boundaries
                fx = max(0, min(fx, w - 1))
                fy = max(0, min(fy, h - 1))
                fw = max(1, min(fw, w - fx))
                fh = max(1, min(fh, h - fy))

                landmarks = {
                    "right_eye": (int(best_face[4]), int(best_face[5])),
                    "left_eye": (int(best_face[6]), int(best_face[7])),
                    "nose": (int(best_face[8]), int(best_face[9])),
                    "right_mouth": (int(best_face[10]), int(best_face[11])),
                    "left_mouth": (int(best_face[12]), int(best_face[13])),
                }
                return (fx, fy, fw, fh, landmarks)

        # 2. Fallback to Haar Cascade
        if self.face_cascade is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.2, minNeighbors=4, minSize=(40, 40)
            )
            if len(faces) > 0:
                best_face = max(faces, key=lambda f: f[2] * f[3])
                fx, fy, fw, fh = best_face
                return (int(fx), int(fy), int(fw), int(fh), None)

        return None

    def calculate_mouth_openness_score(
        self,
        frame_gray: np.ndarray,
        face_box: Tuple[int, int, int, int],
        landmarks: Optional[Dict[str, Tuple[int, int]]] = None
    ) -> float:
        """
        Calculates mouth openness / scream score (0.0 to 1.0).
        Open mouths (laughter, screams, gasps) form a distinct dark cavity
        in the lower third of the face with sharp contrast against lips/teeth.
        """
        fx, fy, fw, fh = face_box
        h_frame, w_frame = frame_gray.shape[:2]

        if landmarks and "right_mouth" in landmarks and "left_mouth" in landmarks:
            rm = landmarks["right_mouth"]
            lm = landmarks["left_mouth"]
            # Mouth width between corners
            mouth_w = abs(lm[0] - rm[0])
            mouth_center_x = (rm[0] + lm[0]) // 2
            mouth_center_y = (rm[1] + lm[1]) // 2

            # Define mouth ROI around mouth center
            half_w = max(15, mouth_w // 2 + 5)
            half_h = max(12, int(fh * 0.15))
            mx1 = max(0, mouth_center_x - half_w)
            mx2 = min(w_frame, mouth_center_x + half_w)
            my1 = max(0, mouth_center_y - half_h // 2)
            my2 = min(h_frame, mouth_center_y + half_h)
            mouth_roi = frame_gray[my1:my2, mx1:mx2]
        else:
            # Fallback: lower 35% of face bounding box
            my1 = max(0, fy + int(fh * 0.65))
            my2 = min(h_frame, fy + fh)
            mx1 = max(0, fx + int(fw * 0.2))
            mx2 = min(w_frame, fx + int(fw * 0.8))
            mouth_roi = frame_gray[my1:my2, mx1:mx2]

        if mouth_roi.size == 0 or mouth_roi.shape[0] < 5 or mouth_roi.shape[1] < 5:
            return 0.0

        # Contrast analysis: dark cavity inside mouth vs surrounding face
        # When mouth is wide open, dark pixels (< 30% of face median intensity) increase drastically
        median_val = float(np.median(mouth_roi))
        if median_val <= 10:
            return 0.0

        # Dark threshold for mouth interior
        dark_thresh = median_val * 0.55
        dark_ratio = np.mean(mouth_roi < dark_thresh)

        # Vertical gradient (upper lip vs cavity vs lower lip)
        grad_y = cv2.Sobel(mouth_roi, cv2.CV_64F, 0, 1, ksize=3)
        vertical_energy = float(np.mean(np.abs(grad_y)))

        # Normalize score
        cavity_score = min(1.0, dark_ratio * 3.5)
        contrast_score = min(1.0, vertical_energy / 40.0)

        return float(np.clip(0.6 * cavity_score + 0.4 * contrast_score, 0.0, 1.0))

    def calculate_smile_score(
        self, frame_gray: np.ndarray, face_box: Tuple[int, int, int, int]
    ) -> float:
        """Detects smiles/laughter using Haar smile cascade."""
        if self.smile_cascade is None:
            return 0.0

        fx, fy, fw, fh = face_box
        h_frame, w_frame = frame_gray.shape[:2]

        # Lower half of the face
        y1 = max(0, fy + int(fh * 0.5))
        y2 = min(h_frame, fy + fh)
        x1 = max(0, fx + int(fw * 0.15))
        x2 = min(w_frame, fx + int(fw * 0.85))

        roi = frame_gray[y1:y2, x1:x2]
        if roi.size == 0 or roi.shape[0] < 15 or roi.shape[1] < 15:
            return 0.0

        smiles = self.smile_cascade.detectMultiScale(
            roi, scaleFactor=1.3, minNeighbors=18, minSize=(25, 25)
        )
        if len(smiles) > 0:
            # Largest smile in mouth area
            best_s = max(smiles, key=lambda s: s[2] * s[3])
            smile_area_ratio = (best_s[2] * best_s[3]) / float(fw * fh)
            return float(np.clip(smile_area_ratio * 8.0, 0.2, 1.0))

        return 0.0

    def analyze_frame_reaction(
        self,
        frame: np.ndarray,
        prev_face_box: Optional[Tuple[int, int, int, int]] = None,
        prev_face_gray: Optional[np.ndarray] = None
    ) -> Tuple[float, Optional[Tuple[int, int, int, int]], Optional[np.ndarray]]:
        """
        Analyzes a single frame for hype/reaction intensity.
        Returns:
            (hype_score [0.0 - 1.0], face_box, face_roi_gray)
        """
        detection = self.detect_primary_face(frame)
        if detection is None:
            return (0.0, None, None)

        fx, fy, fw, fh, landmarks = detection
        face_box = (fx, fy, fw, fh)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        face_roi_gray = gray[fy:fy+fh, fx:fx+fw]

        # 1. Mouth openness / scream score
        mouth_score = self.calculate_mouth_openness_score(gray, face_box, landmarks)

        # 2. Smile / laughter score
        smile_score = self.calculate_smile_score(gray, face_box)

        # 3. Kinetic motion score (head movement / jumping)
        motion_score = 0.0
        if prev_face_box is not None:
            p_fx, p_fy, p_fw, p_fh = prev_face_box
            # Displacement of face center normalized by face width
            curr_cx, curr_cy = fx + fw / 2.0, fy + fh / 2.0
            prev_cx, prev_cy = p_fx + p_fw / 2.0, p_fy + p_fh / 2.0
            dist = np.sqrt((curr_cx - prev_cx) ** 2 + (curr_cy - prev_cy) ** 2)
            norm_dist = dist / max(1.0, float(fw))
            motion_score = float(np.clip(norm_dist * 2.5, 0.0, 1.0))

            # Inter-frame face ROI difference if sizes match
            if prev_face_gray is not None and prev_face_gray.shape == face_roi_gray.shape:
                diff = np.mean(np.abs(face_roi_gray.astype(float) - prev_face_gray.astype(float)))
                pixel_diff_score = float(np.clip(diff / 45.0, 0.0, 1.0))
                motion_score = max(motion_score, pixel_diff_score)

        # Combined hype score:
        # High expression (mouth or smile) + motion
        expression_score = max(mouth_score * 1.1, smile_score * 0.9)
        combined_score = float(np.clip(
            0.65 * expression_score + 0.35 * motion_score,
            0.0, 1.0
        ))

        return (combined_score, face_box, face_roi_gray)


def analyze_candidate_facecam_segments(
    video_path: Path | str,
    candidate_segments: List[Tuple],
    sample_fps: float = 2.0,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    cancel_event: Optional[Any] = None,
    threads: int = 0,
) -> List[Tuple]:
    """
    Pass 2 of the AI Highlight Pipeline:
    Selectively samples frames ONLY from candidate highlight intervals identified by Pass 1.
    Computes face reaction scores and calculates composite hype scores.

    Args:
        video_path: Path to the input video.
        candidate_segments: List of (start_sec, end_sec, peak_dbfs) from audio analysis.
        sample_fps: Frame sampling frequency per second of candidate segment (default 2.0 fps).
        progress_callback: Progress callback (percent 0-100, status text).
        cancel_event: Optional threading.Event to abort early.
        threads: Thread count for computer vision processing (0 = default/all).

    Returns:
        List of enriched segments: (start_sec, end_sec, peak_dbfs, face_score, composite_score)
    """
    if threads > 0:
        try:
            cv2.setNumThreads(threads)
        except Exception:
            pass

    if not candidate_segments:
        return []

    video_path = Path(video_path)
    if not video_path.exists():
        return candidate_segments

    # Initialize FacecamAnalyzer
    analyzer = FacecamAnalyzer()
    if not analyzer.is_ready():
        print("[FacecamAI] Warning: Face models not available, skipping vision pass.")
        return candidate_segments

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"[FacecamAI] Could not open video: {video_path}")
        return candidate_segments

    source_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_step = max(1, int(round(source_fps / sample_fps)))
    time_step = frame_step / source_fps

    total_segments = len(candidate_segments)
    enriched_results: List[Tuple] = []

    # Calculate audio peak range for normalization
    audio_peaks = [s[2] if len(s) >= 3 else -20.0 for s in candidate_segments]
    min_audio = min(audio_peaks) if audio_peaks else -40.0
    max_audio = max(audio_peaks) if audio_peaks else 0.0
    audio_range = max(1.0, max_audio - min_audio)

    for seg_idx, seg in enumerate(candidate_segments):
        if cancel_event and cancel_event.is_set():
            break

        start_sec = seg[0]
        end_sec = seg[1]
        audio_peak = seg[2] if len(seg) >= 3 else -20.0

        if progress_callback:
            pct = (seg_idx / max(1, total_segments)) * 100.0
            progress_callback(
                pct,
                f"Facecam AI analýza: moment {seg_idx + 1}/{total_segments} ({start_sec:.1f}s - {end_sec:.1f}s)..."
            )

        # Seek to start time
        start_frame_idx = int(start_sec * source_fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame_idx)

        current_time = start_sec
        prev_box = None
        prev_gray = None
        face_scores = []

        while current_time < end_sec:
            if cancel_event and cancel_event.is_set():
                break

            ret, frame = cap.read()
            if not ret or frame is None:
                break

            # Resize frame to standard 640x360 for consistent and fast AI detection
            h, w = frame.shape[:2]
            if w > 640 or h > 360:
                scale = 640.0 / max(w, 1)
                new_w = 640
                new_h = int(round(h * scale))
                frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

            score, face_box, face_gray = analyzer.analyze_frame_reaction(
                frame, prev_box, prev_gray
            )
            if face_box is not None:
                face_scores.append(score)
                prev_box = face_box
                prev_gray = face_gray

            # Skip ahead by frame_step
            current_time += time_step
            next_frame_idx = int(current_time * source_fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, next_frame_idx)

        # Calculate representative face score for this segment
        # We value the peak reaction moment within the segment heavily (80% peak, 20% average)
        if face_scores:
            peak_face = float(np.max(face_scores))
            avg_face = float(np.mean(face_scores))
            seg_face_score = round(0.75 * peak_face + 0.25 * avg_face, 2)
        else:
            seg_face_score = 0.0

        # Normalize audio score to [0.0, 1.0]
        norm_audio_score = float(np.clip((audio_peak - min_audio) / audio_range, 0.0, 1.0))

        # Composite score:
        # If face reaction is detected, it contributes 50% to ranking priority!
        # If no face is visible in that segment, audio determines the score.
        if seg_face_score > 0.05:
            composite_score = round(0.5 * norm_audio_score + 0.5 * seg_face_score, 3)
        else:
            composite_score = round(norm_audio_score * 0.7, 3)

        enriched_results.append((
            round(start_sec, 2),
            round(end_sec, 2),
            round(audio_peak, 1),
            seg_face_score,
            composite_score
        ))

    cap.release()

    if progress_callback:
        progress_callback(100.0, "Facecam AI analýza dokončena.")

    return enriched_results
