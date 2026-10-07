#!/bin/bash
# ====================================================
#   Simple Multi-Platform Video Downloader (macOS)
# ====================================================

# Navigate to script's directory
cd "$(dirname "$0")"

echo "===================================================="
echo "       Simple Multi-Platform Video Downloader"
echo "===================================================="
echo ""

# Check if port 8000 is already running
if lsof -i :8000 > /dev/null 2>&1; then
    echo "⚡ Server is already running on http://localhost:8000"
    echo "Opening browser..."
    open "http://localhost:8000"
    echo "Press Enter to exit or close this terminal window."
    read -r
    exit 0
fi

# Activate virtual environment if present
if [ -d "backend/.venv" ]; then
    source backend/.venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "Starting Server at http://localhost:8000 ..."
sleep 1 && open "http://localhost:8000" &

cd backend
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
