import os
import re
import logging
from datetime import datetime
from urllib.parse import urlparse
import urllib.request
import ssl
import uuid
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

def process_download(url: str, target_folder: str = None) -> dict:
    url = url.strip()
    valid, err_message = is_supported_url(url)
    if not valid:
        logger.warning(f"Validation failed for URL '{url}': {err_message}")
        return {"success": False, "error": err_message}
    
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(backend_dir)
    downloads_dir = os.path.join(project_root, "VDO")
    os.makedirs(downloads_dir, exist_ok=True)
    
    # Configure outtmpl based on whether a specific target creator/page folder was supplied
    if target_folder and target_folder.strip():
        safe_folder = re.sub(r'[\\/*?:"<>|]', "_", target_folder.strip())
        save_tmpl = os.path.join(downloads_dir, safe_folder, '%(title).100s_%(id)s.%(ext)s')
        os.makedirs(os.path.join(downloads_dir, safe_folder), exist_ok=True)
    else:
        # Auto-organize by uploader, channel, or playlist title if target_folder is not specified
        save_tmpl = os.path.join(downloads_dir, '%(channel,uploader,playlist_title|General_Clips)s', '%(title).100s_%(id)s.%(ext)s')
    
    logger.info(f"Starting download for URL: {url} into template: {save_tmpl}")
    
    # Configure base yt-dlp options for Apple-compatible codecs and safe filenames
    base_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'format_sort': ['vcodec:h264', 'acodec:aac'],
        'merge_output_format': 'mp4',
        'outtmpl': save_tmpl,
        'restrictfilenames': True,
        'noplaylist': False,  # Allow playlists and channels to be processed
        'overwrites': True,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 35,
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
                
                entries = info_dict['entries'] if 'entries' in info_dict and info_dict.get('entries') else [info_dict]
                downloaded_items = []
                
                for entry in entries:
                    if not entry:
                        continue
                    
                    filepath = None
                    if 'requested_downloads' in entry and entry['requested_downloads']:
                        filepath = entry['requested_downloads'][0].get('filepath')
                        
                    if not filepath:
                        filepath = ydl.prepare_filename(entry)
                        base, ext = os.path.splitext(filepath)
                        if ext != '.mp4' and os.path.exists(base + '.mp4'):
                            filepath = base + '.mp4'
                            
                    if not filepath or not os.path.exists(filepath):
                        video_id = entry.get('id')
                        if video_id:
                            # Walk through VDO and all creator subfolders to find the downloaded file
                            for root_dir, _, files in os.walk(downloads_dir):
                                for fname in files:
                                    if video_id in fname and not fname.endswith('.part'):
                                        filepath = os.path.join(root_dir, fname)
                                        break
                                if filepath and os.path.exists(filepath):
                                    break
                                    
                    if filepath and os.path.exists(filepath):
                        rel_path = os.path.relpath(filepath, downloads_dir)
                        # Replace backslashes on Windows for URL URLs
                        url_path = rel_path.replace('\\', '/')
                        downloaded_items.append({
                            "filename": os.path.basename(filepath),
                            "rel_path": url_path,
                            "download_url": f"/files/{url_path}",
                            "title": entry.get('title', os.path.basename(filepath))
                        })
                
                if not downloaded_items:
                    continue
                
                logger.info(f"Successfully downloaded {len(downloaded_items)} video(s) from {url}")
                return {
                    "success": True,
                    "items": downloaded_items,
                    "filename": downloaded_items[0]["filename"],
                    "download_url": downloaded_items[0]["download_url"]
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

def download_image(url: str, target_folder: str = None) -> dict:
    if not url or not url.strip():
        return {"success": False, "error": "URL cannot be empty."}
        
    try:
        # If it's a Facebook photo viewer URL, resolve it to the high-res image URL using gallery-dl
        if "facebook.com" in url and ("/photo" in url or "fbid=" in url):
            import subprocess
            logger.info(f"Resolving high-res image URL for {url}")
            gallery_dl_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", ".venv", "bin", "gallery-dl")
            cmd = [gallery_dl_path, "--cookies-from-browser", "chrome", "--get-urls", url]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                urls = result.stdout.strip().split('\n')
                if urls and "http" in urls[-1]:
                    url = urls[-1].strip()
                    logger.info(f"Resolved to high-res URL: {url}")
                else:
                    logger.warning(f"Could not resolve high-res URL, gallery-dl output: {result.stdout} {result.stderr}")
            except Exception as e:
                logger.error(f"Error resolving high-res URL with gallery-dl: {e}")
                
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        folder_name = target_folder.strip() if target_folder else "image/Facebook_Page"
        
        # Ensure it's in the image directory
        if not folder_name.startswith("image/"):
            folder_name = f"image/{folder_name}"
            
        full_output_dir = os.path.join(base_dir, folder_name)
        os.makedirs(full_output_dir, exist_ok=True)
        
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        path_parts = parsed_url.path.split('/')
        fb_filename = path_parts[-1] if path_parts else ""
        if not fb_filename or not fb_filename.endswith(('.jpg', '.png', '.webp', '.jpeg')):
            import hashlib
            # Fallback to deterministic hash of the url path
            fb_filename = f"image_{hashlib.md5(parsed_url.path.encode()).hexdigest()[:12]}.jpg"
            
        filename = fb_filename
        filepath = os.path.join(full_output_dir, filename)
        
        # Skip download if exact file already exists to save time and bandwidth
        if os.path.exists(filepath):
            logger.info(f"Image already exists, skipping download: {filepath}")
            rel_path = f"{folder_name}/{filename}"
            return {
                "success": True,
                "items": [{"filename": filename, "rel_path": rel_path, "download_url": f"/files/{rel_path}", "title": filename}],
                "filename": filename,
                "download_url": f"/files/{rel_path}"
            }
            
        logger.info(f"Downloading image from {url} to {filepath}")
        
        import requests
        try:
            response = requests.get(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'},
                timeout=(10, 30),
                stream=True
            )
            response.raise_for_status()
            with open(filepath, 'wb') as out_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        out_file.write(chunk)
        except Exception as e:
            logger.error(f"Failed to download image {url}: {e}")
            return {"success": False, "error": str(e)}
        rel_path = f"{folder_name}/{filename}"
        
        return {
            "success": True,
            "items": [{
                "filename": filename,
                "rel_path": rel_path,
                "download_url": f"/files/{rel_path}",
                "title": filename
            }],
            "filename": filename,
            "download_url": f"/files/{rel_path}"
        }
    except Exception as e:
        logger.error(f"Image download failed for {url}: {str(e)}")
        return {"success": False, "error": f"Image download failed: {str(e)}"}
