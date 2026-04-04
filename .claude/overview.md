# Overview

v5.17 — Downloads video/audio from YouTube and supported sites.

## Features
- Quality selection with file size preview
- Thumbnail preview with caching
- Trimming (start/end sliders + preview frames)
- Clipboard monitoring for URLs (Clipboard Mode tab)
- Catbox upload with history (Uploader tab)
- Dark/light QSS theme, dark title bar on Windows (DWM/ctypes)

## Files
- `downloader_pyqt6.py` — main app (PyQt6, ~4000 lines UI shell)
- `constants.py` — all config constants
- `managers/` — 7 manager modules (download, encoding, trimming, clipboard, upload, update, utils)
- `requirements.txt` — dependency ranges for development
- `requirements.lock` — pinned versions for reproducible CI builds
