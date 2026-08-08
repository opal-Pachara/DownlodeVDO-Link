import os
import asyncio
import uuid
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import downloader
import scraper

app = FastAPI(
    title="Simple Multi-Platform Video Downloader API",
    description="API for fetching and downloading videos from YouTube, TikTok, Facebook, and Instagram.",
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
    url: str = Field(..., description="Target video URL from YouTube, TikTok, Facebook, or Instagram")
    download_type: str = Field("video", description="Type of media to download (video or image)")

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

def is_facebook_page_or_profile(url: str) -> bool:
    u = url.lower()
    if "facebook.com" not in u and "fb.watch" not in u:
        return False
    # Identify profile, page, or Reels tab URLs that are not direct single-clip IDs
    if any(key in u for key in ["profile.php", "/people/", "sk=reels", "sk=videos", "/reels", "/videos"]) and not ("reel/" in u and "/reel/" not in u.split("?")[0].rstrip("/")) and not ("v=" in u) and not ("fb.watch/" in u):
        # Explicitly match sk=reels_tab or profile links
        if any(k in u for k in ["sk=reels", "sk=videos", "profile.php", "/people/"]):
            return True
        # Match ends with /reels or /videos
        clean_path = urlparse(url).path.rstrip("/").lower()
        if clean_path.endswith("/reels") or clean_path.endswith("/videos"):
            return True
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]
    # Simple username URL like facebook.com/zuck or facebook.com/pagename
    if len(path_parts) == 1 and not parsed.query and "fb.watch" not in u:
        return True
    return False

async def run_background_download_job(job_id: str, url: str, download_type: str = "video"):
    job = jobs.get(job_id)
    if not job:
        return
    try:
        url = url.strip()
        
        if download_type == "image":
            job["status"] = "scraping"
            job["progress_message"] = "⚡ Scraping Facebook Page for high-res photos..."
            
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cookie_path = os.path.join(project_root, "cookies.txt")
            cookie_file = cookie_path if os.path.exists(cookie_path) else None
            
            scrape_result = await scraper.scrape_facebook_images(url, max_scrolls=500, cookie_file=cookie_file)
            
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

        # 1. Check for Smart Copy-Paste bulk text / multi-link extraction (Cmd+A -> Paste)
        extracted_urls = scraper.extract_urls_from_text(url)
        if len(extracted_urls) > 1 or (" " in url or "\n" in url) and len(extracted_urls) >= 1:
            job["status"] = "downloading"
            job["page_name"] = "Smart_Batch_Extract"
            job["total_videos"] = len(extracted_urls)
            job["progress_message"] = f"⚡ Smart Copy-Paste detected! Discovered {len(extracted_urls)} clip URLs from pasted webpage text. Starting batch download..."
            
            for idx, clip_url in enumerate(extracted_urls, start=1):
                job["progress_message"] = f"Downloading clip {idx} of {job['total_videos']} into organized VDO folders..."
                result = await asyncio.to_thread(downloader.process_download, clip_url)
                if result.get("success"):
                    items = result.get("items", [{"filename": result["filename"], "download_url": result["download_url"], "title": result["filename"], "rel_path": result.get("filename")}])
                    job["items"].extend(items)
                    job["completed_videos"] += 1
            
            job["status"] = "completed"
            job["progress_message"] = f"✅ Successfully saved {job['completed_videos']} clip(s) from Smart Copy-Paste into VDO creator folders!"
            return

        is_fb_page = is_facebook_page_or_profile(url)
        if is_fb_page:
            job["status"] = "scraping"
            job["progress_message"] = "⚡ Auto-Cookie bypass active: Scraping Facebook Page with Playwright to harvest 100% of Reel/Video URLs..."
            
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cookie_path = os.path.join(project_root, "cookies.txt")
            cookie_file = cookie_path if os.path.exists(cookie_path) else None
            
            scrape_result = await scraper.scrape_facebook_page(url, max_scrolls=80, cookie_file=cookie_file)
            
            if scrape_result.get("success") and scrape_result.get("video_urls"):
                page_name = scrape_result["page_name"]
                urls_to_download = scrape_result["video_urls"]
                job["page_name"] = page_name
                job["total_videos"] = len(urls_to_download)
                job["status"] = "downloading"
                
                for idx, reel_url in enumerate(urls_to_download, start=1):
                    job["progress_message"] = f"Downloading video {idx} of {job['total_videos']} into VDO/{page_name} folder..."
                    result = await asyncio.to_thread(downloader.process_download, reel_url, target_folder=page_name)
                    if result.get("success"):
                        items = result.get("items", [{"filename": result["filename"], "download_url": result["download_url"], "title": result["filename"], "rel_path": result.get("filename")}])
                        job["items"].extend(items)
                        job["completed_videos"] += 1
                
                job["status"] = "completed"
                job["progress_message"] = f"✅ Successfully downloaded all {job['completed_videos']} clip(s) from Facebook Page '{page_name}' into folder VDO/{page_name}!"
                return
            else:
                job["progress_message"] = "No public Reels found via scraper; attempting direct yt-dlp extraction..."

        job["status"] = "downloading"
        job["progress_message"] = "Downloading video or channel playlist..."
        result = await asyncio.to_thread(downloader.process_download, url)
        
        if result.get("success"):
            items = result.get("items", [{"filename": result["filename"], "download_url": result["download_url"], "title": result["filename"], "rel_path": result.get("filename")}])
            job["items"] = items
            job["completed_videos"] = len(items)
            job["total_videos"] = len(items)
            job["status"] = "completed"
            job["progress_message"] = f"Successfully downloaded {len(items)} file(s) into VDO folder!"
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
        "download_type": request.download_type
    }
    asyncio.create_task(run_background_download_job(job_id, request.url, request.download_type))
    return {"success": True, "job_id": job_id, "status": "starting"}

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
    base_folder = "image" if is_image else "VDO"
    if is_image:
        filepath = filepath[len("image/"):]
        
    file_path = os.path.join(project_root, base_folder, filepath)
    
    # Prevent directory traversal attacks
    real_path = os.path.realpath(file_path)
    downloads_real_dir = os.path.realpath(os.path.join(project_root, base_folder))
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
