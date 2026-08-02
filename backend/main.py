import os
import asyncio
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import downloader

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

@app.get("/files/{filename}")
async def get_downloaded_file(filename: str):
    """
    Serves a downloaded video file with appropriate media type and headers to prompt browser downloads.
    """
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(backend_dir)
    file_path = os.path.join(project_root, "VDO", filename)
    
    # Prevent directory traversal attacks
    real_path = os.path.realpath(file_path)
    downloads_real_dir = os.path.realpath(os.path.join(project_root, "VDO"))
    if not real_path.startswith(downloads_real_dir):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
        
    if not os.path.exists(real_path) or not os.path.isfile(real_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found or no longer available.")
        
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
