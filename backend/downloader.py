import os
import re
import logging
from datetime import datetime
from urllib.parse import urlparse
import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget

def strip_ansi(text: str) -> str:
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("VideoDownloader")

SUPPORTED_DOMAINS = [
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "facebook.com",
    "fb.watch",
    "instagram.com"
]

def is_supported_url(url: str) -> tuple[bool, str]:
    if not url or not url.strip():
        return False, "URL cannot be empty."
    
    try:
        parsed = urlparse(url.strip())
        if not parsed.scheme or not parsed.netloc:
            return False, "Invalid URL structure. Must begin with http:// or https://."
        
        netloc = parsed.netloc.lower()
        # Remove common prefixes
        if netloc.startswith("www."):
            netloc = netloc[4:]
        elif netloc.startswith("m."):
            netloc = netloc[2:]
        elif netloc.startswith("l.facebook.com") or netloc.startswith("l.instagram.com"):
            netloc = netloc[2:]
            
        is_matched = any(netloc == domain or netloc.endswith(f".{domain}") for domain in SUPPORTED_DOMAINS)
        if not is_matched:
            return False, f"Unsupported domain ({netloc}). Supported platforms: YouTube, TikTok, Facebook, Instagram."
        
        return True, ""
    except Exception as e:
        return False, f"Invalid URL format: {str(e)}"

def process_download(url: str) -> dict:
    url = url.strip()
    valid, err_message = is_supported_url(url)
    if not valid:
        logger.warning(f"Validation failed for URL '{url}': {err_message}")
        return {"success": False, "error": err_message}
    
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(backend_dir)
    downloads_dir = os.path.join(project_root, "VDO")
    os.makedirs(downloads_dir, exist_ok=True)
    
    logger.info(f"Starting download for URL: {url} into {downloads_dir}")
    
    # Configure base yt-dlp options for Apple-compatible codecs and safe filenames
    base_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'format_sort': ['vcodec:h264', 'acodec:aac'],
        'merge_output_format': 'mp4',
        'outtmpl': os.path.join(downloads_dir, '%(title).100s_%(id)s.%(ext)s'),
        'restrictfilenames': True,
        'noplaylist': True,
        'overwrites': True,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
        'extract_flat': False,
        'nocheckcertificate': True,
    }

    # Automatically utilize cookies.txt if provided in root folder (especially helpful inside Docker containers)
    cookie_file_path = os.path.join(project_root, "cookies.txt")
    if os.path.exists(cookie_file_path) and os.path.isfile(cookie_file_path):
        base_opts["cookiefile"] = cookie_file_path
        logger.info(f"Using exported Netscape cookies file located at {cookie_file_path}")

    # Define fallback strategies for resilient extraction across Facebook, TikTok, Instagram, and YouTube
    download_attempts = [
        {"desc": "Standard extraction", "opts": {}},
        {"desc": "Chrome session cookies", "opts": {"cookiesfrombrowser": ("chrome", )}},
        {"desc": "Safari session cookies", "opts": {"cookiesfrombrowser": ("safari", )}},
        {"desc": "Chrome browser TLS impersonation", "opts": {"impersonate": ImpersonateTarget("chrome")}},
    ]

    last_error = None
    for attempt_idx, strategy in enumerate(download_attempts, start=1):
        try:
            current_opts = dict(base_opts)
            current_opts.update(strategy["opts"])
            logger.info(f"[Attempt {attempt_idx}/{len(download_attempts)}] Downloading {url} via: {strategy['desc']}")
            
            with yt_dlp.YoutubeDL(current_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
                if not info_dict:
                    continue
                
                if 'entries' in info_dict and info_dict['entries']:
                    info_dict = info_dict['entries'][0]
                    
                filepath = None
                if 'requested_downloads' in info_dict and info_dict['requested_downloads']:
                    filepath = info_dict['requested_downloads'][0].get('filepath')
                    
                if not filepath:
                    filepath = ydl.prepare_filename(info_dict)
                    base, ext = os.path.splitext(filepath)
                    if ext != '.mp4' and os.path.exists(base + '.mp4'):
                        filepath = base + '.mp4'
                        
                if not filepath or not os.path.exists(filepath):
                    video_id = info_dict.get('id')
                    if video_id:
                        for fname in os.listdir(downloads_dir):
                            if video_id in fname:
                                filepath = os.path.join(downloads_dir, fname)
                                break
                                
                if not filepath or not os.path.exists(filepath):
                    continue
                
                filename = os.path.basename(filepath)
                logger.info(f"Successfully downloaded video: {filename} from {url}")
                return {
                    "success": True,
                    "filename": filename,
                    "download_url": f"/files/{filename}"
                }
        except Exception as e:
            last_error = e
            logger.warning(f"Strategy '{strategy['desc']}' failed for {url}: {strip_ansi(str(e))}")
            continue

    # If all fallback strategies fail, return cleaned error feedback
    raw_msg = strip_ansi(str(last_error)) if last_error else "Unknown error occurred"
    err_str = raw_msg.lower()
    logger.error(f"All download strategies failed for {url}. Final error: {raw_msg}")
    
    if "private" in err_str or "this video is private" in err_str:
        error_msg = "This video is marked as private and cannot be downloaded."
    elif "cannot parse data" in err_str or "unable to parse" in err_str:
        error_msg = "Cannot read video data from Facebook. The link might be expired or restricted."
    elif "login" in err_str or "sign in" in err_str or "authentication" in err_str:
        error_msg = "This video requires login authentication to access."
    elif "timeout" in err_str or "timed out" in err_str:
        error_msg = "Download timed out. The server was unresponsive."
    else:
        error_msg = raw_msg
        if "ERROR:" in error_msg:
            error_msg = error_msg.split("ERROR:", 1)[-1].strip()
            
    return {"success": False, "error": f"Download failed: {error_msg}"}
