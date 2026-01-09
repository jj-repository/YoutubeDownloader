"""YoutubeDownloader Constants Module

Contains all application constants for configuration, timeouts, validation limits,
and UI settings.
"""
from pathlib import Path

# Preview and UI dimensions
PREVIEW_WIDTH = 240
PREVIEW_HEIGHT = 135
SLIDER_LENGTH = 400

# Timing constants (milliseconds)
PREVIEW_DEBOUNCE_MS = 500
UI_UPDATE_DELAY_MS = 100
UI_INITIAL_DELAY_MS = 100
AUTO_UPLOAD_DELAY_MS = 500
CLIPBOARD_POLL_INTERVAL_MS = 500

# Process and download timeouts (seconds)
PROCESS_TERMINATE_TIMEOUT = 3
TEMP_DIR_MAX_AGE = 3600  # 1 hour
DOWNLOAD_TIMEOUT = 3600  # 60 minutes max for any download
DOWNLOAD_PROGRESS_TIMEOUT = 600  # 10 minutes without progress = stalled
TIMEOUT_CHECK_INTERVAL = 10
CLIPBOARD_TIMEOUT = 0.5
METADATA_FETCH_TIMEOUT = 30
STREAM_FETCH_TIMEOUT = 15
FFPROBE_TIMEOUT = 10
DEPENDENCY_CHECK_TIMEOUT = 5
SHUTDOWN_GRACE_PERIOD_SEC = 0.5

# Cache and threading
PREVIEW_CACHE_SIZE = 20
MAX_WORKER_THREADS = 3
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 2

# Video/Audio encoding settings
VIDEO_CRF = 23
AUDIO_BITRATE = '128k'
BUFFER_SIZE = '16K'
CHUNK_SIZE = '10M'
CONCURRENT_FRAGMENTS = '5'
PROGRESS_COMPLETE = 100

# Validation limits
MAX_VOLUME = 2.0
MIN_VOLUME = 0.0
MAX_VIDEO_DURATION = 86400  # 24 hours
BYTES_PER_MB = 1024 * 1024
CATBOX_MAX_SIZE_MB = 200
MAX_FILENAME_LENGTH = 200
DEFAULT_VIDEO_QUALITY = "480"

# UI element sizes
CLIPBOARD_URL_LIST_HEIGHT = 12

# Version and Update
APP_VERSION = "3.3.0"
GITHUB_REPO = "jj-repository/YoutubeDownloader"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}"

# File paths for persistence
APP_DATA_DIR = Path.home() / ".youtubedownloader"
UPLOAD_HISTORY_FILE = APP_DATA_DIR / "upload_history.txt"
CLIPBOARD_URLS_FILE = APP_DATA_DIR / "clipboard_urls.json"
CONFIG_FILE = APP_DATA_DIR / "config.json"
LOG_FILE = APP_DATA_DIR / "youtubedownloader.log"

# Default language
DEFAULT_LANGUAGE = 'en'
