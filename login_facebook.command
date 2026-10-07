#!/bin/bash
cd "$(dirname "$0")"
if [ -d "backend/.venv" ]; then
    source backend/.venv/bin/activate
fi
python3 login_facebook.py
