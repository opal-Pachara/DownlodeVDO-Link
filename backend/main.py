import os
import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uuid
import re
import random
import logging
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

logger = logging.getLogger("MainAPI")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")

# Ensure backend directory is in sys.path for relative imports
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

try:
    import downloader
    import scraper
    import processor
except ImportError:
    from backend import downloader
    from backend import scraper
    from backend import processor

app = FastAPI(
    title="Simple Multi-Platform Video Downloader API",
    description="API for fetching and downloading videos from TikTok, Facebook, and Instagram.",
    version="1.0.0"
)

# Configure CORS to allow typical local Vite development server URLs
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:[0-9]+)?",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DownloadRequest(BaseModel):
    url: str = Field(..., description="Target video URL from TikTok, Douyin, Facebook, or Instagram")
    download_type: str = Field("video", description="Type of media to download (video or image)")
    flip: bool = Field(False, description="Whether to flip video horizontally")
    brighten: bool = Field(False, description="Whether to slightly boost brightness and contrast")
    watermark_text: str = Field("", description="Watermark text to overlay on the video")
    watermark_position: str = Field("bottom_right", description="Position of watermark: bottom_right, center, top_right, top_left, bottom_left")
    watermark_opacity: float = Field(0.25, ge=0.05, le=1.0, description="Opacity of text watermark between 0.05 and 1.0")
    anti_detection: bool = Field(False, description="Enable 6-layer anti-fingerprint evasion suite (audio pitch, video speed, crop, noise)")

@app.post("/download")
async def download_video_endpoint(request: DownloadRequest):
    """
    Accepts a video URL, runs the download operations asynchronously in a background thread,
    and returns download access information or structured JSON error explanations.
    """
    if not request.url or not request.url.strip():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "URL cannot be empty."}
        )
        
    # Execute blocking yt-dlp call in a separate worker thread
    result = await asyncio.to_thread(downloader.process_download, request.url)
    
    if not result.get("success"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=result
        )
        
    return result

# In-memory dictionary for real-time job status tracking
jobs = {}

def is_facebook_single_video(url: str) -> bool:
    u = url.lower().split("?")[0].rstrip("/")
    if "fb.watch/" in u:
        return True
    if "/share/v/" in u or "/share/r/" in u or "/share/p/" in u:
        return True
    if "/reel/" in u and not u.endswith("/reels"):
        parts = u.split("/reel/")
        if len(parts) > 1 and len(parts[1].strip("/")) > 0:
            return True
    if "/videos/" in u and not u.endswith("/videos"):
        parts = u.split("/videos/")
        if len(parts) > 1 and len(parts[1].strip("/")) > 0:
            return True
    if "/posts/" in u or "/story.php" in u or "/permalink.php" in u:
        return True
    if "watch" in u and ("v=" in url.lower() or "video_id=" in url.lower()):
        return True
    return False

def is_facebook_page_or_profile(url: str) -> bool:
    u = url.lower()
    if "facebook.com" not in u and "fb.watch" not in u:
        return False
    if is_facebook_single_video(url):
        return False
    return True

def is_instagram_profile(url: str) -> bool:
    u = url.lower()
    if "instagram.com" not in u:
        return False
    parsed = urlparse(url)
    clean_path = parsed.path.strip("/")
    path_parts = clean_path.split("/")
    
    # It's a reel or post if it starts with p or reel or reels
    if len(path_parts) >= 1 and path_parts[0] in ["p", "reel", "reels"]:
        return False
        
    # Standard profile url like instagram.com/username or instagram.com/username/reels
    if len(path_parts) >= 1:
        return True
        
    return False

def is_reddit_subreddit(url: str) -> tuple[bool, str]:
    u = url.lower().split("?")[0].rstrip("/")
    if "reddit.com" not in u and "redd.it" not in u:
        return False, ""
    if "/comments/" in u or "redd.it/" in u:
        return False, ""
    sub_name = scraper.extract_subreddit_name(url)
    if sub_name and sub_name != "reddit":
        return True, sub_name
    return False, ""

async def apply_processing_to_items(
    items: list[dict],
    project_root: str,
    flip: bool,
    brighten: bool,
    watermark_text: str,
    watermark_position: str,
    watermark_opacity: float = 0.25,
    anti_detection: bool = False,
    job: dict = None
) -> list[dict]:
    """Applies FFmpeg transformations (flip, brighten, watermark, anti-detection) to downloaded video items."""
    if not (flip or brighten or (watermark_text and watermark_text.strip()) or anti_detection):
        return items
        
    processed_items = []
    for itm in items:
        raw_rel = itm.get("rel_path", "")
        if not raw_rel:
            processed_items.append(itm)
            continue
            
        raw_file = os.path.join(project_root, "VDO", raw_rel)
        if not os.path.exists(raw_file):
            processed_items.append(itm)
            continue
            
        out_file = os.path.join(project_root, "VDO_processed", raw_rel)
        if job:
            mode_desc = "Anti-Detection + Enhancement" if anti_detection else "Enhancement & Watermark"
            job["progress_message"] = f"🎨 Applying {mode_desc} to {itm.get('filename', 'video')}..."
            
        res = await asyncio.to_thread(
            processor.process_video,
            input_file=raw_file,
            output_file=out_file,
            flip=flip,
            brighten=brighten,
            watermark_text=watermark_text,
            watermark_position=watermark_position,
            watermark_opacity=watermark_opacity,
            anti_detection=anti_detection
        )
        
        if res.get("success"):
            norm_rel = raw_rel.replace('\\', '/')
            processed_items.append({
                "filename": itm.get("filename"),
                "rel_path": f"VDO_processed/{norm_rel}",
                "download_url": f"/files/VDO_processed/{norm_rel}",
                "title": itm.get("title", itm.get("filename"))
            })
        else:
            # Fallback to original if processing encountered an issue
            err_msg = res.get("error", "Unknown processing error")
            logger.warning(f"Video processing failed for '{raw_rel}': {err_msg}. Using raw downloaded video.")
            processed_items.append(itm)
            
    return processed_items

async def run_background_download_job(
    job_id: str,
    url: str,
    download_type: str = "video",
    flip: bool = False,
    brighten: bool = False,
    watermark_text: str = "",
    watermark_position: str = "bottom_right",
    watermark_opacity: float = 0.25,
    anti_detection: bool = False
):
    job = jobs.get(job_id)
    if not job:
        return
    try:
        url = url.strip()
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Clean markdown link format e.g. [title](https://url)
        md_match = re.search(r'\((https?://[^\s\)]+)\)', url)
        if md_match:
            url = md_match.group(1).strip()
        elif not url.startswith("http://") and not url.startswith("https://"):
            single_match = re.findall(r'(https?://[^\s"\'<>]+)', url)
            if len(single_match) == 1:
                url = single_match[0].strip()
        
        # Resolve Douyin short links (v.douyin.com) to canonical aweme URL
        if "douyin.com" in url.lower() or "iesdouyin.com" in url.lower():
            url = downloader.resolve_douyin_url(url)
            job["url"] = url
        
        # Reject YouTube URLs as requested
        if "youtube.com" in url.lower() or "youtu.be" in url.lower():
            job["status"] = "error"
            job["error"] = "YouTube downloads are disabled. Supported platforms: TikTok, Douyin, Facebook, Instagram."
            job["progress_message"] = f"Error: {job['error']}"
            return
        
        if download_type == "image":
            job["status"] = "scraping"
            job["progress_message"] = "⚡ Scraping Facebook Page for high-res photos..."
            
            cookie_path = os.path.join(project_root, "cookies.txt")
            cookie_file = cookie_path if os.path.exists(cookie_path) else None
            
            def run_fb_img_scraper_sync(u, s, c):
                return asyncio.run(scraper.scrape_facebook_images(u, max_scrolls=s, cookie_file=c))
            
            scrape_result = await asyncio.to_thread(run_fb_img_scraper_sync, url, 500, cookie_file)
            
            if scrape_result.get("success") and scrape_result.get("image_urls"):
                page_name = scrape_result["page_name"]
                urls_to_download = scrape_result["image_urls"]
                job["page_name"] = page_name
                job["total_videos"] = len(urls_to_download)
                job["status"] = "downloading"
                
                for idx, img_url in enumerate(urls_to_download, start=1):
                    job["progress_message"] = f"Downloading image {idx} of {job['total_videos']} into image/{page_name} folder..."
                    result = await asyncio.to_thread(downloader.download_image, img_url, target_folder=page_name)
                    if result.get("success"):
                        items = result.get("items", [{"filename": result["filename"], "download_url": result["download_url"], "title": result["filename"], "rel_path": result.get("filename")}])
                        job["items"].extend(items)
                        job["completed_videos"] += 1
                
                job["status"] = "completed"
                job["progress_message"] = f"✅ Successfully downloaded all {job['completed_videos']} image(s) from Facebook Page '{page_name}' into folder image/{page_name}!"
            else:
                job["status"] = "error"
                job["error"] = scrape_result.get("error", "No images found.")
                job["progress_message"] = f"Error: {job['error']}"
            return

        is_processing_active = flip or brighten or (watermark_text and watermark_text.strip()) or anti_detection

        # 1. Check if target is a Facebook Page / Profile / Reels Tab (ALWAYS scrape full stream)
        is_fb_page = is_facebook_page_or_profile(url)
        if is_fb_page:
            job["status"] = "scraping"
            job["progress_message"] = "⚡ Auto-Cookie bypass active: Scraping Facebook Reels and Videos (Browser scroll + GraphQL cursor pagination for 1000+ clips)..."
            
            cookie_path = os.path.join(project_root, "cookies.txt")
            cookie_file = cookie_path if os.path.exists(cookie_path) else None
            
            def run_fb_scraper_sync(u, s, c):
                return asyncio.run(scraper.scrape_facebook_page(u, max_scrolls=s, cookie_file=c))
            
            scrape_result = await asyncio.to_thread(run_fb_scraper_sync, url, 15000, cookie_file)
            
            if scrape_result.get("success") and scrape_result.get("video_urls"):
                page_name = scrape_result["page_name"]
                raw_urls = scrape_result["video_urls"]

                # Deduplicate against already-downloaded files in target folder
                target_vdo_dir = os.path.join(project_root, "VDO", page_name)
                already_downloaded_ids = set()
                if os.path.isdir(target_vdo_dir):
                    for fn in os.listdir(target_vdo_dir):
                        id_match = re.search(r'_(\d{10,})\.', fn)
                        if id_match:
                            already_downloaded_ids.add(id_match.group(1))

                urls_to_download = []
                for u in raw_urls:
                    vid_id_m = re.search(r'/reel/(\d+)', u)
                    vid_id = vid_id_m.group(1) if vid_id_m else None
                    if not vid_id or vid_id not in already_downloaded_ids:
                        urls_to_download.append(u)

                skipped_existing = len(raw_urls) - len(urls_to_download)
                job["page_name"] = page_name
                job["total_videos"] = len(urls_to_download)
                job["status"] = "downloading"
                job["progress_message"] = (
                    f"⚡ Found {len(raw_urls)} clips from '{page_name}'"
                    f"{f' ({skipped_existing} already downloaded, skipping)' if skipped_existing else ''}"
                    f" — Starting parallel download (10 concurrent)..."
                )

                # Check disk space (warn if < 5GB free)
                try:
                    import shutil as _shutil
                    total, used, free = _shutil.disk_usage(project_root)
                    free_gb = free / (1024**3)
                    if free_gb < 5.0:
                        job["progress_message"] += f" ⚠️ Warning: Only {free_gb:.1f}GB disk space remaining!"
                    logger.info(f"Disk space: {free_gb:.1f}GB free")
                except Exception:
                    pass

                # Concurrent download with semaphore — up to 10 clips downloaded in parallel
                semaphore = asyncio.Semaphore(10)
                lock = asyncio.Lock()

                async def download_one_fb(reel_url: str):
                    async with semaphore:
                        result = await asyncio.to_thread(downloader.process_download, reel_url, target_folder=page_name)
                        if result.get("success"):
                            raw_items = result.get("items", [{
                                "filename": result["filename"],
                                "download_url": result["download_url"],
                                "title": result["filename"],
                                "rel_path": result.get("filename")
                            }])
                            final_items = await apply_processing_to_items(
                                raw_items, project_root, flip, brighten, watermark_text,
                                watermark_position, watermark_opacity=watermark_opacity,
                                anti_detection=anti_detection, job=job
                            )
                            async with lock:
                                job["items"].extend(final_items)
                                job["completed_videos"] += 1
                                remaining = job['total_videos'] - job['completed_videos']
                                job["progress_message"] = (
                                    f"⬇️ Downloading {job['completed_videos']}/{job['total_videos']} clips "
                                    f"({remaining} remaining) — 10 concurrent threads"
                                )

                await asyncio.gather(*[download_one_fb(u) for u in urls_to_download])

                job["status"] = "completed"
                folder_target = f"VDO_processed/{page_name}" if is_processing_active else f"VDO/{page_name}"
                skipped = job['total_videos'] - job['completed_videos']
                skip_msg = f" (skipped {skipped} private/restricted posts)" if skipped > 0 else ""
                job["progress_message"] = f"✅ Successfully saved {job['completed_videos']} video(s){skip_msg} into {folder_target}!"
                return
            else:
                job["progress_message"] = "Playwright scraper found no videos. Falling back to direct download via yt-dlp..."

        # 2. Check if target is an Instagram Profile
        is_ig_profile = is_instagram_profile(url)
        if is_ig_profile:
            job["status"] = "scraping"
            job["progress_message"] = "⚡ Scraping Instagram Profile for Reels and Posts..."
            
            cookie_path = os.path.join(project_root, "cookies.txt")
            cookie_file = cookie_path if os.path.exists(cookie_path) else None
            
            def run_ig_scraper_sync(u, s, c):
                return asyncio.run(scraper.scrape_instagram_profile(u, max_scrolls=s, cookie_file=c))
            
            scrape_result = await asyncio.to_thread(run_ig_scraper_sync, url, 80, cookie_file)
            
            if scrape_result.get("success") and scrape_result.get("video_urls"):
                page_name = scrape_result["page_name"]
                urls_to_download = scrape_result["video_urls"]
                job["page_name"] = page_name
                job["total_videos"] = len(urls_to_download)
                job["status"] = "downloading"
                job["progress_message"] = f"⚡ Found {len(urls_to_download)} clips from '{page_name}' — Starting parallel download (10 concurrent)..."

                semaphore_ig = asyncio.Semaphore(10)
                lock_ig = asyncio.Lock()

                async def download_one_ig(ig_url: str):
                    async with semaphore_ig:
                        result = await asyncio.to_thread(downloader.process_download, ig_url, target_folder=page_name)
                        if result.get("success"):
                            raw_items = result.get("items", [{
                                "filename": result["filename"],
                                "download_url": result["download_url"],
                                "title": result["filename"],
                                "rel_path": result.get("filename")
                            }])
                            final_items = await apply_processing_to_items(
                                raw_items, project_root, flip, brighten, watermark_text,
                                watermark_position, watermark_opacity=watermark_opacity,
                                anti_detection=anti_detection, job=job
                            )
                            async with lock_ig:
                                job["items"].extend(final_items)
                                job["completed_videos"] += 1
                                remaining = job['total_videos'] - job['completed_videos']
                                job["progress_message"] = (
                                    f"⬇️ Downloading {job['completed_videos']}/{job['total_videos']} clips "
                                    f"({remaining} remaining) — 10 concurrent threads"
                                )

                await asyncio.gather(*[download_one_ig(u) for u in urls_to_download])

                job["status"] = "completed"
                folder_target = f"VDO_processed/{page_name}" if is_processing_active else f"VDO/{page_name}"
                skipped = job['total_videos'] - job['completed_videos']
                skip_msg = f" (skipped {skipped} private/restricted posts)" if skipped > 0 else ""
                job["progress_message"] = f"✅ Successfully saved {job['completed_videos']} video(s){skip_msg} into {folder_target}!"
                return
            else:
                job["progress_message"] = "Playwright scraper found no videos. Falling back to direct download via yt-dlp..."

        # 3. Check if target is a TikTok Profile
        is_tt_profile = scraper.is_tiktok_profile(url)
        if is_tt_profile:
            job["status"] = "scraping"
            job["progress_message"] = "⚡ Scraping TikTok Profile to harvest 100% of video links..."
            
            cookie_path = os.path.join(project_root, "cookies.txt")
            cookie_file = cookie_path if os.path.exists(cookie_path) else None
            
            scrape_result = await scraper.scrape_tiktok_profile(url, max_scrolls=150, cookie_file=cookie_file)
            
            if scrape_result.get("success") and scrape_result.get("video_urls"):
                page_name = scrape_result["page_name"]
                urls_to_download = scrape_result["video_urls"]
                job["page_name"] = page_name
                job["total_videos"] = len(urls_to_download)
                job["status"] = "downloading"
                job["progress_message"] = f"⚡ Found {len(urls_to_download)} clips from TikTok '@{page_name}' — Starting parallel download (5 concurrent)..."

                semaphore_tt = asyncio.Semaphore(5)
                lock_tt = asyncio.Lock()

                async def download_one_tiktok(tt_url: str):
                    async with semaphore_tt:
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                        result = await asyncio.to_thread(downloader.process_download, tt_url, target_folder=page_name)
                        if result.get("success"):
                            raw_items = result.get("items", [{
                                "filename": result["filename"],
                                "download_url": result["download_url"],
                                "title": result["filename"],
                                "rel_path": result.get("filename")
                            }])
                            final_items = await apply_processing_to_items(
                                raw_items, project_root, flip, brighten, watermark_text,
                                watermark_position, watermark_opacity=watermark_opacity,
                                anti_detection=anti_detection, job=job
                            )
                            async with lock_tt:
                                job["items"].extend(final_items)
                                job["completed_videos"] += 1
                                remaining = job['total_videos'] - job['completed_videos']
                                skipped_note = " (skipped existing)" if result.get("skipped") else ""
                                job["progress_message"] = (
                                    f"⬇️ Downloading {job['completed_videos']}/{job['total_videos']} clips{skipped_note} "
                                    f"({remaining} remaining) — 5 concurrent threads"
                                )

                await asyncio.gather(*[download_one_tiktok(u) for u in urls_to_download])

                job["status"] = "completed"
                folder_target = f"VDO_processed/{page_name}" if is_processing_active else f"VDO/{page_name}"
                skipped = job['total_videos'] - job['completed_videos']
                skip_msg = f" (skipped {skipped} private/restricted posts)" if skipped > 0 else ""
                job["progress_message"] = f"✅ Successfully saved {job['completed_videos']} TikTok video(s){skip_msg} into {folder_target}!"
                return
            else:
                page_name = scrape_result.get("page_name") or scraper.extract_tiktok_username(url)
                job["status"] = "error"
                job["error"] = f"Unable to harvest clips from TikTok profile @{page_name}. The profile may be private, restricted, or rate-limited."
                job["progress_message"] = f"Error: {job['error']}"
                return

        # 4. Check if target is a Reddit Subreddit (e.g. r/videos, r/funny)
        is_sub, sub_name = is_reddit_subreddit(url)
        if is_sub:
            job["status"] = "scraping"
            page_name = f"r_{sub_name}"
            job["page_name"] = page_name
            job["progress_message"] = f"⚡ Harvesting video posts from Subreddit 'r/{sub_name}'..."
            
            cookie_path = os.path.join(project_root, "cookies.txt")
            cookie_file = cookie_path if os.path.exists(cookie_path) else None
            
            def run_sub_scraper_sync(u, s, c):
                return asyncio.run(scraper.scrape_subreddit(u, max_scrolls=s, cookie_file=c))
                
            scrape_result = await asyncio.to_thread(run_sub_scraper_sync, url, 40, cookie_file)
            if scrape_result.get("success") and scrape_result.get("video_urls"):
                urls_to_download = scrape_result["video_urls"]
                job["total_videos"] = len(urls_to_download)
                job["status"] = "downloading"
                job["progress_message"] = f"⚡ Found {len(urls_to_download)} posts from r/{sub_name} — Starting parallel download (5 concurrent)..."

                semaphore_rd = asyncio.Semaphore(5)
                lock_rd = asyncio.Lock()

                async def download_one_reddit(post_url: str):
                    async with semaphore_rd:
                        await asyncio.sleep(random.uniform(0.5, 1.2))
                        result = await asyncio.to_thread(downloader.process_download, post_url, target_folder=page_name)
                        if result.get("success"):
                            raw_items = result.get("items", [{
                                "filename": result["filename"],
                                "download_url": result["download_url"],
                                "title": result["filename"],
                                "rel_path": result.get("filename")
                            }])
                            final_items = await apply_processing_to_items(
                                raw_items, project_root, flip, brighten, watermark_text,
                                watermark_position, watermark_opacity=watermark_opacity,
                                anti_detection=anti_detection, job=job
                            )
                            async with lock_rd:
                                job["items"].extend(final_items)
                                job["completed_videos"] += 1
                                remaining = job['total_videos'] - job['completed_videos']
                                skipped_note = " (skipped existing)" if result.get("skipped") else ""
                                job["progress_message"] = (
                                    f"⬇️ Downloading {job['completed_videos']}/{job['total_videos']} clips{skipped_note} "
                                    f"({remaining} remaining) — 5 concurrent threads"
                                )

                await asyncio.gather(*[download_one_reddit(u) for u in urls_to_download])

                job["status"] = "completed"
                folder_target = f"VDO_processed/{page_name}" if is_processing_active else f"VDO/{page_name}"
                skipped = job['total_videos'] - job['completed_videos']
                skip_msg = f" (skipped {skipped} non-video/external link posts)" if skipped > 0 else ""
                job["progress_message"] = f"✅ Successfully saved {job['completed_videos']} Reddit video(s){skip_msg} into {folder_target}!"
                return
            else:
                job["status"] = "error"
                job["error"] = scrape_result.get("error", f"Could not find any video posts in Subreddit r/{sub_name}.")
                job["progress_message"] = f"Error: {job['error']}"
                return

        # 5. Check for Smart Copy-Paste bulk text / multi-link extraction (Cmd+A -> Paste)
        extracted_urls = scraper.extract_urls_from_text(url)
        if len(extracted_urls) > 1:
            job["status"] = "downloading"
            job["page_name"] = "Smart_Batch_Extract"
            job["total_videos"] = len(extracted_urls)
            job["progress_message"] = f"⚡ Smart Copy-Paste detected! Discovered {len(extracted_urls)} clip URLs from pasted webpage text. Starting batch download..."
            
            for idx, clip_url in enumerate(extracted_urls, start=1):
                job["progress_message"] = f"Downloading clip {idx} of {job['total_videos']} into organized VDO folders..."
                result = await asyncio.to_thread(downloader.process_download, clip_url)
                if result.get("success"):
                    raw_items = result.get("items", [{"filename": result["filename"], "download_url": result["download_url"], "title": result["filename"], "rel_path": result.get("filename")}])
                    final_items = await apply_processing_to_items(raw_items, project_root, flip, brighten, watermark_text, watermark_position, watermark_opacity=watermark_opacity, anti_detection=anti_detection, job=job)
                    job["items"].extend(final_items)
                    job["completed_videos"] += 1
            
            job["status"] = "completed"
            job["progress_message"] = f"✅ Successfully saved & processed {job['completed_videos']} clip(s) from Smart Copy-Paste into creator folders!"
            return

        # 5. Direct single video / channel / playlist download via yt-dlp
        job["status"] = "downloading"
        job["progress_message"] = "Downloading video or channel playlist..."
        result = await asyncio.to_thread(downloader.process_download, url)
        
        if result.get("success"):
            raw_items = result.get("items", [{"filename": result["filename"], "download_url": result["download_url"], "title": result["filename"], "rel_path": result.get("filename")}])
            job["total_videos"] = len(raw_items)
            final_items = await apply_processing_to_items(raw_items, project_root, flip, brighten, watermark_text, watermark_position, watermark_opacity=watermark_opacity, anti_detection=anti_detection, job=job)
            job["items"] = final_items
            job["completed_videos"] = len(final_items)
            job["status"] = "completed"
            folder_target = "VDO_processed" if is_processing_active else "VDO"
            job["progress_message"] = f"Successfully downloaded & processed {len(final_items)} file(s) into {folder_target} folder!"
        else:
            job["status"] = "error"
            job["error"] = result.get("error", "Download failed.")
            job["progress_message"] = f"Error: {job['error']}"
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        job["progress_message"] = f"Fatal Error: {str(e)}"

@app.post("/download_job")
async def start_download_job(request: DownloadRequest):
    if not request.url or not request.url.strip():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "URL cannot be empty."}
        )
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "id": job_id,
        "status": "starting",
        "progress_message": "Initializing download tasks...",
        "url": request.url,
        "page_name": "VDO",
        "total_videos": 0,
        "completed_videos": 0,
        "items": [],
        "error": "",
        "download_type": request.download_type,
        "flip": request.flip,
        "brighten": request.brighten,
        "watermark_text": request.watermark_text,
        "watermark_position": request.watermark_position,
        "watermark_opacity": request.watermark_opacity,
        "anti_detection": request.anti_detection
    }
    asyncio.create_task(run_background_download_job(
        job_id,
        request.url,
        request.download_type,
        flip=request.flip,
        brighten=request.brighten,
        watermark_text=request.watermark_text,
        watermark_position=request.watermark_position,
        watermark_opacity=request.watermark_opacity,
        anti_detection=request.anti_detection
    ))
    return {"success": True, "job_id": job_id, "status": "starting"}

@app.get("/jobs")
async def list_jobs():
    """Returns list of recent jobs."""
    return list(jobs.values())

@app.get("/jobs/latest")
async def get_latest_job():
    """Returns the most recent job if any."""
    if not jobs:
        return {"has_job": False}
    latest_id = list(jobs.keys())[-1]
    return {"has_job": True, "job": jobs[latest_id]}

@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job ID not found.")
    return job

@app.get("/files/{filepath:path}")
async def get_downloaded_file(filepath: str):
    """
    Serves a downloaded file with appropriate media type and headers to prompt browser downloads.
    Supports accessing files neatly segregated inside individual creator/page subfolders.
    """
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(backend_dir)
    
    is_image = filepath.startswith("image/")
    is_processed = filepath.startswith("VDO_processed/")
    
    if is_image:
        base_folder = "image"
        filepath = filepath[len("image/"):]
    elif is_processed:
        base_folder = "VDO_processed"
        filepath = filepath[len("VDO_processed/"):]
    else:
        base_folder = "VDO"
        if filepath.startswith("VDO/"):
            filepath = filepath[len("VDO/"):]
        
    target_base = os.path.join(project_root, base_folder)
    os.makedirs(target_base, exist_ok=True)
    file_path = os.path.join(target_base, filepath)
    
    # Prevent directory traversal attacks
    real_path = os.path.realpath(file_path)
    downloads_real_dir = os.path.realpath(target_base)
    if not real_path.startswith(downloads_real_dir):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
        
    if not os.path.exists(real_path) or not os.path.isfile(real_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found or no longer available.")
        
    filename = os.path.basename(real_path)
    return FileResponse(
        path=real_path,
        media_type="application/octet-stream",
        filename=filename
    )

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "VideoDownloaderBackend"}

# Serve compiled frontend SPA in production container build (Docker / npm run build)
frontend_build_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
if os.path.exists(frontend_build_dir):
    app.mount("/", StaticFiles(directory=frontend_build_dir, html=True), name="static")
