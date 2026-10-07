import os
import sys
import subprocess
import shutil
import logging
import re
import json
import tempfile
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("VideoProcessor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")

_filter_cache: dict[str, bool] = {}


def has_ffmpeg_filter(filter_name: str) -> bool:
    """Checks whether a specific filter is supported by the installed FFmpeg build."""
    if filter_name in _filter_cache:
        return _filter_cache[filter_name]
    try:
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            return False
        res = subprocess.run([ffmpeg_bin, "-filters"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=5)
        found = False
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[1] == filter_name:
                    found = True
                    break
        _filter_cache[filter_name] = found
        return found
    except Exception:
        _filter_cache[filter_name] = False
        return False


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
    """Finds a reliable system font that supports Thai and Latin text across Windows, macOS, and Linux."""
    candidates = []
    if sys.platform == 'win32':
        candidates = [
            r"C:\Windows\Fonts\tahoma.ttf",
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\leelawad.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\cordia.ttf",
        ]
    elif sys.platform == 'darwin':
        candidates = [
            "/System/Library/Fonts/Supplemental/Thonburi.ttc",
            "/System/Library/Fonts/ThonburiUI.ttc",
            "/System/Library/Fonts/Supplemental/Ayuthaya.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Tahoma.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
    else:  # Linux / Docker
        candidates = [
            "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]

    for font in candidates:
        if os.path.exists(font):
            return font
    return ""


def get_watermark_overlay_xy(position: str) -> str:
    """Returns FFmpeg overlay coordinate formula based on selected position."""
    pos = (position or "bottom_right").lower().strip()
    if pos == "center":
        return "(W-w)/2:(H-h)/2"
    elif pos == "top_right":
        return "W-w-24:24"
    elif pos == "top_left":
        return "24:24"
    elif pos == "bottom_left":
        return "24:H-h-24"
    else:  # default bottom_right
        return "W-w-24:H-h-24"


def create_watermark_image(text: str, opacity: float = 0.25, in_h: int = 1080) -> str:
    """
    Renders watermark text into a transparent PNG file using Pillow.
    Ensures complete cross-platform support (Mac, Windows, Linux) without requiring FFmpeg libfreetype/drawtext.
    Includes auto-scaling, drop shadow, and stroke for clear contrast on all backgrounds.
    """
    font_path = get_font_file()
    font_size = max(18, min(52, int(in_h / 30))) if in_h > 0 else 32

    font = None
    if font_path:
        try:
            font = ImageFont.truetype(font_path, font_size)
        except Exception as e:
            logger.warning(f"Could not load TrueType font '{font_path}': {e}. Falling back to default.")

    if not font:
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

    # Measure text bounding box
    dummy_img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    d = ImageDraw.Draw(dummy_img)
    if font and hasattr(d, "textbbox"):
        bbox = d.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    else:
        text_w = len(text) * int(font_size * 0.6)
        text_h = font_size

    pad = 16
    img_w = max(50, text_w + pad * 2)
    img_h = max(30, text_h + pad * 2)

    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    op = max(0.05, min(1.0, float(opacity)))
    alpha = int(255 * op)
    shadow_alpha = int(alpha * 0.45)
    border_alpha = int(alpha * 0.35)

    # 1. Subtle drop shadow
    draw.text((pad + 2, pad + 2), text, font=font, fill=(0, 0, 0, shadow_alpha))
    # 2. Main text with soft contrast stroke
    draw.text((pad, pad), text, font=font, fill=(255, 255, 255, alpha), stroke_width=1, stroke_fill=(0, 0, 0, border_alpha))

    temp_file = tempfile.NamedTemporaryFile(suffix=".png", prefix="wm_", delete=False)
    img.save(temp_file.name, format="PNG")
    temp_file.close()
    return temp_file.name


def escape_drawtext(text: str) -> str:
    """Escapes characters for FFmpeg drawtext filter (fallback)."""
    if not text:
        return ""
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
    Applies FFmpeg filters to a video with cross-platform resilience:
    - flip: Horizontal flip (hflip)
    - brighten: Slight brightness (+0.06) and contrast (+1.03) enhancement
    - watermark_text: Overlays transparent text watermark rendered via Pillow (works on both Mac and Windows)
    - watermark_opacity: Float between 0.05 and 1.0 (default 0.25)
    - anti_detection: Multi-vector evasion suite with native FFmpeg filter fallbacks
    - sharpen_hd: Auto-upscale low-res videos to 1080p via Lanczos with CAS or unsharp
    """
    if not os.path.exists(input_file):
        return {"success": False, "error": f"Input file not found: {input_file}"}

    has_watermark = bool(watermark_text and watermark_text.strip())

    # If no transformations and no sharpening are chosen, just copy the file
    if not flip and not brighten and not has_watermark and not anti_detection and not sharpen_hd:
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
    audio_args = ["-c:a", "copy"]
    video_codec_args = ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p"]

    # 1. Anti-Detection Multi-Vector Suite
    if anti_detection:
        # Layer 1: Horizontal Flip
        video_filters.append("hflip")

        # Layer 2: Micro-Crop Boundary Removal (3% edge crop)
        video_filters.append("crop=trunc(iw*0.97/2)*2:trunc(ih*0.97/2)*2")

        # Layer 3: Temporal PTS Acceleration (+2%)
        video_filters.append("setpts=PTS/1.02")

        # Layer 4: Color Histogram & Gamma Perturbation
        video_filters.append("eq=brightness=0.04:contrast=1.04:gamma=1.02")

        # Layer 5: Stochastic Sensor Noise (if supported)
        if has_ffmpeg_filter("noise"):
            video_filters.append("noise=alls=1:allf=t")

        # Layer 7: Geometric Micro-Rotation + Scale Zoom (+2%)
        if has_ffmpeg_filter("rotate"):
            rotation_rad = "0.00873"  # 0.5°
            video_filters.append(
                f"rotate={rotation_rad}:bilinear=1:fillcolor=black@0,"
                f"scale=iw*1.02:ih*1.02:flags=lanczos,"
                f"crop=iw/1.02:ih/1.02"
            )

        # Layer 8: YCbCr Hue/Saturation
        video_filters.append("hue=h=0.8:s=1.01")

        # Auto HD Upscale to 1080p if video is below 1080p
        if sharpen_hd and in_h > 0 and in_w > 0:
            if in_h >= in_w and in_h < 1920:
                video_filters.append("scale=w=-2:h=1920:flags=lanczos")
            elif in_w > in_h and in_w < 1920:
                video_filters.append("scale=w=1920:h=-2:flags=lanczos")

        # Layer 9: Sharpening (CAS if available, else unsharp)
        if has_ffmpeg_filter("cas"):
            video_filters.append("cas=0.50")
        else:
            video_filters.append("unsharp=5:5:0.8:5:5:0.0")

        # Layer 10: Temporal Frame Insertion (if supported)
        if has_ffmpeg_filter("tpad"):
            video_filters.append("tpad=start=1:start_mode=clone")

        # Layer 6 + 11 (Audio): Acoustic Tempo & Pitch Shift
        # Check if rubberband is supported; if not, use native atempo + asetrate
        if has_ffmpeg_filter("rubberband"):
            audio_args = [
                "-af", "atempo=1.02,rubberband=pitch=1.015",
                "-c:a", "aac", "-b:a", "256k"
            ]
        else:
            audio_args = [
                "-af", "atempo=1.02,asetrate=44100*1.015,aresample=44100,atempo=1/1.015",
                "-c:a", "aac", "-b:a", "256k"
            ]

        # Layer 12: H.265 (HEVC) or H.264
        video_codec_args = ["-c:v", "libx265", "-preset", "medium", "-crf", "18", "-tag:v", "hvc1", "-pix_fmt", "yuv420p"]

    else:
        # Standard individual toggles
        if flip:
            video_filters.append("hflip")
        if brighten:
            video_filters.append("eq=brightness=0.06:contrast=1.03")

        # Auto HD Upscale to 1080p & Contrast Adaptive Sharpening
        if sharpen_hd and in_h > 0 and in_w > 0:
            if in_h >= in_w and in_h < 1920:
                video_filters.append("scale=w=-2:h=1920:flags=lanczos")
            elif in_w > in_h and in_w < 1920:
                video_filters.append("scale=w=1920:h=-2:flags=lanczos")

            if has_ffmpeg_filter("cas"):
                video_filters.append("cas=0.55")
            else:
                video_filters.append("unsharp=5:5:0.8:5:5:0.0")
        elif sharpen_hd:
            if has_ffmpeg_filter("cas"):
                video_filters.append("cas=0.45")
            else:
                video_filters.append("unsharp=5:5:0.6:5:5:0.0")

    wm_temp_path = None
    try:
        cmd = [ffmpeg_bin, "-y", "-i", input_file]

        if has_watermark:
            # Generate high-contrast, transparent watermark image using Pillow
            wm_temp_path = create_watermark_image(
                watermark_text.strip(),
                opacity=watermark_opacity,
                in_h=in_h
            )
            cmd.extend(["-i", wm_temp_path])

            overlay_xy = get_watermark_overlay_xy(watermark_position)

            if video_filters:
                vf_str = ",".join(video_filters)
                filter_complex_str = f"[0:v]{vf_str}[v0];[v0][1:v]overlay={overlay_xy}[vout]"
            else:
                filter_complex_str = f"[0:v][1:v]overlay={overlay_xy}[vout]"

            cmd.extend(["-filter_complex", filter_complex_str, "-map", "[vout]", "-map", "0:a?"])
        else:
            if video_filters:
                cmd.extend(["-vf", ",".join(video_filters)])
            cmd.extend(["-map", "0:v", "-map", "0:a?"])

        cmd.extend(video_codec_args)
        cmd.extend(audio_args)
        cmd.extend([
            "-movflags", "+faststart",
            output_file
        ])

        codec_name = "H.265/HEVC" if anti_detection else "H.264"
        logger.info(f"Running FFmpeg processing for {input_file} -> {output_file} (watermark='{watermark_text}', codec={codec_name})")

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
    finally:
        if wm_temp_path and os.path.exists(wm_temp_path):
            try:
                os.unlink(wm_temp_path)
            except Exception:
                pass
