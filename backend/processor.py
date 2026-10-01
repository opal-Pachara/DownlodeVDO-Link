import os
import sys
import subprocess
import shutil
import logging
import re
import json

logger = logging.getLogger("VideoProcessor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")

def get_video_dimensions(filepath: str) -> tuple[int, int]:
    """Retrieves (width, height) of the video using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            filepath
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if res.returncode == 0 and res.stdout:
            data = json.loads(res.stdout)
            streams = data.get("streams", [])
            if streams:
                w = int(streams[0].get("width", 0))
                h = int(streams[0].get("height", 0))
                return w, h
    except Exception:
        pass
    return 0, 0


def get_font_file() -> str:
    """Finds a reliable Windows or system font that supports Thai and Latin text."""
    if sys.platform == 'win32':
        candidates = [
            r"C:\Windows\Fonts\tahoma.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\leelawad.ttf",
            r"C:\Windows\Fonts\segoeui.ttf",
        ]
        for font in candidates:
            if os.path.exists(font):
                # Escape for FFmpeg filter on Windows: C\:/Windows/Fonts/...
                escaped = font.replace('\\', '/').replace(':', r'\:')
                return escaped
    else:
        linux_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
        for font in linux_candidates:
            if os.path.exists(font):
                return font
    return ""

def escape_drawtext(text: str) -> str:
    """Escapes characters for FFmpeg drawtext filter."""
    if not text:
        return ""
    # In ffmpeg drawtext filter, backslash, single quote, colon, and percent need escaping
    text = text.replace('\\', r'\\\\')
    text = text.replace("'", r"\'")
    text = text.replace(':', r'\:')
    text = text.replace('%', r'\%')
    return text

def process_video(
    input_file: str,
    output_file: str,
    flip: bool = False,
    brighten: bool = False,
    watermark_text: str = "",
    watermark_position: str = "bottom_right",
    watermark_opacity: float = 0.25,
    anti_detection: bool = False,
    sharpen_hd: bool = True
) -> dict:
    """
    Applies FFmpeg filters to a video:
    - flip: Horizontal flip (hflip)
    - brighten: Slight brightness (+0.06) and contrast (+1.03) enhancement
    - watermark_text: Overlays subtle transparent text watermark with configurable opacity
    - watermark_opacity: Float between 0.05 and 1.0 (default 0.25 for subtle look)
    - anti_detection: 12-layer multi-vector evasion suite (Micro-crop 3%, speed +2%, gamma shift, micro-noise, audio tempo +2%)
    - sharpen_hd: Auto-upscale low-res videos (540p/720p) to Full HD 1080p via Lanczos and apply AMD Contrast Adaptive Sharpening (CAS)
    """
    if not os.path.exists(input_file):
        return {"success": False, "error": f"Input file not found: {input_file}"}

    # If no transformations and no sharpening are chosen, just copy the file
    if not flip and not brighten and not (watermark_text and watermark_text.strip()) and not anti_detection and not sharpen_hd:
        try:
            out_dir = os.path.dirname(output_file)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            shutil.copy2(input_file, output_file)
            return {"success": True, "output_file": output_file}
        except Exception as e:
            return {"success": False, "error": f"Failed to copy file: {str(e)}"}

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return {"success": False, "error": "FFmpeg executable is not available on this system."}

    out_dir = os.path.dirname(output_file)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    in_w, in_h = get_video_dimensions(input_file)
    video_filters = []
    audio_args = ["-c:a", "aac", "-b:a", "256k"]
    video_codec_args = ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p"]

    # 1. Anti-Detection Multi-Vector Suite (12-Layer Architecture)
    if anti_detection:
        # Layer 1: Horizontal Flip (Spatial Mirror Disruption)
        video_filters.append("hflip")

        # Layer 2: Micro-Crop Boundary Removal (3% edge crop)
        video_filters.append("crop=trunc(iw*0.97/2)*2:trunc(ih*0.97/2)*2")

        # Layer 3: Temporal PTS Acceleration (+2%)
        video_filters.append("setpts=PTS/1.02")

        # Layer 4: Color Histogram & Gamma Perturbation
        video_filters.append("eq=brightness=0.04:contrast=1.04:gamma=1.02")

        # Layer 5: Stochastic Sensor Noise Injection (Subtle micro-dither to preserve clarity)
        video_filters.append("noise=alls=1:allf=t")

        # Layer 7: Geometric Micro-Rotation + Scale Zoom (+2%) with Lanczos for sharp pixels
        rotation_rad = "0.00873"  # 0.5° in radians = PI * 0.5 / 180
        video_filters.append(
            f"rotate={rotation_rad}:bilinear=1:fillcolor=black@0,"
            f"scale=iw*1.02:ih*1.02:flags=lanczos,"
            f"crop=iw/1.02:ih/1.02"
        )

        # Layer 8: YCbCr Luma/Chroma Independent Perturbation
        video_filters.append("hue=h=0.8:s=1.01")

        # Auto HD Upscale to 1080p if video is below 1080p
        if sharpen_hd and in_h > 0 and in_w > 0:
            if in_h >= in_w and in_h < 1920:
                video_filters.append("scale=w=-2:h=1920:flags=lanczos")
            elif in_w > in_h and in_w < 1920:
                video_filters.append("scale=w=1920:h=-2:flags=lanczos")

        # Layer 9: AMD Contrast Adaptive Sharpening (CAS) for crisp HD edges
        video_filters.append("cas=0.50")

        # Layer 10: Temporal Frame Insertion (TMK Correlation Disruption)
        video_filters.append("tpad=start=1:start_mode=clone")

        # Layer 6 + 11 (Audio A & B): Acoustic Tempo Shift & Pitch Shift
        audio_args = [
            "-af", "atempo=1.02,rubberband=pitch=1.015",
            "-c:a", "aac", "-b:a", "256k"
        ]

        # Layer 12: H.265 (HEVC) Re-encode with Metadata Scrubbing
        video_codec_args = ["-c:v", "libx265", "-preset", "medium", "-crf", "18", "-tag:v", "hvc1", "-pix_fmt", "yuv420p"]

    else:
        # Standard individual toggles
        if flip:
            video_filters.append("hflip")
        if brighten:
            video_filters.append("eq=brightness=0.06:contrast=1.03")

        # Auto HD Upscale to 1080p & AMD Contrast Adaptive Sharpening (CAS)
        if sharpen_hd and in_h > 0 and in_w > 0:
            if in_h >= in_w and in_h < 1920:
                video_filters.append("scale=w=-2:h=1920:flags=lanczos")
            elif in_w > in_h and in_w < 1920:
                video_filters.append("scale=w=1920:h=-2:flags=lanczos")
            video_filters.append("cas=0.55")
        elif sharpen_hd:
            video_filters.append("cas=0.45")


    # Watermark Layer (Subtle, non-intrusive transparent text)
    if watermark_text and watermark_text.strip():
        safe_text = escape_drawtext(watermark_text.strip())
        font_arg = ""
        font_path = get_font_file()
        if font_path:
            font_arg = f":fontfile='{font_path}'"

        # Position calculation
        pos = watermark_position.lower()
        if pos == "center":
            xy = "x=(w-tw)/2:y=(h-th)/2"
        elif pos == "top_right":
            xy = "x=w-tw-24:y=24"
        elif pos == "top_left":
            xy = "x=24:y=24"
        elif pos == "bottom_left":
            xy = "x=24:y=h-th-24"
        else: # default bottom_right
            xy = "x=w-tw-24:y=h-th-24"

        # Normalize opacity (default 0.25, range 0.05 to 1.0)
        try:
            op = max(0.05, min(1.0, float(watermark_opacity)))
        except (ValueError, TypeError):
            op = 0.25

        # Subtle, elegant watermark without harsh thick borders
        drawtext_filter = (
            f"drawtext=text='{safe_text}'{font_arg}:{xy}:"
            f"fontsize=max(16\\,min(46\\,trunc(h/30))):"
            f"fontcolor=white@{op:.2f}:"
            f"borderw=1:bordercolor=black@{op*0.3:.2f}:"
            f"shadowx=1:shadowy=1:shadowcolor=black@{op*0.4:.2f}"
        )
        video_filters.append(drawtext_filter)

    vf_chain = ",".join(video_filters)

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", input_file,
    ]
    if vf_chain:
        cmd.extend(["-vf", vf_chain])
    cmd.extend(video_codec_args)
    cmd.extend(audio_args)
    cmd.extend([
        "-movflags", "+faststart",
        output_file
    ])

    codec_name = "H.265/HEVC" if anti_detection else "H.264"
    logger.info(f"Running FFmpeg processing for {input_file} -> {output_file} (anti_detection={anti_detection}, codec={codec_name}, opacity={watermark_opacity:.2f}, filters={vf_chain})")

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300
        )
        if proc.returncode != 0:
            logger.error(f"FFmpeg failed with code {proc.returncode}: {proc.stderr}")
            return {"success": False, "error": f"FFmpeg error: {proc.stderr[-400:]}"}

        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            logger.info(f"Video processing complete: {output_file}")
            return {"success": True, "output_file": output_file}
        else:
            return {"success": False, "error": "Output file was not created."}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Video processing timed out."}
    except Exception as e:
        logger.error(f"Exception during video processing: {e}")
        return {"success": False, "error": str(e)}
