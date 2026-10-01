import os
import re
import logging
from datetime import datetime
from urllib.parse import urlparse
import urllib.request
import ssl
import uuid
import json
import shutil
import time
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
            
        if "youtube.com" in netloc or "youtu.be" in netloc:
            return False, "YouTube downloads are disabled. Supported platforms: TikTok, Facebook, Instagram."
            
        is_matched = any(netloc == domain or netloc.endswith(f".{domain}") for domain in SUPPORTED_DOMAINS)
        if not is_matched:
            return False, f"Unsupported domain ({netloc}). Supported platforms: TikTok, Facebook, Instagram."
        
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
    safe_folder = re.sub(r'[\r\n\t\\/*?:"<>|]', "_", target_folder.strip()).strip('. ') if target_folder and target_folder.strip() else None
    if safe_folder:
        target_dir = os.path.join(downloads_dir, safe_folder)
        save_tmpl = os.path.join(target_dir, '%(title).100s_%(id)s.%(ext)s')
        os.makedirs(target_dir, exist_ok=True)
    else:
        # Auto-organize by uploader, channel, or playlist title if target_folder is not specified
        save_tmpl = os.path.join(downloads_dir, '%(channel,uploader,playlist_title|General_Clips)s', '%(title).100s_%(id)s.%(ext)s')
    
    # Check if this video has already been downloaded (skip existing within target folder)
    video_id_match = re.search(r'/video/(\d+)', url) or re.search(r'/(?:reel|reels)/([A-Za-z0-9_\-]+)', url) or re.search(r'/p/([A-Za-z0-9_\-]+)', url)
    if video_id_match:
        vid_id = video_id_match.group(1)
        # Strictly search ONLY within target_dir if safe_folder was specified to guarantee no cross-creator file pollution
        search_dirs = [target_dir] if safe_folder else [downloads_dir]
        
        found_existing = False
        for s_dir in search_dirs:
            if found_existing:
                break
            if os.path.exists(s_dir):
                for root_d, _, files in os.walk(s_dir):
                    for f in files:
                        # Strict ID match (e.g. title_vidid.mp4 or _vidid.) rather than loose substring match
                        if (f.endswith(f"_{vid_id}.mp4") or f.endswith(f"_{vid_id}.webm") or f.endswith(f"_{vid_id}.mkv") or f"_{vid_id}." in f) and not f.endswith('.part'):
                            existing_file = os.path.join(root_d, f)
                            rel_path = os.path.relpath(existing_file, downloads_dir).replace('\\', '/')
                            logger.info(f"File for video {vid_id} already exists in {rel_path}. Skipping re-download.")
                            return {
                                "success": True,
                                "skipped": True,
                                "items": [{
                                    "filename": os.path.basename(existing_file),
                                    "rel_path": rel_path,
                                    "download_url": f"/files/{rel_path}",
                                    "title": os.path.basename(existing_file)
                                }],
                                "filename": os.path.basename(existing_file),
                                "download_url": f"/files/{rel_path}"
                            }

    logger.info(f"Starting download for URL: {url} into template: {save_tmpl}")
    
    # Configure base yt-dlp options for highest original quality and safe filenames
    base_opts = {
        'format': 'bestvideo+bestaudio/best',
        'format_sort': ['res', 'fps', 'br', 'size'],
        'merge_output_format': 'mp4',
        'postprocessors': [{
            'key': 'FFmpegVideoRemuxer',
            'preferedformat': 'mp4',
        }],
        'outtmpl': save_tmpl,
        'restrictfilenames': True,
        'windowsfilenames': True,
        'trim_file_name': 100,
        'noplaylist': False,          # Allow playlists and channels to be processed
        'overwrites': True,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 60,         # Increased from 35s to handle slow FB/IG servers
        'extract_flat': False,
        'nocheckcertificate': True,
        # Retry & resilience settings
        'retries': 5,                 # Retry individual fragments up to 5 times
        'fragment_retries': 8,        # Retry video fragments 8 times before giving up
        'file_access_retries': 3,
        'sleep_interval': 1,          # Wait 1s between retries to avoid rate-limiting
        'max_sleep_interval': 5,
        'ignoreerrors': True,         # Don't abort entire playlist/batch on a single failure
        'concurrent_fragment_downloads': 4,  # Download 4 fragments in parallel (faster)
        # HTTP headers to look more like a real browser
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept-Language': 'th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        },
    }

    # Automatically utilize cookies.txt if provided in root folder (especially helpful inside Docker containers)
    cookie_file_path = os.path.join(project_root, "cookies.txt")
    if os.path.exists(cookie_file_path) and os.path.isfile(cookie_file_path) and os.path.getsize(cookie_file_path) > 0:
        base_opts["cookiefile"] = cookie_file_path
        logger.info(f"Using exported Netscape cookies file located at {cookie_file_path}")

    # Define fallback strategies for resilient extraction across TikTok, Facebook, and Instagram
    is_tiktok = "tiktok.com" in url.lower()
    if is_tiktok:
        download_attempts = [
            {"desc": "Chrome browser TLS impersonation", "opts": {"impersonate": ImpersonateTarget("chrome")}},
            {"desc": "Chrome session cookies + TLS impersonation", "opts": {"cookiesfrombrowser": ("chrome", ), "impersonate": ImpersonateTarget("chrome")}},
            {"desc": "Edge session cookies + TLS impersonation",  "opts": {"cookiesfrombrowser": ("edge", ), "impersonate": ImpersonateTarget("chrome")}},
            {"desc": "Standard extraction", "opts": {}},
        ]
    else:
        download_attempts = [
            {"desc": "Standard extraction", "opts": {}},
            {"desc": "Chrome session cookies", "opts": {"cookiesfrombrowser": ("chrome", )}},
            {"desc": "Edge session cookies",  "opts": {"cookiesfrombrowser": ("edge", )}},
            {"desc": "Firefox session cookies", "opts": {"cookiesfrombrowser": ("firefox", )}},
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
                            # Prioritize search in target_dir if specified, otherwise downloads_dir
                            search_root = target_dir if safe_folder else downloads_dir
                            for root_dir, _, files in os.walk(search_root):
                                for fname in files:
                                    if (fname.endswith(f"_{video_id}.mp4") or f"_{video_id}." in fname) and not fname.endswith('.part'):
                                        filepath = os.path.join(root_dir, fname)
                                        break
                                if filepath and os.path.exists(filepath):
                                    break
                                    
                    if filepath and os.path.exists(filepath):
                        # Ensure clips are not saved into an empty or '_' folder if uploader was missing
                        parent_folder = os.path.basename(os.path.dirname(filepath))
                        if parent_folder in ['_', '']:
                            clean_dir = os.path.join(downloads_dir, 'General_Clips')
                            os.makedirs(clean_dir, exist_ok=True)
                            new_path = os.path.join(clean_dir, os.path.basename(filepath))
                            try:
                                if not os.path.exists(new_path):
                                    shutil.move(filepath, new_path)
                                    filepath = new_path
                            except Exception:
                                pass
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

    # If all yt-dlp strategies failed for a TikTok video, execute direct TikWM CDN fallback
    if is_tiktok:
        logger.info(f"yt-dlp strategies hit rate limit/WAF for {url}. Attempting high-speed TikWM CDN stream fallback...")
        tikwm_result = download_tiktok_fallback(url, target_folder=safe_folder or target_folder)
        if tikwm_result.get("success"):
            return tikwm_result

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

def download_tiktok_fallback(url: str, target_folder: str = None) -> dict:
    """
    High-reliability fallback for TikTok videos when yt-dlp encounters HTTP 403 Forbidden or WAF challenge.
    Resolves direct high-definition CDN stream from TikWM API and streams MP4 file directly to disk.
    """
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(backend_dir)
    downloads_dir = os.path.join(project_root, "VDO")
    safe_folder = re.sub(r'[\r\n\t\\/*?:"<>|]', "_", target_folder.strip()).strip('. ') if target_folder and target_folder.strip() else "TikTok_Clips"
    target_dir = os.path.join(downloads_dir, safe_folder)
    os.makedirs(target_dir, exist_ok=True)
    
    vid_match = re.search(r'/video/(\d+)', url)
    vid_id = vid_match.group(1) if vid_match else str(uuid.uuid4())[:8]

    # Check if already present
    if os.path.exists(target_dir):
        for f in os.listdir(target_dir):
            if vid_id in f and (f.endswith('.mp4') or f.endswith('.webm')) and not f.endswith('.part'):
                rel_path = os.path.relpath(os.path.join(target_dir, f), downloads_dir).replace('\\', '/')
                return {
                    "success": True,
                    "skipped": True,
                    "items": [{"filename": f, "rel_path": rel_path, "download_url": f"/files/{rel_path}", "title": f}],
                    "filename": f,
                    "download_url": f"/files/{rel_path}"
                }

    api_url = f"https://www.tikwm.com/api/?url={url}&hd=1"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*'
    }

    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as response:
                payload = json.loads(response.read().decode('utf-8', errors='ignore'))
                
            if payload.get("code") == 0 and payload.get("data"):
                data = payload["data"]
                # Prioritize HD stream URL (1080p/720p without watermark)
                play_url = data.get("hdplay") or data.get("play") or data.get("wmplay")
                raw_title = data.get("title") or f"TikTok_video_{vid_id}"
                clean_title = re.sub(r'[\r\n\t\\/*?:"<>|]', "_", raw_title)
                clean_title = re.sub(r'[_ .]+$', '', clean_title).strip('. ')[:80]
                if not clean_title:
                    clean_title = f"TikTok_video_{vid_id}"
                filename = f"{clean_title}_{vid_id}.mp4"
                file_dest = os.path.join(target_dir, filename)

                if play_url:
                    stream_req = urllib.request.Request(play_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(stream_req, timeout=30) as stream_resp, open(file_dest, 'wb') as out_f:
                        while True:
                            chunk = stream_resp.read(64 * 1024)
                            if not chunk:
                                break
                            out_f.write(chunk)

                    if os.path.exists(file_dest) and os.path.getsize(file_dest) > 1000:
                        rel_path = os.path.relpath(file_dest, downloads_dir).replace('\\', '/')
                        logger.info(f"TikWM CDN Fallback successfully saved TikTok video {vid_id} -> {rel_path} ({os.path.getsize(file_dest)} bytes)")
                        return {
                            "success": True,
                            "items": [{
                                "filename": filename,
                                "rel_path": rel_path,
                                "download_url": f"/files/{rel_path}",
                                "title": raw_title
                            }],
                            "filename": filename,
                            "download_url": f"/files/{rel_path}"
                        }
            time.sleep(1.2)
        except Exception as e:
            logger.warning(f"[TikWM Fallback Attempt {attempt}/3] Error for {url}: {e}")
            time.sleep(1.2)

    return {"success": False, "error": "All TikTok download strategies (yt-dlp + TikWM fallback) failed."}

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
