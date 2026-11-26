#!/bin/bash
# Double-click to run the app on macOS. First run installs everything (about 5-10 minutes).
cd "$(dirname "$0")" || exit 1

PY=""
for p in python3.12 python3.11 python3.13 python3.10 python3; do
  command -v "$p" >/dev/null && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 10))' && PY="$p" && break
done
[ -z "$PY" ] && { echo "Install Python 3.10+ first:  brew install python@3.12"; read -r; exit 1; }

[ -x .venv/bin/python ] || "$PY" -m venv .venv
source .venv/bin/activate
echo "Checking packages (the first run downloads about 1 GB)..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt certifi || { echo "Package install failed."; read -r; exit 1; }
export SSL_CERT_FILE="$(python -m certifi)"   # python.org builds ship without certificates

command -v ffmpeg >/dev/null || echo "Note: install ffmpeg (brew install ffmpeg) to use voice answers."

echo "Starting the app at http://localhost:8501 - keep this window open; close it to stop."
(sleep 4; open http://localhost:8501) &
python -m streamlit run app.py --server.port 8501 --server.headless true --server.fileWatcherType none --browser.gatherUsageStats false
