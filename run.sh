#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
[[ -x ./venv/bin/python ]] || { echo "Error: venv not found. Run 'python3 -m venv venv && venv/bin/pip install -r requirements.txt' first."; exit 1; }
./venv/bin/python downloader_pyqt6.py
