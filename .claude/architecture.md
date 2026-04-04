# Architecture

## Structure
```
downloader_pyqt6.py     — UI shell: window, tabs, signal slots, widget handlers (~4000 lines)
constants.py            — all config/paths/timeouts/API constants (126 lines)
managers/
  __init__.py
  utils.py              — pure functions: sanitize, validate, hms, url checks (377 lines)
  encoding.py           — ffmpeg: CRF/bitrate/two-pass, HW encoder (400 lines)
  update_manager.py     — app + yt-dlp self-update system (925 lines)
  upload_manager.py     — Catbox upload: single + queue (254 lines)
  trimming_manager.py   — duration fetch, preview frames, cache (460 lines)
  clipboard_manager.py  — clipboard monitoring, batch download state (530 lines)
  download_manager.py   — download orchestration, command builders, trim/byte-range (1594 lines)
```

## Components
- `YouTubeDownloader(QMainWindow)` — UI shell, delegates to managers
- `DownloadManager(QObject)` — download orchestration, yt-dlp subprocess
- `TrimmingManager(QObject)` — duration fetch, preview extraction
- `ClipboardManager(QObject)` — clipboard monitoring, batch download
- `UploadManager(QObject)` — Catbox upload (single + queue)
- `UpdateManager(QObject)` — app + yt-dlp update
- `EncodingService` — ffmpeg encoding (plain class, no QObject)
- yt-dlp — video download (subprocess)
- ffmpeg — media processing (subprocess)
- catboxpy — Catbox upload

## Manager Dependency DAG (no cycles)
```
utils (no deps)
  <- encoding (uses tool paths)
    <- trimming (uses encoding)
    <- download (uses encoding, trimming state)
      <- clipboard (uses download command builders)
  <- upload (standalone)
  <- update (standalone)
```

## PyQt6 Design
- Managers with signals inherit QObject; pure logic (encoding, utils) are plain
- Main window creates all managers, connects their signals to `_do_*` UI slots
- Workers receive pre-captured widget state dicts (no direct GUI access)
- Clipboard polling via QTimer on main window
- Themes: QSS dark/light
- Shutdown: `closeEvent` + `_shutting_down` flag on managers

## Signals
Each manager defines its own signals. Main window connects them all:
```python
self.download_mgr.sig_update_progress.connect(self._do_update_progress)
self.clipboard_mgr.sig_clipboard_status.connect(self._do_clipboard_status)
self.update_mgr.sig_show_update_dialog.connect(self._show_update_dialog)
# etc.
```

## Locks
- `download_mgr.download_lock` — download lifecycle
- `clipboard_mgr.clipboard_lock` — clipboard URL list
- `clipboard_mgr.auto_download_lock` — auto-download state
- `upload_mgr.upload_lock` — trimmer upload
- `upload_mgr.uploader_lock` (RLock) — upload queue
- `trimming_mgr.preview_lock` — preview thread
- `trimming_mgr.fetch_lock` — duration fetch
- `config_lock` — config read/write (on main window)
