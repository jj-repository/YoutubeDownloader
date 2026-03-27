# Configuration & Constants

## Config
Path: `~/.youtubedownloader/config.json`
- `auto_check_updates`: bool (default: true)
- Validation: `validate_config_json()` — type-checks each key, preserves unknown keys

## App Data (`~/.youtubedownloader/`)
- `config.json` — preferences
- `upload_history.txt` — Catbox history (max 1000 lines)
- `clipboard_urls.json` — saved URLs
- `youtubedownloader.log` — log (max 1MB, rotated)

## constants.py
```python
# UI
PREVIEW_WIDTH = 240; PREVIEW_HEIGHT = 135; SLIDER_LENGTH = 400
# Timeouts (seconds)
DOWNLOAD_TIMEOUT = 3600; METADATA_FETCH_TIMEOUT = 30; FFPROBE_TIMEOUT = 10
# Limits
CATBOX_MAX_SIZE_MB = 200; MAX_FILENAME_LENGTH = 200; MAX_VIDEO_DURATION = 86400
```
