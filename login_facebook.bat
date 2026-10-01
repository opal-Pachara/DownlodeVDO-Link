@echo off
title Facebook Login Helper
echo ====================================================
echo      Facebook Auto-Login & Cookie Generator
echo ====================================================
echo.
echo Opening Facebook login window...
cd /d "%~dp0"
python login_facebook.py
pause
