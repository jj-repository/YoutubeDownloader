# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**YouTube Downloader** is a Python desktop application for downloading videos from YouTube and other supported sites. It features a tkinter GUI with internationalization, quality selection, thumbnail previews, and integration with Catbox for file uploads.

**Version:** 3.3.0

## Files Structure

```
YoutubeDownloader/
├── downloader.py          # Main application
├── constants.py           # Configuration constants and paths
├── translations.py        # i18n translations (English, German)
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

1. **YouTubeDownloaderGUI class**: Main application with all UI and logic
2. **yt-dlp integration**: Backend for video downloading
3. **ffmpeg integration**: Media processing (optional)
4. **Catbox integration**: File upload via catboxpy

### Key Features

- Video/audio download from YouTube and supported sites
- Quality selection with preview
- Thumbnail preview with caching
- Clipboard monitoring for URLs
- Upload to Catbox with history
- Multi-language support (EN/DE)
- Dark theme UI

## Configuration

**Config Path:** `~/.youtubedownloader/config.json`

**Stored Settings:**
- `language`: UI language ("en" or "de")
- `auto_check_updates`: Check for updates on startup (default: true)

**Config Validation:**
- Schema validation in `validate_config_json()`
- Type checking for each key
- Unknown keys logged but preserved

## Update System

**Status:** Fully implemented with SHA256 verification and UI toggle

**Components:**
- `_load_auto_check_updates_setting()`: Load preference from config
- `_save_auto_check_updates_setting()`: Save preference to config
- `_check_for_updates()`: Fetches latest release from GitHub API
- `_version_newer()`: Semantic version comparison
- `_show_update_dialog()`: Modal with Update Now / Open Releases / Later
- `_apply_update()`: Downloads, verifies SHA256, applies update

**GitHub Integration:**
- Repository: `jj-repository/YoutubeDownloader`
- API: `https://api.github.com/repos/jj-repository/YoutubeDownloader/releases/latest`
- Checksum file: `downloader.py.sha256`

**Security:**
- SHA256 checksum verification required
- Aborts if checksum file missing (404)
- Deletes downloaded file if verification fails

**Missing (compared to autoclicker):**
- No backup file creation before update

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
PREVIEW_WIDTH = 320
PREVIEW_HEIGHT = 180
SLIDER_LENGTH = 200
```

**Timeouts:**
```python
DOWNLOAD_TIMEOUT = 300        # 5 minutes
METADATA_FETCH_TIMEOUT = 30   # 30 seconds
FFPROBE_TIMEOUT = 10          # 10 seconds
```

**File Limits:**
```python
CATBOX_MAX_SIZE_MB = 200
MAX_FILENAME_LENGTH = 200
MAX_VIDEO_DURATION = 7200     # 2 hours
```

## Translations (translations.py)

**Supported Languages:**
- English (en) - default
- German (de)

**Usage:**
```python
from translations import tr, set_language

set_language('de')
message = tr('download_complete')  # Returns German translation
```

**Adding new strings:**
1. Add key to TRANSLATIONS dict with both 'en' and 'de' values
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

1. **No backup before update**: Unlike autoclicker, doesn't create `.backup` file
2. **Hardcoded supported sites**: URL patterns could be more extensible
3. **Large single file**: Main downloader.py is large, could benefit from further modularization

## Common Development Tasks

### Adding new translation string
1. Add to TRANSLATIONS in translations.py:
   ```python
   'new_key': {'en': 'English text', 'de': 'German text'}
   ```
2. Use `tr('new_key')` in downloader.py

### Adding backup before update
Reference autoclicker.py:
```python
import shutil
current_script = Path(__file__).resolve()
backup_path = current_script.with_suffix('.py.backup')
shutil.copy2(current_script, backup_path)
```

### Modifying download behavior
- Quality selection: `_on_quality_change()`
- Download execution: Uses yt-dlp subprocess
- Progress tracking: Parses yt-dlp output

## File Locations

**Application Data:** `~/.youtubedownloader/`
- `config.json` - User preferences
- `upload_history.json` - Catbox upload history
- `clipboard_urls.json` - Saved clipboard URLs
- `youtubedownloader.log` - Application log
