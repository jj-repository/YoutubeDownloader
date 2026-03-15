# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**YouTube Downloader** is a Python desktop application for downloading videos from YouTube and other supported sites. It features a tkinter GUI with internationalization, quality selection, thumbnail previews, and integration with Catbox for file uploads.

**Version:** 3.9.2

## Files Structure

```
YoutubeDownloader/
├── downloader.py          # Main application
├── constants.py           # Configuration constants and paths
├── translations.py        # i18n translations (English, German, Polish)
├── requirements.txt       # Python dependencies
└── CLAUDE.md              # This file
```

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python downloader.py
```

## Architecture Overview

### Modular Design

Recent refactoring extracted:
- **constants.py**: All configuration values, paths, timeouts, API constants
- **translations.py**: Translation dictionary and `tr()` function

### Core Components

1. **YouTubeDownloader class**: Main application with all UI and logic
2. **yt-dlp integration**: Backend for video downloading
3. **ffmpeg integration**: Media processing (optional)
4. **Catbox integration**: File upload via catboxpy

### Key Features

- Video/audio download from YouTube and supported sites
- Quality selection with preview
- Thumbnail preview with caching
- Clipboard monitoring for URLs
- Upload to Catbox with history
- Multi-language support (English (en), German (de), Polish (pl))
- Dark theme UI

## Configuration

**Config Path:** `~/.youtubedownloader/config.json`

**Stored Settings:**
- `language`: UI language ("en", "de", or "pl")
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
- `_safe_after()`: Thread-safe scheduling that prevents crashes during shutdown

**GitHub Integration:**
- Repository: `jj-repository/YoutubeDownloader`
- API: `https://api.github.com/repos/jj-repository/YoutubeDownloader/releases/latest`

**Security:**
- App updates verified against GitHub's git tree SHA (git blob hash comparison)
- yt-dlp binary updates verified against published SHA2-256SUMS
- Syntax checking via `compile()` as additional safety net
- Backup file created before replacing each module
- All three modules downloaded and verified before any are replaced (atomic update)
- All `root.after()` calls from worker threads use `_safe_after()` to prevent crashes during shutdown
- Config file access protected by `config_lock` (both reads and writes)
- Upload queue protected by `uploader_lock` (RLock for reentrant access)

## Dependencies

Core dependencies from constants.py patterns:
- `tkinter` (standard library)
- `PIL/Pillow` - Image handling
- `yt-dlp` - Video downloading
- `catboxpy` - Catbox.moe upload API
- `pyperclip` (optional) - Clipboard access
- `dbus` (optional) - KDE Klipper integration

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

## Translations (translations.py)

**Supported Languages:**
- English (en) - default
- German (de)
- Polish (pl)

**Usage:**
```python
from translations import tr, set_language

set_language('de')
message = tr('download_complete')  # Returns German translation
```

**Adding new strings:**
1. Add key to TRANSLATIONS dict with 'en', 'de', and 'pl' values
2. Use `tr('key_name')` in code

## Clipboard Integration

**Supported Methods:**
1. `dbus` - KDE Klipper integration (Linux)
2. `pyperclip` - Cross-platform fallback
3. `tkinter` - Basic clipboard access

**URL Detection:**
- Monitors clipboard for YouTube/supported URLs
- Configurable polling interval
- Maintains list of detected URLs

## Known Issues / Technical Debt

1. **Hardcoded supported sites**: URL patterns could be more extensible
2. **Large single file**: Main downloader.py is large, could benefit from further modularization

## Recent Fixes (January 2026)

- Fixed hardcoded English strings in validate_youtube_url() to use translation system
- All URL validation messages now use tr() for proper internationalization
- Fixed Windows venv path detection (uses Scripts/ and .exe extension instead of bin/)

## Language System

Uses `translations.py` module for all language management:
- `translations.set_language(code)`: Set current language
- `translations.get_language()`: Get current language code
- `tr(key)`: Get translated string for current language

## Common Development Tasks

### Adding new translation string
1. Add to TRANSLATIONS in translations.py:
   ```python
   'new_key': {'en': 'English text', 'de': 'German text', 'pl': 'Polish text'}
   ```
2. Use `tr('new_key')` in downloader.py

### Modifying download behavior
- Quality selection: `_on_quality_change()`
- Download execution: Uses yt-dlp subprocess
- Progress tracking: Parses yt-dlp output

## File Locations

**Application Data:** `~/.youtubedownloader/`
- `config.json` - User preferences
- `upload_history.txt` - Catbox upload history
- `clipboard_urls.json` - Saved clipboard URLs
- `youtubedownloader.log` - Application log

---

## Review Status

> **Last Full Review:** 2026-03-15
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
- [x] _safe_after() prevents TclError from worker threads on shutdown
- [x] _shutting_down flag for graceful thread termination

### Internationalization Review
- [x] All UI strings use tr()
- [x] Audio-only detection works in all languages
- [x] URL validation messages internationalized
- [x] Error messages internationalized
- [x] Language switching works

### Code Quality
- [x] Modular design (constants.py, translations.py)
- [x] Config validation
- [x] Proper error handling
- [x] Log rotation (5MB max, 2 backups)
- [x] Upload history capped (1000 lines max)
- [x] Preview cache files cleaned from disk

## Quality Standards

**Target:** YouTube download tool - reliable downloads, good UX

| Aspect | Standard | Status |
|--------|----------|--------|
| Security | Safe URL/subprocess handling | Met |
| i18n | All user-facing strings translated | Met |
| Reliability | Downloads complete successfully | Met |
| UX | Progress feedback, quality selection | Met |
| Documentation | CLAUDE.md current | Met |

## Intentional Design Decisions

| Decision | Rationale |
|----------|-----------|
| yt-dlp backend | Best maintained YouTube downloader; handles site changes |
| Separate constants.py | Clean separation; easy to modify limits/timeouts |
| Separate translations.py | Easy to add new languages |
| Catbox integration | Convenient sharing for downloaded files |
| Clipboard monitoring | Common workflow - copy URL, app detects it |
| Backup before update | Creates .py.backup files before replacing modules |

## Won't Fix (Accepted Limitations)

| Issue | Reason |
|-------|--------|
| Large single file (downloader.py) | Works fine; further splitting adds complexity |
| Hardcoded site patterns | yt-dlp handles site detection; our patterns are just hints |
| _find_latest_file heuristic | Picks newest file in Downloads; rare edge case if another app writes simultaneously |
| Catbox upload no timeout/cancel | Third-party library limitation; would require significant refactoring |
| Slider change detection heuristic | Minor edge case in rapid slider manipulation |

## Completed Optimizations

- URL validation internationalized
- Constants extracted to module
- Translations extracted to module
- Config validation
- Quality selection with preview

**DO NOT further optimize:** Download speed is determined by yt-dlp and network. UI is responsive. Thumbnail caching is implemented.
