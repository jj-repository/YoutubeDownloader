# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**YouTube Downloader** is a Python desktop application for downloading videos from YouTube and other supported sites. It features a PyQt6 GUI with quality selection, thumbnail previews, trimming, and integration with Catbox for file uploads.

**Version:** 5.0.2

## Files Structure

```
YoutubeDownloader/
├── downloader_pyqt6.py    # Main application (PyQt6 GUI)
├── downloader.py          # Legacy tkinter version (archived, not the active app)
├── constants.py           # Configuration constants and paths
├── requirements.txt       # Python dependencies
└── CLAUDE.md              # This file
```

**Untracked scratch files** (not committed, can be ignored):
- `_port_callbacks.py`, `_port_download.py`, `_port_updates.py` — migration scratch files
- `downloader_pyqt6_part1.py` — draft/scratch file

> **Note:** `run.sh` still launches `downloader.py` (tkinter). To run the active app, use:
> ```bash
> ./venv/bin/python downloader_pyqt6.py
> ```

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python downloader_pyqt6.py
```

## Architecture Overview

### Modular Design

- **constants.py**: All configuration values, paths, timeouts, API constants
- **downloader_pyqt6.py**: Full application — GUI construction + all business logic

### Core Components

1. **YouTubeDownloader class** (`QMainWindow`): Main window with all UI and logic
2. **yt-dlp integration**: Backend for video downloading (subprocess)
3. **ffmpeg integration**: Media processing (optional)
4. **Catbox integration**: File upload via catboxpy

### PyQt6 Architecture

- **Thread safety**: Worker threads communicate with GUI via `pyqtSignal`/`pyqtSlot` — 20 signals defined on `YouTubeDownloader`
- **Worker threads**: Receive pre-captured widget state dicts (no direct GUI access from threads)
- **Clipboard polling**: `QTimer`-based (replaces `root.after()` from tkinter version)
- **Themes**: QSS dark/light theme system (replaces tkinter style config)
- **Shutdown**: `closeEvent` handles cleanup; `_shutting_down` flag for graceful thread termination

### Key Signals

```python
sig_update_progress     # float 0-100 → progress bar
sig_update_status       # (message, color) → status label
sig_reset_buttons       # → re-enable Download/Stop buttons
sig_show_messagebox     # (type, title, message) → modal dialog
sig_clipboard_progress  # float → clipboard tab progress
sig_show_update_dialog  # (latest_version, release_data) → update modal
sig_show_ytdlp_update   # (current, latest) → yt-dlp update dialog
# ... and 13 more
```

### Key Features

- Video/audio download from YouTube and supported sites
- Quality selection with file size preview
- Thumbnail preview with caching
- Trimming with start/end sliders and preview frames
- Clipboard monitoring for URLs (Clipboard Mode tab)
- Upload to Catbox with history (Uploader tab)
- Dark/light theme (QSS)
- Dark title bar on Windows (DWM API via ctypes)

## Configuration

**Config Path:** `~/.youtubedownloader/config.json`

**Stored Settings:**
- `auto_check_updates`: Check for updates on startup (default: true)

**Config Validation:**
- Schema validation in `validate_config_json()`
- Type checking for each key
- Unknown keys logged but preserved

## Update System

**Status:** Fully implemented with integrity verification and UI toggle

**Components:**
- `_load_auto_check_updates_setting()`: Load preference from config
- `_save_auto_check_updates_setting()`: Save preference to config
- `_check_for_updates()`: Fetches latest release from GitHub API
- `_version_newer()`: Semantic version comparison
- `_show_update_dialog()`: Modal with Update Now / Open Releases / Later
- `_apply_update()`: Downloads, verifies integrity, backs up, and applies update

**GitHub Integration:**
- Repository: `jj-repository/YoutubeDownloader`
- API: `https://api.github.com/repos/jj-repository/YoutubeDownloader/releases/latest`

**Security:**
- App updates verified against GitHub's git tree SHA (git blob hash comparison)
- yt-dlp binary updates verified against published SHA2-256SUMS
- Syntax checking via `compile()` as additional safety net
- Backup file created before replacing each module
- All modules downloaded and verified before any are replaced (atomic update)
- Config file access protected by `config_lock` (both reads and writes)
- Upload queue protected by `uploader_lock` (RLock for reentrant access)

## Dependencies

- `PyQt6` - GUI framework
- `PIL/Pillow` - Image handling
- `yt-dlp` - Video downloading
- `catboxpy` - Catbox.moe upload API
- `pyperclip` (optional) - Clipboard access
- `dbus` (optional, Linux) - KDE Klipper integration

## Constants (constants.py)

**UI Constants:**
```python
PREVIEW_WIDTH = 240
PREVIEW_HEIGHT = 135
SLIDER_LENGTH = 400
```

**Timeouts:**
```python
DOWNLOAD_TIMEOUT = 3600      # 60 minutes
METADATA_FETCH_TIMEOUT = 30  # 30 seconds
FFPROBE_TIMEOUT = 10         # 10 seconds
```

**File Limits:**
```python
CATBOX_MAX_SIZE_MB = 200
MAX_FILENAME_LENGTH = 200
MAX_VIDEO_DURATION = 86400    # 24 hours
```

## Clipboard Integration

**Supported Methods:**
1. `dbus` - KDE Klipper integration (Linux)
2. `pyperclip` - Cross-platform fallback
3. Qt clipboard - Basic clipboard access

**URL Detection:**
- Monitors clipboard for YouTube/supported URLs
- QTimer-based polling
- Maintains list of detected URLs

## Known Issues / Technical Debt

1. **Hardcoded supported sites**: URL patterns could be more extensible
2. **`run.sh` outdated**: Still launches `downloader.py` (tkinter), not the active PyQt6 app
3. **Large single file**: `downloader_pyqt6.py` is ~6000 lines, could benefit from further modularization

## Common Development Tasks

### Modifying download behavior
- Quality selection: `_on_quality_change()`
- Download execution: Uses yt-dlp subprocess
- Progress tracking: Parses yt-dlp output, emitted via `sig_update_progress`

### Adding a new signal (worker → GUI)
1. Define `sig_foo = pyqtSignal(...)` on `YouTubeDownloader`
2. Connect in `__init__`: `self.sig_foo.connect(self._do_foo)`
3. Implement `_do_foo(self, ...)` — runs on GUI thread
4. Emit from worker: `self.sig_foo.emit(...)`

## File Locations

**Application Data:** `~/.youtubedownloader/`
- `config.json` - User preferences
- `upload_history.txt` - Catbox upload history
- `clipboard_urls.json` - Saved clipboard URLs
- `youtubedownloader.log` - Application log

---

## Versioning

Version bumps default to **+0.0.1** (patch) unless explicitly told otherwise.

---

## Review Status

> **Last Full Review:** 2026-03-27
> **Status:** Production Ready

### Security Review
- [x] URL validation before download
- [x] Safe subprocess usage (no shell=True)
- [x] Config validation with schema
- [x] Git blob SHA verification for app updates
- [x] SHA256 verification for yt-dlp binary updates
- [x] No command injection (proper argument passing)
- [x] Timeout on all network operations
- [x] Config file access protected by lock
- [x] Unpredictable temp file names (tempfile module)

### Thread Safety Review
- [x] download_lock protects is_downloading state
- [x] clipboard_lock protects clipboard URL list
- [x] config_lock protects config read/write
- [x] uploader_lock (RLock) protects upload queue
- [x] PyQt6 signals/slots for all worker → GUI communication (thread-safe by design)
- [x] _shutting_down flag for graceful thread termination

### Code Quality
- [x] Modular design (constants.py)
- [x] Config validation
- [x] Proper error handling
- [x] Log rotation (1MB max)
- [x] Upload history capped (1000 lines max)
- [x] Preview cache files cleaned from disk

## Quality Standards

**Target:** YouTube download tool - reliable downloads, good UX

| Aspect | Standard | Status |
|--------|----------|--------|
| Security | Safe URL/subprocess handling | Met |
| UI Strings | Inline English strings | Met |
| Reliability | Downloads complete successfully | Met |
| UX | Progress feedback, quality selection, trimming | Met |
| Documentation | CLAUDE.md current | Met |

## Intentional Design Decisions

| Decision | Rationale |
|----------|-----------|
| PyQt6 GUI | Replaced tkinter; better cross-platform appearance, native widgets, signals/slots |
| yt-dlp backend | Best maintained YouTube downloader; handles site changes |
| Separate constants.py | Clean separation; easy to modify limits/timeouts |
| Catbox integration | Convenient sharing for downloaded files |
| Clipboard monitoring | Common workflow - copy URL, app detects it |
| Backup before update | Creates .py.backup files before replacing modules |
| Signals for thread→GUI | Qt's built-in mechanism; safe by design, no manual locking needed for UI updates |

## Won't Fix (Accepted Limitations)

| Issue | Reason |
|-------|--------|
| Large single file (downloader_pyqt6.py) | Works fine; further splitting adds complexity |
| Hardcoded site patterns | yt-dlp handles site detection; our patterns are just hints |
| _find_latest_file heuristic | Picks newest file in Downloads; rare edge case if another app writes simultaneously |
| Catbox upload no timeout/cancel | Third-party library limitation; would require significant refactoring |
| run.sh launches tkinter version | Legacy script; use `python downloader_pyqt6.py` directly |

## Completed Optimizations

- Constants extracted to module
- Config validation
- Quality selection with preview
- Full PyQt6 GUI rewrite (v5.0.0)
- Dark title bar on Windows
- SwornTweaks-style tab bar

**DO NOT further optimize:** Download speed is determined by yt-dlp and network. UI is responsive. Thumbnail caching is implemented.
