# Architecture

## Structure
- `constants.py` — all config/paths/timeouts/API constants
- `downloader_pyqt6.py` — full app: GUI + business logic

## Components
- `YouTubeDownloader(QMainWindow)` — main window, all UI and logic
- yt-dlp — video download (subprocess)
- ffmpeg — media processing (optional)
- catboxpy — Catbox upload

## PyQt6 Design
- 20 signals on `YouTubeDownloader`; workers use `pyqtSignal`/`pyqtSlot` for all GUI communication
- Worker threads receive pre-captured widget state dicts (no direct GUI access)
- Clipboard polling via `QTimer`
- Themes: QSS dark/light
- Shutdown: `closeEvent` + `_shutting_down` flag

## Signals (partial)
```python
sig_update_progress     # float 0-100 → progress bar
sig_update_status       # (message, color) → status label
sig_reset_buttons       # → re-enable buttons
sig_show_messagebox     # (type, title, msg) → modal
sig_clipboard_progress  # float → clipboard tab
sig_show_update_dialog  # (version, data) → update modal
sig_show_ytdlp_update   # (current, latest) → yt-dlp dialog
# + 13 more
```

## Locks
- `download_lock` — `is_downloading` state
- `clipboard_lock` — clipboard URL list
- `config_lock` — config read/write
- `uploader_lock` (RLock) — upload queue
- `_shutting_down` — graceful thread exit
