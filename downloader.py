#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import sys
import subprocess

# On Windows, prevent subprocess calls from opening visible console windows
_subprocess_kwargs = {}
if sys.platform == 'win32':
    _subprocess_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
import threading
import re
import logging
import logging.handlers
import json
import webbrowser
from pathlib import Path
from PIL import Image, ImageTk, ImageDraw, ImageFont
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import shutil
import signal
import glob
from collections import OrderedDict
from catboxpy.catbox import CatboxClient

# Import from modular components
from constants import (
    PREVIEW_WIDTH, PREVIEW_HEIGHT, SLIDER_LENGTH, PREVIEW_DEBOUNCE_MS,
    PROCESS_TERMINATE_TIMEOUT, TEMP_DIR_MAX_AGE, DOWNLOAD_TIMEOUT,
    DOWNLOAD_PROGRESS_TIMEOUT, PREVIEW_CACHE_SIZE, MAX_WORKER_THREADS,
    MAX_RETRY_ATTEMPTS, RETRY_DELAY, CLIPBOARD_POLL_INTERVAL_MS,
    VIDEO_CRF, AUDIO_BITRATE, BUFFER_SIZE, CHUNK_SIZE, CONCURRENT_FRAGMENTS,
    UI_UPDATE_DELAY_MS, PROGRESS_COMPLETE, CLIPBOARD_TIMEOUT,
    METADATA_FETCH_TIMEOUT, STREAM_FETCH_TIMEOUT, FFPROBE_TIMEOUT,
    DEPENDENCY_CHECK_TIMEOUT, TIMEOUT_CHECK_INTERVAL, MAX_VOLUME, MIN_VOLUME,
    MAX_VIDEO_DURATION, BYTES_PER_MB, CATBOX_MAX_SIZE_MB, MAX_FILENAME_LENGTH,
    CLIPBOARD_URL_LIST_HEIGHT, UI_INITIAL_DELAY_MS,
    AUTO_UPLOAD_DELAY_MS,
    TARGET_MAX_SIZE_BYTES, TARGET_AUDIO_BITRATE_BPS,
    SIZE_CONSTRAINED_RESOLUTIONS, SIZE_CONSTRAINED_MIN_BITRATES,
    APP_VERSION, GITHUB_REPO,
    GITHUB_RELEASES_URL, GITHUB_API_LATEST, GITHUB_RAW_URL, APP_DATA_DIR,
    UPLOAD_HISTORY_FILE, CLIPBOARD_URLS_FILE, CONFIG_FILE, LOG_FILE,
    THEMES,
)

# Try to import dbus for KDE Klipper integration
try:
    import dbus
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False

# Try to import pyperclip for cross-platform clipboard support
try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False

# Configure logging
APP_DATA_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1*1024*1024, backupCount=0),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def _excepthook(exc_type, exc_value, exc_tb):
    """Log unhandled exceptions to the log file before crashing."""
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = _excepthook

# Compiled regex patterns for performance
PROGRESS_REGEX = re.compile(r'(\d+\.?\d*)%')
SPEED_REGEX = re.compile(r'(\d+\.?\d*\s*[KMG]iB/s)')
ETA_REGEX = re.compile(r'ETA\s+(\d{2}:\d{2}(?::\d{2})?)')
FILESIZE_REGEX = re.compile(r'(\d+\.?\d*\s*[KMG]iB)')
TIME_REGEX = re.compile(r'^(\d{1,2}):(\d{2}):(\d{2})$')

class YouTubeDownloader:
    def __init__(self, root):
        logger.info("Initializing YoutubeDownloader")
        self.root = root
        self.root.title('YoutubeDownloader')
        if sys.platform == 'win32':
            self.root.geometry("680x700")
            self.root.minsize(580, 400)
        else:
            self.root.geometry("900x1140")
            self.root.minsize(750, 600)
        self.root.resizable(True, True)

        # Set window icon
        try:
            icon_path = self._get_resource_path('icon.png')
            if os.path.exists(icon_path):
                icon_img = ImageTk.PhotoImage(Image.open(icon_path))
                self.root.iconphoto(True, icon_img)
                self._icon_ref = icon_img  # Keep reference
        except Exception as e:
            logger.error(f"Error setting window icon: {e}")

        self.download_path = str(Path.home() / "Downloads")
        self.current_process = None
        self.is_downloading = False
        self.video_duration = 0
        self.video_title = None
        self.is_fetching_duration = False
        self.last_progress_time = None
        self.download_start_time = None
        self.timeout_monitor_thread = None
        self._shutting_down = False

        # Detect bundled executables (when packaged with PyInstaller)
        self.ffmpeg_path = self._get_bundled_executable('ffmpeg')
        self.ffprobe_path = self._get_bundled_executable('ffprobe')
        self.ytdlp_path = self._get_bundled_executable('yt-dlp')

        # Frame preview variables
        self.start_preview_image = None
        self.end_preview_image = None
        self.temp_dir = None
        self.current_video_url = None
        self.preview_update_timer = None
        self.last_preview_update = 0
        self.preview_thread_running = False  # Track if preview thread is active
        # Use OrderedDict for O(1) LRU cache operations
        self.preview_cache = OrderedDict()  # Cache for preview frames {timestamp: file_path}

        # Volume control
        self.volume_var = tk.DoubleVar(value=1.0)  # 1.0 = 100%

        # Local file support
        self.local_file_path = None

        # Upload to Catbox.moe
        self.last_output_file = None  # Track last downloaded/processed file
        self.is_uploading = False
        self.catbox_client = CatboxClient()  # Anonymous upload client

        # Custom filename
        self.custom_filename = None  # User-specified output filename

        # Playlist support
        self.is_playlist = False  # Track if current URL is a playlist
        self.estimated_filesize = None  # Estimated file size for current video

        # Initialize temp directory with cleanup on exit
        self._init_temp_directory()

        # Clean up leftover files from previous self-updates
        self._cleanup_old_updates()

        # Check dependencies once at startup
        self.dependencies_ok = self.check_dependencies()
        if not self.dependencies_ok:
            logger.warning("Dependencies check failed at startup")

        # Detect hardware encoder (must run after check_dependencies sets ffmpeg_path)
        self.hw_encoder = self._detect_hw_encoder()

        # Thread pool for background tasks
        self.thread_pool = ThreadPoolExecutor(max_workers=MAX_WORKER_THREADS, thread_name_prefix="ytdl_worker")

        # Thread safety locks
        self.preview_lock = threading.Lock()  # Protect preview thread state
        self.clipboard_lock = threading.Lock()  # Protect clipboard URL list
        self.auto_download_lock = threading.Lock()  # Protect auto-download state
        self.download_lock = threading.Lock()  # Protect download state
        self.upload_lock = threading.Lock()  # Protect upload state
        self.uploader_lock = threading.RLock()  # Protect uploader queue state (reentrant for nested calls)
        self.fetch_lock = threading.Lock()  # Protect duration fetch state
        self.config_lock = threading.Lock()  # Protect config read-modify-write

        # Clipboard Mode variables
        self.clipboard_monitoring = False
        self.clipboard_monitor_thread = None
        self.clipboard_last_content = ""
        self.clipboard_url_list = []  # List of dict: {'url': str, 'status': str, 'widget': Frame}
        self.clipboard_download_path = str(Path.home() / "Downloads")
        self.clipboard_downloading = False
        self.clipboard_auto_downloading = False  # Separate flag for auto-downloads
        self.clipboard_current_download_index = 0
        self.clipboard_url_widgets = {}
        self.klipper_interface = None  # KDE Klipper D-Bus interface

        # Theme mode
        self.current_theme = self._load_theme_preference()

        # Auto-upload feature
        self.auto_upload_var = tk.BooleanVar(value=False)  # Auto-upload after download/trim

        # Uploader tab variables
        self.uploader_file_queue = []  # List of file paths to upload
        self.uploader_is_uploading = False
        self.uploader_current_index = 0

        # Load persisted clipboard URLs
        self._load_clipboard_urls()

        # Try to connect to KDE Klipper
        if DBUS_AVAILABLE:
            try:
                bus = dbus.SessionBus()
                klipper = bus.get_object('org.kde.klipper', '/klipper')
                self.klipper_interface = dbus.Interface(klipper, 'org.kde.klipper.klipper')
                logger.info("Connected to KDE Klipper clipboard manager")
            except Exception as e:
                logger.info(f"KDE Klipper not available: {e}")
                self.klipper_interface = None

        # Create clipboard download directory
        Path(self.clipboard_download_path).mkdir(parents=True, exist_ok=True)

        self.setup_ui()

        # Bind cleanup on window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Check for updates on startup if enabled (delay to let UI initialize)
        if self._load_auto_check_updates_setting():
            self.root.after(2000, lambda: self.thread_pool.submit(self._check_for_updates, True))

    # Persistence methods

    def _load_clipboard_urls(self):
        """Load persisted clipboard URLs from previous session"""
        try:
            if CLIPBOARD_URLS_FILE.exists():
                with open(CLIPBOARD_URLS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    # Validate JSON structure
                    if not isinstance(data, dict):
                        raise ValueError("Invalid clipboard URLs file format: expected dict")
                    if 'urls' not in data:
                        raise ValueError("Invalid clipboard URLs file format: missing 'urls' key")
                    if not isinstance(data['urls'], list):
                        raise ValueError("Invalid clipboard URLs file format: 'urls' must be a list")

                    # Store URLs, will be restored to UI after setup_ui() completes
                    self.persisted_clipboard_urls = data['urls']
                    logger.info(f"Loaded {len(self.persisted_clipboard_urls)} persisted clipboard URLs")
            else:
                self.persisted_clipboard_urls = []
        except Exception as e:
            logger.error(f"Error loading clipboard URLs: {e}")
            self.persisted_clipboard_urls = []

    def _save_clipboard_urls(self):
        """Save clipboard URLs to file for persistence between sessions"""
        try:
            CLIPBOARD_URLS_FILE.parent.mkdir(parents=True, exist_ok=True)
            # Save only pending and failed URLs (not completed ones)
            with self.clipboard_lock:
                urls_to_save = [
                    {'url': item['url'], 'status': item['status']}
                    for item in self.clipboard_url_list
                    if item['status'] in ['pending', 'failed']
                ]
            with open(CLIPBOARD_URLS_FILE, 'w', encoding='utf-8') as f:
                json.dump({'urls': urls_to_save}, f, indent=2)
            logger.info(f"Saved {len(urls_to_save)} clipboard URLs")
        except Exception as e:
            logger.error(f"Error saving clipboard URLs: {e}")

    def _restore_clipboard_urls(self):
        """Restore persisted URLs to the UI (called after setup_ui)"""
        if hasattr(self, 'persisted_clipboard_urls') and self.persisted_clipboard_urls:
            for url_data in self.persisted_clipboard_urls:
                url = url_data.get('url', '')
                status = url_data.get('status', 'pending')
                with self.clipboard_lock:
                    url_exists = url and url not in [item['url'] for item in self.clipboard_url_list]
                if url_exists:
                    self._add_url_to_clipboard_list(url)
                    if status == 'failed':
                        self._update_url_status(url, 'failed')
            logger.info(f"Restored {len(self.persisted_clipboard_urls)} URLs to clipboard list")
            self.persisted_clipboard_urls = None

    def _load_auto_check_updates_setting(self):
        """Load auto-check updates setting from config"""
        try:
            with self.config_lock:
                if CONFIG_FILE.exists():
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        return config.get('auto_check_updates', True)  # Default to True
        except Exception as e:
            logger.error(f"Error loading auto_check_updates setting: {e}")
        return True  # Default to True

    def _save_auto_check_updates_setting(self):
        """Save auto-check updates setting to config"""
        with self.config_lock:
            try:
                CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

                config = {}
                if CONFIG_FILE.exists():
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        config = json.load(f)

                config['auto_check_updates'] = self.auto_check_updates_var.get()

                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2)

                logger.info(f"Saved auto_check_updates: {config['auto_check_updates']}")
            except Exception as e:
                logger.error(f"Error saving auto_check_updates setting: {e}")

    def _load_theme_preference(self):
        """Load saved theme preference from config"""
        try:
            with self.config_lock:
                if CONFIG_FILE.exists():
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        theme = config.get('theme', 'dark')
                        if theme in THEMES:
                            return theme
        except Exception as e:
            logger.error(f"Error loading theme preference: {e}")
        return 'dark'

    def _save_theme_preference(self):
        """Save theme preference to config"""
        with self.config_lock:
            try:
                CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

                config = {}
                if CONFIG_FILE.exists():
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        config = json.load(f)

                config['theme'] = self.current_theme

                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2)

                logger.info(f"Saved theme preference: {self.current_theme}")
            except Exception as e:
                logger.error(f"Error saving theme preference: {e}")

    def _toggle_theme(self):
        """Toggle between light and dark theme"""
        self.current_theme = 'dark' if self.current_theme == 'light' else 'light'
        self._apply_theme()
        self._save_theme_preference()

    def _setup_settings_tab(self, parent):
        """Setup Settings tab UI"""
        # Dark mode toggle
        self.dark_mode_var = tk.BooleanVar(value=self.current_theme == 'dark')
        ttk.Checkbutton(parent, text='Dark Mode',
                       variable=self.dark_mode_var,
                       command=self._toggle_theme).grid(row=0, column=0, sticky=tk.W, pady=(0, 10))

        ttk.Separator(parent).grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        # Update section
        ttk.Label(parent, text='Updates', font=('Arial', 11, 'bold')).grid(row=2, column=0, sticky=tk.W, pady=(5, 5))

        self.auto_check_updates_var = tk.BooleanVar(value=self._load_auto_check_updates_setting())
        ttk.Checkbutton(parent, text='Check for updates on startup',
                       variable=self.auto_check_updates_var,
                       command=self._save_auto_check_updates_setting).grid(row=3, column=0, sticky=tk.W, pady=(0, 5))

        ttk.Button(parent, text='Check for Updates',
                  command=self._check_for_updates_clicked).grid(row=4, column=0, sticky=tk.W, pady=(0, 10))

        ttk.Separator(parent).grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        # Readme link
        ttk.Button(parent, text="Readme",
                  command=lambda: webbrowser.open(f'https://github.com/{GITHUB_REPO}#readme')).grid(row=6, column=0, sticky=tk.W, pady=(5, 10))

        ttk.Separator(parent).grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        # Takodachi image
        try:
            img_path = self._get_resource_path('takodachi.webp')
            if os.path.exists(img_path):
                with Image.open(img_path) as img:
                    img.thumbnail((120, 120), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                img_label = ttk.Label(parent, image=photo)
                img_label.image = photo  # Keep reference
                img_label.grid(row=8, column=0, pady=(10, 5))
        except Exception as e:
            logger.error(f"Error loading settings image: {e}")

        # Credits
        ttk.Label(parent, text="by JJ", font=('Arial', 10, 'bold')).grid(row=9, column=0, pady=(5, 2))
        ttk.Label(parent, text=f"v{APP_VERSION}", font=('Arial', 9)).grid(row=10, column=0)

    def _setup_help_tab(self, parent):
        """Setup Help tab with usage guide"""
        ttk.Label(parent, text='How to Use YoutubeDownloader', font=('Arial', 14, 'bold')).grid(
            row=0, column=0, sticky=tk.W, pady=(0, 10))

        btn_frame = ttk.Frame(parent)
        btn_frame.grid(row=1, column=0, sticky=tk.W, pady=(0, 15))
        ttk.Button(btn_frame, text='GitHub',
                  command=lambda: webbrowser.open(f'https://github.com/{GITHUB_REPO}')).pack(side=tk.LEFT, padx=(0, 5))
        self._report_bug_btn = tk.Button(btn_frame, text='Report a Bug', relief='flat', padx=8, pady=2,
                  fg='black', bg='#ddaa00', activebackground='#bb8800', activeforeground='black',
                  command=lambda: webbrowser.open(f'https://github.com/{GITHUB_REPO}/issues/new?template=bug_report.yml'))
        self._report_bug_btn.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text='Open Log Folder',
                  command=lambda: webbrowser.open(str(APP_DATA_DIR))).pack(side=tk.LEFT)

        ttk.Separator(parent).grid(row=2, column=0, sticky=(tk.W, tk.E), pady=5)

        sections = [
            ('Clipboard Mode', 'Copy any YouTube URL (Ctrl+C) and it will automatically appear in the detected URLs list. You can download them individually or click "Download All" to batch download. Enable "Auto-download" to start downloading as soon as a URL is detected.'),
            ('Trimmer', 'Paste a YouTube URL and select your desired quality. To trim a video, enable "Enable video trimming", click "Fetch Video Duration", then use the sliders or time fields to set start and end points. Frame previews show exactly what you\'re selecting.'),
            ('Uploader', 'Upload local video or audio files to Catbox.moe for easy sharing. Click "Add Files" to select files, then "Upload to Catbox.moe" to upload. URLs are automatically copied to your clipboard. You can also enable auto-upload in the Trimmer tab to upload after each download.'),
            ('Settings', 'Toggle dark mode, check for updates, and view app info.'),
            ('Reporting a Bug', 'Click "Report a Bug" above to open the bug report form on GitHub. '
             'To help us find the issue, click "Open Log Folder" and attach the youtubedownloader.log file to your report. '
             'The log records errors, download activity, and crash details automatically.'),
        ]

        row = 3
        for title_text, desc_text in sections:
            ttk.Label(parent, text=title_text, font=('Arial', 11, 'bold')).grid(
                row=row, column=0, sticky=tk.W, pady=(10, 3))
            ttk.Label(parent, text=desc_text, wraplength=550, justify=tk.LEFT,
                     font=('Arial', 9)).grid(
                row=row+1, column=0, sticky=tk.W, padx=(10, 0))
            row += 2

    def _get_resource_path(self, filename):
        """Get path to a resource file (works for both source and bundled mode)"""
        if getattr(sys, 'frozen', False):
            # Check next to executable first
            exe_dir = os.path.dirname(sys.executable)
            local_path = os.path.join(exe_dir, filename)
            if os.path.exists(local_path):
                return local_path
            # Fall back to _MEIPASS
            bundle_dir = getattr(sys, '_MEIPASS', exe_dir)
            return os.path.join(bundle_dir, filename)
        else:
            return os.path.join(os.path.dirname(__file__), filename)

    def _apply_theme(self):
        """Apply the current theme colors to all widgets"""
        colors = THEMES[self.current_theme]
        style = ttk.Style()

        # Use 'clam' theme as base (most customizable)
        style.theme_use('clam')

        # Configure ttk styles
        style.configure('.', background=colors['bg'], foreground=colors['fg'],
                       fieldbackground=colors['entry_bg'], bordercolor=colors['border'],
                       darkcolor=colors['bg'], lightcolor=colors['bg'],
                       troughcolor=colors['canvas_bg'], selectbackground=colors['select_bg'],
                       selectforeground=colors['select_fg'], arrowcolor=colors['fg'])

        style.configure('TFrame', background=colors['bg'])
        style.configure('TLabel', background=colors['bg'], foreground=colors['fg'])
        style.configure('TButton', background=colors['canvas_bg'], foreground=colors['fg'])
        style.map('TButton',
                  background=[('active', colors['select_bg']), ('pressed', colors['select_bg'])],
                  foreground=[('active', colors['select_fg']), ('pressed', colors['select_fg'])])
        style.configure('TCheckbutton', background=colors['bg'], foreground=colors['fg'])
        style.map('TCheckbutton', background=[('active', colors['bg'])])
        style.configure('TRadiobutton', background=colors['bg'], foreground=colors['fg'])
        style.map('TRadiobutton', background=[('active', colors['bg'])])
        style.configure('TEntry', fieldbackground=colors['entry_bg'], foreground=colors['entry_fg'],
                       insertcolor=colors['fg'])
        style.configure('TCombobox', fieldbackground=colors['entry_bg'], foreground=colors['entry_fg'],
                       selectbackground=colors['select_bg'], selectforeground=colors['select_fg'])
        style.map('TCombobox', fieldbackground=[('readonly', colors['entry_bg'])],
                  selectbackground=[('readonly', colors['select_bg'])])
        style.configure('TNotebook', background=colors['bg'])
        style.configure('TNotebook.Tab', background=colors['canvas_bg'], foreground=colors['fg'],
                       padding=[10, 4])
        style.map('TNotebook.Tab',
                  background=[('selected', colors['bg']), ('active', colors['select_bg'])],
                  foreground=[('selected', colors['fg']), ('active', colors['select_fg'])])
        style.configure('TProgressbar', background=colors['select_bg'], troughcolor=colors['canvas_bg'])
        style.configure('TSeparator', background=colors['border'])
        style.configure('TScale', background=colors['bg'], troughcolor=colors['canvas_bg'])
        style.configure('TScrollbar', background=colors['canvas_bg'], troughcolor=colors['bg'],
                       arrowcolor=colors['fg'])

        # Configure root window
        self.root.configure(bg=colors['bg'])

        # Configure tk widgets (non-ttk) that need explicit colors
        self._apply_theme_to_tk_widgets(colors)

    def _apply_theme_to_tk_widgets(self, colors):
        """Apply theme colors to pure tk widgets that don't use ttk styling"""
        # Tab scrollable canvases
        if hasattr(self, '_tab_canvases'):
            for c in self._tab_canvases:
                c.configure(bg=colors['bg'])

        # Preview labels
        if hasattr(self, 'start_preview_label'):
            self.start_preview_label.configure(bg=colors['preview_bg'], fg=colors['preview_fg'])
        if hasattr(self, 'end_preview_label'):
            self.end_preview_label.configure(bg=colors['preview_bg'], fg=colors['preview_fg'])

        # Clipboard URL list canvas
        if hasattr(self, 'clipboard_url_canvas'):
            self.clipboard_url_canvas.configure(bg=colors['canvas_bg'],
                                                highlightbackground=colors['border'])
        # Uploader file list canvas
        if hasattr(self, 'uploader_file_canvas'):
            self.uploader_file_canvas.configure(bg=colors['canvas_bg'],
                                                highlightbackground=colors['border'])


        # Status indicator canvases in clipboard URL list
        if hasattr(self, 'clipboard_url_widgets'):
            for url, widgets in self.clipboard_url_widgets.items():
                if 'status_canvas' in widgets:
                    widgets['status_canvas'].configure(bg=colors['status_canvas_bg'])

    def _version_newer(self, latest, current):
        """Compare version strings to check if latest is newer than current.

        Args:
            latest: Latest version string (e.g., '3.1.3')
            current: Current version string (e.g., '3.1.2')

        Returns:
            bool: True if latest is newer than current
        """
        try:
            latest_parts = tuple(map(int, latest.split('.')))
            current_parts = tuple(map(int, current.split('.')))
            return latest_parts > current_parts
        except (ValueError, AttributeError):
            return False

    def _check_for_updates_clicked(self):
        """Handle Check for Updates button click"""
        self.thread_pool.submit(self._check_for_updates, False)

    def _check_for_updates(self, silent=True):
        """Check GitHub for new app version and yt-dlp updates.

        Args:
            silent: If True, don't show dialog when up-to-date or on error
        """
        import urllib.request
        import urllib.error

        ytdlp_update_available = False
        ytdlp_current = None
        ytdlp_latest = None

        try:
            logger.info("Checking for updates...")
            if not silent:
                self._safe_after(0, lambda: self.update_status('Checking for updates...', "blue"))

            # Check app update from GitHub
            try:
                request = urllib.request.Request(
                    GITHUB_API_LATEST,
                    headers={'User-Agent': f'YoutubeDownloader/{APP_VERSION}'}
                )
                with urllib.request.urlopen(request, timeout=10) as response:
                    data = json.loads(response.read().decode())

                latest_version = data.get('tag_name', '').lstrip('v')

                if latest_version and self._version_newer(latest_version, APP_VERSION):
                    logger.info(f"App update available: {APP_VERSION} -> {latest_version}")
                    self._safe_after(0, lambda: self._show_update_dialog(latest_version, data))
                    return
                else:
                    logger.info(f"App is up to date: {APP_VERSION}")

            except Exception as e:
                logger.error(f"Error checking app updates: {e}")

            # Check yt-dlp update (PyPI for source, GitHub releases for bundled)
            try:
                ytdlp_current = self._get_ytdlp_version()
                if ytdlp_current:
                    # Get latest version from GitHub releases (works for both modes)
                    request = urllib.request.Request(
                        'https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest',
                        headers={'User-Agent': f'YoutubeDownloader/{APP_VERSION}'}
                    )
                    with urllib.request.urlopen(request, timeout=10) as response:
                        release_data = json.loads(response.read().decode())

                    ytdlp_latest = release_data.get('tag_name', '').lstrip('v')

                    if ytdlp_latest:
                        current_parsed = self._parse_ytdlp_version(ytdlp_current)
                        latest_parsed = self._parse_ytdlp_version(ytdlp_latest)

                        if latest_parsed > current_parsed:
                            logger.info(f"yt-dlp update available: {ytdlp_current} -> {ytdlp_latest}")
                            ytdlp_update_available = True
                        else:
                            logger.info(f"yt-dlp is up to date: {ytdlp_current}")

            except Exception as e:
                logger.error(f"Error checking yt-dlp updates: {e}")

            # Show appropriate dialog based on what was found
            if ytdlp_update_available:
                self._safe_after(0, lambda: self._show_ytdlp_update_dialog(ytdlp_current, ytdlp_latest))
            elif not silent:
                self._safe_after(0, lambda: messagebox.showinfo(
                    'Up to Date',
                    f'You are running the latest version (v{APP_VERSION}).'
                ))

        except urllib.error.URLError as e:
            logger.error(f"Network error checking for updates: {e}")
            if not silent:
                self._safe_after(0, lambda: messagebox.showerror(
                    'Update Error',
                    f'Failed to check for updates:\n{e}'
                ))
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            if not silent:
                self._safe_after(0, lambda: messagebox.showerror(
                    'Update Error',
                    f'Failed to check for updates:\n{e}'
                ))

    def _show_update_dialog(self, latest_version, release_data):
        """Show update available dialog with options.

        Args:
            latest_version: The latest version string
            release_data: The GitHub release API response data
        """
        dialog = tk.Toplevel(self.root)
        dialog.title('Update Available')
        dialog.transient(self.root)
        dialog.grab_set()
        colors = THEMES[self.current_theme]
        dialog.configure(bg=colors['bg'])

        # Center dialog on parent
        dialog.geometry("400x200")
        dialog.resizable(False, False)

        # Message
        msg = f'A new version is available!\n\nCurrent: v{APP_VERSION}\nLatest: v{latest_version}\n\nWould you like to update?'
        ttk.Label(dialog, text=msg, justify=tk.CENTER, wraplength=350).pack(pady=20)

        # Buttons frame
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)

        def update_now():
            dialog.destroy()
            self.thread_pool.submit(self._apply_update, release_data)

        def open_releases():
            dialog.destroy()
            webbrowser.open(GITHUB_RELEASES_URL)

        ttk.Button(btn_frame, text='Update Now', command=update_now).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text='Open Releases Page', command=open_releases).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text='Later', command=dialog.destroy).pack(side=tk.LEFT, padx=5)

        # Center the dialog on screen
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2
        y = (dialog.winfo_screenheight() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

    def _compute_git_blob_sha(self, content):
        """Compute the git blob SHA1 hash for content (same as git hash-object)."""
        import hashlib
        header = f"blob {len(content)}\0".encode()
        return hashlib.sha1(header + content).hexdigest()

    def _verify_file_against_github(self, tag_name, filename, content, headers):
        """Verify downloaded file content matches GitHub's git tree SHA."""
        import urllib.request

        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}?ref={tag_name}"
        request = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            file_info = json.loads(response.read().decode())

        expected_sha = file_info.get('sha', '')
        actual_sha = self._compute_git_blob_sha(content)

        if actual_sha != expected_sha:
            raise RuntimeError(
                f"Integrity check failed for {filename}!\n"
                f"Expected SHA: {expected_sha[:16]}...\n"
                f"Got SHA: {actual_sha[:16]}...\n"
                f"The file may have been tampered with."
            )
        logger.info(f"Integrity verified for {filename}: {actual_sha[:16]}...")

    def _cleanup_old_updates(self):
        """Remove leftover files from previous self-updates (.old exes, .bat trampolines)."""
        try:
            if getattr(sys, 'frozen', False):
                exe_dir = Path(sys.executable).parent
                for pattern in ('*.old', '_update_*.bat', '_update_*.sh'):
                    for stale in exe_dir.glob(pattern):
                        try:
                            stale.unlink()
                            logger.info(f"Cleaned up old update file: {stale}")
                        except OSError:
                            pass
        except Exception as e:
            logger.error(f"Error cleaning old update files: {e}")

    def _is_onedir_frozen(self):
        """Check if running as PyInstaller --onedir (installed) vs --onefile (portable).

        In onedir mode, sys._MEIPASS points to the app directory (same as exe parent).
        In onefile mode, sys._MEIPASS is a temp extraction directory.
        """
        if not getattr(sys, 'frozen', False):
            return False
        meipass = Path(getattr(sys, '_MEIPASS', ''))
        return meipass == Path(sys.executable).parent

    def _get_update_asset_url(self, release_data):
        """Find the download URL for the right release asset for this platform.

        Returns:
            str or None: The browser_download_url for the matching asset
        """
        if sys.platform == 'win32':
            target = 'YTDownloader-Windows.exe'
        else:
            target = 'YTDownloader-Linux.tar.gz'

        for asset in release_data.get('assets', []):
            if asset.get('name') == target:
                return asset['browser_download_url']
        return None

    def _apply_update(self, release_data):
        """Download and apply update, then restart the application.

        Routes to the appropriate strategy based on how the app is running:
        - Source (.py): replace modules, then restart via Python interpreter
        - Frozen portable (onefile): download new exe, rename-dance, restart
        - Frozen installed (onedir): direct user to GitHub releases page
        """
        if getattr(sys, 'frozen', False):
            if self._is_onedir_frozen():
                # Installed version — can't self-update, point to installer
                self._safe_after(0, lambda: messagebox.showinfo(
                    'Update Complete',
                    'Your installed version cannot self-update.\n\nThe releases page will open so you can download the latest installer.'
                ))
                self._safe_after(0, lambda: webbrowser.open(GITHUB_RELEASES_URL))
            else:
                self._apply_update_frozen(release_data)
        else:
            self._apply_update_source(release_data)

    def _apply_update_source(self, release_data):
        """Download, verify, and replace .py source files, then auto-restart."""
        import urllib.request
        import shutil
        import tempfile

        try:
            self._safe_after(0, lambda: self.update_status('Downloading update...', "blue"))

            tag_name = release_data.get('tag_name', 'main')
            headers = {'User-Agent': f'YoutubeDownloader/{APP_VERSION}'}
            current_script = Path(__file__).resolve()
            script_dir = current_script.parent

            modules = ['downloader.py', 'constants.py']
            downloaded = {}

            # Download and verify all modules before replacing any
            for module_name in modules:
                download_url = f"{GITHUB_RAW_URL}/{tag_name}/{module_name}"
                logger.info(f"Downloading: {download_url}")
                request = urllib.request.Request(download_url, headers=headers)

                with urllib.request.urlopen(request, timeout=60) as response:
                    content = response.read()

                self._verify_file_against_github(tag_name, module_name, content, headers)

                try:
                    compile(content, module_name, 'exec')
                except SyntaxError as e:
                    raise RuntimeError(f"{module_name} has syntax errors: {e}")

                downloaded[module_name] = content

            # All verified — backup and replace
            for module_name, content in downloaded.items():
                module_path = script_dir / module_name
                backup_path = module_path.with_suffix('.py.backup')
                if module_path.exists():
                    shutil.copy2(module_path, backup_path)
                    logger.info(f"Created backup: {backup_path}")

                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(mode='wb', suffix='.py', delete=False,
                                                      dir=str(script_dir)) as tmp_file:
                        tmp_file.write(content)
                        tmp_path = tmp_file.name
                    shutil.move(tmp_path, module_path)
                    logger.info(f"Updated: {module_path}")
                except Exception:
                    if tmp_path and os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    raise

            # Auto-restart: spawn new process, then shut down
            self._safe_after(0, lambda: self.update_status('Update complete — restarting...', "green"))
            logger.info("Restarting after source update...")

            def _do_restart():
                subprocess.Popen([sys.executable] + sys.argv)
                self.on_closing()

            self._safe_after(500, _do_restart)

        except Exception as e:
            logger.error(f"Error applying update: {e}")
            self._safe_after(0, lambda: messagebox.showerror(
                'Update Failed',
                f'Failed to download update:\n{e}'
            ))

    def _apply_update_frozen(self, release_data):
        """Self-update a frozen portable exe via download + rename-and-replace."""
        import urllib.request

        try:
            self._safe_after(0, lambda: self.update_status('Downloading update...', "blue"))

            download_url = self._get_update_asset_url(release_data)
            if not download_url:
                raise RuntimeError("Could not find a download for this platform in the release.")

            headers = {'User-Agent': f'YoutubeDownloader/{APP_VERSION}'}
            exe_path = Path(sys.executable).resolve()

            if sys.platform == 'win32':
                self._apply_update_frozen_windows(download_url, headers, exe_path)
            else:
                self._apply_update_frozen_linux(download_url, headers, exe_path)

        except Exception as e:
            logger.error(f"Error applying frozen update: {e}")
            self._safe_after(0, lambda: messagebox.showerror(
                'Update Failed',
                f'Failed to download update:\n{e}'
            ))

    def _apply_update_frozen_windows(self, download_url, headers, exe_path):
        """Windows portable exe update: rename-dance with .bat trampoline fallback."""
        import urllib.request

        new_exe = exe_path.with_suffix('.exe.new')
        old_exe = exe_path.with_name(exe_path.stem + '.old')

        # Download the new exe with progress
        logger.info(f"Downloading update: {download_url}")
        self._safe_after(0, lambda: self.update_status('Downloading update... please wait', "blue"))
        request = urllib.request.Request(download_url, headers=headers)
        with urllib.request.urlopen(request, timeout=300) as response:
            total = int(response.headers.get('Content-Length', 0))
            chunks = []
            downloaded = 0
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = int(downloaded / total * 100)
                    mb = downloaded / (1024 * 1024)
                    total_mb = total / (1024 * 1024)
                    self._safe_after(0, lambda p=pct, m=mb, t=total_mb: self.update_status(
                        f'Downloading update... {m:.1f}/{t:.1f} MB ({p}%)', "blue"))
            content = b''.join(chunks)

        if len(content) < 1024:
            raise RuntimeError("Downloaded file is too small — likely corrupted.")

        new_exe.write_bytes(content)
        logger.info(f"Downloaded new exe: {new_exe} ({len(content):,} bytes)")

        # Rename dance: running.exe → .old, .new → running.exe
        try:
            if old_exe.exists():
                old_exe.unlink()
            exe_path.rename(old_exe)
            logger.info(f"Renamed running exe aside: {exe_path} → {old_exe}")

            try:
                new_exe.rename(exe_path)
                logger.info(f"Moved new exe into place: {new_exe} → {exe_path}")
            except Exception:
                # Restore if moving new exe into place fails
                if old_exe.exists() and not exe_path.exists():
                    old_exe.rename(exe_path)
                raise

            # Success — spawn new exe via cmd with delay so old process exits first
            self._safe_after(0, lambda: self.update_status('Update complete — restarting...', "green"))

            def _do_restart():
                logger.info(f"Launching updated exe: {exe_path}")
                subprocess.Popen(
                    f'cmd /c timeout /t 2 /nobreak >nul & start "" "{exe_path}"',
                    shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                self.on_closing()

            self._safe_after(500, _do_restart)

        except OSError as rename_err:
            # Rename failed (rare) — fall back to .bat trampoline
            logger.warning(f"Rename failed ({rename_err}), falling back to bat trampoline")
            self._launch_bat_trampoline(exe_path, new_exe)

    def _launch_bat_trampoline(self, exe_path, new_exe):
        """Write a .bat that waits for us to exit, swaps the exe, and relaunches."""
        import time as _time

        bat_path = exe_path.parent / f'_update_{int(_time.time())}.bat'
        bat_content = (
            '@echo off\r\n'
            'timeout /t 2 /noblock >nul\r\n'
            f'move /y "{new_exe}" "{exe_path}"\r\n'
            f'start "" "{exe_path}"\r\n'
            'del "%~f0"\r\n'
        )
        bat_path.write_text(bat_content)
        logger.info(f"Wrote update trampoline: {bat_path}")

        self._safe_after(0, lambda: self.update_status('Update complete — restarting...', "green"))

        def _do_restart():
            subprocess.Popen(
                ['cmd', '/c', str(bat_path)],
                creationflags=subprocess.CREATE_NO_WINDOW,
                close_fds=True,
            )
            self.on_closing()

        self._safe_after(500, _do_restart)

    def _apply_update_frozen_linux(self, download_url, headers, exe_path):
        """Linux portable binary update: download tar.gz, extract, replace in place."""
        import urllib.request
        import tarfile
        import io
        import shutil
        import tempfile

        logger.info(f"Downloading update: {download_url}")
        request = urllib.request.Request(download_url, headers=headers)
        with urllib.request.urlopen(request, timeout=300) as response:
            content = response.read()

        if len(content) < 1024:
            raise RuntimeError("Downloaded file is too small — likely corrupted.")

        logger.info(f"Downloaded tar.gz ({len(content):,} bytes), extracting...")

        with tarfile.open(fileobj=io.BytesIO(content), mode='r:gz') as tar:
            # Find the binary inside the archive
            binary_member = None
            for member in tar.getmembers():
                if member.isfile() and 'YTDownloader' in member.name:
                    binary_member = member
                    break

            if not binary_member:
                raise RuntimeError("Could not find YTDownloader binary in archive.")

            # Extract just the binary content (safe — no path traversal)
            f = tar.extractfile(binary_member)
            if not f:
                raise RuntimeError("Could not read binary from archive.")
            binary_content = f.read()

        # Write to temp file next to exe, then atomically move into place
        # (Linux allows replacing a running binary — the OS keeps the old inode open)
        with tempfile.NamedTemporaryFile(delete=False, dir=str(exe_path.parent)) as tmp:
            tmp.write(binary_content)
            tmp_path = Path(tmp.name)

        shutil.move(str(tmp_path), str(exe_path))
        os.chmod(str(exe_path), 0o755)
        logger.info(f"Replaced binary: {exe_path}")

        # Spawn new binary and shut down
        self._safe_after(0, lambda: self.update_status('Update complete — restarting...', "green"))

        def _do_restart():
            logger.info(f"Launching updated binary: {exe_path}")
            subprocess.Popen([str(exe_path)])
            self.on_closing()

        self._safe_after(500, _do_restart)

    def _get_ytdlp_version(self):
        """Get the current yt-dlp version.

        Returns:
            str: Version string (e.g., '2025.12.08') or None if failed
        """
        try:
            result = subprocess.run(
                [self.ytdlp_path, '--version'],
                capture_output=True,
                timeout=10,
                **_subprocess_kwargs
            )
            if result.returncode == 0:
                return result.stdout.decode('utf-8', errors='replace').strip()
        except Exception as e:
            logger.error(f"Error getting yt-dlp version: {e}")
        return None

    def _get_pip_path(self):
        """Get the pip path for the venv.

        Returns:
            str: Path to pip executable or None
        """
        script_dir = Path(__file__).parent
        if sys.platform == 'win32':
            pip_path = script_dir / 'venv' / 'Scripts' / 'pip.exe'
        else:
            pip_path = script_dir / 'venv' / 'bin' / 'pip'

        if pip_path.exists():
            return str(pip_path)

        # Try current Python's pip
        python_bin = Path(sys.executable).parent
        if sys.platform == 'win32':
            pip_path = python_bin / 'pip.exe'
        else:
            pip_path = python_bin / 'pip'

        if pip_path.exists():
            return str(pip_path)

        return None

    def _parse_ytdlp_version(self, version_str):
        """Parse yt-dlp version string into comparable tuple.

        Args:
            version_str: Version string (e.g., '2026.02.04')

        Returns:
            tuple: Version as tuple of integers (e.g., (2026, 2, 4))
        """
        try:
            return tuple(int(part) for part in version_str.split('.'))
        except (ValueError, AttributeError):
            return (0,)

    def _show_ytdlp_update_dialog(self, current_version, latest_version):
        """Show yt-dlp update available dialog."""
        result = messagebox.askyesno(
            'yt-dlp Update Available',
            f'A new version of yt-dlp is available!\n\nCurrent: {current_version}\nLatest: {latest_version}\n\nThis may fix download issues.\nUpdate now?'
        )

        if result:
            if getattr(sys, 'frozen', False):
                self.thread_pool.submit(self._apply_ytdlp_update_binary, latest_version)
            else:
                pip_path = self._get_pip_path()
                if pip_path:
                    self.thread_pool.submit(self._apply_ytdlp_update_pip, pip_path)
                else:
                    messagebox.showwarning(
                        'Update Not Supported',
                        'Cannot auto-update yt-dlp in this mode.\n\nPlease update yt-dlp manually or download the latest app release.'
                    )

    def _apply_ytdlp_update_pip(self, pip_path):
        """Apply yt-dlp update using pip (when running from source)."""
        try:
            logger.info("Updating yt-dlp via pip...")
            self._safe_after(0, lambda: self.update_status('Updating yt-dlp...', "blue"))

            result = subprocess.run(
                [pip_path, 'install', '--upgrade', 'yt-dlp'],
                capture_output=True,
                timeout=120,
                **_subprocess_kwargs
            )

            if result.returncode == 0:
                new_version = self._get_ytdlp_version() or "unknown"
                logger.info(f"yt-dlp updated successfully to {new_version}")

                self._safe_after(0, lambda: self.update_status(
                    f'Current yt-dlp: {new_version}', "green"
                ))
                self._safe_after(0, lambda: messagebox.showinfo(
                    'yt-dlp Updated',
                    f'yt-dlp has been updated to version {new_version}.'
                ))
            else:
                error_msg = result.stderr.decode('utf-8', errors='replace').strip() or result.stdout.decode('utf-8', errors='replace').strip()
                raise RuntimeError(error_msg or "pip returned non-zero exit code")

        except subprocess.TimeoutExpired:
            logger.error("yt-dlp update timed out")
            self._safe_after(0, lambda: messagebox.showerror(
                'yt-dlp Update Failed',
                'Failed to update yt-dlp:\n\nUpdate timed out'
            ))
        except Exception as e:
            logger.error(f"Error updating yt-dlp: {e}")
            self._safe_after(0, lambda: messagebox.showerror(
                'yt-dlp Update Failed',
                f'Failed to update yt-dlp:\n\n{e}'
            ))

    def _apply_ytdlp_update_binary(self, latest_version):
        """Download latest yt-dlp binary from GitHub releases with SHA256 verification."""
        import urllib.request
        import hashlib

        try:
            logger.info("Downloading latest yt-dlp binary...")
            self._safe_after(0, lambda: self.update_status('Updating yt-dlp...', "blue"))

            headers = {'User-Agent': f'YoutubeDownloader/{APP_VERSION}'}
            exe_dir = os.path.dirname(sys.executable)

            if sys.platform == 'win32':
                binary_name = 'yt-dlp.exe'
                download_url = f'https://github.com/yt-dlp/yt-dlp/releases/latest/download/{binary_name}'
                target_path = os.path.join(exe_dir, binary_name)
            else:
                binary_name = 'yt-dlp'
                download_url = f'https://github.com/yt-dlp/yt-dlp/releases/latest/download/{binary_name}'
                target_path = os.path.join(exe_dir, binary_name)

            # Download SHA256SUMS from yt-dlp releases
            sha256sums_url = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/SHA2-256SUMS'
            sha_request = urllib.request.Request(sha256sums_url, headers=headers)
            with urllib.request.urlopen(sha_request, timeout=30) as response:
                sha256sums = response.read().decode('utf-8')

            # Find expected hash for our binary
            expected_hash = None
            for line in sha256sums.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1] == binary_name:
                    expected_hash = parts[0].lower()
                    break

            if not expected_hash:
                raise RuntimeError(f"Could not find SHA256 for {binary_name} in SHA2-256SUMS")
            logger.info(f"Expected SHA256 for {binary_name}: {expected_hash[:16]}...")

            # Download the binary
            tmp_fd = tempfile.NamedTemporaryFile(dir=exe_dir, delete=False, suffix='.tmp')
            tmp_path = tmp_fd.name
            tmp_fd.close()

            request = urllib.request.Request(download_url, headers=headers)
            with urllib.request.urlopen(request, timeout=120) as response:
                with open(tmp_path, 'wb') as f:
                    shutil.copyfileobj(response, f)

            # Verify SHA256
            with open(tmp_path, 'rb') as f:
                actual_hash = hashlib.sha256(f.read()).hexdigest().lower()

            if actual_hash != expected_hash:
                os.remove(tmp_path)
                raise RuntimeError(
                    f"SHA256 verification failed for {binary_name}!\n"
                    f"Expected: {expected_hash[:32]}...\n"
                    f"Got: {actual_hash[:32]}...\n"
                    f"The file may have been tampered with."
                )
            logger.info(f"SHA256 verified for {binary_name}: {actual_hash[:16]}...")

            # Replace the old binary
            if os.path.exists(target_path):
                os.remove(target_path)
            os.rename(tmp_path, target_path)

            # Make executable on Linux
            if sys.platform != 'win32':
                os.chmod(target_path, 0o755)

            # Update the path so the app uses the new binary immediately
            self.ytdlp_path = target_path

            new_version = self._get_ytdlp_version() or latest_version
            logger.info(f"yt-dlp binary updated successfully to {new_version}")

            self._safe_after(0, lambda: self.update_status(
                f'Current yt-dlp: {new_version}', "green"
            ))
            self._safe_after(0, lambda: messagebox.showinfo(
                'yt-dlp Updated',
                f'yt-dlp has been updated to version {new_version}.'
            ))

        except Exception as e:
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            logger.error(f"Error downloading yt-dlp binary: {e}")
            self._safe_after(0, lambda: messagebox.showerror(
                'yt-dlp Update Failed',
                f'Failed to update yt-dlp:\n\n{e}'
            ))

    def save_upload_link(self, link, filename=""):
        """Save uploaded video link to history file"""
        try:
            UPLOAD_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(UPLOAD_HISTORY_FILE, 'a', encoding='utf-8') as f:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{timestamp} | {filename} | {link}\n")
            # Trim history file if it exceeds 1000 lines (keep last 500)
            try:
                with open(UPLOAD_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                if len(lines) > 1000:
                    with open(UPLOAD_HISTORY_FILE, 'w', encoding='utf-8') as f:
                        f.writelines(lines[-500:])
                    logger.info("Trimmed upload history to last 500 entries")
            except Exception as trim_err:
                logger.error(f"Error trimming upload history: {trim_err}")
            logger.info(f"Saved upload link to history: {link}")
        except Exception as e:
            logger.error(f"Error saving upload link: {e}")

    def view_upload_history(self):
        """View upload link history in a new window"""
        history_window = tk.Toplevel(self.root)
        history_window.title('Upload Link History')
        history_window.geometry("800x500")
        history_window.configure(bg=THEMES[self.current_theme]['bg'])

        # Create text widget with scrollbar
        frame = ttk.Frame(history_window, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        theme_colors = THEMES[self.current_theme]
        text_widget = tk.Text(frame, wrap=tk.WORD, yscrollcommand=scrollbar.set, font=('Consolas', 9),
                             bg=theme_colors['entry_bg'], fg=theme_colors['entry_fg'],
                             insertbackground=theme_colors['fg'])
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)

        # Load and display history
        try:
            if UPLOAD_HISTORY_FILE.exists():
                with open(UPLOAD_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content:
                        text_widget.insert('1.0', content)
                    else:
                        text_widget.insert('1.0', 'No upload history yet.')
            else:
                text_widget.insert('1.0', 'No upload history yet.')
        except Exception as e:
            text_widget.insert('1.0', f'Error loading history: {e}')

        text_widget.config(state='disabled')  # Make read-only

        # Add copy and clear buttons
        button_frame = ttk.Frame(history_window, padding="10")
        button_frame.pack(fill=tk.X)

        def copy_all():
            self.root.clipboard_clear()
            self.root.clipboard_append(text_widget.get('1.0', tk.END))
            messagebox.showinfo('Copied', 'History copied to clipboard!')

        def clear_history():
            if messagebox.askyesno('Clear History', 'Are you sure you want to clear all upload history?'):
                try:
                    if UPLOAD_HISTORY_FILE.exists():
                        UPLOAD_HISTORY_FILE.unlink()
                    text_widget.config(state='normal')
                    text_widget.delete('1.0', tk.END)
                    text_widget.insert('1.0', 'No upload history yet.')
                    text_widget.config(state='disabled')
                except Exception as e:
                    messagebox.showerror('Error', f'Failed to clear history: {e}')

        ttk.Button(button_frame, text='Copy All', command=copy_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text='Clear History', command=clear_history).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text='Close', command=history_window.destroy).pack(side=tk.RIGHT, padx=5)

    def retry_network_operation(self, operation, operation_name, *args, **kwargs):
        """Retry a network operation with exponential backoff"""
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                return operation(*args, **kwargs)
            except subprocess.TimeoutExpired as e:
                if attempt == MAX_RETRY_ATTEMPTS:
                    logger.error(f"{operation_name} failed after {MAX_RETRY_ATTEMPTS} attempts: timeout")
                    raise
                logger.warning(f"{operation_name} timeout (attempt {attempt}/{MAX_RETRY_ATTEMPTS}), retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY * attempt)  # Exponential backoff
            except subprocess.CalledProcessError as e:
                if attempt == MAX_RETRY_ATTEMPTS:
                    logger.error(f"{operation_name} failed after {MAX_RETRY_ATTEMPTS} attempts: {e}")
                    raise
                logger.warning(f"{operation_name} failed (attempt {attempt}/{MAX_RETRY_ATTEMPTS}), retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY * attempt)
            except Exception as e:
                # Don't retry on unexpected errors
                logger.error(f"{operation_name} failed with unexpected error: {e}")
                raise

    # Security and validation methods

    @staticmethod
    def sanitize_filename(filename):
        """Sanitize filename to prevent path traversal and command injection.

        Removes:
        - Path separators (/, \\\\)
        - Parent directory references (..)
        - Shell metacharacters
        - Control characters
        - Leading/trailing dots and spaces
        """
        if not filename:
            return ""

        # Remove path separators and null bytes
        for char in ['/', '\\', '\x00']:
            filename = filename.replace(char, '')
        # Remove parent directory references (loop to handle '....' -> '..' -> '')
        while '..' in filename:
            filename = filename.replace('..', '')

        # Remove shell metacharacters that could be dangerous
        shell_chars = ['$', '`', '|', ';', '&', '<', '>', '(', ')', '{', '}', '[', ']', '!', '*', '?', '~', '^']
        for char in shell_chars:
            filename = filename.replace(char, '')

        # Remove control characters (ASCII 0-31 and 127)
        filename = ''.join(char for char in filename if ord(char) >= 32 and ord(char) != 127)

        # Remove leading/trailing dots and spaces
        filename = filename.strip('. ')

        # Limit length to filesystem limits
        if len(filename) > MAX_FILENAME_LENGTH:
            filename = filename[:MAX_FILENAME_LENGTH]

        return filename

    @staticmethod
    def validate_download_path(path):
        """Validate download path to prevent path traversal attacks.

        Args:
            path: The path to validate

        Returns:
            tuple: (is_valid, normalized_path, error_message)
        """
        try:
            # Normalize the path
            normalized = os.path.normpath(os.path.abspath(path))
            normalized_path = Path(normalized)

            # Check for path traversal attempts in both original and normalized path
            if '..' in path or '..' in normalized:
                return (False, None, "Path contains directory traversal sequences")

            # Ensure the path is within user's home directory or common safe locations
            home_dir = Path.home()
            safe_dirs = [
                home_dir,
                Path('/tmp'),
                Path(os.path.expandvars('$TEMP')) if sys.platform == 'win32' else Path('/tmp'),
            ]

            # Use is_relative_to for proper path containment check (not just prefix matching)
            is_safe = False
            for safe_dir in safe_dirs:
                try:
                    safe_resolved = safe_dir.resolve()
                    normalized_path.resolve().relative_to(safe_resolved)
                    is_safe = True
                    break
                except ValueError:
                    continue

            if not is_safe:
                return (False, None, "Download path must be within home directory or temp folder")

            return (True, normalized, None)
        except Exception as e:
            return (False, None, f"Path validation error: {str(e)}")

    @staticmethod
    def validate_config_json(config):
        """Validate configuration JSON structure.

        Args:
            config: The parsed JSON config dict

        Returns:
            bool: True if config is valid, False otherwise
        """
        if not isinstance(config, dict):
            return False

        # Define allowed keys and their expected types
        allowed_keys = {
            'auto_check_updates': bool,
            'theme': str,
        }

        for key, value in config.items():
            if key not in allowed_keys:
                logger.warning(f"Unknown config key ignored: {key}")
                continue
            expected_type = allowed_keys[key]
            if not isinstance(value, expected_type):
                logger.warning(f"Config key '{key}' has wrong type, expected {expected_type.__name__}")
                return False

        return True

    @staticmethod
    def validate_volume(volume):
        """Validate and clamp volume value to safe range."""
        try:
            vol = float(volume)
            return max(MIN_VOLUME, min(MAX_VOLUME, vol))
        except (ValueError, TypeError):
            return 1.0  # Default to 100%

    @staticmethod
    def validate_time(time_str):
        """Validate time format HH:MM:SS and return seconds, or None if invalid."""
        if not time_str:
            return None

        match = TIME_REGEX.match(time_str.strip())
        if not match:
            return None

        hours, minutes, seconds = map(int, match.groups())
        if minutes >= 60 or seconds >= 60:
            return None

        total_seconds = hours * 3600 + minutes * 60 + seconds
        if total_seconds > MAX_VIDEO_DURATION:
            return None

        return total_seconds

    @staticmethod
    def validate_time_range(start_seconds, end_seconds, duration):
        """Validate that time range is logical and within bounds."""
        if start_seconds is None or end_seconds is None or duration is None:
            return False

        if start_seconds < 0 or end_seconds < 0:
            return False

        if start_seconds >= end_seconds:
            return False

        if end_seconds > duration:
            return False

        return True

    @staticmethod
    def safe_process_cleanup(process, timeout=PROCESS_TERMINATE_TIMEOUT):
        """Safely terminate and cleanup a subprocess.

        Args:
            process: subprocess.Popen instance
            timeout: Seconds to wait for graceful termination

        Returns:
            bool: True if process was cleaned up successfully
        """
        if process is None:
            return True

        try:
            if process.poll() is None:  # Process still running
                process.terminate()
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    logger.warning(f"Process {process.pid} did not terminate, forcing kill")
                    process.kill()
                    process.wait()

            # Close pipes to prevent resource leaks
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
            if process.stdin:
                process.stdin.close()

            return True
        except Exception as e:
            logger.error(f"Error cleaning up process: {e}")
            return False

    # Command building helper methods

    def build_base_ytdlp_command(self):
        """Build base yt-dlp command with common options.

        Returns:
            list: Base command with common flags
        """
        return [
            self.ytdlp_path,
            '--concurrent-fragments', CONCURRENT_FRAGMENTS,
            '--buffer-size', BUFFER_SIZE,
            '--http-chunk-size', CHUNK_SIZE,
            '--newline',
            '--progress',
        ]

    def build_audio_ytdlp_command(self, url, output_path, volume=1.0):
        """Build yt-dlp command for audio-only download.

        Args:
            url: YouTube URL
            output_path: Full output path with filename template
            volume: Volume multiplier (default 1.0)

        Returns:
            list: Complete command for audio download
        """
        cmd = self.build_base_ytdlp_command()
        cmd.extend([
            '-f', 'bestaudio',
            '--extract-audio',
            '--audio-format', 'mp3',
            '--audio-quality', AUDIO_BITRATE,
        ])

        # Add volume filter if needed
        if volume != 1.0:
            cmd.extend(['--postprocessor-args', f'ffmpeg:-af volume={volume}'])

        cmd.extend(['-o', output_path, url])
        return cmd

    def build_video_ytdlp_command(self, url, output_path, quality, volume=1.0,
                                    trim_start=None, trim_end=None):
        """Build yt-dlp command for video download with optional trimming.

        Args:
            url: YouTube URL
            output_path: Full output path with filename template
            quality: Video height (e.g., '1080', '720')
            volume: Volume multiplier (default 1.0)
            trim_start: Start time in seconds (optional)
            trim_end: End time in seconds (optional)

        Returns:
            list: Complete command for video download
        """
        cmd = self.build_base_ytdlp_command()
        cmd.extend([
            '-f', f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]',
            '--merge-output-format', 'mp4',
        ])

        # Add trimming if specified
        trim_enabled = trim_start is not None and trim_end is not None
        if trim_enabled:
            start_hms = self.seconds_to_hms(trim_start)
            end_hms = self.seconds_to_hms(trim_end)
            cmd.extend([
                '--download-sections', f'*{start_hms}-{end_hms}',
                '--force-keyframes-at-cuts',
            ])

        # Build ffmpeg postprocessor args if needed
        needs_processing = trim_enabled or volume != 1.0
        if needs_processing:
            ffmpeg_args = self._get_video_encoder_args(mode='crf') + ['-c:a', 'aac', '-b:a', AUDIO_BITRATE]
            if volume != 1.0:
                ffmpeg_args.extend(['-af', f'volume={volume}'])

            cmd.extend(['--postprocessor-args', 'ffmpeg:' + ' '.join(ffmpeg_args)])

        cmd.extend(['-o', output_path, url])
        return cmd

    def validate_youtube_url(self, url):
        """Validate if URL is a valid YouTube URL"""
        if not url:
            return False, 'URL is empty'
        if len(url) > 2048:
            return False, 'URL is too long'

        try:
            parsed = urlparse(url)

            # Check for valid YouTube domains
            valid_domains = [
                'youtube.com', 'www.youtube.com', 'm.youtube.com',
                'youtu.be', 'www.youtu.be'
            ]

            if parsed.netloc not in valid_domains:
                return False, 'Not a YouTube URL. Please enter a valid YouTube link.'

            # For youtu.be short links
            if 'youtu.be' in parsed.netloc:
                if not parsed.path or parsed.path == '/':
                    return False, 'Invalid YouTube short URL'
                return True, 'Valid YouTube URL'

            # For youtube.com links
            if 'youtube.com' in parsed.netloc:
                # Check for /watch?v= format
                if '/watch' in parsed.path:
                    query_params = parse_qs(parsed.query)
                    if 'v' not in query_params:
                        return False, 'Missing video ID in URL'
                    return True, 'Valid YouTube URL'

                # Check for /shorts/ format
                elif '/shorts/' in parsed.path:
                    return True, 'Valid YouTube Shorts URL'

                # Check for /embed/ format
                elif '/embed/' in parsed.path:
                    return True, 'Valid YouTube embed URL'

                # Check for /v/ format (old style)
                elif '/v/' in parsed.path:
                    return True, 'Valid YouTube URL'

                # Check for playlist
                elif '/playlist' in parsed.path or 'list=' in parsed.query:
                    return True, 'Valid YouTube Playlist URL'

                else:
                    return False, 'Unrecognized YouTube URL format'

            return False, 'Invalid URL format'

        except Exception as e:
            logger.error(f"URL validation error: {e}")
            return False, f"Invalid URL format: {str(e)}"

    def is_playlist_url(self, url):
        """Check if URL is a YouTube playlist"""
        try:
            parsed = urlparse(url)
            # Check for playlist in path or list parameter in query
            if '/playlist' in parsed.path:
                return True
            query_params = parse_qs(parsed.query)
            if 'list=' in parsed.query and query_params.get('list'):
                return True
            return False
        except (ValueError, AttributeError):
            return False

    def is_pure_playlist_url(self, url):
        """Check if URL is a pure playlist URL (e.g. /playlist?list=YYY) without a video context."""
        try:
            parsed = urlparse(url)
            return '/playlist' in parsed.path
        except (ValueError, AttributeError):
            return False

    def strip_playlist_params(self, url):
        """Strip playlist-related params (list, index) from a URL, keeping the video context."""
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query, keep_blank_values=True)
            params.pop('list', None)
            params.pop('index', None)
            # Flatten single-value lists for urlencode
            flat_params = {k: v[0] if len(v) == 1 else v for k, v in params.items()}
            new_query = urlencode(flat_params, doseq=True)
            return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
        except (ValueError, AttributeError):
            return url

    def _init_temp_directory(self):
        """Initialize temp directory and clean up orphaned ones from previous crashes"""
        # Clean up old orphaned temp directories
        temp_base = tempfile.gettempdir()
        old_dirs = glob.glob(os.path.join(temp_base, "ytdl_preview_*"))
        for old_dir in old_dirs:
            try:
                # Only remove if older than TEMP_DIR_MAX_AGE (to avoid conflicts with other instances)
                dir_age = time.time() - os.path.getmtime(old_dir)
                if dir_age > TEMP_DIR_MAX_AGE:
                    shutil.rmtree(old_dir, ignore_errors=True)
            except OSError:
                pass  # Directory may have been removed by another process

        # Create new temp directory
        self.temp_dir = tempfile.mkdtemp(prefix="ytdl_preview_")

    def setup_ui(self):
        """Setup the complete user interface with all tabs and widgets.

        Creates a tabbed interface with three main tabs:
        - Trimmer: Video download, trimming, and preview
        - Clipboard Mode: Automatic URL detection and batch downloading
        - Uploader: File upload to Catbox.moe

        Features:
        - Scrollable canvas for all content
        - Mouse wheel scrolling support
        - Responsive layout with proper grid configuration
        """
        # Configure root grid to expand
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Apply theme before creating widgets
        self._apply_theme()

        # Create notebook directly in root
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))

        # Tab padding - smaller on Windows to reduce wasted space
        tab_pad = "10" if sys.platform == 'win32' else "20"

        # Helper: create a scrollable tab frame
        def make_scrollable_tab(notebook, tab_text):
            outer = ttk.Frame(notebook)
            notebook.add(outer, text=tab_text)
            outer.grid_rowconfigure(0, weight=1)
            outer.grid_columnconfigure(0, weight=1)

            canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0, bg=THEMES[self.current_theme]['bg'])
            scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
            inner = ttk.Frame(canvas, padding=tab_pad)

            window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)

            canvas.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))

            # Expand inner frame to fill canvas width
            def on_canvas_configure(event):
                canvas.itemconfig(window_id, width=event.width)
            canvas.bind('<Configure>', on_canvas_configure)

            # Update scroll region and show/hide scrollbar as needed
            def on_inner_configure(event):
                canvas.configure(scrollregion=canvas.bbox("all"))
                # Show scrollbar only when content overflows
                if inner.winfo_reqheight() > canvas.winfo_height():
                    scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
                else:
                    scrollbar.grid_remove()
            inner.bind('<Configure>', on_inner_configure)

            # Mouse wheel scrolling
            def _on_mousewheel(event):
                canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            def _on_mousewheel_linux(event):
                if event.num == 4:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.yview_scroll(1, "units")

            def bind_scroll(widget):
                widget.bind("<MouseWheel>", _on_mousewheel)
                widget.bind("<Button-4>", _on_mousewheel_linux)
                widget.bind("<Button-5>", _on_mousewheel_linux)
                for child in widget.winfo_children():
                    bind_scroll(child)

            canvas.bind("<MouseWheel>", _on_mousewheel)
            canvas.bind("<Button-4>", _on_mousewheel_linux)
            canvas.bind("<Button-5>", _on_mousewheel_linux)
            self.root.after(UI_INITIAL_DELAY_MS, lambda: bind_scroll(inner))

            # Store canvas ref for theming
            if not hasattr(self, '_tab_canvases'):
                self._tab_canvases = []
            self._tab_canvases.append(canvas)

            return inner

        # Clipboard Mode tab
        clipboard_tab_frame = make_scrollable_tab(self.notebook, "  Clipboard Mode  ")

        # Trimmer tab
        main_tab_frame = make_scrollable_tab(self.notebook, "  Trimmer  ")

        # Uploader tab
        uploader_tab_frame = make_scrollable_tab(self.notebook, "  Uploader  ")

        # Spacer tab (disabled, dynamically sized to push Settings/Help right)
        spacer = ttk.Frame(self.notebook)
        self.notebook.add(spacer, text="", state='disabled')
        self._spacer_tab_index = self.notebook.index('end') - 1

        # Settings tab
        settings_tab_frame = make_scrollable_tab(self.notebook, "  Settings  ")

        # Help tab with red indicator
        help_tab_frame = make_scrollable_tab(self.notebook, "  Help  ")
        self._help_tab_nb_index = self.notebook.index('end') - 1
        # Create small red circle image for Help tab
        help_icon = Image.new('RGB', (8, 8), color='#cc3333')
        self._help_icon_ref = ImageTk.PhotoImage(help_icon)
        self.notebook.tab(self._help_tab_nb_index, image=self._help_icon_ref, compound='left')

        # Dynamically resize spacer to right-align Settings/Help
        def _update_spacer_width(event=None):
            self.notebook.update_idletasks()
            total_w = self.notebook.winfo_width()
            if total_w < 50:
                return
            # Measure width of all real tabs (approximate via tab count * avg width)
            # Use a binary-search-like approach: set spacer text and check if it fits
            # Simpler: calculate available space and fill with spaces
            # Each space in the tab header is roughly 4-7px depending on font
            space_char_w = 6  # approximate width of a space in tab font
            # Width of left tabs (Clipboard Mode + Trimmer + Uploader) ≈ 300px
            # Width of right tabs (Settings + Help) ≈ 160px
            right_tabs_w = 180
            left_tabs_w = 310 if sys.platform == 'win32' else 400
            available = total_w - left_tabs_w - right_tabs_w - 20
            num_spaces = max(1, int(available / space_char_w))
            self.notebook.tab(self._spacer_tab_index, text=" " * num_spaces)

        self.notebook.bind('<Configure>', _update_spacer_width)
        self.root.after(200, _update_spacer_width)

        ttk.Label(main_tab_frame, text='YouTube URL or Local File:', font=('Arial', 12)).grid(row=0, column=0, sticky=tk.W, pady=(0, 10))

        # URL/File input frame
        url_input_frame = ttk.Frame(main_tab_frame)
        url_input_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        self.url_entry = ttk.Entry(url_input_frame, width=50)
        self.url_entry.pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True)
        self.url_entry.bind('<KeyRelease>', self.on_url_change)

        ttk.Button(url_input_frame, text='Browse Local File', command=self.browse_local_file).pack(side=tk.LEFT)

        # Mode indicator label
        self.mode_label = ttk.Label(main_tab_frame, text="", foreground="green", font=('Arial', 9))
        self.mode_label.grid(row=2, column=0, sticky=tk.W, pady=(0, 10))

        # Video Quality section - dropdown
        quality_frame = ttk.Frame(main_tab_frame)
        quality_frame.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(10, 5))

        ttk.Label(quality_frame, text='Video Quality:', font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=(0, 10))

        self.quality_var = tk.StringVar(value="480")
        self.quality_var.trace_add('write', self.on_quality_change)

        quality_options = ["1440", "1080", "720", "480", "360", "240", "none (Audio only)"]
        self.quality_combo = ttk.Combobox(quality_frame, textvariable=self.quality_var,
            values=quality_options, state='readonly', width=20)
        self.quality_combo.pack(side=tk.LEFT)

        self.keep_below_10mb_var = tk.BooleanVar(value=False)
        self.keep_below_10mb_check = ttk.Checkbutton(
            quality_frame, text='Keep video below 10MB',
            variable=self.keep_below_10mb_var,
            command=self._on_keep_below_10mb_toggle)
        self.keep_below_10mb_check.pack(side=tk.LEFT, padx=(20, 0))

        ttk.Separator(main_tab_frame, orient='horizontal').grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)

        # Trimming section with Volume Control on the right
        trim_and_volume_row = ttk.Frame(main_tab_frame)
        trim_and_volume_row.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 3))

        # Left side: Trim Video
        ttk.Label(trim_and_volume_row, text='Trim Video:', font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=(0, 30))

        # Right side: Volume Adjustment
        ttk.Label(trim_and_volume_row, text='Volume:', font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=(20, 5))

        self.volume_slider = ttk.Scale(trim_and_volume_row, from_=0, to=2.0, variable=self.volume_var,
                                        orient='horizontal', length=150, command=self.on_volume_change)
        self.volume_slider.pack(side=tk.LEFT, padx=(0, 5))

        # Volume entry field
        self.volume_entry = ttk.Entry(trim_and_volume_row, width=6)
        self.volume_entry.pack(side=tk.LEFT, padx=(0, 3))
        self.volume_entry.insert(0, "100")
        self.volume_entry.bind('<Return>', self.on_volume_entry_change)
        self.volume_entry.bind('<FocusOut>', self.on_volume_entry_change)

        self.volume_label = ttk.Label(trim_and_volume_row, text="%", font=('Arial', 9))
        self.volume_label.pack(side=tk.LEFT, padx=(0, 5))

        # Reset to 100% button
        ttk.Button(trim_and_volume_row, text='Reset to 100%', command=self.reset_volume, width=12).pack(side=tk.LEFT)

        # Trim checkbox row with fetch button
        trim_checkbox_frame = ttk.Frame(main_tab_frame)
        trim_checkbox_frame.grid(row=6, column=0, sticky=tk.W, padx=(20, 0), pady=(3, 5))

        self.trim_enabled_var = tk.BooleanVar()
        ttk.Checkbutton(trim_checkbox_frame, text='Enable video trimming', variable=self.trim_enabled_var,
                       command=self.toggle_trim).pack(side=tk.LEFT)

        self.fetch_duration_btn = ttk.Button(trim_checkbox_frame, text='Fetch Video Duration', command=self.fetch_duration_clicked, state='disabled')
        self.fetch_duration_btn.pack(side=tk.LEFT, padx=(10, 0))

        # Video info label
        self.video_info_label = ttk.Label(main_tab_frame, text="", foreground="green", wraplength=500, justify=tk.LEFT)
        self.video_info_label.grid(row=7, column=0, sticky=tk.W, padx=(20, 0), pady=(2, 0))

        # File size estimation label
        self.filesize_label = ttk.Label(main_tab_frame, text="", foreground="green", font=('Arial', 9))
        self.filesize_label.grid(row=8, column=0, sticky=tk.W, padx=(20, 0), pady=(2, 0))

        # Preview frame to hold both previews side by side
        preview_container = ttk.Frame(main_tab_frame)
        preview_container.grid(row=9, column=0, sticky=tk.W, padx=(40, 0), pady=(10, 5))

        # Start time preview
        start_preview_frame = ttk.Frame(preview_container)
        start_preview_frame.grid(row=0, column=0, padx=(0, 20))

        ttk.Label(start_preview_frame, text='Start Time:', font=('Arial', 9)).pack()
        self.start_preview_label = tk.Label(start_preview_frame, bg='gray20', fg='white', relief='sunken')
        self.start_preview_label.pack(pady=(5, 0))

        # Create placeholder images
        self.placeholder_image = self.create_placeholder_image(PREVIEW_WIDTH, PREVIEW_HEIGHT, 'Preview')
        self.loading_image = self.create_placeholder_image(PREVIEW_WIDTH, PREVIEW_HEIGHT, 'Loading...')
        self.start_preview_label.config(image=self.placeholder_image)

        # End time preview
        end_preview_frame = ttk.Frame(preview_container)
        end_preview_frame.grid(row=0, column=1)

        ttk.Label(end_preview_frame, text='End Time:', font=('Arial', 9)).pack()
        self.end_preview_label = tk.Label(end_preview_frame, bg='gray20', fg='white', relief='sunken')
        self.end_preview_label.pack(pady=(5, 0))
        self.end_preview_label.config(image=self.placeholder_image)

        # Start time slider and entry
        start_control_frame = ttk.Frame(main_tab_frame)
        start_control_frame.grid(row=10, column=0, sticky=tk.W, padx=(40, 0), pady=(2, 2))

        self.start_time_var = tk.DoubleVar(value=0)
        self.start_slider = ttk.Scale(start_control_frame, from_=0, to=100, variable=self.start_time_var,
                                      orient='horizontal', length=SLIDER_LENGTH, command=self.on_slider_change, state='disabled')
        self.start_slider.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(start_control_frame, text="Start Time:", font=('Arial', 9)).pack(side=tk.LEFT, padx=(0, 5))
        self.start_time_entry = ttk.Entry(start_control_frame, width=10, state='disabled')
        self.start_time_entry.pack(side=tk.LEFT)
        self.start_time_entry.insert(0, "00:00:00")
        self.start_time_entry.bind('<Return>', self.on_start_entry_change)
        self.start_time_entry.bind('<FocusOut>', self.on_start_entry_change)

        # End time slider and entry
        end_control_frame = ttk.Frame(main_tab_frame)
        end_control_frame.grid(row=11, column=0, sticky=tk.W, padx=(40, 0), pady=(2, 2))

        self.end_time_var = tk.DoubleVar(value=100)
        self.end_slider = ttk.Scale(end_control_frame, from_=0, to=100, variable=self.end_time_var,
                                    orient='horizontal', length=SLIDER_LENGTH, command=self.on_slider_change, state='disabled')
        self.end_slider.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(end_control_frame, text="End Time:", font=('Arial', 9)).pack(side=tk.LEFT, padx=(0, 5))
        self.end_time_entry = ttk.Entry(end_control_frame, width=10, state='disabled')
        self.end_time_entry.pack(side=tk.LEFT)
        self.end_time_entry.insert(0, "00:00:00")
        self.end_time_entry.bind('<Return>', self.on_end_entry_change)
        self.end_time_entry.bind('<FocusOut>', self.on_end_entry_change)

        # Trim duration display
        self.trim_duration_label = ttk.Label(main_tab_frame, text='Selected Duration: 00:00:00', foreground="green", font=('Arial', 9, 'bold'))
        self.trim_duration_label.grid(row=12, column=0, sticky=tk.W, padx=(40, 0), pady=(3, 0))

        ttk.Separator(main_tab_frame, orient='horizontal').grid(row=13, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)

        path_frame = ttk.Frame(main_tab_frame)
        path_frame.grid(row=14, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(path_frame, text='Save to:').pack(side=tk.LEFT)
        self.path_label = ttk.Label(path_frame, text=self.download_path, foreground="green")
        self.path_label.pack(side=tk.LEFT, padx=(10, 10))
        ttk.Button(path_frame, text='Change', command=self.change_path).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(path_frame, text='Open Folder', command=self.open_download_folder).pack(side=tk.LEFT)

        # Filename customization
        filename_frame = ttk.Frame(main_tab_frame)
        filename_frame.grid(row=15, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(filename_frame, text='Output filename:', font=('Arial', 9)).pack(side=tk.LEFT, padx=(0, 5))
        self.filename_entry = ttk.Entry(filename_frame, width=40)
        self.filename_entry.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(filename_frame, text='(Optional - leave empty for auto-generated name)', foreground="gray", font=('Arial', 8)).pack(side=tk.LEFT)

        button_frame = ttk.Frame(main_tab_frame)
        button_frame.grid(row=16, column=0, columnspan=2, pady=(0, 10))

        self.download_btn = ttk.Button(button_frame, text='Download', command=self.start_download)
        self.download_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_btn = ttk.Button(button_frame, text='Stop', command=self.stop_download, state='disabled')
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 15))

        # Speed limit controls
        self.speed_limit_var = tk.StringVar(value="")
        self.speed_limit_entry = ttk.Entry(button_frame, textvariable=self.speed_limit_var, width=6)
        self.speed_limit_entry.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Label(button_frame, text="MB/s", font=('Arial', 9)).pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(main_tab_frame, mode='determinate', length=560, maximum=100)
        self.progress.grid(row=17, column=0, columnspan=2)

        self.progress_label = ttk.Label(main_tab_frame, text="0%", foreground="green")
        self.progress_label.grid(row=18, column=0, columnspan=2, pady=(5, 0))

        self.status_label = ttk.Label(main_tab_frame, text='Ready', foreground="green")
        self.status_label.grid(row=19, column=0, columnspan=2, pady=(10, 0))

        # Upload to Catbox.moe Section
        ttk.Separator(main_tab_frame, orient='horizontal').grid(row=20, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)

        ttk.Label(main_tab_frame, text='Upload to Streaming Site:', font=('Arial', 11, 'bold')).grid(row=21, column=0, sticky=tk.W, pady=(0, 3))

        upload_frame = ttk.Frame(main_tab_frame)
        upload_frame.grid(row=22, column=0, columnspan=2, sticky=tk.W, pady=(5, 5))

        self.upload_btn = ttk.Button(upload_frame, text='Upload to Catbox.moe', command=self.start_upload, state='disabled')
        self.upload_btn.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(upload_frame, text='View Upload History', command=self.view_upload_history).pack(side=tk.LEFT, padx=(0, 10))

        self.upload_status_label = ttk.Label(upload_frame, text="", foreground="green", font=('Arial', 9))
        self.upload_status_label.pack(side=tk.LEFT)

        # Auto-upload checkbox
        auto_upload_frame = ttk.Frame(main_tab_frame)
        auto_upload_frame.grid(row=23, column=0, columnspan=2, sticky=tk.W, padx=(20, 0), pady=(5, 0))

        ttk.Checkbutton(auto_upload_frame, text='Auto-upload after download/trim completes',
                       variable=self.auto_upload_var).pack(side=tk.LEFT)

        # Upload URL display (initially hidden)
        self.upload_url_frame = ttk.Frame(main_tab_frame)
        self.upload_url_frame.grid(row=24, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))

        ttk.Label(self.upload_url_frame, text='Upload URL:', font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 5))

        self.upload_url_entry = ttk.Entry(self.upload_url_frame, width=60, state='readonly')
        self.upload_url_entry.pack(side=tk.LEFT, padx=(0, 10))

        self.copy_url_btn = ttk.Button(self.upload_url_frame, text='Copy URL', command=self.copy_upload_url)
        self.copy_url_btn.pack(side=tk.LEFT)

        # Hide upload URL frame initially
        self.upload_url_frame.grid_remove()

        # Setup Clipboard Mode UI (tab was created at the beginning)
        self.setup_clipboard_mode_ui(clipboard_tab_frame)

        # Setup Uploader UI
        self.setup_uploader_ui(uploader_tab_frame)

        # Setup Settings tab
        self._setup_settings_tab(settings_tab_frame)

        # Setup Help tab
        self._setup_help_tab(help_tab_frame)

        # Restore persisted clipboard URLs
        self._restore_clipboard_urls()

        # Bind tab change event
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    def setup_clipboard_mode_ui(self, parent):
        """Setup Clipboard Mode tab UI"""

        # Header
        ttk.Label(parent, text='Clipboard Mode', font=('Arial', 14, 'bold')).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 3))

        ttk.Label(parent, text='Copy YouTube URLs (Ctrl+C) to automatically detect and download them.',
                  foreground="gray", font=('Arial', 9)).grid(
            row=1, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))

        # Mode Toggle
        mode_frame = ttk.Frame(parent)
        mode_frame.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(0, 3))

        ttk.Label(mode_frame, text='Download Mode:', font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=(0, 10))
        self.clipboard_auto_download_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(mode_frame, text='Auto-download (starts immediately)',
                       variable=self.clipboard_auto_download_var).pack(side=tk.LEFT)

        # Settings
        ttk.Separator(parent, orient='horizontal').grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=3)
        ttk.Label(parent, text='Settings', font=('Arial', 11, 'bold')).grid(row=4, column=0, sticky=tk.W, pady=(0, 3))

        settings_frame = ttk.Frame(parent)
        settings_frame.grid(row=5, column=0, columnspan=2, sticky=tk.W, padx=(20, 0), pady=(0, 3))

        # Quality dropdown
        ttk.Label(settings_frame, text='Quality:', font=('Arial', 9)).grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.clipboard_quality_var = tk.StringVar(value="1080")
        quality_options = ["1440", "1080", "720", "480", "360", "240", "none (Audio only)"]
        self.clipboard_quality_combo = ttk.Combobox(settings_frame, textvariable=self.clipboard_quality_var,
            values=quality_options, state='readonly', width=20)
        self.clipboard_quality_combo.grid(row=0, column=1, sticky=tk.W)

        # Speed limit
        ttk.Label(settings_frame, text='Speed limit:', font=('Arial', 9)).grid(row=0, column=2, sticky=tk.W, padx=(20, 5))
        self.clipboard_speed_limit_var = tk.StringVar(value="")
        self.clipboard_speed_limit_entry = ttk.Entry(settings_frame, textvariable=self.clipboard_speed_limit_var, width=6)
        self.clipboard_speed_limit_entry.grid(row=0, column=3, sticky=tk.W)
        ttk.Label(settings_frame, text="MB/s", font=('Arial', 9)).grid(row=0, column=4, sticky=tk.W, padx=(5, 0))

        # Full Playlist Download toggle
        self.clipboard_full_playlist_var = tk.BooleanVar(value=False)
        self.clipboard_full_playlist_check = ttk.Checkbutton(
            settings_frame, text='Full Playlist Download (download all videos when given a playlist link)',
            variable=self.clipboard_full_playlist_var)
        self.clipboard_full_playlist_check.grid(row=1, column=0, columnspan=5, sticky=tk.W, pady=(5, 0))

        # Output Folder
        ttk.Separator(parent, orient='horizontal').grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=3)

        folder_frame = ttk.Frame(parent)
        folder_frame.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 3))

        ttk.Label(folder_frame, text='Save to:', font=('Arial', 9)).pack(side=tk.LEFT)
        self.clipboard_path_label = ttk.Label(folder_frame, text=self.clipboard_download_path, foreground="green")
        self.clipboard_path_label.pack(side=tk.LEFT, padx=(10, 10))
        ttk.Button(folder_frame, text='Change', command=self.change_clipboard_path).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(folder_frame, text='Open Folder', command=self.open_clipboard_folder).pack(side=tk.LEFT)

        # URL List
        ttk.Separator(parent, orient='horizontal').grid(row=8, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=3)

        url_header_frame = ttk.Frame(parent)
        url_header_frame.grid(row=9, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 3))

        ttk.Label(url_header_frame, text='Detected URLs', font=('Arial', 11, 'bold')).pack(side=tk.LEFT)
        self.clipboard_url_count_label = ttk.Label(url_header_frame, text='(0 URLs)', foreground="gray", font=('Arial', 9))
        self.clipboard_url_count_label.pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(url_header_frame, text='Clear All', command=self.clear_all_clipboard_urls).pack(side=tk.RIGHT)

        # Scrollable URL list
        url_list_container = ttk.Frame(parent)
        url_list_container.grid(row=10, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 3))

        theme_colors = THEMES[self.current_theme]
        self.clipboard_url_canvas = tk.Canvas(url_list_container, height=CLIPBOARD_URL_LIST_HEIGHT,
                                             bg=theme_colors['canvas_bg'],
                                             highlightthickness=1, highlightbackground=theme_colors['border'])
        url_scrollbar = ttk.Scrollbar(url_list_container, orient="vertical",
                                      command=self.clipboard_url_canvas.yview)
        self.clipboard_url_list_frame = ttk.Frame(self.clipboard_url_canvas)

        self.clipboard_url_list_frame.bind("<Configure>",
            lambda e: self.clipboard_url_canvas.configure(scrollregion=self.clipboard_url_canvas.bbox("all")))

        self.clipboard_url_canvas.create_window((0, 0), window=self.clipboard_url_list_frame, anchor="nw")
        self.clipboard_url_canvas.configure(yscrollcommand=url_scrollbar.set)

        self.clipboard_url_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        url_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Progress & Controls
        ttk.Separator(parent, orient='horizontal').grid(row=11, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=3)

        button_frame = ttk.Frame(parent)
        button_frame.grid(row=12, column=0, columnspan=2, pady=(0, 3))

        self.clipboard_download_btn = ttk.Button(button_frame, text='Download All',
            command=self.start_clipboard_downloads, state='disabled')
        self.clipboard_download_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.clipboard_stop_btn = ttk.Button(button_frame, text='Stop',
            command=self.stop_clipboard_downloads, state='disabled')
        self.clipboard_stop_btn.pack(side=tk.LEFT)

        # Individual progress
        ttk.Label(parent, text='Current Download:', font=('Arial', 9, 'bold')).grid(row=13, column=0, sticky=tk.W, pady=(0, 3))

        self.clipboard_progress = ttk.Progressbar(parent, mode='determinate', length=560, maximum=100)
        self.clipboard_progress.grid(row=14, column=0, columnspan=2)

        self.clipboard_progress_label = ttk.Label(parent, text="0%", foreground="green")
        self.clipboard_progress_label.grid(row=15, column=0, columnspan=2, pady=(5, 0))

        # Total progress
        self.clipboard_total_label = ttk.Label(parent, text='Completed: 0/0 videos',
            foreground="green", font=('Arial', 9, 'bold'))
        self.clipboard_total_label.grid(row=16, column=0, columnspan=2, pady=(5, 0))

        # Status
        self.clipboard_status_label = ttk.Label(parent, text='Ready', foreground="green")
        self.clipboard_status_label.grid(row=17, column=0, columnspan=2, pady=(3, 0))

    def setup_uploader_ui(self, parent):
        """Setup Uploader tab UI"""

        # Header
        ttk.Label(parent, text='Upload Local File', font=('Arial', 14, 'bold')).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 3))

        ttk.Label(parent, text='Upload local video files to Catbox.moe streaming service.',
                  foreground="gray", font=('Arial', 9)).grid(
            row=1, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))

        # File selection
        ttk.Separator(parent, orient='horizontal').grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        file_header_frame = ttk.Frame(parent)
        file_header_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))

        ttk.Label(file_header_frame, text='File Queue:', font=('Arial', 11, 'bold')).pack(side=tk.LEFT)
        self.uploader_queue_count_label = ttk.Label(file_header_frame, text='(0 files)', foreground="gray", font=('Arial', 9))
        self.uploader_queue_count_label.pack(side=tk.LEFT, padx=(10, 0))

        file_select_frame = ttk.Frame(parent)
        file_select_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Button(file_select_frame, text='Add Files', command=self.browse_uploader_files).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(file_select_frame, text='Clear All', command=self.clear_uploader_queue).pack(side=tk.LEFT)

        # Scrollable file list
        file_list_container = ttk.Frame(parent)
        file_list_container.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        theme_colors = THEMES[self.current_theme]
        self.uploader_file_canvas = tk.Canvas(file_list_container, height=75,
                                             bg=theme_colors['canvas_bg'],
                                             highlightthickness=1, highlightbackground=theme_colors['border'])
        file_scrollbar = ttk.Scrollbar(file_list_container, orient="vertical",
                                      command=self.uploader_file_canvas.yview)
        self.uploader_file_list_frame = ttk.Frame(self.uploader_file_canvas)

        self.uploader_file_list_frame.bind("<Configure>",
            lambda e: self.uploader_file_canvas.configure(scrollregion=self.uploader_file_canvas.bbox("all")))

        self.uploader_file_canvas.create_window((0, 0), window=self.uploader_file_list_frame, anchor="nw")
        self.uploader_file_canvas.configure(yscrollcommand=file_scrollbar.set)

        self.uploader_file_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        file_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Upload controls
        ttk.Separator(parent, orient='horizontal').grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        upload_controls_frame = ttk.Frame(parent)
        upload_controls_frame.grid(row=7, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        self.uploader_upload_btn = ttk.Button(upload_controls_frame, text='Upload to Catbox.moe',
                                              command=self.start_uploader_upload, state='disabled')
        self.uploader_upload_btn.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(upload_controls_frame, text='View Upload History', command=self.view_upload_history).pack(side=tk.LEFT)

        self.uploader_status_label = ttk.Label(parent, text="", foreground="green", font=('Arial', 9))
        self.uploader_status_label.grid(row=8, column=0, columnspan=2, sticky=tk.W, pady=(5, 10))

        # Upload URL display (initially hidden)
        self.uploader_url_frame = ttk.Frame(parent)
        self.uploader_url_frame.grid(row=9, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))

        ttk.Label(self.uploader_url_frame, text='Upload URL:', font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 5))

        self.uploader_url_entry = ttk.Entry(self.uploader_url_frame, width=60, state='readonly')
        self.uploader_url_entry.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(self.uploader_url_frame, text='Copy URL', command=self.copy_uploader_url).pack(side=tk.LEFT)

        # Hide URL frame initially
        self.uploader_url_frame.grid_remove()

    # Phase 4: Tab Management & Clipboard Monitoring

    def on_tab_changed(self, event=None):
        """Handle notebook tab changes"""
        current_tab = self.notebook.index(self.notebook.select())
        if current_tab == 0:  # Clipboard Mode tab (first tab)
            self.start_clipboard_monitoring()
        else:  # Trimmer tab (second tab)
            self.stop_clipboard_monitoring()

    def start_clipboard_monitoring(self):
        """Start clipboard monitoring using tkinter polling"""
        # Use clipboard_lock to prevent race conditions when starting/stopping
        with self.clipboard_lock:
            if self.clipboard_monitoring:
                return  # Already monitoring, don't start another polling loop
            self.clipboard_monitoring = True
            logger.info("Clipboard monitoring started (tkinter polling)")
            # Initialize last content from current clipboard (normalized to prevent source mismatches)
            try:
                content = self.root.clipboard_get()
                self.clipboard_last_content = content.strip() if content else ""
            except tk.TclError:
                self.clipboard_last_content = ""
        # Start polling loop (outside lock to avoid holding it during callback scheduling)
        self._poll_clipboard()

    def stop_clipboard_monitoring(self):
        """Stop clipboard monitoring"""
        with self.clipboard_lock:
            if not self.clipboard_monitoring:
                return  # Already stopped
            self.clipboard_monitoring = False
            logger.info("Clipboard monitoring stopped")

    def _poll_clipboard(self):
        """Poll clipboard using best available method for each platform"""
        # Check if monitoring was stopped (with lock for thread safety)
        with self.clipboard_lock:
            if not self.clipboard_monitoring:
                return

        clipboard_content = None

        try:
            # Try KDE Klipper first (most reliable on KDE Plasma Linux)
            if self.klipper_interface:
                try:
                    clipboard_content = str(self.klipper_interface.getClipboardContents())
                except Exception as e:
                    logger.debug(f"Klipper read failed: {e}")
                    clipboard_content = None

            # Try pyperclip (works on Windows even when Firefox has focus)
            if not clipboard_content and PYPERCLIP_AVAILABLE:
                try:
                    clipboard_content = pyperclip.paste()
                except Exception as e:
                    logger.debug(f"Pyperclip read failed: {e}")
                    clipboard_content = None

            # Fallback to tkinter if other methods unavailable or failed
            if not clipboard_content:
                self.root.update_idletasks()
                clipboard_content = self.root.clipboard_get()

            # Normalize clipboard content to prevent false changes from whitespace differences
            if clipboard_content:
                clipboard_content = clipboard_content.strip()

            if clipboard_content and clipboard_content != self.clipboard_last_content:
                logger.info(f"Clipboard changed: {clipboard_content[:80]}")
                self.clipboard_last_content = clipboard_content

                is_valid, message = self.validate_youtube_url(clipboard_content)

                if is_valid:
                    url_exists = clipboard_content in self.clipboard_url_widgets

                    if not url_exists:
                        self._add_url_to_clipboard_list(clipboard_content)
                        logger.info(f"New YouTube URL detected and added: {clipboard_content}")

                        if self.clipboard_auto_download_var.get():
                            logger.info(f"Auto-download enabled, starting download: {clipboard_content}")
                            self._auto_download_single_url(clipboard_content)
                else:
                    logger.debug(f"Clipboard content not a valid YouTube URL: {message}")

        except tk.TclError:
            # This is normal when clipboard is empty or selection owner doesn't respond
            pass
        except Exception as e:
            logger.error(f"Error polling clipboard: {e}")

        # Schedule next poll (with lock to check monitoring state safely)
        with self.clipboard_lock:
            if self.clipboard_monitoring:
                self.root.after(CLIPBOARD_POLL_INTERVAL_MS, self._poll_clipboard)


    # Phase 5: URL List Management

    def _add_url_to_clipboard_list(self, url):
        """Add URL to clipboard list with UI widget"""
        url_frame = ttk.Frame(self.clipboard_url_list_frame, relief='solid', borderwidth=1)
        url_frame.pack(fill=tk.X, padx=5, pady=2)

        theme_colors = THEMES[self.current_theme]
        status_canvas = tk.Canvas(url_frame, width=12, height=12, bg=theme_colors['status_canvas_bg'], highlightthickness=0)
        status_canvas.pack(side=tk.LEFT, padx=(5, 5))
        status_circle = status_canvas.create_oval(2, 2, 10, 10, fill='gray', outline='')

        url_display = url if len(url) <= 60 else url[:57] + "..."
        url_label = ttk.Label(url_frame, text=url_display, font=('Arial', 9))
        url_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        remove_btn = ttk.Button(url_frame, text="X", width=3, command=lambda: self._remove_url_from_list(url))
        remove_btn.pack(side=tk.RIGHT, padx=5)

        url_data = {
            'url': url,
            'status': 'pending',
            'widget': url_frame,
            'status_canvas': status_canvas,
            'status_circle': status_circle
        }

        with self.clipboard_lock:
            # Cap the list to prevent unbounded memory growth
            if len(self.clipboard_url_list) >= 500:
                oldest = self.clipboard_url_list.pop(0)
                self.clipboard_url_widgets.pop(oldest['url'], None)
                if oldest.get('widget'):
                    oldest['widget'].destroy()
            self.clipboard_url_list.append(url_data)
            self.clipboard_url_widgets[url] = url_data
            has_urls = len(self.clipboard_url_list) > 0

        self._update_clipboard_url_count()
        with self.clipboard_lock:
            is_downloading = self.clipboard_downloading
        if has_urls and not is_downloading:
            self.clipboard_download_btn.config(state='normal')

        # Save URLs to persistence file
        self._save_clipboard_urls()

    def _remove_url_from_list(self, url):
        """Remove URL from clipboard list"""
        widget_to_destroy = None
        list_is_empty = False

        with self.clipboard_lock:
            for i, item in enumerate(self.clipboard_url_list):
                if item['url'] == url:
                    widget_to_destroy = item['widget']
                    self.clipboard_url_list.pop(i)
                    if url in self.clipboard_url_widgets:
                        del self.clipboard_url_widgets[url]
                    list_is_empty = len(self.clipboard_url_list) == 0
                    break

        # UI operations outside the lock
        if widget_to_destroy:
            widget_to_destroy.destroy()
            self._update_clipboard_url_count()
            if list_is_empty:
                self.clipboard_download_btn.config(state='disabled')
            logger.info(f"Removed URL: {url}")

            # Save URLs to persistence file
            self._save_clipboard_urls()

    def clear_all_clipboard_urls(self):
        """Clear all URLs from clipboard list"""
        with self.clipboard_lock:
            is_downloading = self.clipboard_downloading
        if is_downloading:
            messagebox.showwarning('Cannot Clear', 'Cannot clear URLs while downloads are in progress.')
            return

        # Take snapshot of widgets to destroy
        with self.clipboard_lock:
            widgets_to_destroy = [item['widget'] for item in self.clipboard_url_list if item['widget']]
            self.clipboard_url_list.clear()
            self.clipboard_url_widgets.clear()

        # UI operations outside the lock
        for widget in widgets_to_destroy:
            widget.destroy()

        self._update_clipboard_url_count()
        self.clipboard_download_btn.config(state='disabled')
        logger.info("Cleared all clipboard URLs")

        # Save URLs to persistence file
        self._save_clipboard_urls()

    def _update_clipboard_url_count(self):
        """Update URL count label"""
        with self.clipboard_lock:
            count = len(self.clipboard_url_list)
        s = 's' if count != 1 else ''
        self.clipboard_url_count_label.config(text=f'({count} URL{s})')

    def _update_url_status(self, url, status):
        """Update visual status of URL: pending (gray), downloading (blue), completed (green), failed (red)"""
        if url in self.clipboard_url_widgets:
            item = self.clipboard_url_widgets[url]
            status_canvas = item['status_canvas']
            status_circle = item['status_circle']

            color_map = {'pending': 'gray', 'downloading': 'blue', 'completed': 'green', 'failed': 'red'}
            color = color_map.get(status, 'gray')
            status_canvas.itemconfig(status_circle, fill=color)

            with self.clipboard_lock:
                for item_data in self.clipboard_url_list:
                    if item_data['url'] == url:
                        item_data['status'] = status
                        break

    # Phase 6: Download Queue (Sequential Processing)

    def start_clipboard_downloads(self):
        """Start downloading all pending URLs sequentially"""
        with self.clipboard_lock:
            is_downloading = self.clipboard_downloading
        if is_downloading:
            return

        with self.clipboard_lock:
            pending_urls = [item for item in self.clipboard_url_list if item['status'] == 'pending']

        if not pending_urls:
            messagebox.showinfo('No URLs', 'No pending URLs to download.')
            return

        with self.clipboard_lock:
            self.clipboard_downloading = True
        self.clipboard_download_btn.config(state='disabled')
        self.clipboard_stop_btn.config(state='normal')

        total_count = len(pending_urls)
        self.clipboard_total_label.config(text=f'Completed: 0/{total_count} videos')

        logger.info(f"Starting clipboard batch download: {total_count} URLs")
        self.thread_pool.submit(self._process_clipboard_queue)

    def _process_clipboard_queue(self):
        """Process clipboard download queue sequentially"""
        with self.clipboard_lock:
            pending_urls = [item for item in self.clipboard_url_list if item['status'] == 'pending']
        total_count = len(pending_urls)

        for index, item in enumerate(pending_urls):
            with self.clipboard_lock:
                is_downloading = self.clipboard_downloading
            if not is_downloading:
                logger.info("Clipboard downloads stopped by user")
                break

            url = item['url']

            self._safe_after(0, lambda u=url: self._update_url_status(u, 'downloading'))
            self._safe_after(0, lambda i=index, t=total_count:
                self.clipboard_total_label.config(text=f'Completed: {i}/{t} videos'))
            self._safe_after(0, lambda u=url:
                self.update_clipboard_status(f'Downloading: {u[:50]}...', "blue"))

            success = self._download_clipboard_url(url, check_stop=True)

            if success:
                self._safe_after(0, lambda u=url: self._update_url_status(u, 'completed'))
            else:
                self._safe_after(0, lambda u=url: self._update_url_status(u, 'failed'))

            completed = index + 1
            self._safe_after(0, lambda c=completed, t=total_count:
                self.clipboard_total_label.config(text=f'Completed: {c}/{t} videos'))

        self._safe_after(0, self._finish_clipboard_downloads)

    def _download_clipboard_url(self, url, check_stop=False, check_stop_auto=False):
        """Download single URL or playlist from clipboard mode (blocking, runs in thread). Returns True if successful."""
        process = None
        try:
            quality = self.clipboard_quality_var.get()
            if "none" in quality.lower() or quality == "none (Audio only)":
                quality = "none"

            audio_only = quality.startswith("none")
            is_playlist_url = self.is_playlist_url(url)
            full_playlist_enabled = self.clipboard_full_playlist_var.get()

            # Determine if we're actually downloading as a playlist
            download_as_playlist = is_playlist_url and full_playlist_enabled

            self._safe_after(0, lambda: self.clipboard_progress.config(value=0))
            self._safe_after(0, lambda: self.clipboard_progress_label.config(text="0%"))

            # Use playlist-appropriate output template only when downloading full playlist
            if audio_only:
                if download_as_playlist:
                    output_path = os.path.join(self.clipboard_download_path, '%(playlist_index)s-%(title)s.%(ext)s')
                else:
                    output_path = os.path.join(self.clipboard_download_path, '%(title)s.%(ext)s')
            else:
                if download_as_playlist:
                    output_path = os.path.join(self.clipboard_download_path, f'%(playlist_index)s-%(title)s_{quality}p.%(ext)s')
                else:
                    output_path = os.path.join(self.clipboard_download_path, f'%(title)s_{quality}p.%(ext)s')

            # Use helper methods for command construction
            if audio_only:
                cmd = self.build_audio_ytdlp_command(url, output_path, volume=1.0)
            else:
                cmd = self.build_video_ytdlp_command(url, output_path, quality, volume=1.0)

            # Add --no-playlist if it's a playlist URL but full playlist download is disabled
            if is_playlist_url and not full_playlist_enabled:
                cmd.insert(1, '--no-playlist')

            # Add speed limit if set
            cmd.extend(self._get_speed_limit_args(self.clipboard_speed_limit_var))

            if download_as_playlist:
                logger.info(f"Clipboard full playlist download starting: {url}")
            elif is_playlist_url:
                logger.info(f"Clipboard single video from playlist starting: {url}")
            else:
                logger.info(f"Clipboard download starting: {url}")

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       encoding='utf-8', errors='replace', bufsize=1, **_subprocess_kwargs)

            # Track current download phase for status messages
            current_phase = "video" if not audio_only else "audio"
            playlist_item_info = ""  # Track which playlist item we're on

            for line in process.stdout:
                # Check stop flags
                if check_stop:
                    with self.clipboard_lock:
                        is_downloading = self.clipboard_downloading
                    if not is_downloading:
                        self.safe_process_cleanup(process)
                        return False
                if check_stop_auto:
                    with self.auto_download_lock:
                        is_auto_downloading = self.clipboard_auto_downloading
                    if not is_auto_downloading:
                        self.safe_process_cleanup(process)
                        return False

                line_lower = line.lower()

                # Detect phase changes from yt-dlp output
                if 'downloading video' in line_lower or ('video' in line_lower and 'downloading' in line_lower):
                    current_phase = "video"
                elif 'downloading audio' in line_lower or ('audio' in line_lower and 'downloading' in line_lower):
                    current_phase = "audio"

                # Detect playlist item progress (e.g., "Downloading item 1 of 10")
                if download_as_playlist and 'downloading item' in line_lower:
                    item_match = re.search(r'downloading item (\d+) of (\d+)', line_lower)
                    if item_match:
                        playlist_item_info = f" [{item_match.group(1)}/{item_match.group(2)}]"

                if '[download]' in line or 'Downloading' in line:
                    progress_match = PROGRESS_REGEX.search(line)
                    if progress_match:
                        progress = float(progress_match.group(1))
                        self._safe_after(0, lambda p=progress: self.update_clipboard_progress(p))

                        # Show phase-specific status with playlist info if applicable
                        phase = current_phase
                        pinfo = playlist_item_info
                        self._safe_after(0, lambda p=progress, ph=phase, pi=pinfo: self.update_clipboard_status(
                            f'Downloading {ph}{pi}... {p:.1f}%', "blue"))

                # Show merging/processing status
                elif '[Merger]' in line or 'Merging' in line:
                    self._safe_after(0, lambda: self.update_clipboard_status('Merging video and audio...', "blue"))
                elif '[ffmpeg]' in line:
                    self._safe_after(0, lambda: self.update_clipboard_status('Processing with ffmpeg...', "blue"))
                elif '[ExtractAudio]' in line:
                    self._safe_after(0, lambda: self.update_clipboard_status('Extracting audio...', "blue"))

            process.wait()

            if process.returncode == 0:
                self._safe_after(0, lambda: self.update_clipboard_progress(PROGRESS_COMPLETE))
                logger.info(f"Clipboard download completed: {url}")
                success = True
            else:
                logger.error(f"Clipboard download failed: {url}, returncode={process.returncode}")
                success = False

            # Clean up process resources
            self.safe_process_cleanup(process)
            return success

        except Exception as e:
            logger.exception(f"Error downloading clipboard URL {url}: {e}")
            if process:
                self.safe_process_cleanup(process)
            return False

    def _finish_clipboard_downloads(self):
        """Clean up after batch downloads complete"""
        with self.clipboard_lock:
            self.clipboard_downloading = False
            has_urls = len(self.clipboard_url_list) > 0
            completed = sum(1 for item in self.clipboard_url_list if item['status'] == 'completed')
            failed = sum(1 for item in self.clipboard_url_list if item['status'] == 'failed')

        self.clipboard_download_btn.config(state='normal' if has_urls else 'disabled')
        self.clipboard_stop_btn.config(state='disabled')

        if failed > 0:
            self.update_clipboard_status(f'Completed: {completed} | Failed: {failed}', "orange")
        else:
            self.update_clipboard_status(f'All downloads complete! ({completed} videos)', "green")

        logger.info(f"Clipboard batch download finished: {completed} completed, {failed} failed")

    def stop_clipboard_downloads(self):
        """Stop clipboard batch downloads and auto-downloads"""
        stopped = False
        with self.clipboard_lock:
            if self.clipboard_downloading:
                self.clipboard_downloading = False
                stopped = True
        if stopped:
            logger.info("Clipboard batch downloads stopped by user")
        with self.auto_download_lock:
            if self.clipboard_auto_downloading:
                self.clipboard_auto_downloading = False
                stopped = True
        if stopped:
            logger.info("Clipboard auto-downloads stopped by user")
            self.update_clipboard_status('Downloads stopped by user', "orange")
            self.clipboard_stop_btn.config(state='disabled')

    def _auto_download_single_url(self, url):
        """Auto-download single URL when detected (if auto-download enabled)"""
        # Check if another auto-download is already in progress (thread-safe)
        with self.auto_download_lock:
            with self.clipboard_lock:
                downloading_count = sum(1 for item in self.clipboard_url_list if item['status'] == 'downloading')
            if downloading_count > 0:
                # Another download is in progress, keep this one pending
                logger.info(f"URL queued (another download in progress): {url}")
                return

            self.clipboard_auto_downloading = True
            self._update_url_status(url, 'downloading')

        # Update UI outside the lock
        self.clipboard_stop_btn.config(state='normal')  # Enable stop button
        self._update_auto_download_total()
        self.thread_pool.submit(self._auto_download_worker, url)

    def _auto_download_worker(self, url):
        """Worker thread for auto-downloading single URL"""
        # Check if stopped before starting
        with self.auto_download_lock:
            is_auto_downloading = self.clipboard_auto_downloading
        if not is_auto_downloading:
            self._safe_after(0, lambda: self._update_url_status(url, 'pending'))
            return

        self._safe_after(0, lambda: self.update_clipboard_status(f'Auto-downloading: {url[:50]}...', "blue"))

        success = self._download_clipboard_url(url, check_stop_auto=True)

        # Check if stopped during download
        with self.auto_download_lock:
            is_auto_downloading = self.clipboard_auto_downloading
        if not is_auto_downloading:
            self._safe_after(0, lambda: self._update_url_status(url, 'pending'))
            self._safe_after(0, lambda: self.update_clipboard_status('Auto-download stopped', "orange"))
            return

        # Schedule all UI updates and next download in a single callback to ensure order
        self._safe_after(0, lambda: self._handle_auto_download_complete(url, success))

    def _handle_auto_download_complete(self, url, success):
        """Handle auto-download completion - runs on main thread"""
        if success:
            self._update_url_status(url, 'completed')
            self._update_auto_download_total()
            self.update_clipboard_status(f'Auto-download complete: {url[:50]}...', "green")
            # Auto-remove successfully completed URLs from list
            self._remove_url_from_list(url)
            logger.info(f"Auto-download completed and removed: {url}")
        else:
            self._update_url_status(url, 'failed')
            self._update_auto_download_total()
            self.update_clipboard_status(f'Auto-download failed: {url[:50]}...', "red")
            logger.info(f"Auto-download failed: {url}")

        # Now check for next pending download (all state is consistent now)
        self._check_pending_auto_downloads()

    def _disable_stop_if_idle(self):
        """Disable stop button if no downloads in progress"""
        with self.clipboard_lock:
            is_downloading = self.clipboard_downloading
        with self.auto_download_lock:
            is_auto_downloading = self.clipboard_auto_downloading
        if not is_downloading and not is_auto_downloading:
            self.clipboard_stop_btn.config(state='disabled')

    def _check_pending_auto_downloads(self):
        """Check if there are pending URLs that need to be auto-downloaded"""
        # Reset auto-downloading flag if no more downloads
        with self.auto_download_lock:
            self.clipboard_auto_downloading = False

        if self.clipboard_auto_download_var.get():
            # Find first pending URL
            with self.clipboard_lock:
                next_pending_url = None
                for item in self.clipboard_url_list:
                    if item['status'] == 'pending':
                        next_pending_url = item['url']
                        break  # Only start one at a time

            if next_pending_url:
                self._auto_download_single_url(next_pending_url)
        else:
            # Disable stop button if idle
            self._disable_stop_if_idle()

    def _update_auto_download_total(self):
        """Update total progress for auto-downloads"""
        with self.clipboard_lock:
            total = len(self.clipboard_url_list)
            completed = sum(1 for item in self.clipboard_url_list if item['status'] in ['completed', 'failed'])
        self.clipboard_total_label.config(text=f'Completed: {completed}/{total} videos')

    # Phase 7: Helper Methods

    def update_clipboard_progress(self, value):
        """Update clipboard mode progress bar"""
        try:
            value = float(value)
            value = max(0, min(100, value))  # Clamp to 0-100
            self.clipboard_progress['value'] = value
            self.clipboard_progress_label.config(text=f"{value:.1f}%")
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid progress value: {value} - {e}")

    def update_clipboard_status(self, message, color):
        """Update clipboard mode status label"""
        self.clipboard_status_label.config(text=message, foreground=color)

    def change_clipboard_path(self):
        """Change clipboard mode download path"""
        path = filedialog.askdirectory(initialdir=self.clipboard_download_path)
        if path:
            # Validate path for security (prevent path traversal attacks)
            is_valid, normalized_path, error_msg = self.validate_download_path(path)
            if not is_valid:
                messagebox.showerror('Error', error_msg)
                return
            path = normalized_path

            if not os.path.exists(path):
                messagebox.showerror('Error', f'Path does not exist: {path}')
                return

            if not os.path.isdir(path):
                messagebox.showerror('Error', f'Path is not a directory: {path}')
                return

            test_file = os.path.join(path, ".ytdl_write_test")
            try:
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
            except (IOError, OSError) as e:
                messagebox.showerror('Error', f'Path is not writable:\n{path}\n\n{e}')
                return

            self.clipboard_download_path = path
            self.clipboard_path_label.config(text=path)
            logger.info(f"Clipboard download path changed to: {path}")

    def open_clipboard_folder(self):
        """Open clipboard mode download folder"""
        try:
            if sys.platform == 'win32':
                os.startfile(self.clipboard_download_path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', self.clipboard_download_path], close_fds=True, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(['xdg-open', self.clipboard_download_path], close_fds=True, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            messagebox.showerror('Error', f'Failed to open folder:\n{e}')

    def create_placeholder_image(self, width, height, text):
        """Create a placeholder image with text"""
        img = Image.new('RGB', (width, height), color='#2d2d2d')
        draw = ImageDraw.Draw(img)

        # Draw text in center - use default font for cross-platform compatibility
        try:
            font = ImageFont.load_default()
        except (IOError, OSError):
            font = None

        # Get text bounding box to center it
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        position = ((width - text_width) // 2, (height - text_height) // 2)
        draw.text(position, text, fill='white', font=font)

        return ImageTk.PhotoImage(img)

    def seconds_to_hms(self, seconds):
        """Convert seconds to HH:MM:SS format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def toggle_trim(self):
        """Enable or disable trimming controls"""
        enabled = self.trim_enabled_var.get()
        if enabled:
            self.fetch_duration_btn.config(state='normal')
            if self.video_duration > 0:
                self.start_slider.config(state='normal')
                self.end_slider.config(state='normal')
                self.start_time_entry.config(state='normal')
                self.end_time_entry.config(state='normal')
        else:
            self.fetch_duration_btn.config(state='disabled')
            self.start_slider.config(state='disabled')
            self.end_slider.config(state='disabled')
            self.start_time_entry.config(state='disabled')
            self.end_time_entry.config(state='disabled')

        # Update file size display when trimming is toggled
        self._update_trimmed_filesize()

    def fetch_duration_clicked(self):
        """Handler for fetch duration button"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror('Error', 'Please enter a YouTube URL or select a local file')
            return

        # Check if it's a local file or YouTube URL
        if self.is_local_file(url):
            # Validate local file exists
            if not os.path.isfile(url):
                messagebox.showerror('Error', f'File not found:\n{url}')
                return
            self.local_file_path = url
        else:
            # Validate YouTube URL
            is_valid, message = self.validate_youtube_url(url)
            if not is_valid:
                messagebox.showerror('Invalid URL', message)
                logger.warning(f"Invalid URL rejected: {url}")
                return
            self.local_file_path = None

            # Check if it's a playlist
            if self.is_playlist_url(url):
                if self.is_pure_playlist_url(url):
                    # Pure playlist URL — block trimming
                    self.is_playlist = True
                    self.trim_enabled_var.set(False)
                    self.toggle_trim()  # Disable trim controls
                    self.video_info_label.config(text='Playlist detected - Trimming and upload disabled for playlists', foreground="orange")
                    self.filesize_label.config(text="")
                    logger.info("Playlist URL detected - trimming disabled")
                    # Don't fetch duration for playlists
                    return
                else:
                    # Video URL with playlist context — strip playlist params, treat as single video
                    url = self.strip_playlist_params(url)
                    self.url_entry.delete(0, tk.END)
                    self.url_entry.insert(0, url)
                    self.is_playlist = False
                    self.video_info_label.config(text='Playlist parameters removed - downloading single video', foreground="green")
                    logger.info(f"Stripped playlist params from video URL: {url}")
            else:
                self.is_playlist = False

        with self.fetch_lock:
            is_fetching = self.is_fetching_duration
        if is_fetching or self.is_downloading:
            return

        # Save the URL for preview extraction and clear cache
        if self.current_video_url != url:
            self.current_video_url = url
            self._clear_preview_cache()
        else:
            self.current_video_url = url

        with self.fetch_lock:
            self.is_fetching_duration = True
        self.fetch_duration_btn.config(state='disabled')
        self.update_status('Fetching video duration...', "blue")

        # Submit to thread pool
        self.thread_pool.submit(self.fetch_video_duration, url)

    def fetch_video_duration(self, url):
        """Fetch video duration and info from URL or local file"""
        try:
            # Check if local file
            if self.is_local_file(url):
                return self._fetch_local_file_duration(url)

            # Fetch duration
            def _fetch_duration():
                cmd = [self.ytdlp_path, '--get-duration', url]
                return subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace', timeout=METADATA_FETCH_TIMEOUT, **_subprocess_kwargs)

            result = self.retry_network_operation(_fetch_duration, "Fetch duration")

            # Fetch title in parallel
            def _fetch_title():
                cmd = [self.ytdlp_path, '--get-title', url]
                return subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace', timeout=METADATA_FETCH_TIMEOUT, **_subprocess_kwargs)

            title_result = self.retry_network_operation(_fetch_title, "Fetch title")

            if result.returncode == 0:
                duration_str = result.stdout.strip()
                # Parse duration (format can be SS, MM:SS, or HH:MM:SS)
                parts = duration_str.split(':')
                try:
                    if len(parts) == 1:  # Just seconds (e.g., "59")
                        duration = int(parts[0])
                    elif len(parts) == 2:  # MM:SS
                        mins, secs = int(parts[0]), int(parts[1])
                        if mins < 0 or secs < 0 or secs >= 60:
                            raise ValueError(f"Invalid time values in duration: {duration_str}")
                        duration = mins * 60 + secs
                    elif len(parts) == 3:  # HH:MM:SS
                        hours, mins, secs = int(parts[0]), int(parts[1]), int(parts[2])
                        if hours < 0 or mins < 0 or secs < 0 or mins >= 60 or secs >= 60:
                            raise ValueError(f"Invalid time values in duration: {duration_str}")
                        duration = hours * 3600 + mins * 60 + secs
                    else:
                        raise ValueError(f"Invalid duration format: {duration_str}")

                    # Validate duration is reasonable (max 24 hours to prevent slider issues)
                    MAX_DURATION = 24 * 3600  # 24 hours in seconds
                    if duration < 0:
                        raise ValueError(f"Negative duration: {duration}")
                    if duration > MAX_DURATION:
                        logger.warning(f"Duration {duration}s exceeds max, capping to {MAX_DURATION}s")
                        duration = MAX_DURATION

                    self.video_duration = duration
                except (ValueError, OverflowError) as e:
                    raise ValueError(f"Invalid duration format: {duration_str} ({e})")

                # Update UI on main thread
                video_title = None
                if title_result and title_result.returncode == 0:
                    video_title = title_result.stdout.strip()
                    self.video_title = video_title
                    logger.info(f"Video title: {video_title}")

                self._safe_after(0, lambda: self._update_duration_ui(video_title))

                # Fetch estimated file size
                self._fetch_file_size(url)

                self.update_status('Duration fetched successfully', "green")
                logger.info(f"Successfully fetched video duration: {self.video_duration}s")
            else:
                raise Exception(f"yt-dlp returned error: {result.stderr}")

        except subprocess.TimeoutExpired:
            error_msg = 'Request timed out. Please check your internet connection.'
            self._safe_after(0, lambda: messagebox.showerror('Error', error_msg))
            self.update_status('Duration fetch timed out', "red")
            logger.error("Timeout fetching video duration")
        except ValueError as e:
            error_msg = f'Invalid duration format received: {e}'
            self._safe_after(0, lambda: messagebox.showerror('Error', error_msg))
            self.update_status('Invalid duration format', "red")
            logger.error(f"Duration parsing error: {e}")
        except Exception as e:
            err_msg = f'Failed to fetch video duration:\n{e}'
            self._safe_after(0, lambda: messagebox.showerror('Error', err_msg))
            self.update_status('Failed to fetch duration', "red")
            logger.exception(f"Unexpected error fetching duration: {e}")

        finally:
            with self.fetch_lock:
                self.is_fetching_duration = False
            self._safe_after(0, lambda: self.fetch_duration_btn.config(state='normal') if self.trim_enabled_var.get() else None)

    def _update_duration_ui(self, video_title=None):
        """Update duration-related UI elements on the main thread"""
        self.start_slider.config(from_=0, to=self.video_duration, state='normal')
        self.end_slider.config(from_=0, to=self.video_duration, state='normal')
        self.start_time_var.set(0)
        self.end_time_var.set(self.video_duration)

        self.start_time_entry.config(state='normal')
        self.end_time_entry.config(state='normal')
        self.start_time_entry.delete(0, tk.END)
        self.start_time_entry.insert(0, self.seconds_to_hms(0))
        self.end_time_entry.delete(0, tk.END)
        self.end_time_entry.insert(0, self.seconds_to_hms(self.video_duration))

        self.trim_duration_label.config(text=f'Selected Duration: {self.seconds_to_hms(self.video_duration)}')

        if video_title:
            self.video_info_label.config(text=f'Title: {video_title}')

        self.root.after(UI_INITIAL_DELAY_MS, self.update_previews)

    def _update_duration_ui_local(self, video_title):
        """Update duration-related UI for local files on the main thread"""
        self._update_duration_ui()
        if video_title:
            self.video_info_label.config(text=f'File: {video_title}')

    def _fetch_file_size(self, url):
        """Fetch estimated file size for the video (runs in background thread)"""
        def _fetch():
            try:
                quality = self.quality_var.get()

                # Build format selector based on quality
                if quality.startswith("none") or quality == "none (Audio only)":
                    format_selector = "bestaudio"
                else:
                    format_selector = f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]'

                cmd = [self.ytdlp_path, '--dump-json', '-f', format_selector, url]
                result = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace', timeout=STREAM_FETCH_TIMEOUT, **_subprocess_kwargs)

                if result.returncode == 0:
                    info = json.loads(result.stdout)
                    filesize = info.get('filesize') or info.get('filesize_approx')

                    if filesize:
                        # Convert to MB and update UI on main thread
                        filesize_mb = filesize / BYTES_PER_MB
                        self._safe_after(0, lambda: self._update_filesize_display(filesize, filesize_mb))
                    else:
                        self._safe_after(0, lambda: self._update_filesize_display(None, None))
                else:
                    self._safe_after(0, lambda: self._update_filesize_display(None, None))
            except Exception as e:
                logger.debug(f"Could not fetch file size: {e}")
                self._safe_after(0, lambda: self._update_filesize_display(None, None))

        # Run in background thread
        self.thread_pool.submit(_fetch)

    def _update_filesize_display(self, filesize_bytes, filesize_mb):
        """Update file size display on main thread"""
        if filesize_bytes and filesize_mb:
            self.filesize_label.config(text=f'Estimated size: {filesize_mb:.1f} MB')
            self.estimated_filesize = filesize_bytes
        elif filesize_mb is None and filesize_bytes is None:
            self.filesize_label.config(text='Estimated size: Unknown')
            self.estimated_filesize = None

        # Update trimmed size if trimming is enabled
        self._update_trimmed_filesize()

    def _on_keep_below_10mb_toggle(self):
        """Enable/disable quality dropdown based on 10MB checkbox state."""
        if self.keep_below_10mb_var.get():
            self.quality_combo.config(state='disabled')
        else:
            self.quality_combo.config(state='readonly')

    def on_quality_change(self, *args):
        """Handle quality selection changes - re-fetch file size with new quality"""
        # Disable 10MB checkbox for audio-only
        quality = self.quality_var.get()
        if quality.startswith("none") or "none (Audio only)" in quality:
            self.keep_below_10mb_var.set(False)
            self.keep_below_10mb_check.config(state='disabled')
            self.quality_combo.config(state='readonly')
        else:
            self.keep_below_10mb_check.config(state='normal')

        # Only re-fetch if we have a valid URL and have already fetched duration
        if self.current_video_url and self.video_duration > 0 and not self.is_playlist:
            # Show loading indicator
            self.filesize_label.config(text='Calculating size...')
            # Re-fetch file size with new quality setting (in background)
            self._fetch_file_size(self.current_video_url)

    def _update_trimmed_filesize(self):
        """Update file size estimate based on trim selection using linear calculation"""
        if not self.estimated_filesize or not self.trim_enabled_var.get():
            # If no size estimate or trimming disabled, show original size
            if self.estimated_filesize:
                filesize_mb = self.estimated_filesize / BYTES_PER_MB
                self.filesize_label.config(text=f'Estimated size: {filesize_mb:.1f} MB')
            return

        # Calculate trimmed size using linear approach
        start_time = int(self.start_time_var.get())
        end_time = int(self.end_time_var.get())
        selected_duration = end_time - start_time

        if self.video_duration > 0:
            duration_percentage = selected_duration / self.video_duration
            trimmed_size = self.estimated_filesize * duration_percentage
            trimmed_size_mb = trimmed_size / BYTES_PER_MB
            self.filesize_label.config(text=f'Estimated size (trimmed): {trimmed_size_mb:.1f} MB — with re-encoding/trimming file will be larger')

    def _fetch_local_file_duration(self, filepath):
        """Fetch duration from local file using ffprobe"""
        try:
            cmd = [
                self.ffprobe_path,
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                filepath
            ]

            result = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace', timeout=FFPROBE_TIMEOUT, check=True, **_subprocess_kwargs)
            duration_seconds = float(result.stdout.strip())
            self.video_duration = int(duration_seconds)

            video_title = Path(filepath).stem

            # Update UI on main thread
            self._safe_after(0, lambda vt=video_title: self._update_duration_ui_local(vt))
            self.update_status('Duration fetched successfully', "green")
            logger.info(f"Local file duration: {self.video_duration}s")

        except subprocess.CalledProcessError as e:
            error_msg = f'Failed to read video file:\n{e.stderr if e.stderr else str(e)}'
            self._safe_after(0, lambda: messagebox.showerror('Error', error_msg))
            self.update_status('Failed to read file:\n', "red")
            logger.error(f"ffprobe error: {e}")
        except ValueError as e:
            error_msg = 'Invalid video file format'
            self._safe_after(0, lambda: messagebox.showerror('Error', error_msg))
            self.update_status('Invalid video file format', "red")
            logger.error(f"Duration parsing error: {e}")
        except Exception as e:
            err_msg = f'Failed to read file:\n{e}'
            self._safe_after(0, lambda: messagebox.showerror('Error', err_msg))
            self.update_status('Failed to read file:\n', "red")
            logger.exception(f"Unexpected error reading local file: {e}")
        finally:
            with self.fetch_lock:
                self.is_fetching_duration = False
            self._safe_after(0, lambda: self.fetch_duration_btn.config(state='normal') if self.trim_enabled_var.get() else None)

    def on_slider_change(self, event=None):
        """Handle slider changes and enforce valid time ranges.

        Called when start/end time sliders are moved by the user or programmatically.
        Ensures start time is always before end time by automatically adjusting
        the other slider when needed.

        Args:
            event: Optional event object. If None, no automatic adjustment occurs
                   (used for programmatic updates to prevent adjustment loops)

        Behavior:
            - If start >= end and event exists, adjusts the non-moved slider
            - Updates HH:MM:SS entry fields to match slider values
            - Recalculates selected duration label
            - Updates estimated file size for trimmed segment
            - Schedules debounced preview frame update
        """
        start_time = int(self.start_time_var.get())
        end_time = int(self.end_time_var.get())

        # Ensure start is before end
        if start_time >= end_time:
            if event:  # Only adjust if this was a user interaction
                # Determine which slider was moved and adjust the other
                if abs(self.start_slider.get() - start_time) < 0.1:  # Start slider was moved
                    end_time = min(start_time + 1, self.video_duration)
                    self.end_time_var.set(end_time)
                else:  # End slider was moved
                    start_time = max(end_time - 1, 0)
                    self.start_time_var.set(start_time)

        # Update entry fields
        self.start_time_entry.delete(0, tk.END)
        self.start_time_entry.insert(0, self.seconds_to_hms(start_time))
        self.end_time_entry.delete(0, tk.END)
        self.end_time_entry.insert(0, self.seconds_to_hms(end_time))

        # Update selected duration
        selected_duration = end_time - start_time
        self.trim_duration_label.config(text=f'Selected Duration: {self.seconds_to_hms(selected_duration)}')

        # Update file size based on trim selection
        self._update_trimmed_filesize()

        # Schedule preview update with debouncing
        self.schedule_preview_update()

    def hms_to_seconds(self, hms_str):
        """Convert HH:MM:SS format to seconds"""
        try:
            parts = hms_str.strip().split(':')
            if len(parts) != 3:
                return None
            hours, minutes, seconds = map(int, parts)
            if hours < 0 or not (0 <= minutes <= 59) or not (0 <= seconds <= 59):
                return 0
            return hours * 3600 + minutes * 60 + seconds
        except (ValueError, AttributeError):
            return None

    def on_start_entry_change(self, event=None):
        """Handle changes to start time entry field"""
        value_str = self.start_time_entry.get()
        seconds = self.hms_to_seconds(value_str)

        if seconds is not None and 0 <= seconds <= self.video_duration:
            # Valid input, update the slider
            self.start_time_var.set(seconds)
            # on_slider_change will be called automatically via the variable trace
            # But we need to trigger it manually since we're setting the variable directly
            self.on_slider_change()
        else:
            # Invalid input, restore the current value
            current_time = int(self.start_time_var.get())
            self.start_time_entry.delete(0, tk.END)
            self.start_time_entry.insert(0, self.seconds_to_hms(current_time))

    def on_end_entry_change(self, event=None):
        """Handle changes to end time entry field"""
        value_str = self.end_time_entry.get()
        seconds = self.hms_to_seconds(value_str)

        if seconds is not None and 0 <= seconds <= self.video_duration:
            # Valid input, update the slider
            self.end_time_var.set(seconds)
            # Trigger slider change handler
            self.on_slider_change()
        else:
            # Invalid input, restore the current value
            current_time = int(self.end_time_var.get())
            self.end_time_entry.delete(0, tk.END)
            self.end_time_entry.insert(0, self.seconds_to_hms(current_time))

    def on_volume_change(self, event=None):
        """Handle volume slider changes"""
        volume_percent = int(self.volume_var.get() * 100)
        self.volume_entry.delete(0, tk.END)
        self.volume_entry.insert(0, str(volume_percent))

    def on_volume_entry_change(self, event=None):
        """Handle volume entry field changes"""
        try:
            volume_percent = int(self.volume_entry.get())
            # Clamp to 0-200 range
            volume_percent = max(0, min(200, volume_percent))
            self.volume_var.set(volume_percent / 100.0)
            # Update entry with clamped value
            self.volume_entry.delete(0, tk.END)
            self.volume_entry.insert(0, str(volume_percent))
        except ValueError:
            # If invalid input, reset to current slider value
            volume_percent = int(self.volume_var.get() * 100)
            self.volume_entry.delete(0, tk.END)
            self.volume_entry.insert(0, str(volume_percent))

    def reset_volume(self):
        """Reset volume to 100%"""
        self.volume_var.set(1.0)
        self.volume_entry.delete(0, tk.END)
        self.volume_entry.insert(0, "100")

    def start_upload(self):
        """Start upload to Catbox.moe in a background thread"""
        if not self.last_output_file or not os.path.isfile(self.last_output_file):
            messagebox.showerror('Error', 'No file available to upload. Please download/process a video first.')
            return

        # Check file size (200MB limit for Catbox.moe)
        file_size_mb = os.path.getsize(self.last_output_file) / BYTES_PER_MB
        if file_size_mb > CATBOX_MAX_SIZE_MB:
            messagebox.showerror('File Too Large',
                               f"File size ({file_size_mb:.1f} MB) exceeds Catbox.moe's 200MB limit.\nPlease trim the video or use a lower quality setting.")
            return

        # Disable upload button during upload
        self.upload_btn.config(state='disabled')
        self.upload_status_label.config(text='Uploading...', foreground="blue")
        self.upload_url_frame.grid_remove()

        # Start upload in background thread
        self.thread_pool.submit(self.upload_to_catbox)

    def upload_to_catbox(self):
        """Upload file to Catbox.moe and display the URL"""
        try:
            with self.upload_lock:
                self.is_uploading = True
            logger.info(f"Starting upload to Catbox.moe: {self.last_output_file}")

            # Upload file using catboxpy
            file_url = self.catbox_client.upload(self.last_output_file)

            # Update UI on success
            self._safe_after(0, lambda: self._upload_success(file_url))
            logger.info(f"Upload successful: {file_url}")

        except Exception as e:
            error_msg = str(e)
            self._safe_after(0, lambda: self._upload_failed(error_msg))
            logger.exception(f"Upload failed: {e}")

        finally:
            with self.upload_lock:
                self.is_uploading = False

    def _upload_success(self, file_url):
        """Handle successful upload (called on main thread)"""
        self.upload_status_label.config(text='Upload complete!', foreground="green")

        # Show URL in entry field
        self.upload_url_entry.config(state='normal')
        self.upload_url_entry.delete(0, tk.END)
        self.upload_url_entry.insert(0, file_url)
        self.upload_url_entry.config(state='readonly')
        self.upload_url_frame.grid()

        # Re-enable upload button for re-uploading if needed
        self.upload_btn.config(state='normal')

        # Save upload link to history
        filename = os.path.basename(self.last_output_file) if self.last_output_file else "unknown"
        self.save_upload_link(file_url, filename)

        messagebox.showinfo('Upload Complete',
                          f'File uploaded successfully!\n\nURL: {file_url}\n\nThe URL has been copied to your clipboard.')

        # Auto-copy to clipboard
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(file_url)
        except tk.TclError:
            logger.warning("Failed to copy URL to clipboard")

    def _upload_failed(self, error_msg):
        """Handle failed upload (called on main thread)"""
        self.upload_status_label.config(text='Upload failed', foreground="red")
        self.upload_btn.config(state='normal')
        messagebox.showerror('Upload Failed', f'Failed to upload file:\n\n{error_msg}')

    def copy_upload_url(self):
        """Copy upload URL to clipboard"""
        url = self.upload_url_entry.get()
        if url:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self.upload_status_label.config(text='URL copied to clipboard!', foreground="green")
            logger.info("Upload URL copied to clipboard")

    # Uploader tab methods

    def browse_uploader_files(self):
        """Browse and select multiple files for upload in Uploader tab"""
        file_paths = filedialog.askopenfilenames(
            title='Select Video Files',
            filetypes=[
                ('Video files', "*.mp4 *.avi *.mkv *.mov *.flv *.wmv *.webm *.m4v"),
                ('Audio files', "*.mp3 *.m4a *.wav *.flac *.aac *.ogg"),
                ('All files', "*.*")
            ]
        )

        if file_paths:
            for file_path in file_paths:
                # Check file size
                file_size_mb = os.path.getsize(file_path) / BYTES_PER_MB
                if file_size_mb > CATBOX_MAX_SIZE_MB:
                    messagebox.showwarning('File Too Large',
                                         f'Skipped: {os.path.basename(file_path)}\nFile size ({file_size_mb:.1f} MB) exceeds 200MB limit.')
                    continue

                # Add to queue if not already there
                with self.uploader_lock:
                    already_in_queue = any(item['path'] == file_path for item in self.uploader_file_queue)
                if not already_in_queue:
                    self._add_file_to_uploader_queue(file_path)
                    logger.info(f"Added file to upload queue: {file_path}")

    def _add_file_to_uploader_queue(self, file_path):
        """Add a file to the upload queue with UI widget"""
        file_frame = ttk.Frame(self.uploader_file_list_frame, relief='solid', borderwidth=1)
        file_frame.pack(fill=tk.X, padx=5, pady=2)

        filename = os.path.basename(file_path)
        file_size_mb = os.path.getsize(file_path) / BYTES_PER_MB

        file_label = ttk.Label(file_frame, text=f'{filename} ({file_size_mb:.1f} MB)', font=('Arial', 9))
        file_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 10))

        remove_btn = ttk.Button(file_frame, text="X", width=3,
                              command=lambda: self._remove_file_from_queue(file_path))
        remove_btn.pack(side=tk.RIGHT, padx=5)

        with self.uploader_lock:
            self.uploader_file_queue.append({'path': file_path, 'widget': file_frame})
        self._update_uploader_queue_count()

        with self.uploader_lock:
            is_uploading = self.uploader_is_uploading
            queue_len = len(self.uploader_file_queue)
        if queue_len > 0 and not is_uploading:
            self.uploader_upload_btn.config(state='normal')

    def _remove_file_from_queue(self, file_path):
        """Remove a file from the upload queue"""
        widget_to_destroy = None
        with self.uploader_lock:
            for i, item in enumerate(self.uploader_file_queue):
                if item['path'] == file_path:
                    widget_to_destroy = item.get('widget')
                    self.uploader_file_queue.pop(i)
                    logger.info(f"Removed file from queue: {file_path}")
                    break
        if widget_to_destroy:
            widget_to_destroy.destroy()
        self._update_uploader_queue_count()
        with self.uploader_lock:
            if len(self.uploader_file_queue) == 0:
                self.uploader_upload_btn.config(state='disabled')

    def clear_uploader_queue(self):
        """Clear all files from upload queue"""
        with self.uploader_lock:
            is_uploading = self.uploader_is_uploading
        if is_uploading:
            messagebox.showwarning('Cannot Clear', 'Cannot clear queue while uploads are in progress.')
            return

        widgets_to_destroy = []
        with self.uploader_lock:
            for item in self.uploader_file_queue:
                if item.get('widget'):
                    widgets_to_destroy.append(item['widget'])
            self.uploader_file_queue.clear()
        for widget in widgets_to_destroy:
            widget.destroy()
        self._update_uploader_queue_count()
        self.uploader_upload_btn.config(state='disabled')
        logger.info("Cleared all files from upload queue")

    def _update_uploader_queue_count(self):
        """Update file queue count label"""
        with self.uploader_lock:
            count = len(self.uploader_file_queue)
        s = 's' if count != 1 else ''
        self.uploader_queue_count_label.config(text=f'({count} file{s})')

    def start_uploader_upload(self):
        """Start uploading all files in queue sequentially"""
        with self.uploader_lock:
            queue_empty = len(self.uploader_file_queue) == 0
        if queue_empty:
            messagebox.showinfo('No Files', 'No files in queue. Please add files first.')
            return

        with self.uploader_lock:
            is_uploading = self.uploader_is_uploading
        if is_uploading:
            return

        with self.uploader_lock:
            self.uploader_is_uploading = True
        self.uploader_current_index = 0
        self.uploader_upload_btn.config(state='disabled')
        self.uploader_url_frame.grid_remove()

        # Start upload queue processing in background thread
        self.thread_pool.submit(self._process_uploader_queue)

    def _process_uploader_queue(self):
        """Process upload queue sequentially"""
        with self.uploader_lock:
            queue_snapshot = list(self.uploader_file_queue)
        total_count = len(queue_snapshot)

        for index, item in enumerate(queue_snapshot):
            with self.uploader_lock:
                is_uploading = self.uploader_is_uploading
            if not is_uploading:
                logger.info("Uploader queue processing stopped by user")
                break

            file_path = item['path']
            filename = os.path.basename(file_path)

            self._safe_after(0, lambda i=index, t=total_count, fn=filename:
                self.uploader_status_label.config(
                    text=f'Uploading {i+1}/{t}: {fn}...',
                    foreground="blue"))

            success = self._upload_single_file(file_path)

            if not success:
                # Continue with next file even if one fails
                continue

        self._safe_after(0, self._finish_uploader_queue)

    def _upload_single_file(self, file_path):
        """Upload a single file from the queue. Returns True if successful."""
        try:
            logger.info(f"Uploading file from queue: {file_path}")

            # Upload file using catboxpy
            file_url = self.catbox_client.upload(file_path)

            # Save upload link to history
            filename = os.path.basename(file_path)
            self.save_upload_link(file_url, filename)

            # Show latest URL in entry field
            self._safe_after(0, lambda url=file_url: self._show_upload_url(url))

            logger.info(f"Upload successful: {file_url}")
            return True

        except Exception as e:
            logger.exception(f"Upload failed for {file_path}: {e}")
            error_msg = str(e)
            filename = os.path.basename(file_path)
            full_error = f"Failed to upload {filename}:\n\n{error_msg}"
            self._safe_after(0, lambda msg=full_error:
                messagebox.showerror('Upload Failed', msg))
            return False

    def _show_upload_url(self, file_url):
        """Display the most recent upload URL"""
        self.uploader_url_entry.config(state='normal')
        self.uploader_url_entry.delete(0, tk.END)
        self.uploader_url_entry.insert(0, file_url)
        self.uploader_url_entry.config(state='readonly')
        self.uploader_url_frame.grid()

        # Auto-copy to clipboard
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(file_url)
        except tk.TclError:
            logger.warning("Failed to copy URL to clipboard")

    def _finish_uploader_queue(self):
        """Clean up after queue upload completes"""
        widgets_to_destroy = []
        with self.uploader_lock:
            self.uploader_is_uploading = False

            # Collect widgets and clear the queue
            for item in self.uploader_file_queue:
                if item.get('widget'):
                    widgets_to_destroy.append(item['widget'])

            count = len(self.uploader_file_queue)
            self.uploader_file_queue.clear()
        for widget in widgets_to_destroy:
            widget.destroy()
        self._update_uploader_queue_count()

        self.uploader_status_label.config(text=f'All uploads complete! ({count} files)', foreground="green")
        self.uploader_upload_btn.config(state='disabled')

        logger.info(f"Uploader queue finished: {count} files uploaded")

    def copy_uploader_url(self):
        """Copy upload URL to clipboard from Uploader tab"""
        url = self.uploader_url_entry.get()
        if url:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self.uploader_status_label.config(text='URL copied to clipboard!', foreground="green")
            logger.info("Upload URL copied to clipboard from Uploader tab")

    def _find_latest_file(self):
        """Find the most recently created file in the download directory"""
        try:
            download_dir = Path(self.download_path)
            if not download_dir.exists():
                return None

            # Get all files (not directories) in download directory
            files = [f for f in download_dir.iterdir() if f.is_file()]
            if not files:
                return None

            # Find most recently created file
            latest_file = max(files, key=lambda f: f.stat().st_ctime)
            return str(latest_file)

        except Exception as e:
            logger.error(f"Error finding latest file: {e}")
            return None

    def _enable_upload_button(self, filepath):
        """Enable upload button after successful download (thread-safe)"""
        if filepath and os.path.isfile(filepath):
            self.last_output_file = filepath
            self._safe_after(0, lambda: self._do_enable_upload(filepath))

    def _do_enable_upload(self, filepath):
        """Actual upload button enable on main thread"""
        self.upload_btn.config(state='normal')
        logger.info(f"Upload enabled for: {filepath}")

        # Auto-upload if enabled (but not for playlists)
        if self.auto_upload_var.get():
            url = self.url_entry.get().strip()
            if url and self.is_playlist_url(url):
                logger.info("Auto-upload skipped for playlist URL")
            else:
                logger.info("Auto-upload enabled, starting upload...")
                self.root.after(AUTO_UPLOAD_DELAY_MS, self.start_upload)

    def schedule_preview_update(self):
        """Schedule preview update with debouncing to avoid excessive calls"""
        if self._shutting_down:
            return

        # Cancel any pending update
        if self.preview_update_timer:
            self.root.after_cancel(self.preview_update_timer)

        # Schedule new update after debounce delay
        self.preview_update_timer = self.root.after(PREVIEW_DEBOUNCE_MS, self.update_previews)

    def _clear_preview_cache(self):
        """Clear the preview frame cache, deleting cached files from disk"""
        logger.info("Clearing preview cache")
        for timestamp, file_path in self.preview_cache.items():
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except OSError as e:
                logger.debug(f"Failed to delete cached preview file {file_path}: {e}")
        self.preview_cache.clear()

    def _cache_preview_frame(self, timestamp, file_path):
        """Add a frame to the cache with LRU eviction (O(1) operations with OrderedDict)"""
        # If timestamp already exists, remove it first to update position
        if timestamp in self.preview_cache:
            del self.preview_cache[timestamp]

        # Remove oldest if cache is full
        if len(self.preview_cache) >= PREVIEW_CACHE_SIZE:
            # popitem(last=False) removes the oldest (first) item in O(1)
            oldest_key, old_path = self.preview_cache.popitem(last=False)
            # Optionally delete the old cached file
            try:
                if os.path.exists(old_path):
                    os.remove(old_path)
            except OSError:
                pass  # File may already be removed or locked

        # Add to cache (will be at the end, marking it as most recently used)
        self.preview_cache[timestamp] = file_path

    def _get_cached_frame(self, timestamp):
        """Get a cached frame if available (O(1) with OrderedDict.move_to_end)"""
        if timestamp in self.preview_cache:
            # Update access order (move to end as most recently used) - O(1) operation
            self.preview_cache.move_to_end(timestamp)
            return self.preview_cache[timestamp]
        return None

    def extract_frame(self, timestamp):
        """Extract a single frame at the given timestamp"""
        if not self.current_video_url:
            return None

        # Check cache first
        cached = self._get_cached_frame(timestamp)
        if cached and os.path.exists(cached):
            logger.debug(f"Using cached frame for timestamp {timestamp}s")
            return cached

        try:
            # Create unique temp file for this frame
            temp_file = os.path.join(self.temp_dir, f"frame_{timestamp}.jpg")

            # Handle local files differently
            if self.is_local_file(self.current_video_url):
                # For local files, use the file path directly
                video_url = self.current_video_url
            else:
                # Get the actual video stream URL using yt-dlp with retry
                # Use a format that includes video+audio to avoid segmented streams
                def _get_stream_url():
                    get_url_cmd = [
                        self.ytdlp_path,
                        '-f', 'best[height<=480]/best',  # Combined format is more reliable for frame extraction
                        '--no-playlist',
                        '-g',
                        self.current_video_url
                    ]
                    return subprocess.run(get_url_cmd, capture_output=True, encoding='utf-8', errors='replace', timeout=STREAM_FETCH_TIMEOUT, check=True, **_subprocess_kwargs)

                result = self.retry_network_operation(_get_stream_url, f"Get stream URL for frame at {timestamp}s")
                video_url = result.stdout.strip().split('\n')[0]

                if not video_url:
                    logger.error("Failed to get stream URL - empty response")
                    return None

                # Validate that the stream URL looks like a valid URL
                if not (video_url.startswith('http://') or video_url.startswith('https://')):
                    logger.error(f"Invalid stream URL format: {video_url[:100]}")
                    return None

            # Now extract frame from the actual stream with retry
            def _extract_frame():
                cmd = [
                    self.ffmpeg_path,
                    '-nostdin',
                ]
                # Add HTTP streaming options for YouTube URLs
                if video_url.startswith('http'):
                    cmd.extend([
                        '-reconnect', '1',
                        '-reconnect_streamed', '1',
                        '-reconnect_delay_max', '5',
                        '-timeout', '10000000',  # 10 second timeout in microseconds
                    ])
                cmd.extend([
                    '-ss', str(timestamp),
                    '-i', video_url,
                    '-vframes', '1',
                    '-q:v', '2',
                    '-y',
                    temp_file
                ])
                return subprocess.run(cmd, capture_output=True, timeout=STREAM_FETCH_TIMEOUT, check=True, **_subprocess_kwargs)

            self.retry_network_operation(_extract_frame, f"Extract frame at {timestamp}s")

            if os.path.exists(temp_file):
                # Cache the extracted frame
                self._cache_preview_frame(timestamp, temp_file)
                return temp_file

        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout while extracting frame at {timestamp}s")
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error extracting frame at {timestamp}s: {e}")
        except Exception as e:
            logger.error(f"Unexpected error extracting frame at {timestamp}s: {e}")

        return None

    def update_previews(self):
        """Update both preview images"""
        if self._shutting_down:
            return

        if not self.current_video_url or self.video_duration == 0:
            return

        # Prevent spawning multiple preview threads (thread-safe)
        with self.preview_lock:
            if self.preview_thread_running:
                return
            self.preview_thread_running = True

        start_time = int(float(self.start_time_var.get()))
        end_time = int(float(self.end_time_var.get()))

        # Show loading indicators
        self.start_preview_label.config(image=self.loading_image)
        self.end_preview_label.config(image=self.loading_image)

        # Submit to thread pool instead of creating new thread
        try:
            self.thread_pool.submit(self._update_previews_thread, start_time, end_time)
        except RuntimeError:
            # Thread pool already shut down
            with self.preview_lock:
                self.preview_thread_running = False

    def _update_previews_thread(self, start_time, end_time):
        """Background thread to extract and update preview frames"""
        try:
            # Adjust end_time if it's at or near the video end (ffmpeg struggles with exact EOF)
            adjusted_end_time = end_time
            if self.video_duration > 0 and end_time >= self.video_duration - 1:
                adjusted_end_time = max(0, self.video_duration - 3)  # 3 seconds before end
                logger.debug(f"Adjusted end preview time from {end_time}s to {adjusted_end_time}s (near EOF)")

            logger.info(f"Extracting preview frames at {start_time}s and {adjusted_end_time}s")

            # Extract start frame
            start_frame_path = self.extract_frame(start_time)
            if start_frame_path:
                self._update_preview_image(start_frame_path, 'start')
            else:
                # Show error placeholder if extraction failed
                error_img = self.create_placeholder_image(PREVIEW_WIDTH, PREVIEW_HEIGHT, 'Error')
                self.start_preview_image = error_img  # Keep reference to avoid GC
                self._safe_after(0, lambda img=error_img: self._set_start_preview(img))

            # Extract end frame (using adjusted time to avoid EOF issues)
            end_frame_path = self.extract_frame(adjusted_end_time)
            if end_frame_path:
                self._update_preview_image(end_frame_path, 'end')
            else:
                # Show error placeholder if extraction failed
                error_img = self.create_placeholder_image(PREVIEW_WIDTH, PREVIEW_HEIGHT, 'Error')
                self.end_preview_image = error_img  # Keep reference to avoid GC
                self._safe_after(0, lambda img=error_img: self._set_end_preview(img))
        finally:
            # Use lock when resetting flag to prevent race condition with spawn check
            with self.preview_lock:
                self.preview_thread_running = False

    def _update_preview_image(self, image_path, position):
        """Update preview image in UI (must be called from main thread or scheduled)"""
        try:
            # Load and resize image (using context manager for proper cleanup)
            with Image.open(image_path) as img:
                img.thumbnail((PREVIEW_WIDTH, PREVIEW_HEIGHT), Image.Resampling.LANCZOS)
                # Convert to PhotoImage (must be done before context exits)
                photo = ImageTk.PhotoImage(img)

            # CRITICAL: Store reference BEFORE scheduling to prevent GC
            # The lambda uses default argument to capture the photo object immediately
            if position == 'start':
                self.start_preview_image = photo  # Keep reference to avoid GC
                self._safe_after(0, lambda p=photo: self._set_start_preview(p))
            else:
                self.end_preview_image = photo  # Keep reference to avoid GC
                self._safe_after(0, lambda p=photo: self._set_end_preview(p))

        except Exception as e:
            logger.error(f"Error updating preview image for {position}: {e}")

    def _set_start_preview(self, photo):
        """Set start preview image (called on main thread)"""
        self.start_preview_image = photo  # Keep reference to avoid garbage collection
        self.start_preview_label.config(image=photo, text='')

    def _set_end_preview(self, photo):
        """Set end preview image (called on main thread)"""
        self.end_preview_image = photo  # Keep reference to avoid garbage collection
        self.end_preview_label.config(image=photo, text='')

    def change_path(self):
        """Change download path with validation"""
        path = filedialog.askdirectory(initialdir=self.download_path)
        if path:
            # Validate path for security (prevent path traversal)
            is_valid, normalized_path, error_msg = self.validate_download_path(path)
            if not is_valid:
                messagebox.showerror('Error', error_msg)
                return

            path = normalized_path

            # Validate that path exists and is writable
            if not os.path.exists(path):
                messagebox.showerror('Error', f'Path does not exist: {path}')
                return

            if not os.path.isdir(path):
                messagebox.showerror('Error', f'Path is not a directory: {path}')
                return

            # Test write permissions
            test_file = os.path.join(path, ".ytdl_write_test")
            try:
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
            except (IOError, OSError) as e:
                messagebox.showerror('Error', f'Path is not writable:\n{path}\n\n{e}')
                return

            self.download_path = path
            self.path_label.config(text=path)

    def open_download_folder(self):
        """Open the download folder in the system file manager"""
        try:
            if sys.platform == 'win32':
                os.startfile(self.download_path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', self.download_path], close_fds=True, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(['xdg-open', self.download_path], close_fds=True, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            messagebox.showerror('Error', f'Failed to open folder:\n{e}')

    def browse_local_file(self):
        """Open file dialog to select a local video file"""
        filetypes = [
            ('Video files', '*.mp4 *.mkv *.avi *.mov *.flv *.webm *.wmv *.m4v'),
            ('All files', '*.*')
        ]

        filepath = filedialog.askopenfilename(
            title='Select a video file',
            filetypes=filetypes,
            initialdir=str(Path.home())
        )

        if filepath:
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, filepath)
            self.local_file_path = filepath
            self.mode_label.config(
                text=f'Mode: Local File | {Path(filepath).name}',
                foreground="green"
            )
            # Clear filename field for new file
            self.filename_entry.delete(0, tk.END)
            logger.info(f"Local file selected: {filepath}")

    def on_url_change(self, event=None):
        """Detect if input is URL or file path"""
        input_text = self.url_entry.get().strip()

        if not input_text:
            self.mode_label.config(text="")
            self.local_file_path = None
            return

        # Clear filename field when URL/file changes
        self.filename_entry.delete(0, tk.END)

        if self.is_local_file(input_text):
            self.local_file_path = input_text
            self.mode_label.config(
                text=f'Mode: Local File | {Path(input_text).name}',
                foreground="green"
            )
        else:
            self.local_file_path = None
            self.mode_label.config(
                text='Mode: YouTube Download',
                foreground="green"
            )

    def is_local_file(self, input_text):
        """Check if input is a local file path"""
        if os.path.isfile(input_text):
            return True

        path = Path(input_text)
        video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm', '.wmv', '.m4v', '.ts', '.mpg', '.mpeg'}
        if path.suffix.lower() in video_extensions:
            return True

        return False

    def _get_bundled_executable(self, name):
        """Get path to bundled executable (ffmpeg/ffprobe/yt-dlp) if available"""
        # When packaged with PyInstaller, bundled files are in sys._MEIPASS
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            if sys.platform == 'win32':
                exe_name = f"{name}.exe"
            else:
                exe_name = name

            # Check next to the main executable first (user-updated copy takes priority)
            exe_dir = os.path.dirname(sys.executable)
            local_path = os.path.join(exe_dir, exe_name)
            if os.path.exists(local_path):
                logger.info(f"Using local {name}: {local_path}")
                return local_path

            # Fall back to bundled copy in _MEIPASS temp dir
            bundle_dir = getattr(sys, '_MEIPASS', exe_dir)
            bundled_path = os.path.join(bundle_dir, exe_name)
            if os.path.exists(bundled_path):
                logger.info(f"Using bundled {name}: {bundled_path}")
                return bundled_path

        # When running from source, check local venv first
        else:
            # Check venv in script directory
            script_dir = Path(__file__).parent
            # Windows uses Scripts folder, Unix uses bin
            if sys.platform == 'win32':
                venv_subdir = 'Scripts'
                exe_name = f"{name}.exe"
            else:
                venv_subdir = 'bin'
                exe_name = name

            venv_path = script_dir / 'venv' / venv_subdir / exe_name
            if venv_path.exists():
                logger.info(f"Using venv {name}: {venv_path}")
                return str(venv_path)

            # Check current Python's bin directory (if venv is activated)
            python_bin_path = Path(sys.executable).parent / exe_name
            if python_bin_path.exists():
                logger.info(f"Using Python bin {name}: {python_bin_path}")
                return str(python_bin_path)

        # Fall back to system PATH
        return name

    def check_dependencies(self):
        """Check if yt-dlp, ffmpeg, and ffprobe are available"""
        try:
            # Check yt-dlp - for bundled apps, just verify the binary exists and is executable
            # Running --version can fail due to PyInstaller environment issues even when it works
            if os.path.isfile(self.ytdlp_path) and os.access(self.ytdlp_path, os.X_OK):
                # Try to get version but don't fail if it doesn't work
                result = subprocess.run([self.ytdlp_path, '--version'],
                                      capture_output=True, timeout=DEPENDENCY_CHECK_TIMEOUT, **_subprocess_kwargs)
                version = result.stdout.decode('utf-8', errors='replace').strip()
                if version:
                    logger.info(f"yt-dlp version: {version}")
                else:
                    logger.info(f"yt-dlp is available at: {self.ytdlp_path}")
            elif shutil.which(self.ytdlp_path):
                # System PATH yt-dlp
                result = subprocess.run([self.ytdlp_path, '--version'],
                                      capture_output=True, timeout=DEPENDENCY_CHECK_TIMEOUT, **_subprocess_kwargs)
                logger.info(f"yt-dlp version: {result.stdout.decode('utf-8', errors='replace').strip()}")
            else:
                logger.error(f"yt-dlp not found at: {self.ytdlp_path}")
                return False

            # Check ffmpeg (use bundled or system)
            result = subprocess.run([self.ffmpeg_path, '-version'],
                                  capture_output=True, timeout=DEPENDENCY_CHECK_TIMEOUT, **_subprocess_kwargs)
            if result.returncode == 0:
                logger.info(f"ffmpeg is available at: {self.ffmpeg_path}")
            else:
                logger.error("ffmpeg check failed")
                return False

            # Check ffprobe (use bundled or system)
            result = subprocess.run([self.ffprobe_path, '-version'],
                                  capture_output=True, timeout=DEPENDENCY_CHECK_TIMEOUT, **_subprocess_kwargs)
            if result.returncode == 0:
                logger.info(f"ffprobe is available at: {self.ffprobe_path}")
            else:
                logger.error("ffprobe check failed")
                return False

            return True
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.error(f"Dependency check failed: {e}")
            return False

    def _detect_hw_encoder(self):
        """Probe for hardware H.264 encoders (AMD AMF, NVIDIA NVENC). Returns encoder name or None."""
        if not self.dependencies_ok:
            return None
        # Try encoders in order of preference
        for encoder in ('h264_amf', 'h264_nvenc'):
            try:
                probe_out = os.path.join(tempfile.gettempdir(), f'ytdl_hwprobe.mp4')
                cmd = [self.ffmpeg_path, '-hide_banner', '-y', '-loglevel', 'error',
                       '-f', 'lavfi', '-i', 'testsrc2=size=64x64:rate=25:duration=1',
                       '-vf', 'format=nv12', '-frames:v', '10',
                       '-c:v', encoder, probe_out]
                result = subprocess.run(cmd, capture_output=True, timeout=10, **_subprocess_kwargs)
                try:
                    os.remove(probe_out)
                except OSError:
                    pass
                if result.returncode == 0:
                    logger.info(f"Hardware encoder available: {encoder}")
                    return encoder
                else:
                    stderr = result.stderr.decode('utf-8', errors='replace').strip()
                    logger.info(f"Hardware encoder {encoder} not available: {stderr[-200:]}")
            except (subprocess.TimeoutExpired, OSError) as e:
                logger.info(f"Hardware encoder {encoder} probe failed: {e}")
        logger.info("No hardware encoder found, using libx264")
        return None

    def _get_video_encoder_args(self, mode='crf', target_bitrate=None):
        """Get video encoder arguments based on available hardware.

        Args:
            mode: 'crf' for quality-based (trim/volume), 'bitrate' for target bitrate (10MB)
            target_bitrate: Required when mode='bitrate'

        Returns:
            list: ffmpeg encoder arguments
        """
        if self.hw_encoder:
            if mode == 'crf':
                if self.hw_encoder == 'h264_amf':
                    return ['-c:v', 'h264_amf', '-quality', 'balanced', '-rc', 'cqp', '-qp_i', '23', '-qp_p', '23']
                else:  # h264_nvenc
                    return ['-c:v', 'h264_nvenc', '-preset', 'p4', '-rc', 'constqp', '-qp', '23']
            else:  # bitrate mode
                maxrate = int(target_bitrate * 1.5)
                bufsize = int(target_bitrate * 2)
                if self.hw_encoder == 'h264_amf':
                    return ['-c:v', 'h264_amf', '-quality', 'balanced',
                            '-b:v', str(target_bitrate), '-maxrate', str(maxrate), '-bufsize', str(bufsize)]
                else:  # h264_nvenc
                    return ['-c:v', 'h264_nvenc', '-preset', 'p4',
                            '-b:v', str(target_bitrate), '-maxrate', str(maxrate), '-bufsize', str(bufsize)]
        else:
            # Software fallback
            if mode == 'crf':
                return ['-c:v', 'libx264', '-crf', str(VIDEO_CRF), '-preset', 'ultrafast']
            else:  # bitrate mode
                maxrate = int(target_bitrate * 1.5)
                bufsize = int(target_bitrate * 2)
                return ['-c:v', 'libx264', '-b:v', str(target_bitrate),
                        '-maxrate', str(maxrate), '-bufsize', str(bufsize), '-preset', 'ultrafast']

    def start_download(self):
        url = self.url_entry.get().strip()

        if not url:
            messagebox.showerror('Error', 'Please enter a YouTube URL or select a local file')
            return

        # Check if local file or YouTube URL
        is_local = self.is_local_file(url)

        if is_local:
            # Validate local file exists
            if not os.path.isfile(url):
                messagebox.showerror('Error', f'File not found:\n{url}')
                return
        else:
            # Validate YouTube URL
            is_valid, message = self.validate_youtube_url(url)
            if not is_valid:
                messagebox.showerror('Invalid URL', message)
                logger.warning(f"Invalid URL rejected for download: {url}")
                return

            # Check if it's a playlist and update flag
            if self.is_playlist_url(url) and not self.is_pure_playlist_url(url):
                # Video URL with playlist context — strip playlist params
                url = self.strip_playlist_params(url)
                self.is_playlist = False
            else:
                self.is_playlist = self.is_playlist_url(url)

        if not self.dependencies_ok:
            messagebox.showerror('Error', 'yt-dlp or ffmpeg is not installed.\n\nInstall with:\npip install yt-dlp\n\nand install ffmpeg from your package manager')
            return

        logger.info(f"Starting download for URL: {url}")

        with self.download_lock:
            self.is_downloading = True
            self.download_start_time = time.time()
            self.last_progress_time = time.time()
        self.download_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.progress['value'] = 0
        self.progress_label.config(text="0%")

        # Submit download and timeout monitor to thread pool
        self.thread_pool.submit(self.download, url)
        self.thread_pool.submit(self._monitor_download_timeout)

    def _monitor_download_timeout(self):
        """Monitor download for timeouts (absolute and progress-based)"""
        while True:
            time.sleep(TIMEOUT_CHECK_INTERVAL)  # Check at configured interval

            if self._shutting_down:
                break

            with self.download_lock:
                is_still_downloading = self.is_downloading

            if not is_still_downloading:
                break

            current_time = time.time()

            # Check absolute timeout
            if self.download_start_time:
                elapsed = current_time - self.download_start_time
                if elapsed > DOWNLOAD_TIMEOUT:
                    logger.error(f"Download exceeded absolute timeout ({DOWNLOAD_TIMEOUT}s)")
                    self._safe_after(0, lambda: self._timeout_download('Download timeout (60 min limit exceeded)'))
                    break

            # Check progress timeout (stalled download)
            if self.last_progress_time:
                time_since_progress = current_time - self.last_progress_time
                if time_since_progress > DOWNLOAD_PROGRESS_TIMEOUT:
                    logger.error(f"Download stalled (no progress for {DOWNLOAD_PROGRESS_TIMEOUT}s)")
                    self._safe_after(0, lambda: self._timeout_download('Download stalled (no progress for 10 minutes)'))
                    break

    def _timeout_download(self, reason):
        """Handle download timeout"""
        with self.download_lock:
            downloading = self.is_downloading
        if downloading:
            logger.warning(f"Timing out download: {reason}")
            self.update_status(reason, "red")
            self.stop_download()

    def _get_speed_limit_args(self, speed_limit_var=None):
        """Get yt-dlp speed limit arguments if speed limit is set

        Args:
            speed_limit_var: Optional StringVar to use. Defaults to self.speed_limit_var
        """
        if speed_limit_var is None:
            speed_limit_var = self.speed_limit_var
        speed_limit_str = speed_limit_var.get().strip()
        if speed_limit_str:
            try:
                speed_limit = float(speed_limit_str)
                if speed_limit > 0:
                    # yt-dlp expects rate in bytes/second, user enters MB/s
                    rate_bytes = int(speed_limit * BYTES_PER_MB)
                    return ['--limit-rate', f'{rate_bytes}']
            except ValueError:
                # Invalid input, ignore
                pass
        return []

    def stop_download(self):
        """Stop download gracefully, with forced termination as fallback"""
        with self.download_lock:
            process_to_cleanup = self.current_process
            is_active = self.is_downloading

        if process_to_cleanup and is_active:
            self.safe_process_cleanup(process_to_cleanup)

            with self.download_lock:
                self.is_downloading = False
            self.update_status('Download stopped', "orange")
            self.download_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            self.progress['value'] = 0
            self.progress_label.config(text="0%")

    def _size_constrained_encode(self, input_file, output_file, target_bitrate, duration,
                                  volume_multiplier=1.0, scale_height=None,
                                  start_time=None, end_time=None):
        """Encode a video to hit a target bitrate (for 10MB size constraint).

        Uses single-pass with hardware encoding if available, or two-pass with
        software encoding as fallback. Progress is reported via update_status/update_progress.
        Returns True on success, False on failure or cancellation.
        """
        if self.hw_encoder:
            return self._encode_single_pass(input_file, output_file, target_bitrate, duration,
                                            volume_multiplier, scale_height, start_time, end_time)
        else:
            return self._encode_two_pass(input_file, output_file, target_bitrate, duration,
                                         volume_multiplier, scale_height, start_time, end_time)

    def _run_ffmpeg_with_progress(self, cmd, duration, status_prefix):
        """Run an ffmpeg command, parsing progress output. Returns True on success."""
        logger.info(f"{status_prefix}: {' '.join(cmd)}")
        self.last_progress_time = time.time()
        self.update_progress(0)

        with self.download_lock:
            self.current_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding='utf-8', errors='replace', bufsize=1, **_subprocess_kwargs)

        for line in self.current_process.stdout:
            with self.download_lock:
                if not self.is_downloading:
                    self.safe_process_cleanup(self.current_process)
                    return False
            if 'out_time_ms=' in line:
                try:
                    time_ms = int(line.split('=')[1].strip())
                    current = time_ms / 1_000_000
                    if duration > 0:
                        pct = min(100, (current / duration) * 100)
                        self.update_progress(pct)
                        self.update_status(f'{status_prefix}... {pct:.0f}%', 'blue')
                except (ValueError, IndexError):
                    pass
            self.last_progress_time = time.time()

        self.current_process.wait()
        if self.current_process.returncode != 0:
            stderr = self.current_process.stderr.read() if self.current_process.stderr else ''
            logger.error(f"{status_prefix} failed (rc {self.current_process.returncode}): {stderr}")
            self.safe_process_cleanup(self.current_process)
            return False
        return True

    def _encode_single_pass(self, input_file, output_file, target_bitrate, duration,
                             volume_multiplier=1.0, scale_height=None,
                             start_time=None, end_time=None):
        """Single-pass encode using hardware encoder with bitrate target."""
        input_args = [self.ffmpeg_path, '-y', '-i', input_file]
        if start_time is not None and end_time is not None:
            input_args.extend(['-ss', str(start_time), '-to', str(end_time)])

        vf_args = ['-vf', f'scale=-2:{scale_height}'] if scale_height else []
        enc_args = self._get_video_encoder_args(mode='bitrate', target_bitrate=target_bitrate)
        audio_args = ['-c:a', 'aac', '-b:a', AUDIO_BITRATE]
        if volume_multiplier != 1.0:
            audio_args.extend(['-af', f'volume={volume_multiplier}'])

        cmd = input_args + vf_args + enc_args + audio_args + ['-progress', 'pipe:1', output_file]

        self.update_status('Encoding (GPU)...', 'blue')
        try:
            return self._run_ffmpeg_with_progress(cmd, duration, 'Encoding (GPU)')
        finally:
            if self.current_process:
                for pipe in (self.current_process.stdout, self.current_process.stderr):
                    if pipe:
                        try:
                            pipe.close()
                        except OSError:
                            pass

    def _encode_two_pass(self, input_file, output_file, target_bitrate, duration,
                          volume_multiplier=1.0, scale_height=None,
                          start_time=None, end_time=None):
        """Two-pass encode using software (libx264) with bitrate target."""
        passlogfile = os.path.join(tempfile.gettempdir(), f'ytdl_2pass_{os.getpid()}_{int(time.time())}')

        input_args = [self.ffmpeg_path, '-y', '-i', input_file]
        if start_time is not None and end_time is not None:
            input_args.extend(['-ss', str(start_time), '-to', str(end_time)])

        vf_args = ['-vf', f'scale=-2:{scale_height}'] if scale_height else []
        enc_args = self._get_video_encoder_args(mode='bitrate', target_bitrate=target_bitrate)

        try:
            # --- Pass 1 ---
            self.update_status('Encoding pass 1/2 (analysing)...', 'blue')
            pass1_cmd = input_args + vf_args + enc_args + [
                '-pass', '1', '-passlogfile', passlogfile,
                '-an', '-f', 'null', os.devnull, '-progress', 'pipe:1',
            ]
            if not self._run_ffmpeg_with_progress(pass1_cmd, duration, 'Two-pass pass 1'):
                return False

            # Close pass 1 pipes
            if self.current_process.stdout:
                self.current_process.stdout.close()
            if self.current_process.stderr:
                self.current_process.stderr.close()

            # --- Pass 2 ---
            self.update_status('Encoding pass 2/2...', 'blue')
            pass2_cmd = input_args + vf_args + enc_args + [
                '-pass', '2', '-passlogfile', passlogfile,
                '-c:a', 'aac', '-b:a', AUDIO_BITRATE,
            ]
            if volume_multiplier != 1.0:
                pass2_cmd.extend(['-af', f'volume={volume_multiplier}'])
            pass2_cmd.extend(['-progress', 'pipe:1', output_file])

            return self._run_ffmpeg_with_progress(pass2_cmd, duration, 'Two-pass pass 2')

        finally:
            if self.current_process:
                for pipe in (self.current_process.stdout, self.current_process.stderr):
                    if pipe:
                        try:
                            pipe.close()
                        except OSError:
                            pass
            for suffix in ['', '-0.log', '-0.log.mbtree']:
                p = passlogfile + suffix
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

    def _calculate_optimal_quality(self, duration_seconds):
        """Calculate optimal resolution and video bitrate to keep output below 10MB.

        Picks the highest resolution (down to 360p) where the available bitrate
        still meets that resolution's minimum quality threshold.

        Returns (height: int, video_bitrate_bps: int).
        """
        if duration_seconds <= 0:
            return (360, 100000)
        available_bitrate = int((TARGET_MAX_SIZE_BYTES * 8) / duration_seconds - TARGET_AUDIO_BITRATE_BPS)
        available_bitrate = max(available_bitrate, 100000)

        for height in SIZE_CONSTRAINED_RESOLUTIONS:
            if available_bitrate >= SIZE_CONSTRAINED_MIN_BITRATES[height]:
                return (height, available_bitrate)

        # 360p floor — use whatever bitrate we have
        return (360, available_bitrate)

    def download(self, url):
        keep_below_10mb = False
        temp_dir = None
        try:
            # Route to local file handler if needed
            if self.is_local_file(url):
                return self.download_local_file(url)

            # Trimmer mode always downloads single videos, even from playlist URLs
            # (playlist downloads are only supported in clipboard mode)
            is_playlist_url = self.is_playlist_url(url)

            quality = self.quality_var.get()
            trim_enabled = self.trim_enabled_var.get()
            audio_only = quality.startswith("none") or quality == "none (Audio only)"

            self.update_status('Starting download...', "blue")

            # Check if trimming is enabled and validate
            if trim_enabled:
                if self.video_duration <= 0:
                    self.update_status('Please fetch video duration first', "red")
                    self._reset_buttons()
                    with self.download_lock:
                        self.is_downloading = False
                    return

                start_time = int(float(self.start_time_var.get()))
                end_time = int(float(self.end_time_var.get()))

                if start_time >= end_time:
                    self.update_status('Invalid time range', "red")
                    self._reset_buttons()
                    with self.download_lock:
                        self.is_downloading = False
                    return

            if audio_only:
                # Check for custom filename
                custom_name = self.sanitize_filename(self.filename_entry.get().strip())
                if custom_name:
                    # Use custom filename
                    base_name = custom_name
                else:
                    # Use video title from yt-dlp
                    base_name = '%(title)s'

                # Generate filename with trim times if trimming is enabled
                if trim_enabled:
                    start_hms = self.seconds_to_hms(start_time).replace(':', '-')
                    end_hms = self.seconds_to_hms(end_time).replace(':', '-')
                    output_template = f'{base_name}_[{start_hms}_to_{end_hms}].%(ext)s'
                else:
                    output_template = f'{base_name}.%(ext)s'

                cmd = [
                    self.ytdlp_path,
                    '--concurrent-fragments', CONCURRENT_FRAGMENTS,  # Download fragments in parallel
                    '--buffer-size', BUFFER_SIZE,  # Better buffering
                    '--http-chunk-size', CHUNK_SIZE,  # Larger chunks = fewer requests
                    '-f', 'bestaudio',
                    '--extract-audio',
                    '--audio-format', 'mp3',
                    '--audio-quality', AUDIO_BITRATE,
                    '--newline',
                    '--progress',
                    '-o', os.path.join(self.download_path, output_template),
                ]

                # Build ffmpeg postprocessor args for audio
                ffmpeg_args = []

                if trim_enabled:
                    ffmpeg_args.extend(['-ss', str(start_time), '-to', str(end_time)])

                # Add volume filter (validated)
                volume_multiplier = self.validate_volume(self.volume_var.get())
                if volume_multiplier != 1.0:
                    ffmpeg_args.extend(['-af', f'volume={volume_multiplier}'])

                # Add to command if there are any ffmpeg args
                if ffmpeg_args:
                    cmd.extend(['--postprocessor-args', 'ffmpeg:' + ' '.join(ffmpeg_args)])

                # Add speed limit if set
                cmd.extend(self._get_speed_limit_args())

                # Always use --no-playlist in trimmer mode
                if is_playlist_url:
                    cmd.append('--no-playlist')

                cmd.append(url)
            else:
                if quality.startswith("none") or quality == "none (Audio only)":
                    self.update_status('Please select a video quality', "red")
                    self._reset_buttons()
                    with self.download_lock:
                        self.is_downloading = False
                    return

                keep_below_10mb = self.keep_below_10mb_var.get()

                if keep_below_10mb:
                    # Auto-calculate optimal resolution and bitrate
                    clip_duration = (end_time - start_time) if trim_enabled else self.video_duration
                    height, target_bitrate = self._calculate_optimal_quality(clip_duration)
                    height = str(height)
                    logger.info(f"10MB encode: auto-selected {height}p at {target_bitrate}bps for {clip_duration}s clip")
                else:
                    height = quality

                volume_multiplier = self.validate_volume(self.volume_var.get())

                # Check for custom filename
                custom_name = self.sanitize_filename(self.filename_entry.get().strip())
                if custom_name:
                    base_name = custom_name
                else:
                    base_name = '%(title)s'

                # Generate filename with trim times if trimming is enabled
                if trim_enabled:
                    start_hms_file = self.seconds_to_hms(start_time).replace(':', '-')
                    end_hms_file = self.seconds_to_hms(end_time).replace(':', '-')
                    output_template = f'{base_name}_{height}p_[{start_hms_file}_to_{end_hms_file}].%(ext)s'
                else:
                    output_template = f'{base_name}_{height}p.%(ext)s'

                if keep_below_10mb:
                    # --- Size-constrained path: download, then encode to target bitrate ---
                    temp_dir = tempfile.mkdtemp(prefix='ytdl_10mb_')
                    temp_output_template = os.path.join(temp_dir, '%(title)s.%(ext)s')

                    # Download a stream close to our target bitrate — no point fetching
                    # a high-bitrate stream we're going to re-encode to a lower bitrate
                    dl_bitrate_cap = max(target_bitrate * 2, 1000000)
                    dl_bitrate_cap_k = int(dl_bitrate_cap / 1000)
                    format_sel = (f'bestvideo[height<={height}][vbr<={dl_bitrate_cap_k}]'
                                  f'+bestaudio/bestvideo[height<={height}]+bestaudio/best[height<={height}]')

                    cmd = [
                        self.ytdlp_path,
                        '--concurrent-fragments', CONCURRENT_FRAGMENTS,
                        '--buffer-size', BUFFER_SIZE,
                        '--http-chunk-size', CHUNK_SIZE,
                        '-f', format_sel,
                        '--merge-output-format', 'mp4',
                    ]

                    if trim_enabled:
                        start_hms = self.seconds_to_hms(start_time)
                        end_hms = self.seconds_to_hms(end_time)
                        cmd.extend([
                            '--download-sections', f'*{start_hms}-{end_hms}',
                            '--force-keyframes-at-cuts',
                        ])

                    cmd.extend(self._get_speed_limit_args())
                    if is_playlist_url:
                        cmd.append('--no-playlist')
                    cmd.extend(['--newline', '--progress', '-o', temp_output_template, url])
                else:
                    # --- Normal single-pass path ---
                    temp_dir = None

                    cmd = [
                        self.ytdlp_path,
                        '--concurrent-fragments', CONCURRENT_FRAGMENTS,
                        '--buffer-size', BUFFER_SIZE,
                        '--http-chunk-size', CHUNK_SIZE,
                        '-f', f'bestvideo[height<={height}]+bestaudio/best[height<={height}]',
                        '--merge-output-format', 'mp4',
                    ]

                    if trim_enabled:
                        start_hms = self.seconds_to_hms(start_time)
                        end_hms = self.seconds_to_hms(end_time)
                        cmd.extend([
                            '--download-sections', f'*{start_hms}-{end_hms}',
                            '--force-keyframes-at-cuts',
                        ])

                    # Build ffmpeg postprocessor args for video (only if needed)
                    needs_processing = trim_enabled or volume_multiplier != 1.0

                    if needs_processing:
                        ffmpeg_video_args = self._get_video_encoder_args(mode='crf') + ['-c:a', 'aac', '-b:a', AUDIO_BITRATE]
                        if volume_multiplier != 1.0:
                            ffmpeg_video_args.extend(['-af', f'volume={volume_multiplier}'])
                        cmd.extend(['--postprocessor-args', 'ffmpeg:' + ' '.join(ffmpeg_video_args)])

                    cmd.extend(self._get_speed_limit_args())
                    if is_playlist_url:
                        cmd.append('--no-playlist')
                    cmd.extend([
                        '--newline', '--progress',
                        '-o', os.path.join(self.download_path, output_template),
                        url
                    ])

            logger.info(f"Download command: {' '.join(cmd)}")

            with self.download_lock:
                self.current_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    encoding='utf-8',
                    errors='replace',
                    bufsize=1,
                    **_subprocess_kwargs
                )

            # Parse output for progress
            error_lines = []  # Capture error output for debugging
            try:
                for line in self.current_process.stdout:
                    if not self.is_downloading:
                        break

                    # Capture ERROR lines for debugging (capped to prevent memory growth)
                    if 'ERROR' in line or 'error' in line.lower():
                        if len(error_lines) < 100:
                            error_lines.append(line.strip())
                        logger.warning(f"yt-dlp: {line.strip()}")

                    # Look for download progress - multiple patterns for reliability
                    if '[download]' in line or 'Downloading' in line:
                        # Parse progress percentage
                        progress_match = PROGRESS_REGEX.search(line)
                        if progress_match:
                            progress = float(progress_match.group(1))
                            self.update_progress(progress)

                            # Try to extract speed and ETA from the line
                            speed_match = SPEED_REGEX.search(line)
                            eta_match = ETA_REGEX.search(line)

                            if speed_match and eta_match:
                                status_msg = f'Downloading... {progress:.1f}% at {speed_match.group(1)} | ETA: {eta_match.group(1)}'
                            elif speed_match:
                                status_msg = f'Downloading... {progress:.1f}% at {speed_match.group(1)}'
                            else:
                                status_msg = f'Downloading... {progress:.1f}%'

                            self.update_status(status_msg, "blue")
                            self.last_progress_time = time.time()  # Update progress timestamp
                        elif 'Destination' in line:
                            # yt-dlp is starting download
                            self.update_status('Starting download...', "blue")
                            self.last_progress_time = time.time()

                    # Look for different download phases
                    elif '[info]' in line and 'Downloading' in line:
                        self.update_status('Preparing download...', "blue")
                        self.last_progress_time = time.time()
                    elif '[ExtractAudio]' in line:
                        self.update_status('Extracting audio...', "blue")
                        self.last_progress_time = time.time()
                    elif '[Merger]' in line or 'Merging' in line:
                        self.update_status('Merging video and audio...', "blue")
                        self.last_progress_time = time.time()
                    elif '[ffmpeg]' in line:
                        self.update_status('Processing with ffmpeg...', "blue")
                        self.last_progress_time = time.time()
                    elif 'Post-processing' in line or 'Postprocessing' in line:
                        self.update_status('Post-processing...', "blue")
                        self.last_progress_time = time.time()
                    elif 'has already been downloaded' in line:
                        self.update_status('File already exists, skipping...', "orange")
                        self.last_progress_time = time.time()
            except (BrokenPipeError, IOError) as e:
                if self.is_downloading:
                    logger.warning(f"Pipe error while reading process output: {e}")
                    # Process may have terminated, continue to wait()

            self.current_process.wait()

            if self.current_process.returncode == 0 and self.is_downloading:
                # yt-dlp download succeeded — check if two-pass encoding is needed
                if not audio_only and keep_below_10mb and temp_dir:
                    # Find the downloaded file in temp dir
                    temp_files = glob.glob(os.path.join(temp_dir, '*.mp4'))
                    if not temp_files:
                        self.update_status('Download failed', "red")
                        logger.error("Two-pass: no temp file found after yt-dlp download")
                    else:
                        temp_file = temp_files[0]
                        # Build final output filename
                        video_title = os.path.splitext(os.path.basename(temp_file))[0]
                        if custom_name:
                            final_base = custom_name
                        else:
                            final_base = self.sanitize_filename(video_title) or video_title

                        if trim_enabled:
                            final_name = f'{final_base}_{height}p_[{start_hms_file}_to_{end_hms_file}].mp4'
                        else:
                            final_name = f'{final_base}_{height}p.mp4'

                        final_output = os.path.join(self.download_path, final_name)
                        clip_duration = (end_time - start_time) if trim_enabled else self.video_duration

                        success = self._size_constrained_encode(
                            temp_file, final_output, target_bitrate, clip_duration,
                            volume_multiplier=volume_multiplier, scale_height=height)

                        if success and self.is_downloading:
                            self.update_progress(100)
                            self.update_status('Download complete!', "green")
                            logger.info(f"Two-pass download completed: {final_output}")
                            self._enable_upload_button(final_output)
                        elif self.is_downloading:
                            self.update_status('Download failed', "red")
                            logger.error("Two-pass encoding failed")

                    # Clean up temp dir
                    shutil.rmtree(temp_dir, ignore_errors=True)
                else:
                    # Normal completion
                    self.update_progress(100)
                    self.update_status('Download complete!', "green")
                    logger.info(f"Download completed successfully: {url}")
                    latest_file = self._find_latest_file()
                    self._enable_upload_button(latest_file)

            elif self.is_downloading:
                self.update_status('Download failed', "red")
                logger.error(f"Download failed with return code {self.current_process.returncode}")
                if error_lines:
                    logger.error(f"yt-dlp errors: {'; '.join(error_lines)}")
                # Clean up temp dir on failure
                if not audio_only and keep_below_10mb and temp_dir:
                    shutil.rmtree(temp_dir, ignore_errors=True)

        except FileNotFoundError as e:
            if self.is_downloading:
                error_msg = 'yt-dlp or ffmpeg is not installed.\n\nInstall with:\npip install yt-dlp\n\nand install ffmpeg from your package manager'
                self.update_status(error_msg, "red")
                logger.error(f"Dependency not found: {e}")
        except PermissionError as e:
            if self.is_downloading:
                error_msg = 'Permission denied. Check write permissions for download folder.'
                self.update_status(error_msg, "red")
                logger.error(f"Permission error: {e}")
        except OSError as e:
            if self.is_downloading:
                error_msg = f'OS error: {e}'
                self.update_status(error_msg, "red")
                logger.error(f"OS error during download: {e}")
        except Exception as e:
            if self.is_downloading:
                self.update_status(f'Error: {e}', "red")
                logger.exception(f"Unexpected error during download: {e}")

        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
            with self.download_lock:
                self.is_downloading = False
                proc = self.current_process
                self.current_process = None
            if proc:
                if proc.stdout:
                    proc.stdout.close()
                if proc.stderr:
                    proc.stderr.close()
            self._reset_buttons()

    def download_local_file(self, filepath):
        """Process local video file with trimming, quality adjustment, and volume control"""
        try:
            quality = self.quality_var.get()
            trim_enabled = self.trim_enabled_var.get()
            audio_only = quality.startswith("none") or quality == "none (Audio only)"

            # Initialize trim variables so they exist even when trim is disabled
            start_time = None
            end_time = None

            self.update_status('Processing local file...', "blue")

            # Validate trimming
            if trim_enabled:
                if self.video_duration <= 0:
                    self.update_status('Please fetch video duration first', "red")
                    self._reset_buttons()
                    with self.download_lock:
                        self.is_downloading = False
                    return

                start_time = int(float(self.start_time_var.get()))
                end_time = int(float(self.end_time_var.get()))

                if start_time >= end_time:
                    self.update_status('Invalid time range', "red")
                    self._reset_buttons()
                    with self.download_lock:
                        self.is_downloading = False
                    return

            # Generate output filename
            custom_name = self.sanitize_filename(self.filename_entry.get().strip())
            if custom_name:
                # Use custom filename
                base_name = custom_name
            else:
                # Use original file stem
                input_path = Path(filepath)
                base_name = input_path.stem

            if trim_enabled:
                start_hms = self.seconds_to_hms(start_time).replace(':', '-')
                end_hms = self.seconds_to_hms(end_time).replace(':', '-')
                output_name = f"{base_name}_[{start_hms}_to_{end_hms}]"
            else:
                # Only add "_processed" if using original filename, not custom
                if custom_name:
                    output_name = base_name
                else:
                    output_name = f"{base_name}_processed"

            volume_multiplier = self.validate_volume(self.volume_var.get())

            if audio_only:
                # Extract audio only
                output_file = os.path.join(self.download_path, f"{output_name}.mp3")
                cmd = [self.ffmpeg_path, '-i', filepath]

                if trim_enabled:
                    cmd.extend(['-ss', str(start_time), '-to', str(end_time)])

                cmd.extend(['-vn', '-c:a', 'libmp3lame', '-b:a', AUDIO_BITRATE])

                if volume_multiplier != 1.0:
                    cmd.extend(['-af', f'volume={volume_multiplier}'])

                cmd.extend(['-progress', 'pipe:1', '-y', output_file])
            else:
                # Video processing
                if quality.startswith("none") or quality == "none (Audio only)":
                    self.update_status('Please select a video quality', "red")
                    self._reset_buttons()
                    with self.download_lock:
                        self.is_downloading = False
                    return

                keep_below_10mb = self.keep_below_10mb_var.get()

                if keep_below_10mb:
                    clip_duration = (end_time - start_time) if trim_enabled else self.video_duration
                    if clip_duration <= 0:
                        self._safe_after(0, lambda: self.update_status('Please fetch video duration first', "red"))
                        self._safe_after(0, self._reset_buttons)
                        with self.download_lock:
                            self.is_downloading = False
                        return
                    height, target_bitrate = self._calculate_optimal_quality(clip_duration)
                    height = str(height)
                    logger.info(f"10MB encode (local): auto-selected {height}p at {target_bitrate}bps for {clip_duration}s clip")
                else:
                    height = quality

                output_file = os.path.join(self.download_path, f"{output_name}_{height}p.mp4")

                if keep_below_10mb:
                    # Two-pass encode for optimal 10MB quality
                    clip_duration = (end_time - start_time) if trim_enabled else self.video_duration
                    success = self._size_constrained_encode(
                        filepath, output_file, target_bitrate, clip_duration,
                        volume_multiplier=volume_multiplier,
                        scale_height=height,
                        start_time=start_time if trim_enabled else None,
                        end_time=end_time if trim_enabled else None)

                    if success and self.is_downloading:
                        self.update_progress(100)
                        self.update_status('Processing complete!', "green")
                        logger.info(f"Two-pass local file processing complete: {output_file}")
                        self._enable_upload_button(output_file)
                    elif self.is_downloading:
                        self.update_status('Processing failed', "red")
                    return
                else:
                    cmd = [self.ffmpeg_path, '-i', filepath]

                    if trim_enabled:
                        cmd.extend(['-ss', str(start_time), '-to', str(end_time)])

                    cmd.extend(['-vf', f'scale=-2:{height}'] + self._get_video_encoder_args(mode='crf') + ['-c:a', 'aac', '-b:a', AUDIO_BITRATE])

                    if volume_multiplier != 1.0:
                        cmd.extend(['-af', f'volume={volume_multiplier}'])

                    cmd.extend(['-progress', 'pipe:1', '-y', output_file])

            logger.info(f"Processing local file: {' '.join(cmd)}")

            # Execute ffmpeg
            with self.download_lock:
                self.current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                                         encoding='utf-8', errors='replace', bufsize=1, **_subprocess_kwargs)

            # Parse ffmpeg progress
            total_duration = self.video_duration if not trim_enabled else (end_time - start_time)

            for line in self.current_process.stdout:
                if not self.is_downloading:
                    break

                if 'out_time_ms=' in line:
                    try:
                        time_ms = int(line.split('=')[1].strip())
                        current_time = time_ms / 1000000

                        if total_duration > 0:
                            progress = min(100, (current_time / total_duration) * 100)
                            self.update_progress(progress)
                            self.update_status(f'Processing... {progress:.1f}%', "blue")
                            self.last_progress_time = time.time()
                    except (ValueError, IndexError):
                        pass

            self.current_process.wait()

            if self.current_process.returncode == 0 and self.is_downloading:
                self.update_progress(100)
                self.update_status('Processing complete!', "green")
                logger.info(f"Local file processed: {output_file}")

                # Enable upload button
                self._enable_upload_button(output_file)

            elif self.is_downloading:
                stderr = self.current_process.stderr.read() if self.current_process.stderr else ""
                self.update_status('Processing failed', "red")
                logger.error(f"ffmpeg failed: {stderr}")

        except FileNotFoundError as e:
            if self.is_downloading:
                self.update_status('ffmpeg not found. Please ensure it is installed.', "red")
                logger.error(f"ffmpeg not found: {e}")
        except Exception as e:
            if self.is_downloading:
                self.update_status(f'Error: {e}', "red")
                logger.exception(f"Error processing local file: {e}")
        finally:
            with self.download_lock:
                self.is_downloading = False
                proc = self.current_process
                self.current_process = None
            if proc:
                if proc.stdout:
                    proc.stdout.close()
                if proc.stderr:
                    proc.stderr.close()
            self._reset_buttons()

    def _safe_after(self, delay, callback):
        """Schedule callback on main thread, but only if not shutting down."""
        if not self._shutting_down:
            try:
                self.root.after(delay, callback)
            except (RuntimeError, tk.TclError):
                pass

    def update_progress(self, value):
        """Update main progress bar with validation (thread-safe)"""
        try:
            value = float(value)
            value = max(0, min(100, value))  # Clamp to 0-100
            self._safe_after(0, lambda v=value: self._do_update_progress(v))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid progress value: {value} - {e}")

    def _do_update_progress(self, value):
        """Actual progress update on main thread"""
        self.progress['value'] = value
        self.progress_label.config(text=f"{value:.1f}%")

    def update_status(self, message, color):
        """Update status label (thread-safe)"""
        self._safe_after(0, lambda m=message, c=color: self.status_label.config(text=m, foreground=c))

    def _reset_buttons(self):
        """Reset download/stop buttons to idle state (thread-safe)"""
        self._safe_after(0, lambda: (
            self.download_btn.config(state='normal'),
            self.stop_btn.config(state='disabled')
        ))

    def cleanup_temp_files(self):
        """Clean up temporary preview files"""
        try:
            # Clear cache references
            self._clear_preview_cache()
            # Remove temp directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temp directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {e}")

    def on_closing(self):
        """Handle window close event with proper resource cleanup"""
        logger.info("Application shutdown initiated...")

        # Cancel preview timer before setting shutdown flag
        if hasattr(self, 'preview_update_timer') and self.preview_update_timer:
            self.root.after_cancel(self.preview_update_timer)
            self.preview_update_timer = None

        self._shutting_down = True

        # Save clipboard URLs before shutdown
        try:
            self._save_clipboard_urls()
        except Exception as e:
            logger.error(f"Error saving clipboard URLs: {e}")

        # Stop clipboard monitoring
        self.stop_clipboard_monitoring()

        # Stop clipboard downloads
        with self.clipboard_lock:
            if self.clipboard_downloading:
                self.clipboard_downloading = False

        # Stop any ongoing downloads gracefully
        with self.download_lock:
            process_to_cleanup = self.current_process
            is_active = self.is_downloading

        if is_active and process_to_cleanup:
            logger.info("Terminating active download process...")
            self.safe_process_cleanup(process_to_cleanup)

        # Clean up temp files
        try:
            self.cleanup_temp_files()
        except Exception as e:
            logger.error(f"Error cleaning temp files: {e}")

        # Shutdown thread pool — cancel pending tasks, don't wait forever
        logger.info("Shutting down thread pool...")
        with self.download_lock:
            self.is_downloading = False
        try:
            self.thread_pool.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            # Python 3.6-3.8 compatibility: cancel_futures not supported
            self.thread_pool.shutdown(wait=False)
        except Exception as e:
            logger.error(f"Error shutting down thread pool: {e}")

        logger.info("Application shutdown complete")

        # Close the window
        self.root.destroy()

def main():
    root = tk.Tk()
    app = YouTubeDownloader(root)

    # Setup signal handlers for graceful shutdown (SIGINT, SIGTERM)
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        # Schedule cleanup on the main thread
        root.after(0, app.on_closing)

    signal.signal(signal.SIGINT, signal_handler)
    if sys.platform != 'win32':
        signal.signal(signal.SIGTERM, signal_handler)

    root.mainloop()

if __name__ == "__main__":
    main()
