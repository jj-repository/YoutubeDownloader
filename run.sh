#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
./venv/bin/python downloader_pyqt6.py
