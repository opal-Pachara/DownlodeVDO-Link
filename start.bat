@echo off
title Multi-Platform Video Downloader
echo ====================================================
echo        Simple Multi-Platform Video Downloader
echo ====================================================
echo.
echo Starting Server at http://localhost:8000 ...
start "" "http://localhost:8000"
cd /d "%~dp0backend"
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
