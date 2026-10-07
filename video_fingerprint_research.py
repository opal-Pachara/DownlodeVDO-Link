#!/usr/bin/env python3
"""
Video Fingerprinting Robustness Research Pipeline
==================================================

PURPOSE: Research, benchmarking, and algorithm evaluation ONLY.

This script generates controlled video transformations and evaluates how
a perceptual-hashing fingerprinting algorithm responds to each transformation.

This project must NOT be used to evade, bypass, defeat, or interfere with
copyright enforcement, Rights Manager, Content ID, platform moderation,
or content-identification systems in production.

All experiments must use user-owned, public-domain, synthetic, or
explicitly-licensed research datasets.
"""

import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

INPUT_FILE = "raw_video.mp4"
OUTPUT_DIR = Path("./experiments")
MATRIX_FILE = "experiment_matrix.csv"
RESULTS_FILE = "evaluation_results.csv"
SUMMARY_FILE = "research_summary.json"

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

# Perceptual hash frame sampling settings
HASH_FRAME_COUNT = 16       # Number of frames to sample for fingerprinting
HASH_FRAME_SIZE = "16x16"   # Thumbnail size for perceptual hash
HASH_AUDIO_SAMPLES = 8000   # Number of audio samples for audio fingerprint


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class ExperimentSpec:
    """Specification for a single transformation experiment."""
    experiment_id: str
    source_file: str
    transformation_category: str
    transformation_parameters: str
    output_file: str
    ffmpeg_command: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    codec: str = ""
    audio_present: bool = True
    metadata_present: bool = True


@dataclass
class EvaluationResult:
    """Result from fingerprint comparison."""
    experiment_id: str
    transformation: str
    similarity_score: float = 0.0
    detection: str = "N/A"
    confidence: float = 0.0
    processing_time_ms: float = 0.0
    false_negative: bool = False
    false_positive: bool = False


# ---------------------------------------------------------------------------
# Utility: Probe Video
# ---------------------------------------------------------------------------

def probe_video(filepath: str) -> dict:
    """Extract video metadata using ffprobe."""
    cmd = [
        FFPROBE, "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        filepath
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"  [WARN] Could not probe {filepath}: {e}")
        return {}


def get_video_info(filepath: str) -> dict:
    """Get simplified video info."""
    info = probe_video(filepath)
    result = {
        "duration": 0.0, "width": 0, "height": 0,
        "fps": 0.0, "codec": "", "audio_present": False
    }
    if not info:
        return result

    fmt = info.get("format", {})
    result["duration"] = float(fmt.get("duration", 0))

    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            result["width"] = int(stream.get("width", 0))
            result["height"] = int(stream.get("height", 0))
            result["codec"] = stream.get("codec_name", "")
            # Parse FPS
            r_frame_rate = stream.get("r_frame_rate", "0/1")
            try:
                num, den = r_frame_rate.split("/")
                result["fps"] = round(float(num) / float(den), 2)
            except (ValueError, ZeroDivisionError):
                result["fps"] = 0.0
        elif stream.get("codec_type") == "audio":
            result["audio_present"] = True

    return result


def file_hash(filepath: str, algo: str = "sha256") -> str:
    """Compute file hash."""
    h = hashlib.new(algo)
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# FFmpeg Runner
# ---------------------------------------------------------------------------

def run_ffmpeg(cmd: list[str], label: str = "") -> bool:
    """Run an FFmpeg command and return success status."""
    full_cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "warning"] + cmd
    cmd_str = " ".join(full_cmd)
    print(f"  → {label or 'Running'}: {cmd_str[:120]}...")
    try:
        subprocess.run(full_cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] {label}: {e.stderr[:300] if e.stderr else e}")
        return False


# ---------------------------------------------------------------------------
# Perceptual Hash Fingerprinting (Research Implementation)
# ---------------------------------------------------------------------------

def extract_frame_hashes(filepath: str, num_frames: int = HASH_FRAME_COUNT) -> list[str]:
    """
    Extract perceptual hashes from sampled video frames.
    
    This is a simplified research fingerprint based on average-hash (aHash):
    - Sample N evenly-spaced frames
    - Scale each to a small thumbnail
    - Convert to grayscale
    - Compute average pixel intensity
    - Generate a binary hash based on pixel > average
    """
    info = get_video_info(filepath)
    duration = info["duration"]
    if duration <= 0:
        return []

    hashes = []
    for i in range(num_frames):
        timestamp = (i + 0.5) * duration / num_frames
        # Extract a single frame as raw grayscale pixels
        cmd = [
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{timestamp:.3f}",
            "-i", filepath,
            "-frames:v", "1",
            "-vf", f"scale={HASH_FRAME_SIZE},format=gray",
            "-f", "rawvideo",
            "-pix_fmt", "gray",
            "pipe:1"
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, check=True)
            pixels = list(result.stdout)
            if not pixels:
                continue
            avg = sum(pixels) / len(pixels)
            bits = "".join("1" if p > avg else "0" for p in pixels)
            # Convert binary string to hex hash
            hash_val = hex(int(bits, 2))[2:].zfill(len(bits) // 4)
            hashes.append(hash_val)
        except subprocess.CalledProcessError:
            continue

    return hashes


def hamming_distance(h1: str, h2: str) -> int:
    """Compute Hamming distance between two hex hash strings."""
    if len(h1) != len(h2):
        # Pad shorter hash
        max_len = max(len(h1), len(h2))
        h1 = h1.zfill(max_len)
        h2 = h2.zfill(max_len)
    
    b1 = int(h1, 16)
    b2 = int(h2, 16)
    xor = b1 ^ b2
    return bin(xor).count("1")


def compute_similarity(hashes_original: list[str], hashes_test: list[str]) -> float:
    """
    Compute similarity score between two sets of frame hashes.
    
    Uses best-match alignment: for each frame hash in the test set,
    find the closest match in the original set. This provides robustness
    against temporal shifts.
    
    Returns a score from 0.0 (completely different) to 1.0 (identical).
    """
    if not hashes_original or not hashes_test:
        return 0.0

    hash_bits = len(hashes_original[0]) * 4  # bits in each hash
    if hash_bits == 0:
        return 0.0

    total_similarity = 0.0
    for test_hash in hashes_test:
        best_match = 0.0
        for orig_hash in hashes_original:
            dist = hamming_distance(orig_hash, test_hash)
            sim = 1.0 - (dist / hash_bits)
            best_match = max(best_match, sim)
        total_similarity += best_match

    return total_similarity / len(hashes_test)


# ---------------------------------------------------------------------------
# Layer 1: Temporal Transformations
# ---------------------------------------------------------------------------

def generate_temporal_experiments(input_file: str, output_dir: Path,
                                  src_info: dict) -> list[ExperimentSpec]:
    """Generate temporal transformation variants."""
    experiments = []
    cat = "temporal"
    dur = src_info["duration"]

    # --- Trim beginning ---
    for trim_sec in [0.5, 1.0, 1.5, 2.0]:
        if trim_sec >= dur:
            continue
        exp_id = f"temporal_trim_start_{trim_sec}s"
        out = str(output_dir / cat / f"temporal_trim_start_{trim_sec}s.mp4")
        cmd = ["-ss", str(trim_sec), "-i", input_file, "-c", "copy", out]
        spec = ExperimentSpec(
            experiment_id=exp_id,
            source_file=input_file,
            transformation_category=cat,
            transformation_parameters=json.dumps({"trim_start_seconds": trim_sec}),
            output_file=out,
            ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
        )
        if run_ffmpeg(cmd, exp_id):
            experiments.append(spec)

    # --- Trim ending ---
    for trim_sec in [0.5, 1.0, 1.5, 2.0]:
        new_dur = dur - trim_sec
        if new_dur <= 0:
            continue
        exp_id = f"temporal_trim_end_{trim_sec}s"
        out = str(output_dir / cat / f"temporal_trim_end_{trim_sec}s.mp4")
        cmd = ["-i", input_file, "-t", f"{new_dur:.3f}", "-c", "copy", out]
        spec = ExperimentSpec(
            experiment_id=exp_id,
            source_file=input_file,
            transformation_category=cat,
            transformation_parameters=json.dumps({"trim_end_seconds": trim_sec, "new_duration": round(new_dur, 3)}),
            output_file=out,
            ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
        )
        if run_ffmpeg(cmd, exp_id):
            experiments.append(spec)

    # --- Speed changes ---
    for speed in [0.97, 0.98, 1.02, 1.03]:
        exp_id = f"temporal_speed_{speed}x"
        out = str(output_dir / cat / f"temporal_speed_{speed}x.mp4")
        atempo = 1.0 / speed  # Inverse for audio tempo
        # Clamp atempo to FFmpeg's valid range [0.5, 100.0]
        atempo = max(0.5, min(100.0, atempo))
        vf = f"setpts={1.0/speed}*PTS"
        af = f"atempo={atempo:.6f}"
        cmd = ["-i", input_file, "-vf", vf, "-af", af, "-r", str(src_info["fps"]), out]
        spec = ExperimentSpec(
            experiment_id=exp_id,
            source_file=input_file,
            transformation_category=cat,
            transformation_parameters=json.dumps({"speed_factor": speed}),
            output_file=out,
            ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
        )
        if run_ffmpeg(cmd, exp_id):
            experiments.append(spec)

    return experiments


# ---------------------------------------------------------------------------
# Layer 2: Spatial Transformations
# ---------------------------------------------------------------------------

def generate_spatial_experiments(input_file: str, output_dir: Path,
                                 src_info: dict) -> list[ExperimentSpec]:
    """Generate spatial transformation variants."""
    experiments = []
    cat = "spatial"
    w, h = src_info["width"], src_info["height"]

    # --- Percentage crops ---
    for pct in [5, 10, 15]:
        exp_id = f"spatial_crop_{pct}pct"
        out = str(output_dir / cat / f"spatial_crop_{pct}pct.mp4")
        cw = int(w * (1 - pct / 100))
        ch = int(h * (1 - pct / 100))
        # Ensure even dimensions
        cw = cw - (cw % 2)
        ch = ch - (ch % 2)
        vf = f"crop={cw}:{ch}"
        cmd = ["-i", input_file, "-vf", vf, out]
        spec = ExperimentSpec(
            experiment_id=exp_id,
            source_file=input_file,
            transformation_category=cat,
            transformation_parameters=json.dumps({
                "crop_percent": pct,
                "crop_width": cw, "crop_height": ch,
                "original_width": w, "original_height": h
            }),
            output_file=out,
            ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
        )
        if run_ffmpeg(cmd, exp_id):
            experiments.append(spec)

    # --- Center crop (square) ---
    side = min(w, h)
    side = side - (side % 2)
    exp_id = "spatial_center_crop"
    out = str(output_dir / cat / "spatial_center_crop.mp4")
    vf = f"crop={side}:{side}"
    cmd = ["-i", input_file, "-vf", vf, out]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({"center_crop_side": side}),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    # --- Aspect ratio 16:9 → 9:16 ---
    exp_id = "spatial_aspect_9x16"
    out = str(output_dir / cat / "spatial_aspect_9x16.mp4")
    # Crop center to 9:16 ratio
    target_ratio = 9 / 16
    if w / h > target_ratio:
        new_w = int(h * target_ratio)
        new_w = new_w - (new_w % 2)
        vf = f"crop={new_w}:{h},setsar=1"
    else:
        new_h = int(w / target_ratio)
        new_h = new_h - (new_h % 2)
        vf = f"crop={w}:{new_h},setsar=1"
    cmd = ["-i", input_file, "-vf", vf, out]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({"aspect_ratio": "9:16", "filter": vf}),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    # --- Scale to 720p ---
    exp_id = "spatial_scale_720p"
    out = str(output_dir / cat / "spatial_scale_720p.mp4")
    vf = "scale=-2:720"
    cmd = ["-i", input_file, "-vf", vf, out]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({"scale": "720p"}),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    # --- Scale to 1080p ---
    exp_id = "spatial_scale_1080p"
    out = str(output_dir / cat / "spatial_scale_1080p.mp4")
    vf = "scale=-2:1080"
    cmd = ["-i", input_file, "-vf", vf, out]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({"scale": "1080p"}),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    return experiments


# ---------------------------------------------------------------------------
# Layer 3: Color Transformations
# ---------------------------------------------------------------------------

def generate_color_experiments(input_file: str, output_dir: Path,
                                src_info: dict) -> list[ExperimentSpec]:
    """Generate color transformation variants."""
    experiments = []
    cat = "color"

    # --- Contrast adjustments ---
    for direction, val in [("plus", 1.04), ("minus", 0.96)]:
        exp_id = f"color_contrast_{direction}_4pct"
        out = str(output_dir / cat / f"color_contrast_{val}.mp4")
        vf = f"eq=contrast={val}"
        cmd = ["-i", input_file, "-vf", vf, out]
        spec = ExperimentSpec(
            experiment_id=exp_id,
            source_file=input_file,
            transformation_category=cat,
            transformation_parameters=json.dumps({"contrast": val}),
            output_file=out,
            ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
        )
        if run_ffmpeg(cmd, exp_id):
            experiments.append(spec)

    # --- Saturation adjustments ---
    for direction, val in [("plus", 1.05), ("minus", 0.95)]:
        exp_id = f"color_saturation_{direction}_5pct"
        out = str(output_dir / cat / f"color_saturation_{val}.mp4")
        vf = f"eq=saturation={val}"
        cmd = ["-i", input_file, "-vf", vf, out]
        spec = ExperimentSpec(
            experiment_id=exp_id,
            source_file=input_file,
            transformation_category=cat,
            transformation_parameters=json.dumps({"saturation": val}),
            output_file=out,
            ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
        )
        if run_ffmpeg(cmd, exp_id):
            experiments.append(spec)

    # --- Brightness adjustments ---
    for direction, val in [("plus", 0.03), ("minus", -0.03)]:
        exp_id = f"color_brightness_{direction}_3pct"
        out = str(output_dir / cat / f"color_brightness_{direction}_0.03.mp4")
        vf = f"eq=brightness={val}"
        cmd = ["-i", input_file, "-vf", vf, out]
        spec = ExperimentSpec(
            experiment_id=exp_id,
            source_file=input_file,
            transformation_category=cat,
            transformation_parameters=json.dumps({"brightness": val}),
            output_file=out,
            ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
        )
        if run_ffmpeg(cmd, exp_id):
            experiments.append(spec)

    # --- Gamma variations ---
    for gamma in [0.9, 1.1]:
        exp_id = f"color_gamma_{gamma}"
        out = str(output_dir / cat / f"color_gamma_{gamma}.mp4")
        vf = f"eq=gamma={gamma}"
        cmd = ["-i", input_file, "-vf", vf, out]
        spec = ExperimentSpec(
            experiment_id=exp_id,
            source_file=input_file,
            transformation_category=cat,
            transformation_parameters=json.dumps({"gamma": gamma}),
            output_file=out,
            ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
        )
        if run_ffmpeg(cmd, exp_id):
            experiments.append(spec)

    # --- Mild sharpening ---
    exp_id = "color_sharpen_mild"
    out = str(output_dir / cat / "color_sharpen_mild.mp4")
    vf = "unsharp=5:5:0.5:5:5:0.0"
    cmd = ["-i", input_file, "-vf", vf, out]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({"sharpen": "unsharp=5:5:0.5:5:5:0.0"}),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    # --- Mild blur ---
    exp_id = "color_blur_mild"
    out = str(output_dir / cat / "color_blur_mild.mp4")
    vf = "boxblur=1:1"
    cmd = ["-i", input_file, "-vf", vf, out]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({"blur": "boxblur=1:1"}),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    # --- Combined color: contrast + saturation + brightness ---
    exp_id = "color_combined"
    out = str(output_dir / cat / "color_combined.mp4")
    vf = "eq=contrast=1.04:saturation=1.05:brightness=0.02:gamma=1.05"
    cmd = ["-i", input_file, "-vf", vf, out]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({
            "contrast": 1.04, "saturation": 1.05,
            "brightness": 0.02, "gamma": 1.05
        }),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    return experiments


# ---------------------------------------------------------------------------
# Layer 4: Audio Experiments
# ---------------------------------------------------------------------------

def generate_audio_experiments(input_file: str, output_dir: Path,
                                src_info: dict) -> list[ExperimentSpec]:
    """Generate audio transformation variants."""
    experiments = []
    cat = "audio"

    # A. Original audio (copy)
    exp_id = "audio_original"
    out = str(output_dir / cat / "audio_original.mp4")
    cmd = ["-i", input_file, "-c", "copy", out]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({"audio": "original"}),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd),
        audio_present=True
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    # B. Audio removed
    exp_id = "audio_removed"
    out = str(output_dir / cat / "audio_removed.mp4")
    cmd = ["-i", input_file, "-an", "-c:v", "copy", out]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({"audio": "removed"}),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd),
        audio_present=False
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    # C. Audio replaced with synthetic speech (Thai research narration)
    # Generate a synthetic test tone to simulate TTS (since real TTS requires
    # an external service, we use a sine sweep as a placeholder marker)
    exp_id = "audio_synthetic_speech"
    out = str(output_dir / cat / "audio_synthetic_speech.mp4")
    dur = src_info["duration"]
    # Generate a chirp signal as synthetic audio marker
    af = f"sine=frequency=440:duration={dur},volume=0.3"
    cmd = [
        "-i", input_file,
        "-f", "lavfi", "-i", f"anoisesrc=duration={dur}:color=pink:amplitude=0.02",
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-shortest", out
    ]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({
            "audio": "synthetic_speech_placeholder",
            "note": "Pink noise used as TTS placeholder; replace with actual TTS if available"
        }),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd),
        audio_present=True
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    # D. Audio replaced with royalty-free test audio (sine wave)
    exp_id = "audio_test_tone"
    out = str(output_dir / cat / "audio_test_tone.mp4")
    cmd = [
        "-i", input_file,
        "-f", "lavfi", "-i", f"sine=frequency=1000:duration={dur}",
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-shortest", out
    ]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({"audio": "1kHz_sine_tone"}),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd),
        audio_present=True
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    # E. Synthetic multi-tone test signal
    exp_id = "audio_multitone"
    out = str(output_dir / cat / "audio_multitone.mp4")
    cmd = [
        "-i", input_file,
        "-f", "lavfi", "-i",
        f"sine=frequency=440:duration={dur}",
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-af", "tremolo=f=5:d=0.5",
        "-shortest", out
    ]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({"audio": "440Hz_tremolo_synthetic"}),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd),
        audio_present=True
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    return experiments


# ---------------------------------------------------------------------------
# Layer 5: Overlay Experiments
# ---------------------------------------------------------------------------

def generate_overlay_experiments(input_file: str, output_dir: Path,
                                  src_info: dict) -> list[ExperimentSpec]:
    """Generate overlay transformation variants."""
    experiments = []
    cat = "overlay"
    w, h = src_info["width"], src_info["height"]

    # Use drawbox overlays (drawtext requires libfreetype which is not available)
    overlay_configs = {
        5: {"box_h_pct": 0.05, "color": "white@0.6"},
        10: {"box_h_pct": 0.10, "color": "white@0.5"},
        15: {"box_h_pct": 0.15, "color": "white@0.4"},
    }

    for pct, cfg in overlay_configs.items():
        exp_id = f"overlay_{pct}pct"
        out = str(output_dir / cat / f"overlay_{pct}pct.mp4")
        box_h = int(h * cfg["box_h_pct"])
        box_y = int((h - box_h) / 2)
        # Centered horizontal band covering pct% of frame height
        vf = f"drawbox=x=0:y={box_y}:w=iw:h={box_h}:color={cfg['color']}:t=fill"
        cmd = ["-i", input_file, "-vf", vf, out]
        spec = ExperimentSpec(
            experiment_id=exp_id,
            source_file=input_file,
            transformation_category=cat,
            transformation_parameters=json.dumps({
                "overlay_percent": pct, "box_height": box_h,
                "color": cfg["color"], "type": "drawbox_band"
            }),
            output_file=out,
            ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
        )
        if run_ffmpeg(cmd, exp_id):
            experiments.append(spec)

    # --- Small logo (simulated with colored rectangle, no drawtext needed) ---
    exp_id = "overlay_small_logo"
    out = str(output_dir / cat / "overlay_small_logo.mp4")
    logo_w = int(w * 0.08)
    logo_h = int(h * 0.08)
    vf = f"drawbox=x=20:y=20:w={logo_w}:h={logo_h}:color=red@0.6:t=fill"
    cmd = ["-i", input_file, "-vf", vf, out]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({
            "overlay_type": "small_logo",
            "logo_width": logo_w, "logo_height": logo_h
        }),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    # --- Semi-transparent rectangle ---
    exp_id = "overlay_semitransparent_rect"
    out = str(output_dir / cat / "overlay_semitransparent_rect.mp4")
    rect_h = int(h * 0.15)
    vf = f"drawbox=x=0:y=ih-{rect_h}:w=iw:h={rect_h}:color=black@0.4:t=fill"
    cmd = ["-i", input_file, "-vf", vf, out]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({
            "overlay_type": "semi_transparent_rectangle",
            "rect_height": rect_h, "opacity": 0.4
        }),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    # --- Full-width top banner (drawbox only, no drawtext) ---
    exp_id = "overlay_top_banner"
    out = str(output_dir / cat / "overlay_top_banner.mp4")
    banner_h = int(h * 0.1)
    vf = f"drawbox=x=0:y=0:w=iw:h={banner_h}:color=blue@0.7:t=fill"
    cmd = ["-i", input_file, "-vf", vf, out]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({
            "overlay_type": "top_banner", "banner_height": banner_h
        }),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    return experiments


# ---------------------------------------------------------------------------
# Layer 6: Metadata Experiments
# ---------------------------------------------------------------------------

def generate_metadata_experiments(input_file: str, output_dir: Path,
                                   src_info: dict) -> list[ExperimentSpec]:
    """Generate metadata transformation variants."""
    experiments = []
    cat = "metadata"

    # 1. Original metadata preserved
    exp_id = "metadata_original"
    out = str(output_dir / cat / "metadata_original.mp4")
    cmd = ["-i", input_file, "-c", "copy", out]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({"metadata": "preserved"}),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd),
        metadata_present=True
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    # 2. Metadata removed
    exp_id = "metadata_removed"
    out = str(output_dir / cat / "metadata_removed.mp4")
    cmd = ["-i", input_file, "-map_metadata", "-1", "-c", "copy", out]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({"metadata": "removed"}),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd),
        metadata_present=False
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    return experiments


# ---------------------------------------------------------------------------
# Combined Transformation Experiments
# ---------------------------------------------------------------------------

def generate_combined_experiments(input_file: str, output_dir: Path,
                                   src_info: dict) -> list[ExperimentSpec]:
    """Generate combined transformation variants."""
    experiments = []
    cat = "combined"
    w, h = src_info["width"], src_info["height"]
    dur = src_info["duration"]

    # Experiment A: 1s trim + 5% crop + contrast +4%
    exp_id = "combined_A_trim1s_crop5_contrast"
    out = str(output_dir / cat / f"{exp_id}.mp4")
    cw = int(w * 0.95)
    ch = int(h * 0.95)
    cw = cw - (cw % 2)
    ch = ch - (ch % 2)
    vf = f"crop={cw}:{ch},eq=contrast=1.04"
    cmd = ["-ss", "1", "-i", input_file, "-vf", vf, out]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({
            "trim_start": 1.0, "crop_percent": 5, "contrast": 1.04
        }),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    # Experiment B: 1s trim + 1.03x speed + 10% overlay (drawbox)
    exp_id = "combined_B_trim1s_speed103_overlay10"
    out = str(output_dir / cat / f"{exp_id}.mp4")
    overlay_box_h = int(h * 0.10)
    overlay_box_y = int((h - overlay_box_h) / 2)
    vf = (
        f"setpts={1.0/1.03}*PTS,"
        f"drawbox=x=0:y={overlay_box_y}:w=iw:h={overlay_box_h}:color=white@0.5:t=fill"
    )
    af = f"atempo={1.0/1.03:.6f}"
    cmd = ["-ss", "1", "-i", input_file, "-vf", vf, "-af", af, out]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({
            "trim_start": 1.0, "speed": 1.03, "overlay_percent": 10
        }),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd)
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    # Experiment C: 9:16 conversion + audio replacement + metadata removal
    exp_id = "combined_C_aspect916_audio_meta"
    out = str(output_dir / cat / f"{exp_id}.mp4")
    target_ratio = 9 / 16
    if w / h > target_ratio:
        new_w = int(h * target_ratio)
        new_w = new_w - (new_w % 2)
        vf = f"crop={new_w}:{h},setsar=1"
    else:
        new_h = int(w / target_ratio)
        new_h = new_h - (new_h % 2)
        vf = f"crop={w}:{new_h},setsar=1"
    cmd = [
        "-i", input_file,
        "-f", "lavfi", "-i", f"sine=frequency=1000:duration={dur}",
        "-map", "0:v", "-map", "1:a",
        "-vf", vf,
        "-c:a", "aac", "-b:a", "128k",
        "-map_metadata", "-1",
        "-shortest", out
    ]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({
            "aspect_ratio": "9:16",
            "audio": "replaced_1kHz",
            "metadata": "removed"
        }),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd),
        audio_present=True,
        metadata_present=False
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    # Experiment D: All transformations combined (drawbox overlay)
    exp_id = "combined_D_all"
    out = str(output_dir / cat / f"{exp_id}.mp4")
    cw2 = int(w * 0.90)
    ch2 = int(h * 0.90)
    cw2 = cw2 - (cw2 % 2)
    ch2 = ch2 - (ch2 % 2)
    overlay_h_d = int(h * 0.05)
    vf = (
        f"setpts={1.0/1.02}*PTS,"
        f"crop={cw2}:{ch2},"
        f"eq=contrast=1.04:saturation=1.05:brightness=0.02,"
        f"scale=-2:720,"
        f"drawbox=x=10:y=10:w=200:h={overlay_h_d}:color=white@0.4:t=fill"
    )
    af = f"atempo={1.0/1.02:.6f}"
    cmd = [
        "-ss", "0.5",
        "-i", input_file,
        "-vf", vf, "-af", af,
        "-map_metadata", "-1",
        out
    ]
    spec = ExperimentSpec(
        experiment_id=exp_id,
        source_file=input_file,
        transformation_category=cat,
        transformation_parameters=json.dumps({
            "trim_start": 0.5, "speed": 1.02,
            "crop_percent": 10, "contrast": 1.04,
            "saturation": 1.05, "brightness": 0.02,
            "scale": "720p", "overlay": "5pct_drawbox",
            "metadata": "removed"
        }),
        output_file=out,
        ffmpeg_command=" ".join([FFMPEG, "-y"] + cmd),
        metadata_present=False
    )
    if run_ffmpeg(cmd, exp_id):
        experiments.append(spec)

    return experiments


# ---------------------------------------------------------------------------
# Copy Original
# ---------------------------------------------------------------------------

def copy_original(input_file: str, output_dir: Path) -> ExperimentSpec:
    """Copy original file to experiments directory."""
    out = str(output_dir / "original" / "original.mp4")
    shutil.copy2(input_file, out)
    spec = ExperimentSpec(
        experiment_id="original",
        source_file=input_file,
        transformation_category="original",
        transformation_parameters=json.dumps({"transformation": "none"}),
        output_file=out,
        ffmpeg_command="(copy)"
    )
    return spec


# ---------------------------------------------------------------------------
# Experiment Matrix Writer
# ---------------------------------------------------------------------------

def write_experiment_matrix(experiments: list[ExperimentSpec], filepath: str):
    """Write the experiment matrix to CSV."""
    fieldnames = [
        "experiment_id", "source_file", "transformation_category",
        "transformation_parameters", "output_file", "duration",
        "width", "height", "fps", "codec", "audio_present", "metadata_present"
    ]
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for exp in experiments:
            info = get_video_info(exp.output_file) if os.path.exists(exp.output_file) else {}
            exp.duration = info.get("duration", 0.0)
            exp.width = info.get("width", 0)
            exp.height = info.get("height", 0)
            exp.fps = info.get("fps", 0.0)
            exp.codec = info.get("codec", "")
            if exp.transformation_category not in ("audio",):
                exp.audio_present = info.get("audio_present", False)
            row = {k: getattr(exp, k) for k in fieldnames}
            writer.writerow(row)


# ---------------------------------------------------------------------------
# Evaluation Pipeline
# ---------------------------------------------------------------------------

def run_evaluation(experiments: list[ExperimentSpec],
                   original_hashes: list[str]) -> list[EvaluationResult]:
    """Run perceptual hash fingerprint evaluation on all experiments."""
    results = []

    for exp in experiments:
        if not os.path.exists(exp.output_file):
            continue

        t0 = time.perf_counter()
        test_hashes = extract_frame_hashes(exp.output_file)
        similarity = compute_similarity(original_hashes, test_hashes)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Detection threshold (research parameter)
        DETECTION_THRESHOLD = 0.75
        HIGH_CONFIDENCE_THRESHOLD = 0.90
        
        detected = similarity >= DETECTION_THRESHOLD
        confidence = min(1.0, similarity / HIGH_CONFIDENCE_THRESHOLD) if detected else similarity

        result = EvaluationResult(
            experiment_id=exp.experiment_id,
            transformation=exp.transformation_category,
            similarity_score=round(similarity, 4),
            detection="DETECTED" if detected else "NOT_DETECTED",
            confidence=round(confidence, 4),
            processing_time_ms=round(elapsed_ms, 2),
            false_negative=(exp.experiment_id == "original" and not detected),
            false_positive=False  # We know all are from same source
        )
        results.append(result)

    return results


def write_evaluation_results(results: list[EvaluationResult], filepath: str):
    """Write evaluation results to CSV."""
    fieldnames = [
        "experiment_id", "transformation", "similarity_score",
        "detection", "confidence", "processing_time_ms",
        "false_negative", "false_positive"
    ]
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))


# ---------------------------------------------------------------------------
# Statistical Analysis & Plotting
# ---------------------------------------------------------------------------

def generate_statistics(results: list[EvaluationResult]) -> dict:
    """Generate statistical summary."""
    if not results:
        return {}

    scores = [r.similarity_score for r in results]
    detected = [r for r in results if r.detection == "DETECTED"]
    not_detected = [r for r in results if r.detection == "NOT_DETECTED"]

    n = len(scores)
    mean_sim = sum(scores) / n
    sorted_scores = sorted(scores)
    median_sim = sorted_scores[n // 2] if n % 2 else (sorted_scores[n // 2 - 1] + sorted_scores[n // 2]) / 2
    variance = sum((s - mean_sim) ** 2 for s in scores) / n
    std_sim = math.sqrt(variance)

    detection_rate = len(detected) / n if n > 0 else 0
    fn_rate = sum(1 for r in results if r.false_negative) / n if n > 0 else 0

    # Per-category breakdown
    categories = {}
    for r in results:
        cat = r.transformation
        if cat not in categories:
            categories[cat] = {"scores": [], "detected": 0, "total": 0}
        categories[cat]["scores"].append(r.similarity_score)
        categories[cat]["total"] += 1
        if r.detection == "DETECTED":
            categories[cat]["detected"] += 1

    cat_stats = {}
    for cat, data in categories.items():
        cat_scores = data["scores"]
        cat_n = len(cat_scores)
        cat_mean = sum(cat_scores) / cat_n
        cat_stats[cat] = {
            "detection_rate": data["detected"] / data["total"],
            "mean_similarity": round(cat_mean, 4),
            "count": cat_n
        }

    return {
        "overall": {
            "total_experiments": n,
            "detection_rate": round(detection_rate, 4),
            "mean_similarity": round(mean_sim, 4),
            "median_similarity": round(median_sim, 4),
            "std_similarity": round(std_sim, 4),
            "false_negative_rate": round(fn_rate, 4),
            "false_positive_rate": 0.0
        },
        "per_category": cat_stats
    }


def generate_plots_html(results: list[EvaluationResult], stats: dict,
                         output_dir: Path):
    """Generate an HTML file with interactive charts using Chart.js."""
    
    # Organize data by category
    categories_data = {}
    for r in results:
        cat = r.transformation
        if cat not in categories_data:
            categories_data[cat] = []
        categories_data[cat].append(r)

    # Prepare chart data
    cat_labels = list(categories_data.keys())
    cat_detection_rates = []
    cat_mean_sims = []
    for cat in cat_labels:
        items = categories_data[cat]
        detected = sum(1 for i in items if i.detection == "DETECTED")
        cat_detection_rates.append(round(detected / len(items) * 100, 1))
        cat_mean_sims.append(round(sum(i.similarity_score for i in items) / len(items) * 100, 1))

    # Individual experiment data for scatter plot
    exp_labels = [r.experiment_id for r in results]
    exp_scores = [round(r.similarity_score * 100, 1) for r in results]
    exp_colors = []
    color_map = {
        "original": "#10b981", "temporal": "#3b82f6", "spatial": "#8b5cf6",
        "color": "#f59e0b", "audio": "#ef4444", "overlay": "#ec4899",
        "metadata": "#6366f1", "combined": "#14b8a6"
    }
    for r in results:
        exp_colors.append(color_map.get(r.transformation, "#6b7280"))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Video Fingerprint Research — Results Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
  
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  
  body {{
    font-family: 'Inter', -apple-system, sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    min-height: 100vh;
    padding: 2rem;
  }}
  
  .header {{
    text-align: center;
    margin-bottom: 3rem;
  }}
  
  .header h1 {{
    font-size: 2.2rem;
    font-weight: 700;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6, #ec4899);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.5rem;
  }}
  
  .header p {{
    color: #94a3b8;
    font-size: 1rem;
  }}
  
  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1.5rem;
    margin-bottom: 3rem;
    max-width: 1200px;
    margin-left: auto;
    margin-right: auto;
  }}
  
  .stat-card {{
    background: linear-gradient(145deg, #1e293b, #1a2332);
    border: 1px solid #334155;
    border-radius: 16px;
    padding: 1.5rem;
    text-align: center;
    transition: transform 0.2s, box-shadow 0.2s;
  }}
  
  .stat-card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(59, 130, 246, 0.15);
  }}
  
  .stat-card .value {{
    font-size: 2rem;
    font-weight: 700;
    color: #3b82f6;
    display: block;
    margin-bottom: 0.3rem;
  }}
  
  .stat-card .label {{
    font-size: 0.85rem;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  
  .charts-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
    gap: 2rem;
    max-width: 1400px;
    margin: 0 auto 3rem;
  }}
  
  .chart-card {{
    background: linear-gradient(145deg, #1e293b, #1a2332);
    border: 1px solid #334155;
    border-radius: 16px;
    padding: 1.5rem;
  }}
  
  .chart-card h3 {{
    font-size: 1.1rem;
    font-weight: 600;
    color: #f1f5f9;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #334155;
  }}
  
  .chart-container {{
    position: relative;
    height: 350px;
  }}
  
  .full-width {{
    grid-column: 1 / -1;
  }}
  
  .table-container {{
    max-width: 1400px;
    margin: 0 auto;
    overflow-x: auto;
  }}
  
  table {{
    width: 100%;
    border-collapse: collapse;
    background: #1e293b;
    border-radius: 12px;
    overflow: hidden;
  }}
  
  th {{
    background: #0f172a;
    color: #94a3b8;
    font-weight: 600;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 12px 16px;
    text-align: left;
  }}
  
  td {{
    padding: 10px 16px;
    border-top: 1px solid #334155;
    font-size: 0.9rem;
  }}
  
  tr:hover td {{
    background: #1a2332;
  }}
  
  .badge {{
    display: inline-block;
    padding: 3px 10px;
    border-radius: 99px;
    font-size: 0.75rem;
    font-weight: 600;
  }}
  
  .badge-detected {{
    background: #065f46;
    color: #6ee7b7;
  }}
  
  .badge-not-detected {{
    background: #7f1d1d;
    color: #fca5a5;
  }}
  
  .footer {{
    text-align: center;
    margin-top: 3rem;
    padding: 2rem;
    color: #64748b;
    font-size: 0.85rem;
  }}
  
  .footer strong {{
    color: #94a3b8;
  }}
</style>
</head>
<body>

<div class="header">
  <h1>🔬 Video Fingerprint Research Dashboard</h1>
  <p>Perceptual Hash Robustness Analysis — Generated {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
</div>

<div class="stats-grid">
  <div class="stat-card">
    <span class="value">{stats['overall']['total_experiments']}</span>
    <span class="label">Total Experiments</span>
  </div>
  <div class="stat-card">
    <span class="value">{stats['overall']['detection_rate']*100:.1f}%</span>
    <span class="label">Detection Rate</span>
  </div>
  <div class="stat-card">
    <span class="value">{stats['overall']['mean_similarity']*100:.1f}%</span>
    <span class="label">Mean Similarity</span>
  </div>
  <div class="stat-card">
    <span class="value">{stats['overall']['median_similarity']*100:.1f}%</span>
    <span class="label">Median Similarity</span>
  </div>
  <div class="stat-card">
    <span class="value">{stats['overall']['std_similarity']*100:.1f}%</span>
    <span class="label">Std Deviation</span>
  </div>
  <div class="stat-card">
    <span class="value">{stats['overall']['false_negative_rate']*100:.1f}%</span>
    <span class="label">False Negative Rate</span>
  </div>
</div>

<div class="charts-grid">
  <div class="chart-card">
    <h3>📊 Detection Rate by Category</h3>
    <div class="chart-container">
      <canvas id="detectionChart"></canvas>
    </div>
  </div>
  
  <div class="chart-card">
    <h3>📈 Mean Similarity by Category</h3>
    <div class="chart-container">
      <canvas id="similarityChart"></canvas>
    </div>
  </div>
  
  <div class="chart-card full-width">
    <h3>🎯 Similarity Score per Experiment</h3>
    <div class="chart-container" style="height: 450px;">
      <canvas id="scatterChart"></canvas>
    </div>
  </div>
</div>

<div class="table-container">
  <h2 style="font-size: 1.3rem; margin-bottom: 1rem; color: #f1f5f9;">
    📋 Detailed Results
  </h2>
  <table>
    <thead>
      <tr>
        <th>Experiment</th>
        <th>Category</th>
        <th>Similarity</th>
        <th>Detection</th>
        <th>Confidence</th>
        <th>Time (ms)</th>
      </tr>
    </thead>
    <tbody>
"""

    for r in results:
        badge_class = "badge-detected" if r.detection == "DETECTED" else "badge-not-detected"
        html += f"""      <tr>
        <td><code>{r.experiment_id}</code></td>
        <td>{r.transformation}</td>
        <td>{r.similarity_score*100:.1f}%</td>
        <td><span class="badge {badge_class}">{r.detection}</span></td>
        <td>{r.confidence*100:.1f}%</td>
        <td>{r.processing_time_ms:.1f}</td>
      </tr>
"""

    html += f"""    </tbody>
  </table>
</div>

<div class="footer">
  <strong>Research Notice:</strong> This analysis is for research and algorithm evaluation only.
  Not intended for bypassing content-identification systems.<br>
  Generated by Video Fingerprint Research Pipeline v1.0
</div>

<script>
const catLabels = {json.dumps(cat_labels)};
const catDetectionRates = {json.dumps(cat_detection_rates)};
const catMeanSims = {json.dumps(cat_mean_sims)};
const expLabels = {json.dumps(exp_labels)};
const expScores = {json.dumps(exp_scores)};
const expColors = {json.dumps(exp_colors)};

Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = '#334155';

// Detection Rate Chart
new Chart(document.getElementById('detectionChart'), {{
  type: 'bar',
  data: {{
    labels: catLabels,
    datasets: [{{
      label: 'Detection Rate (%)',
      data: catDetectionRates,
      backgroundColor: ['#10b981', '#3b82f6', '#8b5cf6', '#f59e0b', '#ef4444', '#ec4899', '#6366f1', '#14b8a6'],
      borderRadius: 8,
      borderSkipped: false,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
    }},
    scales: {{
      y: {{
        beginAtZero: true,
        max: 100,
        ticks: {{ callback: v => v + '%' }}
      }}
    }}
  }}
}});

// Similarity Chart
new Chart(document.getElementById('similarityChart'), {{
  type: 'bar',
  data: {{
    labels: catLabels,
    datasets: [{{
      label: 'Mean Similarity (%)',
      data: catMeanSims,
      backgroundColor: ['#10b98180', '#3b82f680', '#8b5cf680', '#f59e0b80', '#ef444480', '#ec489980', '#6366f180', '#14b8a680'],
      borderColor: ['#10b981', '#3b82f6', '#8b5cf6', '#f59e0b', '#ef4444', '#ec4899', '#6366f1', '#14b8a6'],
      borderWidth: 2,
      borderRadius: 8,
      borderSkipped: false,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
    }},
    scales: {{
      y: {{
        beginAtZero: true,
        max: 100,
        ticks: {{ callback: v => v + '%' }}
      }}
    }}
  }}
}});

// Scatter Chart
new Chart(document.getElementById('scatterChart'), {{
  type: 'bar',
  data: {{
    labels: expLabels,
    datasets: [{{
      label: 'Similarity (%)',
      data: expScores,
      backgroundColor: expColors.map(c => c + '80'),
      borderColor: expColors,
      borderWidth: 2,
      borderRadius: 6,
      borderSkipped: false,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: 'y',
    plugins: {{
      legend: {{ display: false }},
    }},
    scales: {{
      x: {{
        beginAtZero: true,
        max: 100,
        ticks: {{ callback: v => v + '%' }}
      }},
      y: {{
        ticks: {{
          font: {{ size: 9 }},
          autoSkip: false
        }}
      }}
    }}
  }}
}});
</script>

</body>
</html>"""

    plot_path = output_dir / "research_dashboard.html"
    with open(plot_path, "w") as f:
        f.write(html)
    print(f"\n✅ Dashboard written to {plot_path}")


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("  VIDEO FINGERPRINT ROBUSTNESS RESEARCH PIPELINE")
    print("  Purpose: Research, benchmarking, algorithm evaluation ONLY")
    print("=" * 70)
    print()

    # --- Validate input ---
    input_file = INPUT_FILE
    if len(sys.argv) > 1:
        input_file = sys.argv[1]

    if not os.path.exists(input_file):
        print(f"❌ Input file not found: {input_file}")
        print(f"   Usage: python3 {sys.argv[0]} [input_video.mp4]")
        print(f"   Default: {INPUT_FILE}")
        sys.exit(1)

    src_info = get_video_info(input_file)
    if src_info["duration"] <= 0:
        print(f"❌ Could not read video info from {input_file}")
        sys.exit(1)

    print(f"📹 Source: {input_file}")
    print(f"   Duration: {src_info['duration']:.2f}s")
    print(f"   Resolution: {src_info['width']}x{src_info['height']}")
    print(f"   FPS: {src_info['fps']}")
    print(f"   Codec: {src_info['codec']}")
    print(f"   Audio: {'Yes' if src_info['audio_present'] else 'No'}")
    print(f"   SHA-256: {file_hash(input_file)[:16]}...")
    print()

    # --- Create output directories ---
    categories = ["original", "temporal", "spatial", "color", "audio",
                   "overlay", "metadata", "combined"]
    for cat in categories:
        (OUTPUT_DIR / cat).mkdir(parents=True, exist_ok=True)

    # --- Generate experiments ---
    all_experiments: list[ExperimentSpec] = []

    print("─" * 50)
    print("📂 Layer 0: Original")
    print("─" * 50)
    orig = copy_original(input_file, OUTPUT_DIR)
    all_experiments.append(orig)
    print(f"  ✓ Copied original\n")

    layers = [
        ("📂 Layer 1: Temporal Transformations", generate_temporal_experiments),
        ("📂 Layer 2: Spatial Transformations", generate_spatial_experiments),
        ("📂 Layer 3: Color Transformations", generate_color_experiments),
        ("📂 Layer 4: Audio Experiments", generate_audio_experiments),
        ("📂 Layer 5: Overlay Experiments", generate_overlay_experiments),
        ("📂 Layer 6: Metadata Experiments", generate_metadata_experiments),
    ]

    for label, generator in layers:
        print("─" * 50)
        print(label)
        print("─" * 50)
        exps = generator(input_file, OUTPUT_DIR, src_info)
        all_experiments.extend(exps)
        print(f"  ✓ Generated {len(exps)} variants\n")

    print("─" * 50)
    print("📂 Layer 7: Combined Transformations")
    print("─" * 50)
    combined = generate_combined_experiments(input_file, OUTPUT_DIR, src_info)
    all_experiments.extend(combined)
    print(f"  ✓ Generated {len(combined)} combined variants\n")

    # --- Write experiment matrix ---
    matrix_path = str(OUTPUT_DIR / MATRIX_FILE)
    write_experiment_matrix(all_experiments, matrix_path)
    print(f"📊 Experiment matrix: {matrix_path}")
    print(f"   Total experiments: {len(all_experiments)}")
    print()

    # --- Run evaluation ---
    print("─" * 50)
    print("🔬 Running Perceptual Hash Evaluation")
    print("─" * 50)
    
    print("  Extracting original fingerprint...")
    original_hashes = extract_frame_hashes(input_file)
    print(f"  ✓ Extracted {len(original_hashes)} frame hashes from original")
    print()

    results = run_evaluation(all_experiments, original_hashes)
    
    # --- Write results ---
    results_path = str(OUTPUT_DIR / RESULTS_FILE)
    write_evaluation_results(results, results_path)
    print(f"\n📊 Evaluation results: {results_path}")

    # --- Statistics ---
    print()
    print("─" * 50)
    print("📈 Statistical Analysis")
    print("─" * 50)
    stats = generate_statistics(results)
    
    overall = stats.get("overall", {})
    print(f"  Detection Rate:     {overall.get('detection_rate', 0)*100:.1f}%")
    print(f"  Mean Similarity:    {overall.get('mean_similarity', 0)*100:.1f}%")
    print(f"  Median Similarity:  {overall.get('median_similarity', 0)*100:.1f}%")
    print(f"  Std Deviation:      {overall.get('std_similarity', 0)*100:.1f}%")
    print(f"  False Negative Rate: {overall.get('false_negative_rate', 0)*100:.1f}%")
    print()

    print("  Per-Category Breakdown:")
    for cat, cat_stat in stats.get("per_category", {}).items():
        print(f"    {cat:12s}  detect={cat_stat['detection_rate']*100:.0f}%  "
              f"mean_sim={cat_stat['mean_similarity']*100:.1f}%  n={cat_stat['count']}")

    # --- Save summary ---
    summary_path = str(OUTPUT_DIR / SUMMARY_FILE)
    summary = {
        "pipeline_version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_file": input_file,
        "source_hash": file_hash(input_file),
        "source_info": src_info,
        "ffmpeg_version": "8.1.2",
        "python_version": sys.version,
        "total_experiments": len(all_experiments),
        "statistics": stats,
        "detection_threshold": 0.75,
        "hash_frame_count": HASH_FRAME_COUNT,
        "hash_frame_size": HASH_FRAME_SIZE,
        "research_notice": (
            "This analysis is for research and algorithm evaluation only. "
            "Not intended for bypassing content-identification systems."
        )
    }
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n📄 Summary: {summary_path}")

    # --- Generate dashboard ---
    print()
    print("─" * 50)
    print("📊 Generating Research Dashboard")
    print("─" * 50)
    generate_plots_html(results, stats, OUTPUT_DIR)

    # --- Summary table ---
    print()
    print("═" * 70)
    print("  RESEARCH SUMMARY TABLE")
    print("═" * 70)
    print(f"{'Transformation':<35} {'Similarity':>10} {'Detection':<15} {'Confidence':>10}")
    print("─" * 70)
    for r in results:
        print(f"{r.experiment_id:<35} {r.similarity_score*100:>9.1f}% "
              f"{r.detection:<15} {r.confidence*100:>9.1f}%")

    print()
    print("✅ Pipeline complete!")
    print(f"   Results in: {OUTPUT_DIR}/")
    print(f"   Dashboard:  {OUTPUT_DIR}/research_dashboard.html")
    print()


if __name__ == "__main__":
    main()
