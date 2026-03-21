#!/usr/bin/env python3
"""YoutubeDownloader — PyQt6 rewrite (Part 1: GUI construction)"""

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
from PIL import Image, ImageDraw, ImageFont
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import shutil
import signal
import glob
from collections import OrderedDict
from catboxpy.catbox import CatboxClient

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor, QDesktopServices, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSizePolicy, QSlider, QTabWidget, QVBoxLayout, QWidget,
)

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

# Additional imports needed by ported business logic
import hashlib
import io
import tarfile
import urllib.request
import urllib.error
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import (
    QDialog, QTextEdit,
)


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


# ---------------------------------------------------------------------------
#  QSS Stylesheets — dark and light, adapted from THEMES colors
# ---------------------------------------------------------------------------

_DARK_STYLE_BASE = """
QWidget { background-color: #1e1e1e; color: #dcdcdc; }
QGroupBox { border: 1px solid #444; border-radius: 4px; margin-top: 8px; padding-top: 14px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #dcdcdc; }
QTabWidget::pane { border: 1px solid #444; }
QTabBar::tab { background: #2d2d2d; color: #dcdcdc; padding: 6px 14px; border: 1px solid #444;
               border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; }
QTabBar::tab:selected { background: #1e1e1e; }
QTabBar::tab:!selected { margin-top: 2px; }
QTabBar::tab:disabled { background: transparent; border: none; min-width: 40px; max-width: 40px; }
QComboBox, QLineEdit { background: #2d2d2d; color: #dcdcdc;
               border: 1px solid #555; border-radius: 3px; padding: 2px; }
QComboBox QAbstractItemView { background: #2d2d2d; color: #dcdcdc; selection-background-color: #264f78; }
QScrollArea { border: none; }
QPushButton { background: #333; color: #dcdcdc; border: 1px solid #555; border-radius: 3px; padding: 5px 12px; }
QPushButton:hover { background: #444; }
QPushButton:disabled { background: #2a2a2a; color: #666; border-color: #444; }
QCheckBox { color: #dcdcdc; spacing: 6px; }
QLabel { color: #dcdcdc; }
QProgressBar { background: #252525; border: 1px solid #444; border-radius: 3px; text-align: center; color: #dcdcdc; }
QProgressBar::chunk { background: #1565c0; border-radius: 2px; }
QSlider::groove:horizontal { background: #252525; height: 6px; border-radius: 3px; }
QSlider::handle:horizontal { background: #dcdcdc; width: 14px; height: 14px; margin: -4px 0; border-radius: 7px; }
QSlider::sub-page:horizontal { background: #1565c0; border-radius: 3px; }
QMessageBox { background-color: #1e1e1e; }
QStatusBar { background: #2d2d2d; color: #aaa; }
QToolTip { background: #2d2d2d; color: #dcdcdc; border: 1px solid #555; }
"""

_LIGHT_STYLE = """
QWidget { background-color: #f0f0f0; color: #1e1e1e; }
QGroupBox { border: 1px solid #bbb; border-radius: 4px; margin-top: 8px; padding-top: 14px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #1e1e1e; }
QTabWidget::pane { border: 1px solid #bbb; }
QTabBar::tab { background: #e0e0e0; color: #1e1e1e; padding: 6px 14px; border: 1px solid #bbb;
               border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; }
QTabBar::tab:selected { background: #f0f0f0; }
QTabBar::tab:!selected { margin-top: 2px; }
QTabBar::tab:disabled { background: transparent; border: none; min-width: 40px; max-width: 40px; }
QComboBox, QLineEdit { background: #ffffff; color: #1e1e1e;
               border: 1px solid #bbb; border-radius: 3px; padding: 2px; }
QComboBox QAbstractItemView { background: #ffffff; color: #1e1e1e; selection-background-color: #1565c0; }
QScrollArea { border: none; }
QPushButton { background: #e0e0e0; color: #1e1e1e; border: 1px solid #bbb; border-radius: 3px; padding: 5px 12px; }
QPushButton:hover { background: #d0d0d0; }
QPushButton:disabled { background: #e8e8e8; color: #999; border-color: #bbb; }
QCheckBox { color: #1e1e1e; }
QCheckBox::indicator { width: 14px; height: 14px; border: 2px solid #888; border-radius: 3px; background: #ffffff; }
QCheckBox::indicator:checked { background: #2e7d32; border-color: #2e7d32; }
QCheckBox::indicator:unchecked:hover { border-color: #555; }
QCheckBox::indicator:disabled { background: #e0e0e0; border-color: #bbb; }
QLabel { color: #1e1e1e; }
QProgressBar { background: #ffffff; border: 1px solid #bbb; border-radius: 3px; text-align: center; color: #1e1e1e; }
QProgressBar::chunk { background: #1565c0; border-radius: 2px; }
QSlider::groove:horizontal { background: #ffffff; height: 6px; border-radius: 3px; }
QSlider::handle:horizontal { background: #1e1e1e; width: 14px; height: 14px; margin: -4px 0; border-radius: 7px; }
QSlider::sub-page:horizontal { background: #1565c0; border-radius: 3px; }
QMessageBox { background-color: #f0f0f0; }
QStatusBar { background: #e0e0e0; color: #555; }
QToolTip { background: #ffffcc; color: #1e1e1e; border: 1px solid #bbb; }
"""


# ---------------------------------------------------------------------------
#  Dark checkbox images (generated at runtime for dark mode, like SwornTweaks)
# ---------------------------------------------------------------------------
_checkbox_temp_dir = None

def _make_checkbox_images():
    """Generate unchecked/checked checkbox PNGs for dark mode QSS."""
    global _checkbox_temp_dir
    if _checkbox_temp_dir and os.path.isdir(_checkbox_temp_dir):
        return _checkbox_temp_dir
    _checkbox_temp_dir = tempfile.mkdtemp(prefix="ytdl_cb_")

    # Unchecked
    unc = QPixmap(18, 18)
    unc.fill(QColor(0, 0, 0, 0))
    p = QPainter(unc)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(136, 136, 136), 2))
    p.setBrush(QColor(45, 45, 45))
    p.drawRoundedRect(1, 1, 16, 16, 3, 3)
    p.end()
    unc.save(os.path.join(_checkbox_temp_dir, "cb_unc.png"))

    # Checked
    chk = QPixmap(18, 18)
    chk.fill(QColor(0, 0, 0, 0))
    p = QPainter(chk)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(46, 125, 50))
    p.drawRoundedRect(1, 1, 16, 16, 3, 3)
    pen = QPen(QColor(255, 255, 255), 2.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    path = QPainterPath()
    path.moveTo(4, 9)
    path.lineTo(7.5, 13)
    path.lineTo(14, 5)
    p.drawPath(path)
    p.end()
    chk.save(os.path.join(_checkbox_temp_dir, "cb_chk.png"))

    return _checkbox_temp_dir


def _build_dark_style():
    """Build dark QSS with generated checkbox images."""
    cb_dir = _make_checkbox_images()
    unc = os.path.join(cb_dir, "cb_unc.png").replace("\\", "/")
    chk = os.path.join(cb_dir, "cb_chk.png").replace("\\", "/")
    return _DARK_STYLE_BASE + f"""
QCheckBox::indicator {{ width: 18px; height: 18px; }}
QCheckBox::indicator:unchecked {{ image: url({unc}); }}
QCheckBox::indicator:checked {{ image: url({chk}); }}
"""


def _set_dark_title_bar(window, dark=True):
    """Set dark/light window title bar on Windows via DWM API."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        hwnd = int(window.winId())
        # Try attribute 20 first (Windows 11 22H2+), fall back to 19 (older builds)
        value = ctypes.c_int(1 if dark else 0)
        hr = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
        if hr != 0:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
    except Exception as e:
        logger.debug(f"Could not set dark title bar: {e}")


# ---------------------------------------------------------------------------
#  Main Window
# ---------------------------------------------------------------------------

class YouTubeDownloader(QMainWindow):
    """Main application window — PyQt6 rewrite."""

    # Signals for thread-safe GUI updates from worker threads
    sig_update_progress = pyqtSignal(float)           # value 0-100
    sig_update_status = pyqtSignal(str, str)          # message, color
    sig_reset_buttons = pyqtSignal()
    sig_show_messagebox = pyqtSignal(str, str, str)   # type, title, message
    sig_clipboard_progress = pyqtSignal(float)        # clipboard tab progress
    sig_clipboard_status = pyqtSignal(str, str)       # clipboard tab status
    sig_clipboard_total = pyqtSignal(str)             # clipboard total label
    sig_upload_status = pyqtSignal(str, str)          # trimmer upload status
    sig_uploader_status = pyqtSignal(str, str)        # uploader tab status
    sig_set_upload_url = pyqtSignal(str)              # show trimmer upload URL
    sig_set_uploader_url = pyqtSignal(str)            # show uploader upload URL
    sig_enable_upload_btn = pyqtSignal(bool)          # enable/disable upload btn
    sig_set_mode_label = pyqtSignal(str)              # trimmer mode indicator
    sig_set_video_info = pyqtSignal(str)              # trimmer video info
    sig_set_filesize_label = pyqtSignal(str)          # trimmer filesize
    sig_update_url_status = pyqtSignal(str, str)      # url, new_status
    sig_add_url_to_list = pyqtSignal(str)             # url to add
    sig_show_update_dialog = pyqtSignal(str, object)  # latest_version, release_data dict
    sig_show_ytdlp_update = pyqtSignal(str, str)      # current_version, latest_version

    # ------------------------------------------------------------------
    #  __init__
    # ------------------------------------------------------------------
    def __init__(self):
        super().__init__()
        logger.info("Initializing YoutubeDownloader (PyQt6)")
        self.setWindowTitle("YoutubeDownloader")

        if sys.platform == 'win32':
            self.resize(580, 720)
            self.setMinimumSize(580, 400)
        else:
            self.resize(900, 1140)
            self.setMinimumSize(750, 600)

        # Window icon
        try:
            icon_path = self._get_resource_path('icon.png')
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            logger.error(f"Error setting window icon: {e}")

        # ---------- state variables ----------
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
        self.preview_thread_running = False
        self.preview_cache = OrderedDict()

        # Volume control — stored as int 0-200 (mapping to 0.0-2.0)
        self._volume_int = 100  # 100 = 1.0 = 100%

        # Local file support
        self.local_file_path = None

        # Upload to Catbox.moe
        self.last_output_file = None
        self.is_uploading = False
        self.catbox_client = CatboxClient()

        # Custom filename
        self.custom_filename = None

        # Playlist support
        self.is_playlist = False
        self.estimated_filesize = None

        # Initialize temp directory with cleanup on exit
        self._init_temp_directory()

        # Clean up leftover files from previous self-updates
        self._cleanup_old_updates()

        # Check dependencies once at startup
        self.dependencies_ok = self.check_dependencies()
        if not self.dependencies_ok:
            logger.warning("Dependencies check failed at startup")

        # Detect hardware encoder
        self.hw_encoder = self._detect_hw_encoder()

        # Thread pool for background tasks
        self.thread_pool = ThreadPoolExecutor(max_workers=MAX_WORKER_THREADS, thread_name_prefix="ytdl_worker")

        # Thread safety locks
        self.preview_lock = threading.Lock()
        self.clipboard_lock = threading.Lock()
        self.auto_download_lock = threading.Lock()
        self.download_lock = threading.Lock()
        self.upload_lock = threading.Lock()
        self.uploader_lock = threading.RLock()
        self.fetch_lock = threading.Lock()
        self.config_lock = threading.Lock()

        # Clipboard Mode variables
        self.clipboard_monitoring = False
        self.clipboard_monitor_thread = None
        self.clipboard_last_content = ""
        self.clipboard_url_list = []
        self.clipboard_download_path = str(Path.home() / "Downloads")
        self.clipboard_downloading = False
        self.clipboard_auto_downloading = False
        self.clipboard_current_download_index = 0
        self.clipboard_url_widgets = {}
        self.klipper_interface = None

        # Theme mode
        self.current_theme = self._load_theme_preference()

        # Uploader tab variables
        self.uploader_file_queue = []
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

        # ---------- connect signals to slots ----------
        self.sig_update_progress.connect(self._do_update_progress)
        self.sig_update_status.connect(self._do_update_status)
        self.sig_reset_buttons.connect(self._do_reset_buttons)
        self.sig_show_messagebox.connect(self._do_show_messagebox)
        self.sig_clipboard_progress.connect(self._do_clipboard_progress)
        self.sig_clipboard_status.connect(self._do_clipboard_status)
        self.sig_clipboard_total.connect(self._do_clipboard_total)
        self.sig_upload_status.connect(self._do_upload_status)
        self.sig_uploader_status.connect(self._do_uploader_status)
        self.sig_set_upload_url.connect(self._do_set_upload_url)
        self.sig_set_uploader_url.connect(self._do_set_uploader_url)
        self.sig_enable_upload_btn.connect(self._do_enable_upload_btn)
        self.sig_set_mode_label.connect(self._do_set_mode_label)
        self.sig_set_video_info.connect(self._do_set_video_info)
        self.sig_set_filesize_label.connect(self._do_set_filesize_label)
        self.sig_update_url_status.connect(self._do_update_url_status)
        self.sig_add_url_to_list.connect(self._do_add_url_to_list)
        self.sig_show_update_dialog.connect(self._show_update_dialog)
        self.sig_show_ytdlp_update.connect(self._show_ytdlp_update_dialog)

        # ---------- build the GUI ----------
        self.setup_ui()

        # Apply initial theme
        self._apply_theme()

        # Restore persisted clipboard URLs
        self._restore_clipboard_urls()

        # Clipboard polling timer (replaces tkinter root.after loop)
        self._clipboard_timer = QTimer(self)
        self._clipboard_timer.setInterval(CLIPBOARD_POLL_INTERVAL_MS)
        self._clipboard_timer.timeout.connect(self._poll_clipboard)

        # Preview debounce timer
        self._preview_debounce_timer = QTimer(self)
        self._preview_debounce_timer.setSingleShot(True)
        self._preview_debounce_timer.setInterval(PREVIEW_DEBOUNCE_MS)

        # Check for updates on startup if enabled
        if self._load_auto_check_updates_setting():
            QTimer.singleShot(2000, lambda: self.thread_pool.submit(self._check_for_updates, True))

    # ------------------------------------------------------------------
    #  Helper — scrollable tab
    # ------------------------------------------------------------------
    @staticmethod
    def _scroll_tab(page: QWidget) -> QScrollArea:
        """Wrap a page widget in a QScrollArea (SwornTweaks pattern)."""
        sa = QScrollArea()
        sa.setWidget(page)
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        return sa

    # ------------------------------------------------------------------
    #  setup_ui
    # ------------------------------------------------------------------
    def setup_ui(self):
        """Build all tabs inside a QTabWidget and set as central widget."""

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        root_layout.addWidget(self._tabs)

        # ---- Clipboard Mode tab ----
        clipboard_page = QWidget()
        clip_layout = QVBoxLayout(clipboard_page)
        self.setup_clipboard_mode_ui(clip_layout)
        clip_layout.addStretch()
        self._tabs.addTab(self._scroll_tab(clipboard_page), "Clipboard Mode")

        # ---- Trimmer tab ----
        trimmer_page = QWidget()
        trim_layout = QVBoxLayout(trimmer_page)
        self._setup_trimmer_ui(trim_layout)
        trim_layout.addStretch()
        self._tabs.addTab(self._scroll_tab(trimmer_page), "Trimmer")

        # ---- Uploader tab ----
        uploader_page = QWidget()
        upl_layout = QVBoxLayout(uploader_page)
        self.setup_uploader_ui(upl_layout)
        upl_layout.addStretch()
        self._tabs.addTab(self._scroll_tab(uploader_page), "Uploader")

        # ---- Invisible spacer tab (visual gap, identical to SwornTweaks) ----
        self._tabs.addTab(QWidget(), "")
        _spacer_idx = self._tabs.count() - 1
        self._tabs.setTabEnabled(_spacer_idx, False)
        self._tabs.setStyleSheet(self._tabs.styleSheet())  # force refresh
        self._tabs.tabBar().setTabButton(
            _spacer_idx, self._tabs.tabBar().ButtonPosition.LeftSide, None)
        self._tabs.tabBar().setTabButton(
            _spacer_idx, self._tabs.tabBar().ButtonPosition.RightSide, None)

        # ---- Settings tab ----
        settings_page = QWidget()
        set_layout = QVBoxLayout(settings_page)
        self._setup_settings_tab(set_layout)
        set_layout.addStretch()
        self._tabs.addTab(self._scroll_tab(settings_page), "Settings")

        # ---- Help tab ----
        help_page = QWidget()
        hlp_layout = QVBoxLayout(help_page)
        self._setup_help_tab(hlp_layout)
        hlp_layout.addStretch()
        self._tabs.addTab(self._scroll_tab(help_page), "Help")

        # Track tab changes for clipboard monitoring
        self._tabs.currentChanged.connect(self._on_tab_changed)

    # ------------------------------------------------------------------
    #  Trimmer tab construction
    # ------------------------------------------------------------------
    def _setup_trimmer_ui(self, layout: QVBoxLayout):
        """Build all widgets for the Trimmer tab."""

        # --- URL / file input ---
        lbl = QLabel("YouTube URL or Local File:")
        lbl.setStyleSheet(lbl.styleSheet() + "font-size: 12px;")
        layout.addWidget(lbl)

        url_row = QHBoxLayout()
        self.url_entry = QLineEdit()
        self.url_entry.setPlaceholderText("Paste YouTube URL or browse a local file")
        self.url_entry.textChanged.connect(self.on_url_change)
        url_row.addWidget(self.url_entry, stretch=1)
        self.browse_file_btn = QPushButton("Browse Local File")
        self.browse_file_btn.clicked.connect(self.browse_local_file)
        url_row.addWidget(self.browse_file_btn)
        layout.addLayout(url_row)

        # Mode indicator
        self.mode_label = QLabel("")
        self.mode_label.setStyleSheet("color: green; font-size: 9pt;")
        layout.addWidget(self.mode_label)

        # --- Quality section ---
        quality_row = QHBoxLayout()
        qlbl = QLabel("Video Quality:")
        qlbl.setStyleSheet(qlbl.styleSheet() + "font-size: 11px; font-weight: bold;")
        quality_row.addWidget(qlbl)

        self.quality_combo = QComboBox()
        self.quality_combo.setEditable(False)
        self.quality_combo.addItems(["1440", "1080", "720", "480", "360", "240", "none (Audio only)"])
        self.quality_combo.setCurrentText("480")
        self.quality_combo.currentIndexChanged.connect(self.on_quality_change)
        quality_row.addWidget(self.quality_combo)

        self.keep_below_10mb_check = QCheckBox("Keep video below 10MB")
        self.keep_below_10mb_check.stateChanged.connect(self._on_keep_below_10mb_toggle)
        quality_row.addWidget(self.keep_below_10mb_check)
        quality_row.addStretch()
        layout.addLayout(quality_row)

        # --- separator ---
        layout.addWidget(self._hsep())

        # --- Trim + Volume header row ---
        tv_row = QHBoxLayout()
        tv_lbl = QLabel("Trim Video:")
        tv_lbl.setStyleSheet(tv_lbl.styleSheet() + "font-size: 11px; font-weight: bold;")
        tv_row.addWidget(tv_lbl)
        tv_row.addSpacing(30)

        vol_lbl = QLabel("Volume:")
        vol_lbl.setStyleSheet(vol_lbl.styleSheet() + "font-size: 11px; font-weight: bold;")
        tv_row.addWidget(vol_lbl)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 200)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(150)
        self.volume_slider.valueChanged.connect(self._on_volume_slider_change)
        tv_row.addWidget(self.volume_slider)

        self.volume_entry = QLineEdit("100")
        self.volume_entry.setFixedWidth(50)
        self.volume_entry.returnPressed.connect(self._on_volume_entry_change)
        tv_row.addWidget(self.volume_entry)

        self.volume_label = QLabel("%")
        self.volume_label.setStyleSheet(self.volume_label.styleSheet() + "font-size: 9px;")
        tv_row.addWidget(self.volume_label)

        self.reset_volume_btn = QPushButton("Reset to 100%")
        self.reset_volume_btn.setFixedWidth(100)
        self.reset_volume_btn.clicked.connect(self.reset_volume)
        tv_row.addWidget(self.reset_volume_btn)
        tv_row.addStretch()
        layout.addLayout(tv_row)

        # --- Trim checkbox + fetch button ---
        trim_ck_row = QHBoxLayout()
        trim_ck_row.setContentsMargins(20, 0, 0, 0)
        self.trim_enabled_check = QCheckBox("Enable video trimming")
        self.trim_enabled_check.stateChanged.connect(self.toggle_trim)
        trim_ck_row.addWidget(self.trim_enabled_check)

        self.fetch_duration_btn = QPushButton("Fetch Video Duration")
        self.fetch_duration_btn.setEnabled(False)
        self.fetch_duration_btn.clicked.connect(self.fetch_duration_clicked)
        trim_ck_row.addWidget(self.fetch_duration_btn)
        trim_ck_row.addStretch()
        layout.addLayout(trim_ck_row)

        # Video info label
        self.video_info_label = QLabel("")
        self.video_info_label.setStyleSheet("color: green;")
        self.video_info_label.setWordWrap(True)
        self.video_info_label.setContentsMargins(20, 0, 0, 0)
        layout.addWidget(self.video_info_label)

        # Filesize estimation label
        self.filesize_label = QLabel("")
        self.filesize_label.setStyleSheet("color: green; font-size: 9pt;")
        self.filesize_label.setContentsMargins(20, 0, 0, 0)
        layout.addWidget(self.filesize_label)

        # --- Preview frames ---
        preview_row = QHBoxLayout()
        preview_row.setContentsMargins(40, 0, 0, 0)

        # Start preview
        start_pv = QVBoxLayout()
        start_pv.addWidget(QLabel("Start Time:"))
        self.start_preview_label = QLabel()
        self.start_preview_label.setFixedSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self.start_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.start_preview_label.setStyleSheet("background: #1a1a1a; color: #d4d4d4;")
        self.start_preview_label.setText("Preview")
        start_pv.addWidget(self.start_preview_label)
        preview_row.addLayout(start_pv)

        preview_row.addSpacing(20)

        # End preview
        end_pv = QVBoxLayout()
        end_pv.addWidget(QLabel("End Time:"))
        self.end_preview_label = QLabel()
        self.end_preview_label.setFixedSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self.end_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.end_preview_label.setStyleSheet("background: #1a1a1a; color: #d4d4d4;")
        self.end_preview_label.setText("Preview")
        end_pv.addWidget(self.end_preview_label)
        preview_row.addLayout(end_pv)

        preview_row.addStretch()
        layout.addLayout(preview_row)

        # --- Start time slider + entry ---
        start_row = QHBoxLayout()
        start_row.setContentsMargins(40, 0, 0, 0)
        self.start_slider = QSlider(Qt.Orientation.Horizontal)
        self.start_slider.setRange(0, MAX_VIDEO_DURATION)
        self.start_slider.setValue(0)
        self.start_slider.setEnabled(False)
        self.start_slider.setMinimumWidth(SLIDER_LENGTH)
        self.start_slider.valueChanged.connect(self.on_start_slider_change)
        start_row.addWidget(self.start_slider)
        start_row.addWidget(QLabel("Start Time:"))
        self.start_time_entry = QLineEdit("00:00:00")
        self.start_time_entry.setFixedWidth(80)
        self.start_time_entry.setEnabled(False)
        self.start_time_entry.returnPressed.connect(self.on_start_entry_change)
        start_row.addWidget(self.start_time_entry)
        start_row.addStretch()
        layout.addLayout(start_row)

        # --- End time slider + entry ---
        end_row = QHBoxLayout()
        end_row.setContentsMargins(40, 0, 0, 0)
        self.end_slider = QSlider(Qt.Orientation.Horizontal)
        self.end_slider.setRange(0, MAX_VIDEO_DURATION)
        self.end_slider.setValue(MAX_VIDEO_DURATION)
        self.end_slider.setEnabled(False)
        self.end_slider.setMinimumWidth(SLIDER_LENGTH)
        self.end_slider.valueChanged.connect(self.on_end_slider_change)
        end_row.addWidget(self.end_slider)
        end_row.addWidget(QLabel("End Time:"))
        self.end_time_entry = QLineEdit("00:00:00")
        self.end_time_entry.setFixedWidth(80)
        self.end_time_entry.setEnabled(False)
        self.end_time_entry.returnPressed.connect(self.on_end_entry_change)
        end_row.addWidget(self.end_time_entry)
        end_row.addStretch()
        layout.addLayout(end_row)

        # Trim duration display
        self.trim_duration_label = QLabel("Selected Duration: 00:00:00")
        self.trim_duration_label.setStyleSheet("color: green; font-size: 9pt; font-weight: bold;")
        self.trim_duration_label.setContentsMargins(40, 0, 0, 0)
        layout.addWidget(self.trim_duration_label)

        # --- separator ---
        layout.addWidget(self._hsep())

        # --- Save path ---
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Save to:"))
        self.path_label = QLabel(self.download_path)
        self.path_label.setStyleSheet("color: green;")
        path_row.addWidget(self.path_label)
        self.change_path_btn = QPushButton("Change")
        self.change_path_btn.clicked.connect(self.change_path)
        path_row.addWidget(self.change_path_btn)
        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.clicked.connect(self.open_download_folder)
        path_row.addWidget(self.open_folder_btn)
        path_row.addStretch()
        layout.addLayout(path_row)

        # --- Filename customization ---
        fn_row = QHBoxLayout()
        fn_row.addWidget(QLabel("Output filename:"))
        self.filename_entry = QLineEdit()
        self.filename_entry.setFixedWidth(300)
        fn_row.addWidget(self.filename_entry)
        opt_lbl = QLabel("(Optional - leave empty for auto-generated name)")
        opt_lbl.setStyleSheet("color: gray; font-size: 8pt;")
        fn_row.addWidget(opt_lbl)
        fn_row.addStretch()
        layout.addLayout(fn_row)

        # --- Download / Stop / Speed limit ---
        btn_row = QHBoxLayout()
        self.download_btn = QPushButton("Download")
        self.download_btn.setStyleSheet(
            "QPushButton { background-color: #1565c0; color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #1976d2; }"
            "QPushButton:disabled { background-color: #2a2a2a; color: #666; }")
        self.download_btn.clicked.connect(self.start_download)
        btn_row.addWidget(self.download_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_download)
        btn_row.addWidget(self.stop_btn)

        btn_row.addSpacing(15)
        self.speed_limit_entry = QLineEdit()
        self.speed_limit_entry.setFixedWidth(55)
        self.speed_limit_entry.setPlaceholderText("")
        btn_row.addWidget(self.speed_limit_entry)
        btn_row.addWidget(QLabel("MB/s"))
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # --- Progress bar + labels ---
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedWidth(560)
        layout.addWidget(self.progress, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.progress_label = QLabel("0%")
        self.progress_label.setStyleSheet("color: green;")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.progress_label)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: green;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.status_label)

        # --- Upload to Catbox.moe section ---
        layout.addWidget(self._hsep())
        upl_header = QLabel("Upload to Streaming Site:")
        upl_header.setStyleSheet(upl_header.styleSheet() + "font-size: 11px; font-weight: bold;")
        layout.addWidget(upl_header)

        upl_row = QHBoxLayout()
        self.upload_btn = QPushButton("Upload to Catbox.moe")
        self.upload_btn.setEnabled(False)
        self.upload_btn.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #388e3c; }"
            "QPushButton:disabled { background-color: #2a2a2a; color: #666; }")
        self.upload_btn.clicked.connect(self.start_upload)
        upl_row.addWidget(self.upload_btn)

        self.view_history_btn = QPushButton("View Upload History")
        self.view_history_btn.clicked.connect(self.view_upload_history)
        upl_row.addWidget(self.view_history_btn)

        self.upload_status_label = QLabel("")
        self.upload_status_label.setStyleSheet("color: green; font-size: 9pt;")
        upl_row.addWidget(self.upload_status_label)
        upl_row.addStretch()
        layout.addLayout(upl_row)

        # Auto-upload checkbox
        auto_upl_row = QHBoxLayout()
        auto_upl_row.setContentsMargins(20, 0, 0, 0)
        self.auto_upload_check = QCheckBox("Auto-upload after download/trim completes")
        auto_upl_row.addWidget(self.auto_upload_check)
        auto_upl_row.addStretch()
        layout.addLayout(auto_upl_row)

        # Upload URL display (initially hidden)
        self.upload_url_widget = QWidget()
        uurl_row = QHBoxLayout(self.upload_url_widget)
        uurl_row.setContentsMargins(0, 0, 0, 0)
        uurl_lbl = QLabel("Upload URL:")
        uurl_lbl.setStyleSheet(uurl_lbl.styleSheet() + "font-size: 9px; font-weight: bold;")
        uurl_row.addWidget(uurl_lbl)
        self.upload_url_entry = QLineEdit()
        self.upload_url_entry.setReadOnly(True)
        self.upload_url_entry.setMinimumWidth(400)
        uurl_row.addWidget(self.upload_url_entry)
        self.copy_url_btn = QPushButton("Copy URL")
        self.copy_url_btn.clicked.connect(self.copy_upload_url)
        uurl_row.addWidget(self.copy_url_btn)
        uurl_row.addStretch()
        self.upload_url_widget.setVisible(False)
        layout.addWidget(self.upload_url_widget)

    # ------------------------------------------------------------------
    #  Clipboard Mode tab construction
    # ------------------------------------------------------------------
    def setup_clipboard_mode_ui(self, layout: QVBoxLayout):
        """Build all widgets for the Clipboard Mode tab."""

        # Header
        hdr = QLabel("Clipboard Mode")
        hdr.setStyleSheet(hdr.styleSheet() + "font-size: 14px; font-weight: bold;")
        layout.addWidget(hdr)

        desc = QLabel("Copy YouTube URLs (Ctrl+C) to automatically detect and download them.")
        desc.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(desc)

        # Mode toggle
        mode_row = QHBoxLayout()
        mlbl = QLabel("Download Mode:")
        mlbl.setStyleSheet(mlbl.styleSheet() + "font-size: 10px; font-weight: bold;")
        mode_row.addWidget(mlbl)
        self.clipboard_auto_download_check = QCheckBox("Auto-download (starts immediately)")
        mode_row.addWidget(self.clipboard_auto_download_check)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # Settings section
        layout.addWidget(self._hsep())
        slbl = QLabel("Settings")
        slbl.setStyleSheet(slbl.styleSheet() + "font-size: 11px; font-weight: bold;")
        layout.addWidget(slbl)

        settings_row = QHBoxLayout()
        settings_row.setContentsMargins(20, 0, 0, 0)
        settings_row.addWidget(QLabel("Quality:"))
        self.clipboard_quality_combo = QComboBox()
        self.clipboard_quality_combo.setEditable(False)
        self.clipboard_quality_combo.addItems(["1440", "1080", "720", "480", "360", "240", "none (Audio only)"])
        self.clipboard_quality_combo.setCurrentText("1080")
        settings_row.addWidget(self.clipboard_quality_combo)

        settings_row.addSpacing(20)
        settings_row.addWidget(QLabel("Speed limit:"))
        self.clipboard_speed_limit_entry = QLineEdit()
        self.clipboard_speed_limit_entry.setFixedWidth(55)
        settings_row.addWidget(self.clipboard_speed_limit_entry)
        settings_row.addWidget(QLabel("MB/s"))
        settings_row.addStretch()
        layout.addLayout(settings_row)

        # Full playlist toggle
        pl_row = QHBoxLayout()
        pl_row.setContentsMargins(20, 0, 0, 0)
        self.clipboard_full_playlist_check = QCheckBox(
            "Full Playlist Download (download all videos when given a playlist link)")
        pl_row.addWidget(self.clipboard_full_playlist_check)
        pl_row.addStretch()
        layout.addLayout(pl_row)

        # Output folder
        layout.addWidget(self._hsep())
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Save to:"))
        self.clipboard_path_label = QLabel(self.clipboard_download_path)
        self.clipboard_path_label.setStyleSheet("color: green;")
        folder_row.addWidget(self.clipboard_path_label)
        chg_btn = QPushButton("Change")
        chg_btn.clicked.connect(self.change_clipboard_path)
        folder_row.addWidget(chg_btn)
        opn_btn = QPushButton("Open Folder")
        opn_btn.clicked.connect(self.open_clipboard_folder)
        folder_row.addWidget(opn_btn)
        folder_row.addStretch()
        layout.addLayout(folder_row)

        # URL list header
        layout.addWidget(self._hsep())
        url_hdr_row = QHBoxLayout()
        url_hdr_row.addWidget(QLabel("Detected URLs"))
        self.clipboard_url_count_label = QLabel("(0 URLs)")
        self.clipboard_url_count_label.setStyleSheet("color: gray; font-size: 9pt;")
        url_hdr_row.addWidget(self.clipboard_url_count_label)
        url_hdr_row.addStretch()
        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self.clear_all_clipboard_urls)
        url_hdr_row.addWidget(clear_btn)
        layout.addLayout(url_hdr_row)

        # Scrollable URL list (QScrollArea + QWidget + QVBoxLayout)
        self.clipboard_url_scroll = QScrollArea()
        self.clipboard_url_scroll.setWidgetResizable(True)
        self.clipboard_url_scroll.setFixedHeight(CLIPBOARD_URL_LIST_HEIGHT)
        self.clipboard_url_scroll.setFrameShape(QFrame.Shape.Box)
        self.clipboard_url_list_widget = QWidget()
        self.clipboard_url_list_layout = QVBoxLayout(self.clipboard_url_list_widget)
        self.clipboard_url_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.clipboard_url_list_layout.setContentsMargins(2, 2, 2, 2)
        self.clipboard_url_list_layout.setSpacing(2)
        self.clipboard_url_scroll.setWidget(self.clipboard_url_list_widget)
        layout.addWidget(self.clipboard_url_scroll)

        # Progress & controls
        layout.addWidget(self._hsep())
        ctrl_row = QHBoxLayout()
        self.clipboard_download_btn = QPushButton("Download All")
        self.clipboard_download_btn.setEnabled(False)
        self.clipboard_download_btn.setStyleSheet(
            "QPushButton { background-color: #1565c0; color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #1976d2; }"
            "QPushButton:disabled { background-color: #2a2a2a; color: #666; }")
        self.clipboard_download_btn.clicked.connect(self.start_clipboard_downloads)
        ctrl_row.addWidget(self.clipboard_download_btn)

        self.clipboard_stop_btn = QPushButton("Stop")
        self.clipboard_stop_btn.setEnabled(False)
        self.clipboard_stop_btn.clicked.connect(self.stop_clipboard_downloads)
        ctrl_row.addWidget(self.clipboard_stop_btn)
        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        # Individual progress
        layout.addWidget(QLabel("Current Download:"))
        self.clipboard_progress = QProgressBar()
        self.clipboard_progress.setRange(0, 100)
        self.clipboard_progress.setValue(0)
        self.clipboard_progress.setFixedWidth(560)
        layout.addWidget(self.clipboard_progress, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.clipboard_progress_label = QLabel("0%")
        self.clipboard_progress_label.setStyleSheet("color: green;")
        self.clipboard_progress_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.clipboard_progress_label)

        # Total progress
        self.clipboard_total_label = QLabel("Completed: 0/0 videos")
        self.clipboard_total_label.setStyleSheet("color: green; font-size: 9pt; font-weight: bold;")
        self.clipboard_total_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.clipboard_total_label)

        # Status
        self.clipboard_status_label = QLabel("Ready")
        self.clipboard_status_label.setStyleSheet("color: green;")
        self.clipboard_status_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.clipboard_status_label)

    # ------------------------------------------------------------------
    #  Uploader tab construction
    # ------------------------------------------------------------------
    def setup_uploader_ui(self, layout: QVBoxLayout):
        """Build all widgets for the Uploader tab."""

        # Header
        hdr = QLabel("Upload Local File")
        hdr.setStyleSheet(hdr.styleSheet() + "font-size: 14px; font-weight: bold;")
        layout.addWidget(hdr)

        desc = QLabel("Upload local video files to Catbox.moe streaming service.")
        desc.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(desc)

        layout.addWidget(self._hsep())

        # File queue header
        fq_row = QHBoxLayout()
        fq_row.addWidget(QLabel("File Queue:"))
        self.uploader_queue_count_label = QLabel("(0 files)")
        self.uploader_queue_count_label.setStyleSheet("color: gray; font-size: 9pt;")
        fq_row.addWidget(self.uploader_queue_count_label)
        fq_row.addStretch()
        layout.addLayout(fq_row)

        # Buttons
        fb_row = QHBoxLayout()
        self.add_files_btn = QPushButton("Add Files")
        self.add_files_btn.clicked.connect(self.browse_uploader_files)
        fb_row.addWidget(self.add_files_btn)
        clr_btn = QPushButton("Clear All")
        clr_btn.clicked.connect(self.clear_uploader_queue)
        fb_row.addWidget(clr_btn)
        fb_row.addStretch()
        layout.addLayout(fb_row)

        # Scrollable file list
        self.uploader_file_scroll = QScrollArea()
        self.uploader_file_scroll.setWidgetResizable(True)
        self.uploader_file_scroll.setFixedHeight(75)
        self.uploader_file_scroll.setFrameShape(QFrame.Shape.Box)
        self.uploader_file_list_widget = QWidget()
        self.uploader_file_list_layout = QVBoxLayout(self.uploader_file_list_widget)
        self.uploader_file_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.uploader_file_list_layout.setContentsMargins(2, 2, 2, 2)
        self.uploader_file_list_layout.setSpacing(2)
        self.uploader_file_scroll.setWidget(self.uploader_file_list_widget)
        layout.addWidget(self.uploader_file_scroll)

        # Upload controls
        layout.addWidget(self._hsep())
        uc_row = QHBoxLayout()
        self.uploader_upload_btn = QPushButton("Upload to Catbox.moe")
        self.uploader_upload_btn.setEnabled(False)
        self.uploader_upload_btn.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #388e3c; }"
            "QPushButton:disabled { background-color: #2a2a2a; color: #666; }")
        self.uploader_upload_btn.clicked.connect(self.start_uploader_upload)
        uc_row.addWidget(self.uploader_upload_btn)

        hist_btn = QPushButton("View Upload History")
        hist_btn.clicked.connect(self.view_upload_history)
        uc_row.addWidget(hist_btn)
        uc_row.addStretch()
        layout.addLayout(uc_row)

        self.uploader_status_label = QLabel("")
        self.uploader_status_label.setStyleSheet("color: green; font-size: 9pt;")
        layout.addWidget(self.uploader_status_label)

        # Upload URL display (initially hidden)
        self.uploader_url_widget = QWidget()
        uurl_row = QHBoxLayout(self.uploader_url_widget)
        uurl_row.setContentsMargins(0, 0, 0, 0)
        uurl_lbl = QLabel("Upload URL:")
        uurl_lbl.setStyleSheet(uurl_lbl.styleSheet() + "font-size: 9px; font-weight: bold;")
        uurl_row.addWidget(uurl_lbl)
        self.uploader_url_entry = QLineEdit()
        self.uploader_url_entry.setReadOnly(True)
        self.uploader_url_entry.setMinimumWidth(400)
        uurl_row.addWidget(self.uploader_url_entry)
        upl_copy_btn = QPushButton("Copy URL")
        upl_copy_btn.clicked.connect(self.copy_uploader_url)
        uurl_row.addWidget(upl_copy_btn)
        uurl_row.addStretch()
        self.uploader_url_widget.setVisible(False)
        layout.addWidget(self.uploader_url_widget)

    # ------------------------------------------------------------------
    #  Settings tab construction
    # ------------------------------------------------------------------
    def _setup_settings_tab(self, layout: QVBoxLayout):
        """Build all widgets for the Settings tab (compact, SwornTweaks-style)."""

        # Version header
        ver_lbl = QLabel(f"YoutubeDownloader v{APP_VERSION}")
        ver_lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(ver_lbl)

        gh_lbl = QLabel(f'<a href="https://github.com/{GITHUB_REPO}" '
                        f'style="color: gray;">github.com/{GITHUB_REPO}</a>')
        gh_lbl.setStyleSheet("color: gray; font-size: 11px;")
        gh_lbl.setOpenExternalLinks(True)
        layout.addWidget(gh_lbl)
        layout.addSpacing(12)

        # Action buttons
        self.check_updates_btn = QPushButton("Check for Updates")
        self.check_updates_btn.clicked.connect(self._check_for_updates_clicked)
        layout.addWidget(self.check_updates_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        readme_btn = QPushButton("Readme")
        readme_btn.setStyleSheet(
            "QPushButton { background-color: #1565c0; color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #1976d2; }")
        readme_btn.clicked.connect(lambda: webbrowser.open(f'https://github.com/{GITHUB_REPO}#readme'))
        layout.addWidget(readme_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addSpacing(12)

        # Settings checkboxes
        self.auto_check_updates_check = QCheckBox("Check for updates on startup")
        self.auto_check_updates_check.setChecked(self._load_auto_check_updates_setting())
        self.auto_check_updates_check.stateChanged.connect(self._save_auto_check_updates_setting)
        layout.addWidget(self.auto_check_updates_check)

        self.dark_mode_check = QCheckBox("Dark Mode")
        self.dark_mode_check.setChecked(self.current_theme == 'dark')
        self.dark_mode_check.stateChanged.connect(self._toggle_theme)
        layout.addWidget(self.dark_mode_check)

        layout.addSpacing(8)

        # Takodachi image
        try:
            img_path = self._get_resource_path('takodachi.webp')
            if os.path.exists(img_path):
                with Image.open(img_path) as pil_img:
                    pil_img.thumbnail((200, 200), Image.Resampling.LANCZOS)
                    pil_img = pil_img.convert("RGBA")
                    data = pil_img.tobytes("raw", "RGBA")
                    qimg = QImage(data, pil_img.width, pil_img.height, QImage.Format.Format_RGBA8888)
                    pix = QPixmap.fromImage(qimg)
                takodachi_label = QLabel()
                takodachi_label.setPixmap(pix)
                layout.addWidget(takodachi_label, alignment=Qt.AlignmentFlag.AlignLeft)
        except Exception as e:
            logger.error(f"Error loading settings image: {e}")

        by_lbl = QLabel("by JJ")
        by_lbl.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(by_lbl)

    # ------------------------------------------------------------------
    #  Help tab construction
    # ------------------------------------------------------------------
    def _setup_help_tab(self, layout: QVBoxLayout):
        """Build all widgets for the Help tab (SwornTweaks-style)."""

        hdr = QLabel("YoutubeDownloader Help")
        hdr.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(hdr)

        # Button row — accent-colored like SwornTweaks
        btn_row = QHBoxLayout()
        readme_btn = QPushButton("Readme")
        readme_btn.setStyleSheet(
            "QPushButton { background-color: #1565c0; color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #1976d2; }")
        readme_btn.clicked.connect(lambda: webbrowser.open(f'https://github.com/{GITHUB_REPO}#readme'))
        btn_row.addWidget(readme_btn)

        self._report_bug_btn = QPushButton("Report Bug")
        self._report_bug_btn.setStyleSheet(
            "QPushButton { background-color: #f9a825; color: #1e1e1e; font-weight: bold; }"
            "QPushButton:hover { background-color: #fbc02d; }")
        self._report_bug_btn.clicked.connect(
            lambda: webbrowser.open(
                f'https://github.com/{GITHUB_REPO}/issues/new?template=bug_report.yml'))
        btn_row.addWidget(self._report_bug_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addSpacing(6)

        # Help sections with thin separators like SwornTweaks
        sections = [
            ('Reporting Bugs',
             'Click "Report Bug" above to open the bug report form on GitHub. '
             'To help us find the issue, click "Open Log Folder" below and attach the '
             'youtubedownloader.log file to your report.'),
            ('Clipboard Mode',
             'Copy any YouTube URL (Ctrl+C) and it will automatically appear in the detected '
             'URLs list. You can download them individually or click "Download All" to batch '
             'download. Enable "Auto-download" to start downloading as soon as a URL is detected.'),
            ('Trimmer',
             'Paste a YouTube URL and select your desired quality. To trim a video, enable '
             '"Enable video trimming", click "Fetch Video Duration", then use the sliders or '
             'time fields to set start and end points. Frame previews show exactly what you\'re '
             'selecting.'),
            ('Uploader',
             'Upload local video or audio files to Catbox.moe for easy sharing. Click "Add Files" '
             'to select files, then "Upload to Catbox.moe" to upload. URLs are automatically copied '
             'to your clipboard. You can also enable auto-upload in the Trimmer tab to upload after '
             'each download.'),
            ('Settings',
             'Toggle dark mode, check for updates, and view app info.'),
        ]

        for title_text, desc_text in sections:
            sep = QLabel()
            sep.setFixedHeight(1)
            sep.setStyleSheet("background-color: #444;")
            layout.addWidget(sep)
            layout.addSpacing(6)
            t_lbl = QLabel(title_text)
            t_lbl.setStyleSheet("font-size: 13px; font-weight: bold;")
            layout.addWidget(t_lbl)
            d_lbl = QLabel(desc_text)
            d_lbl.setWordWrap(True)
            d_lbl.setStyleSheet("color: gray; font-size: 11px;")
            d_lbl.setContentsMargins(10, 0, 0, 0)
            layout.addWidget(d_lbl)
            layout.addSpacing(6)

        # Open Log Folder button at bottom
        layout.addSpacing(8)
        log_btn = QPushButton("Open Log Folder")
        log_btn.clicked.connect(lambda: webbrowser.open(str(APP_DATA_DIR)))
        layout.addWidget(log_btn, alignment=Qt.AlignmentFlag.AlignLeft)

    # ------------------------------------------------------------------
    #  Theme management
    # ------------------------------------------------------------------
    def _apply_theme(self):
        """Apply the current QSS theme to the entire application."""
        if self.current_theme == 'dark':
            qss = _build_dark_style()
        else:
            qss = _LIGHT_STYLE
        QApplication.instance().setStyleSheet(qss)

        # Dark title bar on Windows
        _set_dark_title_bar(self, dark=(self.current_theme == 'dark'))

        # Re-apply inline styles on preview labels based on theme
        colors = THEMES[self.current_theme]
        if hasattr(self, 'start_preview_label'):
            self.start_preview_label.setStyleSheet(
                f"background: {colors['preview_bg']}; color: {colors['preview_fg']};")
        if hasattr(self, 'end_preview_label'):
            self.end_preview_label.setStyleSheet(
                f"background: {colors['preview_bg']}; color: {colors['preview_fg']};")

        # Clipboard URL list scroll area background
        if hasattr(self, 'clipboard_url_scroll'):
            self.clipboard_url_scroll.setStyleSheet(
                f"QScrollArea {{ border: 1px solid {colors['border']}; background: {colors['canvas_bg']}; }}")
            self.clipboard_url_list_widget.setStyleSheet(
                f"background: {colors['canvas_bg']};")

        # Uploader file list
        if hasattr(self, 'uploader_file_scroll'):
            self.uploader_file_scroll.setStyleSheet(
                f"QScrollArea {{ border: 1px solid {colors['border']}; background: {colors['canvas_bg']}; }}")
            self.uploader_file_list_widget.setStyleSheet(
                f"background: {colors['canvas_bg']};")

    def _toggle_theme(self):
        """Toggle between light and dark theme."""
        self.current_theme = 'dark' if self.current_theme == 'light' else 'light'
        # Keep checkbox in sync (if triggered programmatically)
        if hasattr(self, 'dark_mode_check'):
            self.dark_mode_check.blockSignals(True)
            self.dark_mode_check.setChecked(self.current_theme == 'dark')
            self.dark_mode_check.blockSignals(False)
        self._apply_theme()
        self._save_theme_preference()

    # ------------------------------------------------------------------
    #  closeEvent (replaces on_closing)
    # ------------------------------------------------------------------
    def closeEvent(self, event):
        """Handle window close with proper resource cleanup."""
        logger.info("Application shutdown initiated...")

        # Cancel preview timer
        if hasattr(self, '_preview_debounce_timer') and self._preview_debounce_timer.isActive():
            self._preview_debounce_timer.stop()

        self._shutting_down = True

        # Stop clipboard timer
        if hasattr(self, '_clipboard_timer'):
            self._clipboard_timer.stop()

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

        # Shutdown thread pool
        logger.info("Shutting down thread pool...")
        with self.download_lock:
            self.is_downloading = False
        try:
            self.thread_pool.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            self.thread_pool.shutdown(wait=False)
        except Exception as e:
            logger.error(f"Error shutting down thread pool: {e}")

        logger.info("Application shutdown complete")
        event.accept()

    # ------------------------------------------------------------------
    #  Signal-connected slot methods (thread-safe GUI updates)
    # ------------------------------------------------------------------
    def _do_update_progress(self, value: float):
        """Update main progress bar (called on GUI thread via signal)."""
        value = max(0.0, min(100.0, value))
        self.progress.setValue(int(value))
        self.progress_label.setText(f"{value:.1f}%")

    def _do_update_status(self, message: str, color: str):
        """Update status label (called on GUI thread via signal)."""
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {color};")

    def _do_reset_buttons(self):
        """Reset download/stop buttons to idle state (called on GUI thread via signal)."""
        self.download_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _do_show_messagebox(self, msg_type: str, title: str, message: str):
        """Show a message box (called on GUI thread via signal)."""
        if msg_type == "info":
            QMessageBox.information(self, title, message)
        elif msg_type == "warning":
            QMessageBox.warning(self, title, message)
        elif msg_type == "error":
            QMessageBox.critical(self, title, message)
        elif msg_type == "question":
            QMessageBox.question(self, title, message)

    def _do_clipboard_progress(self, value: float):
        """Update clipboard progress bar."""
        value = max(0.0, min(100.0, value))
        self.clipboard_progress.setValue(int(value))
        self.clipboard_progress_label.setText(f"{value:.1f}%")

    def _do_clipboard_status(self, message: str, color: str):
        """Update clipboard status label."""
        self.clipboard_status_label.setText(message)
        self.clipboard_status_label.setStyleSheet(f"color: {color};")

    def _do_clipboard_total(self, text: str):
        """Update clipboard total label."""
        self.clipboard_total_label.setText(text)

    def _do_upload_status(self, message: str, color: str):
        """Update trimmer upload status label."""
        self.upload_status_label.setText(message)
        self.upload_status_label.setStyleSheet(f"color: {color}; font-size: 9pt;")

    def _do_uploader_status(self, message: str, color: str):
        """Update uploader tab status label."""
        self.uploader_status_label.setText(message)
        self.uploader_status_label.setStyleSheet(f"color: {color}; font-size: 9pt;")

    def _do_set_upload_url(self, url: str):
        """Show trimmer upload URL."""
        self.upload_url_entry.setText(url)
        self.upload_url_widget.setVisible(True)

    def _do_set_uploader_url(self, url: str):
        """Show uploader upload URL."""
        self.uploader_url_entry.setText(url)
        self.uploader_url_widget.setVisible(True)

    def _do_enable_upload_btn(self, enabled: bool):
        """Enable or disable the upload button."""
        self.upload_btn.setEnabled(enabled)

    def _do_set_mode_label(self, text: str):
        """Set the trimmer mode indicator label."""
        self.mode_label.setText(text)

    def _do_set_video_info(self, text: str):
        """Set the trimmer video info label."""
        self.video_info_label.setText(text)

    def _do_set_filesize_label(self, text: str):
        """Set the trimmer filesize label."""
        self.filesize_label.setText(text)

    def _do_update_url_status(self, url: str, status: str):
        """Update a URL's status in the clipboard list."""
        widget_data = self.clipboard_url_widgets.get(url)
        if widget_data:
            status_label = widget_data.get('status_label')
            status_text = widget_data.get('status_text')
            colors = {'pending': 'gray', 'downloading': '#ff8c00',
                      'completed': '#00cc00', 'failed': '#ff3333'}
            if status_label:
                status_label.setStyleSheet(
                    f"background: {colors.get(status, 'gray')}; "
                    f"border-radius: 6px; border: none;")
            if status_text:
                status_text.setText(status.capitalize())

    def _do_add_url_to_list(self, url: str):
        """Add a URL to the clipboard list (called on GUI thread via signal)."""
        self._add_url_to_clipboard_list(url)

    # ------------------------------------------------------------------
    #  Thread-safe helper (replaces _safe_after)
    # ------------------------------------------------------------------
    def update_progress(self, value):
        """Update main progress bar (thread-safe)."""
        try:
            value = float(value)
            value = max(0, min(100, value))
            self.sig_update_progress.emit(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid progress value: {value} - {e}")

    def update_status(self, message, color):
        """Update status label (thread-safe)."""
        self.sig_update_status.emit(str(message), str(color))

    def _reset_buttons(self):
        """Reset download/stop buttons (thread-safe)."""
        self.sig_reset_buttons.emit()

    # ------------------------------------------------------------------
    #  Tab change handling & clipboard monitoring
    # ------------------------------------------------------------------
    def _on_tab_changed(self, index):
        """Handle tab changes — start/stop clipboard monitoring."""
        if index == 0:  # Clipboard Mode tab
            self.start_clipboard_monitoring()
        else:
            self.stop_clipboard_monitoring()
    # ------------------------------------------------------------------
    #  Volume slider/entry helpers
    # ------------------------------------------------------------------
    def _on_volume_slider_change(self, value):
        """Sync volume entry when slider moves."""
        self._volume_int = value
        self.volume_entry.blockSignals(True)
        self.volume_entry.setText(str(value))
        self.volume_entry.blockSignals(False)

    def _on_volume_entry_change(self):
        """Sync volume slider when entry is edited."""
        try:
            val = int(self.volume_entry.text())
            val = max(0, min(200, val))
        except (ValueError, TypeError):
            val = 100
        self._volume_int = val
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(val)
        self.volume_slider.blockSignals(False)
        self.volume_entry.setText(str(val))

    @property
    def volume_value(self):
        """Get volume as a float 0.0 - 2.0 (for business logic compatibility)."""
        return self._volume_int / 100.0

    # ------------------------------------------------------------------
    #  Convenience helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _hsep() -> QFrame:
        """Create a horizontal separator line."""
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        return sep

    def _get_resource_path(self, filename):
        """Get path to a resource file (works for both source and bundled mode)."""
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            local_path = os.path.join(exe_dir, filename)
            if os.path.exists(local_path):
                return local_path
            bundle_dir = getattr(sys, '_MEIPASS', exe_dir)
            return os.path.join(bundle_dir, filename)
        else:
            return os.path.join(os.path.dirname(__file__), filename)

    def create_placeholder_pixmap(self, width, height, text):
        """Create a placeholder QPixmap with centered text."""
        pix = QPixmap(width, height)
        pix.fill(QColor("#2d2d2d"))
        painter = QPainter(pix)
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Arial", 10))
        painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
        return pix

    def seconds_to_hms(self, seconds):
        """Convert seconds to HH:MM:SS format."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    # ------------------------------------------------------------------
    #  Persistence methods (carried over from tkinter version)
    # ------------------------------------------------------------------
    def _load_clipboard_urls(self):
        """Load persisted clipboard URLs from previous session."""
        try:
            if CLIPBOARD_URLS_FILE.exists():
                with open(CLIPBOARD_URLS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if not isinstance(data, dict):
                        raise ValueError("Invalid clipboard URLs file format: expected dict")
                    if 'urls' not in data:
                        raise ValueError("Invalid clipboard URLs file format: missing 'urls' key")
                    if not isinstance(data['urls'], list):
                        raise ValueError("Invalid clipboard URLs file format: 'urls' must be a list")
                    self.persisted_clipboard_urls = data['urls']
                    logger.info(f"Loaded {len(self.persisted_clipboard_urls)} persisted clipboard URLs")
            else:
                self.persisted_clipboard_urls = []
        except Exception as e:
            logger.error(f"Error loading clipboard URLs: {e}")
            self.persisted_clipboard_urls = []

    def _save_clipboard_urls(self):
        """Save clipboard URLs to file for persistence between sessions."""
        try:
            CLIPBOARD_URLS_FILE.parent.mkdir(parents=True, exist_ok=True)
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
        """Restore persisted URLs to the UI (called after setup_ui)."""
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
        """Load auto-check updates setting from config."""
        try:
            with self.config_lock:
                if CONFIG_FILE.exists():
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        return config.get('auto_check_updates', True)
        except Exception as e:
            logger.error(f"Error loading auto_check_updates setting: {e}")
        return True

    def _save_auto_check_updates_setting(self):
        """Save auto-check updates setting to config."""
        with self.config_lock:
            try:
                CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
                config = {}
                if CONFIG_FILE.exists():
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                config['auto_check_updates'] = self.auto_check_updates_check.isChecked()
                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2)
                logger.info(f"Saved auto_check_updates: {config['auto_check_updates']}")
            except Exception as e:
                logger.error(f"Error saving auto_check_updates setting: {e}")

    def _load_theme_preference(self):
        """Load saved theme preference from config."""
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
        """Save theme preference to config."""
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

    # ------------------------------------------------------------------
    #  Dependency / init methods (carried over, needed by __init__)
    # ------------------------------------------------------------------
    def _get_bundled_executable(self, name):
        """Get path to bundled executable (ffmpeg/ffprobe/yt-dlp) if available."""
        if getattr(sys, 'frozen', False):
            if sys.platform == 'win32':
                exe_name = f"{name}.exe"
            else:
                exe_name = name
            exe_dir = os.path.dirname(sys.executable)
            local_path = os.path.join(exe_dir, exe_name)
            if os.path.exists(local_path):
                logger.info(f"Using local {name}: {local_path}")
                return local_path
            bundle_dir = getattr(sys, '_MEIPASS', exe_dir)
            bundled_path = os.path.join(bundle_dir, exe_name)
            if os.path.exists(bundled_path):
                logger.info(f"Using bundled {name}: {bundled_path}")
                return bundled_path
        else:
            script_dir = Path(__file__).parent
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
            python_bin_path = Path(sys.executable).parent / exe_name
            if python_bin_path.exists():
                logger.info(f"Using Python bin {name}: {python_bin_path}")
                return str(python_bin_path)
        return name

    def check_dependencies(self):
        """Check if yt-dlp, ffmpeg, and ffprobe are available."""
        try:
            if os.path.isfile(self.ytdlp_path) and os.access(self.ytdlp_path, os.X_OK):
                result = subprocess.run([self.ytdlp_path, '--version'],
                                        capture_output=True, timeout=DEPENDENCY_CHECK_TIMEOUT, **_subprocess_kwargs)
                version = result.stdout.decode('utf-8', errors='replace').strip()
                if version:
                    logger.info(f"yt-dlp version: {version}")
                else:
                    logger.info(f"yt-dlp is available at: {self.ytdlp_path}")
            elif shutil.which(self.ytdlp_path):
                result = subprocess.run([self.ytdlp_path, '--version'],
                                        capture_output=True, timeout=DEPENDENCY_CHECK_TIMEOUT, **_subprocess_kwargs)
                logger.info(f"yt-dlp version: {result.stdout.decode('utf-8', errors='replace').strip()}")
            else:
                logger.error(f"yt-dlp not found at: {self.ytdlp_path}")
                return False

            result = subprocess.run([self.ffmpeg_path, '-version'],
                                    capture_output=True, timeout=DEPENDENCY_CHECK_TIMEOUT, **_subprocess_kwargs)
            if result.returncode == 0:
                logger.info(f"ffmpeg is available at: {self.ffmpeg_path}")
            else:
                logger.error("ffmpeg check failed")
                return False

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
        for encoder in ('h264_amf', 'h264_nvenc'):
            try:
                probe_out = os.path.join(tempfile.gettempdir(), 'ytdl_hwprobe.mp4')
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

    def _init_temp_directory(self):
        """Initialize temp directory and clean up orphaned ones from previous crashes."""
        temp_base = tempfile.gettempdir()
        old_dirs = glob.glob(os.path.join(temp_base, "ytdl_preview_*"))
        for old_dir in old_dirs:
            try:
                dir_age = time.time() - os.path.getmtime(old_dir)
                if dir_age > TEMP_DIR_MAX_AGE:
                    shutil.rmtree(old_dir, ignore_errors=True)
            except OSError:
                pass
        self.temp_dir = tempfile.mkdtemp(prefix="ytdl_preview_")

    def _cleanup_old_updates(self):
        """Remove leftover files from previous self-updates."""
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


    # ==================================================================
    #  PORTED BUSINESS LOGIC METHODS
    # ==================================================================


    # --- from _port_callbacks.py ---

    def _safe_after(self, delay, callback):
        """Schedule *callback* on the GUI thread after *delay* ms.

        Drop-in replacement for the old tkinter ``self.root.after()`` calls
        used by worker threads.  If the application is shutting down the
        callback is silently discarded.
        """
        if not self._shutting_down:
            QTimer.singleShot(max(0, delay), callback)

    # ==================================================================
    #  CLIPBOARD CALLBACKS
    # ==================================================================


    def on_tab_changed(self, index):
        """Handle notebook tab changes."""
        if index == 0:  # Clipboard Mode tab
            self.start_clipboard_monitoring()
        else:
            self.stop_clipboard_monitoring()


    def start_clipboard_monitoring(self):
        """Start clipboard monitoring using QTimer polling."""
        with self.clipboard_lock:
            if self.clipboard_monitoring:
                return
            self.clipboard_monitoring = True
            logger.info("Clipboard monitoring started (QTimer polling)")
            try:
                content = QApplication.clipboard().text()
                self.clipboard_last_content = content.strip() if content else ""
            except Exception:
                self.clipboard_last_content = ""
        self._clipboard_timer.start()


    def stop_clipboard_monitoring(self):
        """Stop clipboard monitoring."""
        with self.clipboard_lock:
            if not self.clipboard_monitoring:
                return
            self.clipboard_monitoring = False
            logger.info("Clipboard monitoring stopped")
        self._clipboard_timer.stop()


    def _poll_clipboard(self):
        """Poll clipboard for new YouTube URLs (called by QTimer)."""
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
            if not clipboard_content:
                try:
                    import pyperclip
                    clipboard_content = pyperclip.paste()
                except Exception:
                    clipboard_content = None

            # Fallback to Qt clipboard
            if not clipboard_content:
                try:
                    clipboard_content = QApplication.clipboard().text()
                except Exception:
                    clipboard_content = None

            # Normalize
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

                        if self.clipboard_auto_download_check.isChecked():
                            logger.info(f"Auto-download enabled, starting download: {clipboard_content}")
                            self._auto_download_single_url(clipboard_content)
                else:
                    logger.debug(f"Clipboard content not a valid YouTube URL: {message}")

        except Exception as e:
            logger.error(f"Error polling clipboard: {e}")


    def _add_url_to_clipboard_list(self, url):
        """Add URL to clipboard list with UI widget."""
        # Build the row widget
        url_frame = QWidget()
        url_frame.setStyleSheet("border: 1px solid #555; border-radius: 2px; padding: 2px;")
        row_layout = QHBoxLayout(url_frame)
        row_layout.setContentsMargins(5, 2, 5, 2)
        row_layout.setSpacing(5)

        # Status indicator (coloured circle via QLabel)
        status_label = QLabel()
        status_label.setFixedSize(12, 12)
        status_label.setStyleSheet(
            "background: gray; border-radius: 6px; border: none;")
        row_layout.addWidget(status_label)

        # URL text
        url_display = url if len(url) <= 60 else url[:57] + "..."
        url_label = QLabel(url_display)
        url_label.setStyleSheet(url_label.styleSheet() + "font-size: 9px;")
        url_label.setStyleSheet("border: none;")
        row_layout.addWidget(url_label, stretch=1)

        # Remove button
        remove_btn = QPushButton("X")
        remove_btn.setFixedWidth(30)
        remove_btn.setStyleSheet("border: none;")
        remove_btn.clicked.connect(lambda checked, u=url: self._remove_url_from_list(u))
        row_layout.addWidget(remove_btn)

        # Add to the scroll-area layout
        self.clipboard_url_list_layout.addWidget(url_frame)

        url_data = {
            'url': url,
            'status': 'pending',
            'widget': url_frame,
            'status_label': status_label,
        }

        with self.clipboard_lock:
            # Cap the list to prevent unbounded memory growth
            if len(self.clipboard_url_list) >= 500:
                oldest = self.clipboard_url_list.pop(0)
                self.clipboard_url_widgets.pop(oldest['url'], None)
                if oldest.get('widget'):
                    oldest['widget'].deleteLater()
            self.clipboard_url_list.append(url_data)
            self.clipboard_url_widgets[url] = url_data
            has_urls = len(self.clipboard_url_list) > 0

        self._update_clipboard_url_count()
        with self.clipboard_lock:
            is_downloading = self.clipboard_downloading
        if has_urls and not is_downloading:
            self.clipboard_download_btn.setEnabled(True)

        # Save URLs to persistence file
        self._save_clipboard_urls()


    def _remove_url_from_list(self, url):
        """Remove URL from clipboard list."""
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

        if widget_to_destroy:
            widget_to_destroy.deleteLater()
            self._update_clipboard_url_count()
            if list_is_empty:
                self.clipboard_download_btn.setEnabled(False)
            logger.info(f"Removed URL: {url}")
            self._save_clipboard_urls()


    def clear_all_clipboard_urls(self):
        """Clear all URLs from clipboard list."""
        with self.clipboard_lock:
            is_downloading = self.clipboard_downloading
        if is_downloading:
            QMessageBox.warning(self, 'Cannot Clear',
                                'Cannot clear URLs while downloads are in progress.')
            return

        with self.clipboard_lock:
            widgets_to_destroy = [
                item['widget'] for item in self.clipboard_url_list if item.get('widget')]
            self.clipboard_url_list.clear()
            self.clipboard_url_widgets.clear()

        for widget in widgets_to_destroy:
            widget.deleteLater()

        self._update_clipboard_url_count()
        self.clipboard_download_btn.setEnabled(False)
        logger.info("Cleared all clipboard URLs")
        self._save_clipboard_urls()


    def _update_clipboard_url_count(self):
        """Update URL count label."""
        with self.clipboard_lock:
            count = len(self.clipboard_url_list)
        s = 's' if count != 1 else ''
        self.clipboard_url_count_label.setText(f'({count} URL{s})')


    def _update_url_status(self, url, status):
        """Update visual status of URL: pending (gray), downloading (blue),
        completed (green), failed (red)."""
        if url in self.clipboard_url_widgets:
            item = self.clipboard_url_widgets[url]
            status_label = item.get('status_label')

            color_map = {
                'pending': 'gray',
                'downloading': 'blue',
                'completed': 'green',
                'failed': 'red',
            }
            color = color_map.get(status, 'gray')
            if status_label:
                status_label.setStyleSheet(
                    f"background: {color}; border-radius: 6px; border: none;")

            with self.clipboard_lock:
                for item_data in self.clipboard_url_list:
                    if item_data['url'] == url:
                        item_data['status'] = status
                        break


    def start_clipboard_downloads(self):
        """Start downloading all pending URLs sequentially."""
        with self.clipboard_lock:
            is_downloading = self.clipboard_downloading
        if is_downloading:
            return

        with self.clipboard_lock:
            pending_urls = [
                item for item in self.clipboard_url_list if item['status'] == 'pending']

        if not pending_urls:
            QMessageBox.information(self, 'No URLs', 'No pending URLs to download.')
            return

        with self.clipboard_lock:
            self.clipboard_downloading = True
        self.clipboard_download_btn.setEnabled(False)
        self.clipboard_stop_btn.setEnabled(True)

        total_count = len(pending_urls)
        self.clipboard_total_label.setText(f'Completed: 0/{total_count} videos')

        # Snapshot clipboard widget values on GUI thread for thread safety
        clip_state = {
            'quality': self.clipboard_quality_combo.currentText(),
            'full_playlist': self.clipboard_full_playlist_check.isChecked(),
            'speed_limit': self.clipboard_speed_limit_entry.text().strip(),
            'download_path': self.clipboard_download_path,
        }
        logger.info(f"Starting clipboard batch download: {total_count} URLs")
        self.thread_pool.submit(self._process_clipboard_queue, clip_state)


    def _process_clipboard_queue(self, clip_state=None):
        """Process clipboard download queue sequentially (runs in worker thread)."""
        with self.clipboard_lock:
            pending_urls = [
                item for item in self.clipboard_url_list if item['status'] == 'pending']
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
                             self.clipboard_total_label.setText(
                                 f'Completed: {i}/{t} videos'))
            self._safe_after(0, lambda u=url:
                             self.update_clipboard_status(
                                 f'Downloading: {u[:50]}...', "blue"))

            success = self._download_clipboard_url(url, check_stop=True, clip_state=clip_state)

            if success:
                self._safe_after(0, lambda u=url: self._update_url_status(u, 'completed'))
            else:
                self._safe_after(0, lambda u=url: self._update_url_status(u, 'failed'))

            completed = index + 1
            self._safe_after(0, lambda c=completed, t=total_count:
                             self.clipboard_total_label.setText(
                                 f'Completed: {c}/{t} videos'))

        self._safe_after(0, self._finish_clipboard_downloads)


    def _download_clipboard_url(self, url, check_stop=False, check_stop_auto=False, clip_state=None):
        """Download single URL or playlist from clipboard mode (blocking, runs
        in thread). Returns True if successful.

        Args:
            clip_state: Dict of clipboard widget values snapshot from GUI thread.
        """
        process = None
        try:
            if clip_state:
                quality = clip_state['quality']
            else:
                quality = self.clipboard_quality_combo.currentText()
            if "none" in quality.lower() or quality == "none (Audio only)":
                quality = "none"

            audio_only = quality.startswith("none")
            is_playlist_url = self.is_playlist_url(url)
            full_playlist_enabled = clip_state['full_playlist'] if clip_state else self.clipboard_full_playlist_check.isChecked()

            download_as_playlist = is_playlist_url and full_playlist_enabled

            self._safe_after(0, lambda: self.clipboard_progress.setValue(0))
            self._safe_after(0, lambda: self.clipboard_progress_label.setText("0%"))

            # Build output path template
            _cdp = clip_state['download_path'] if clip_state else self.clipboard_download_path
            if audio_only:
                if download_as_playlist:
                    output_path = os.path.join(
                        _cdp, '%(playlist_index)s-%(title)s.%(ext)s')
                else:
                    output_path = os.path.join(_cdp, '%(title)s.%(ext)s')
            else:
                if download_as_playlist:
                    output_path = os.path.join(
                        _cdp, f'%(playlist_index)s-%(title)s_{quality}p.%(ext)s')
                else:
                    output_path = os.path.join(
                        _cdp, f'%(title)s_{quality}p.%(ext)s')

            # Build yt-dlp command
            if audio_only:
                cmd = self.build_audio_ytdlp_command(url, output_path, volume=1.0)
            else:
                cmd = self.build_video_ytdlp_command(url, output_path, quality, volume=1.0)

            if is_playlist_url and not full_playlist_enabled:
                cmd.insert(1, '--no-playlist')

            # Speed limit
            _csl = clip_state['speed_limit'] if clip_state else None
            cmd.extend(self._get_speed_limit_args(speed_limit_str=_csl))

            if download_as_playlist:
                logger.info(f"Clipboard full playlist download starting: {url}")
            elif is_playlist_url:
                logger.info(f"Clipboard single video from playlist starting: {url}")
            else:
                logger.info(f"Clipboard download starting: {url}")

            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                encoding='utf-8', errors='replace', bufsize=1, **_subprocess_kwargs)

            current_phase = "video" if not audio_only else "audio"
            playlist_item_info = ""

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

                # Detect phase changes
                if ('downloading video' in line_lower or
                        ('video' in line_lower and 'downloading' in line_lower)):
                    current_phase = "video"
                elif ('downloading audio' in line_lower or
                      ('audio' in line_lower and 'downloading' in line_lower)):
                    current_phase = "audio"

                # Detect playlist item progress
                if download_as_playlist and 'downloading item' in line_lower:
                    item_match = re.search(
                        r'downloading item (\d+) of (\d+)', line_lower)
                    if item_match:
                        playlist_item_info = (
                            f" [{item_match.group(1)}/{item_match.group(2)}]")

                if '[download]' in line or 'Downloading' in line:
                    progress_match = PROGRESS_REGEX.search(line)
                    if progress_match:
                        progress = float(progress_match.group(1))
                        self._safe_after(
                            0, lambda p=progress: self.update_clipboard_progress(p))

                        phase = current_phase
                        pinfo = playlist_item_info
                        self._safe_after(
                            0,
                            lambda p=progress, ph=phase, pi=pinfo:
                                self.update_clipboard_status(
                                    f'Downloading {ph}{pi}... {p:.1f}%', "blue"))

                elif '[Merger]' in line or 'Merging' in line:
                    self._safe_after(
                        0, lambda: self.update_clipboard_status(
                            'Merging video and audio...', "blue"))
                elif '[ffmpeg]' in line:
                    self._safe_after(
                        0, lambda: self.update_clipboard_status(
                            'Processing with ffmpeg...', "blue"))
                elif '[ExtractAudio]' in line:
                    self._safe_after(
                        0, lambda: self.update_clipboard_status(
                            'Extracting audio...', "blue"))

            process.wait()

            if process.returncode == 0:
                self._safe_after(
                    0, lambda: self.update_clipboard_progress(PROGRESS_COMPLETE))
                logger.info(f"Clipboard download completed: {url}")
                success = True
            else:
                logger.error(
                    f"Clipboard download failed: {url}, "
                    f"returncode={process.returncode}")
                success = False

            self.safe_process_cleanup(process)
            return success

        except Exception as e:
            logger.exception(f"Error downloading clipboard URL {url}: {e}")
            if process:
                self.safe_process_cleanup(process)
            return False


    def _finish_clipboard_downloads(self):
        """Clean up after batch downloads complete."""
        with self.clipboard_lock:
            self.clipboard_downloading = False
            has_urls = len(self.clipboard_url_list) > 0
            completed = sum(
                1 for item in self.clipboard_url_list
                if item['status'] == 'completed')
            failed = sum(
                1 for item in self.clipboard_url_list
                if item['status'] == 'failed')

        self.clipboard_download_btn.setEnabled(has_urls)
        self.clipboard_stop_btn.setEnabled(False)

        if failed > 0:
            self.update_clipboard_status(
                f'Completed: {completed} | Failed: {failed}', "orange")
        else:
            self.update_clipboard_status(
                f'All downloads complete! ({completed} videos)', "green")

        logger.info(
            f"Clipboard batch download finished: "
            f"{completed} completed, {failed} failed")


    def stop_clipboard_downloads(self):
        """Stop clipboard batch downloads and auto-downloads."""
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
            self.clipboard_stop_btn.setEnabled(False)


    def _auto_download_single_url(self, url):
        """Auto-download single URL when detected (if auto-download enabled)."""
        with self.auto_download_lock:
            with self.clipboard_lock:
                downloading_count = sum(
                    1 for item in self.clipboard_url_list
                    if item['status'] == 'downloading')
            if downloading_count > 0:
                logger.info(f"URL queued (another download in progress): {url}")
                return

            self.clipboard_auto_downloading = True
            self._update_url_status(url, 'downloading')

        self.clipboard_stop_btn.setEnabled(True)
        self._update_auto_download_total()
        # Snapshot clipboard widget values on GUI thread for thread safety
        clip_state = {
            'quality': self.clipboard_quality_combo.currentText(),
            'full_playlist': self.clipboard_full_playlist_check.isChecked(),
            'speed_limit': self.clipboard_speed_limit_entry.text().strip(),
            'download_path': self.clipboard_download_path,
        }
        self.thread_pool.submit(self._auto_download_worker, url, clip_state)


    def _auto_download_worker(self, url, clip_state=None):
        """Worker thread for auto-downloading single URL."""
        with self.auto_download_lock:
            is_auto_downloading = self.clipboard_auto_downloading
        if not is_auto_downloading:
            self._safe_after(
                0, lambda: self._update_url_status(url, 'pending'))
            return

        self._safe_after(
            0, lambda: self.update_clipboard_status(
                f'Auto-downloading: {url[:50]}...', "blue"))

        success = self._download_clipboard_url(url, check_stop_auto=True, clip_state=clip_state)

        with self.auto_download_lock:
            is_auto_downloading = self.clipboard_auto_downloading
        if not is_auto_downloading:
            self._safe_after(
                0, lambda: self._update_url_status(url, 'pending'))
            self._safe_after(
                0, lambda: self.update_clipboard_status(
                    'Auto-download stopped', "orange"))
            return

        self._safe_after(
            0, lambda: self._handle_auto_download_complete(url, success))


    def _handle_auto_download_complete(self, url, success):
        """Handle auto-download completion — runs on main thread."""
        if success:
            self._update_url_status(url, 'completed')
            self._update_auto_download_total()
            self.update_clipboard_status(
                f'Auto-download complete: {url[:50]}...', "green")
            self._remove_url_from_list(url)
            logger.info(f"Auto-download completed and removed: {url}")
        else:
            self._update_url_status(url, 'failed')
            self._update_auto_download_total()
            self.update_clipboard_status(
                f'Auto-download failed: {url[:50]}...', "red")
            logger.info(f"Auto-download failed: {url}")

        self._check_pending_auto_downloads()


    def _disable_stop_if_idle(self):
        """Disable stop button if no downloads in progress."""
        with self.clipboard_lock:
            is_downloading = self.clipboard_downloading
        with self.auto_download_lock:
            is_auto_downloading = self.clipboard_auto_downloading
        if not is_downloading and not is_auto_downloading:
            self.clipboard_stop_btn.setEnabled(False)


    def _check_pending_auto_downloads(self):
        """Check if there are pending URLs that need to be auto-downloaded."""
        with self.auto_download_lock:
            self.clipboard_auto_downloading = False

        if self.clipboard_auto_download_check.isChecked():
            with self.clipboard_lock:
                next_pending_url = None
                for item in self.clipboard_url_list:
                    if item['status'] == 'pending':
                        next_pending_url = item['url']
                        break

            if next_pending_url:
                self._auto_download_single_url(next_pending_url)
        else:
            self._disable_stop_if_idle()


    def _update_auto_download_total(self):
        """Update total progress for auto-downloads."""
        with self.clipboard_lock:
            total = len(self.clipboard_url_list)
            completed = sum(
                1 for item in self.clipboard_url_list
                if item['status'] in ['completed', 'failed'])
        self.clipboard_total_label.setText(
            f'Completed: {completed}/{total} videos')


    def update_clipboard_progress(self, value):
        """Update clipboard mode progress bar."""
        try:
            value = float(value)
            value = max(0, min(100, value))
            self.clipboard_progress.setValue(int(value))
            self.clipboard_progress_label.setText(f"{value:.1f}%")
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid progress value: {value} - {e}")


    def update_clipboard_status(self, message, color):
        """Update clipboard mode status label."""
        self.clipboard_status_label.setText(message)
        self.clipboard_status_label.setStyleSheet(f"color: {color};")


    def change_clipboard_path(self):
        """Change clipboard mode download path."""
        path = QFileDialog.getExistingDirectory(
            self, 'Select Download Folder', self.clipboard_download_path)
        if path:
            is_valid, normalized_path, error_msg = self.validate_download_path(path)
            if not is_valid:
                QMessageBox.critical(self, 'Error', error_msg)
                return
            path = normalized_path

            if not os.path.exists(path):
                QMessageBox.critical(self, 'Error',
                                     f'Path does not exist: {path}')
                return

            if not os.path.isdir(path):
                QMessageBox.critical(self, 'Error',
                                     f'Path is not a directory: {path}')
                return

            test_file = os.path.join(path, ".ytdl_write_test")
            try:
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
            except (IOError, OSError) as e:
                QMessageBox.critical(
                    self, 'Error',
                    f'Path is not writable:\n{path}\n\n{e}')
                return

            self.clipboard_download_path = path
            self.clipboard_path_label.setText(path)
            logger.info(f"Clipboard download path changed to: {path}")


    def open_clipboard_folder(self):
        """Open clipboard mode download folder."""
        try:
            if sys.platform == 'win32':
                os.startfile(self.clipboard_download_path)
            elif sys.platform == 'darwin':
                subprocess.Popen(
                    ['open', self.clipboard_download_path],
                    close_fds=True, start_new_session=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(
                    ['xdg-open', self.clipboard_download_path],
                    close_fds=True, start_new_session=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            QMessageBox.critical(self, 'Error',
                                 f'Failed to open folder:\n{e}')

    # ==================================================================
    #  TRIMMER CALLBACKS
    # ==================================================================


    def toggle_trim(self, *_args):
        """Enable or disable trimming controls."""
        enabled = self.trim_enabled_check.isChecked()
        if enabled:
            self.fetch_duration_btn.setEnabled(True)
            if self.video_duration > 0:
                self.start_slider.setEnabled(True)
                self.end_slider.setEnabled(True)
                self.start_time_entry.setEnabled(True)
                self.end_time_entry.setEnabled(True)
        else:
            self.fetch_duration_btn.setEnabled(False)
            self.start_slider.setEnabled(False)
            self.end_slider.setEnabled(False)
            self.start_time_entry.setEnabled(False)
            self.end_time_entry.setEnabled(False)

        self._update_trimmed_filesize()


    def fetch_duration_clicked(self):
        """Handler for fetch duration button."""
        url = self.url_entry.text().strip()
        if not url:
            QMessageBox.critical(
                self, 'Error',
                'Please enter a YouTube URL or select a local file')
            return

        if self.is_local_file(url):
            if not os.path.isfile(url):
                QMessageBox.critical(self, 'Error',
                                     f'File not found:\n{url}')
                return
            self.local_file_path = url
        else:
            is_valid, message = self.validate_youtube_url(url)
            if not is_valid:
                QMessageBox.critical(self, 'Invalid URL', message)
                logger.warning(f"Invalid URL rejected: {url}")
                return
            self.local_file_path = None

            if self.is_playlist_url(url):
                if self.is_pure_playlist_url(url):
                    self.is_playlist = True
                    self.trim_enabled_check.setChecked(False)
                    self.toggle_trim()
                    self.video_info_label.setText(
                        'Playlist detected - Trimming and upload disabled for playlists')
                    self.video_info_label.setStyleSheet("color: orange;")
                    self.filesize_label.setText("")
                    logger.info("Playlist URL detected - trimming disabled")
                    return
                else:
                    url = self.strip_playlist_params(url)
                    self.url_entry.clear()
                    self.url_entry.setText(url)
                    self.is_playlist = False
                    self.video_info_label.setText(
                        'Playlist parameters removed - downloading single video')
                    self.video_info_label.setStyleSheet("color: green;")
                    logger.info(
                        f"Stripped playlist params from video URL: {url}")
            else:
                self.is_playlist = False

        with self.fetch_lock:
            is_fetching = self.is_fetching_duration
        if is_fetching or self.is_downloading:
            return

        if self.current_video_url != url:
            self.current_video_url = url
            self._clear_preview_cache()
        else:
            self.current_video_url = url

        with self.fetch_lock:
            self.is_fetching_duration = True
        self.fetch_duration_btn.setEnabled(False)
        self.update_status('Fetching video duration...', "blue")

        self.thread_pool.submit(self.fetch_video_duration, url)


    def fetch_video_duration(self, url):
        """Fetch video duration and info from URL or local file
        (runs in worker thread)."""
        try:
            if self.is_local_file(url):
                return self._fetch_local_file_duration(url)

            def _fetch_duration():
                cmd = [self.ytdlp_path, '--get-duration', url]
                return subprocess.run(
                    cmd, capture_output=True, encoding='utf-8',
                    errors='replace', timeout=METADATA_FETCH_TIMEOUT,
                    **_subprocess_kwargs)

            result = self.retry_network_operation(
                _fetch_duration, "Fetch duration")

            def _fetch_title():
                cmd = [self.ytdlp_path, '--get-title', url]
                return subprocess.run(
                    cmd, capture_output=True, encoding='utf-8',
                    errors='replace', timeout=METADATA_FETCH_TIMEOUT,
                    **_subprocess_kwargs)

            title_result = self.retry_network_operation(
                _fetch_title, "Fetch title")

            if result.returncode == 0:
                duration_str = result.stdout.strip()
                parts = duration_str.split(':')
                try:
                    if len(parts) == 1:
                        duration = int(parts[0])
                    elif len(parts) == 2:
                        mins, secs = int(parts[0]), int(parts[1])
                        if mins < 0 or secs < 0 or secs >= 60:
                            raise ValueError(
                                f"Invalid time values in duration: {duration_str}")
                        duration = mins * 60 + secs
                    elif len(parts) == 3:
                        hours, mins, secs = (
                            int(parts[0]), int(parts[1]), int(parts[2]))
                        if (hours < 0 or mins < 0 or secs < 0
                                or mins >= 60 or secs >= 60):
                            raise ValueError(
                                f"Invalid time values in duration: {duration_str}")
                        duration = hours * 3600 + mins * 60 + secs
                    else:
                        raise ValueError(
                            f"Invalid duration format: {duration_str}")

                    MAX_DURATION = 24 * 3600
                    if duration < 0:
                        raise ValueError(f"Negative duration: {duration}")
                    if duration > MAX_DURATION:
                        logger.warning(
                            f"Duration {duration}s exceeds max, "
                            f"capping to {MAX_DURATION}s")
                        duration = MAX_DURATION

                    self.video_duration = duration
                except (ValueError, OverflowError) as e:
                    raise ValueError(
                        f"Invalid duration format: {duration_str} ({e})")

                video_title = None
                if title_result and title_result.returncode == 0:
                    video_title = title_result.stdout.strip()
                    self.video_title = video_title
                    logger.info(f"Video title: {video_title}")

                self._safe_after(
                    0, lambda: self._update_duration_ui(video_title))

                self._fetch_file_size(url)

                self.update_status('Duration fetched successfully', "green")
                logger.info(
                    f"Successfully fetched video duration: "
                    f"{self.video_duration}s")
            else:
                raise Exception(
                    f"yt-dlp returned error: {result.stderr}")

        except subprocess.TimeoutExpired:
            error_msg = ('Request timed out. '
                         'Please check your internet connection.')
            self.sig_show_messagebox.emit('error', 'Error', error_msg)
            self.update_status('Duration fetch timed out', "red")
            logger.error("Timeout fetching video duration")
        except ValueError as e:
            error_msg = f'Invalid duration format received: {e}'
            self.sig_show_messagebox.emit('error', 'Error', error_msg)
            self.update_status('Invalid duration format', "red")
            logger.error(f"Duration parsing error: {e}")
        except Exception as e:
            err_msg = f'Failed to fetch video duration:\n{e}'
            self.sig_show_messagebox.emit('error', 'Error', err_msg)
            self.update_status('Failed to fetch duration', "red")
            logger.exception(f"Unexpected error fetching duration: {e}")
        finally:
            with self.fetch_lock:
                self.is_fetching_duration = False
            self._safe_after(0, lambda: (
                self.fetch_duration_btn.setEnabled(True)
                if self.trim_enabled_check.isChecked() else None))


    def _update_duration_ui(self, video_title=None):
        """Update duration-related UI elements on the main thread."""
        self.start_slider.setRange(0, self.video_duration)
        self.start_slider.setEnabled(True)
        self.end_slider.setRange(0, self.video_duration)
        self.end_slider.setEnabled(True)

        self.start_slider.blockSignals(True)
        self.start_slider.setValue(0)
        self.start_slider.blockSignals(False)

        self.end_slider.blockSignals(True)
        self.end_slider.setValue(self.video_duration)
        self.end_slider.blockSignals(False)

        self.start_time_entry.setEnabled(True)
        self.end_time_entry.setEnabled(True)
        self.start_time_entry.setText(self.seconds_to_hms(0))
        self.end_time_entry.setText(
            self.seconds_to_hms(self.video_duration))

        self.trim_duration_label.setText(
            f'Selected Duration: {self.seconds_to_hms(self.video_duration)}')

        if video_title:
            self.video_info_label.setText(f'Title: {video_title}')
            self.video_info_label.setStyleSheet("color: green;")

        QTimer.singleShot(UI_INITIAL_DELAY_MS, self.update_previews)


    def _update_duration_ui_local(self, video_title):
        """Update duration-related UI for local files on the main thread."""
        self._update_duration_ui()
        if video_title:
            self.video_info_label.setText(f'File: {video_title}')
            self.video_info_label.setStyleSheet("color: green;")


    def _fetch_file_size(self, url):
        """Fetch estimated file size for the video (runs in background thread)."""
        # Capture quality on GUI thread before submitting to worker
        _quality = self.quality_combo.currentText()

        def _fetch():
            try:
                quality = _quality

                if (quality.startswith("none")
                        or quality == "none (Audio only)"):
                    format_selector = "bestaudio"
                else:
                    format_selector = (
                        f'bestvideo[height<={quality}]+bestaudio/'
                        f'best[height<={quality}]')

                cmd = [self.ytdlp_path, '--dump-json', '-f',
                       format_selector, url]
                result = subprocess.run(
                    cmd, capture_output=True, encoding='utf-8',
                    errors='replace', timeout=STREAM_FETCH_TIMEOUT,
                    **_subprocess_kwargs)

                if result.returncode == 0:
                    info = json.loads(result.stdout)
                    filesize = (info.get('filesize')
                                or info.get('filesize_approx'))

                    if filesize:
                        filesize_mb = filesize / BYTES_PER_MB
                        self._safe_after(
                            0, lambda: self._update_filesize_display(
                                filesize, filesize_mb))
                    else:
                        self._safe_after(
                            0, lambda: self._update_filesize_display(
                                None, None))
                else:
                    self._safe_after(
                        0, lambda: self._update_filesize_display(None, None))
            except Exception as e:
                logger.debug(f"Could not fetch file size: {e}")
                self._safe_after(
                    0, lambda: self._update_filesize_display(None, None))

        self.thread_pool.submit(_fetch)


    def _update_filesize_display(self, filesize_bytes, filesize_mb):
        """Update file size display on main thread."""
        if filesize_bytes and filesize_mb:
            self.filesize_label.setText(
                f'Estimated size: {filesize_mb:.1f} MB')
            self.estimated_filesize = filesize_bytes
        elif filesize_mb is None and filesize_bytes is None:
            self.filesize_label.setText('Estimated size: Unknown')
            self.estimated_filesize = None

        self._update_trimmed_filesize()


    def _on_keep_below_10mb_toggle(self, *_args):
        """Enable/disable quality dropdown based on 10MB checkbox state."""
        if self.keep_below_10mb_check.isChecked():
            self.quality_combo.setEnabled(False)
        else:
            self.quality_combo.setEnabled(True)


    def on_quality_change(self, *_args):
        """Handle quality selection changes — re-fetch file size with new
        quality."""
        quality = self.quality_combo.currentText()
        if quality.startswith("none") or "none (Audio only)" in quality:
            self.keep_below_10mb_check.setChecked(False)
            self.keep_below_10mb_check.setEnabled(False)
            self.quality_combo.setEnabled(True)
        else:
            self.keep_below_10mb_check.setEnabled(True)

        url = self.current_video_url or self.url_entry.text().strip()
        if url and not self.is_playlist:
            is_valid, _ = self.validate_youtube_url(url)
            if is_valid:
                self.filesize_label.setText('Calculating size...')
                self._fetch_file_size(url)


    def _update_trimmed_filesize(self):
        """Update file size estimate based on trim selection using linear
        calculation."""
        if (not self.estimated_filesize
                or not self.trim_enabled_check.isChecked()):
            if self.estimated_filesize:
                filesize_mb = self.estimated_filesize / BYTES_PER_MB
                self.filesize_label.setText(
                    f'Estimated size: {filesize_mb:.1f} MB')
            return

        start_time = self.start_slider.value()
        end_time = self.end_slider.value()
        selected_duration = end_time - start_time

        if self.video_duration > 0:
            duration_percentage = selected_duration / self.video_duration
            trimmed_size = self.estimated_filesize * duration_percentage
            trimmed_size_mb = trimmed_size / BYTES_PER_MB
            self.filesize_label.setText(
                f'Estimated size (trimmed): {trimmed_size_mb:.1f} MB '
                f'— with re-encoding/trimming file will be larger')


    def _fetch_local_file_duration(self, filepath):
        """Fetch duration from local file using ffprobe (runs in worker
        thread)."""
        try:
            cmd = [
                self.ffprobe_path,
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                filepath
            ]

            result = subprocess.run(
                cmd, capture_output=True, encoding='utf-8',
                errors='replace', timeout=FFPROBE_TIMEOUT,
                check=True, **_subprocess_kwargs)
            duration_seconds = float(result.stdout.strip())
            self.video_duration = int(duration_seconds)

            video_title = Path(filepath).stem

            self._safe_after(
                0, lambda vt=video_title: self._update_duration_ui_local(vt))
            self.update_status('Duration fetched successfully', "green")
            logger.info(f"Local file duration: {self.video_duration}s")

        except subprocess.CalledProcessError as e:
            error_msg = (
                f'Failed to read video file:\n'
                f'{e.stderr if e.stderr else str(e)}')
            self.sig_show_messagebox.emit('error', 'Error', error_msg)
            self.update_status('Failed to read file', "red")
            logger.error(f"ffprobe error: {e}")
        except ValueError as e:
            self.sig_show_messagebox.emit(
                'error', 'Error', 'Invalid video file format')
            self.update_status('Invalid video file format', "red")
            logger.error(f"Duration parsing error: {e}")
        except Exception as e:
            err_msg = f'Failed to read file:\n{e}'
            self.sig_show_messagebox.emit('error', 'Error', err_msg)
            self.update_status('Failed to read file', "red")
            logger.exception(f"Unexpected error reading local file: {e}")
        finally:
            with self.fetch_lock:
                self.is_fetching_duration = False
            self._safe_after(0, lambda: (
                self.fetch_duration_btn.setEnabled(True)
                if self.trim_enabled_check.isChecked() else None))


    def on_slider_change(self, *_args):
        """Handle slider changes and enforce valid time ranges.

        Reads current slider positions, updates time entry fields,
        recalculates duration label and file size estimate, and
        schedules a debounced preview update.
        """
        start_time = self.start_slider.value()
        end_time = self.end_slider.value()

        # Ensure start < end
        if start_time >= end_time:
            end_time = min(start_time + 1, self.video_duration)
            self.end_slider.blockSignals(True)
            self.end_slider.setValue(end_time)
            self.end_slider.blockSignals(False)

        # Update entry fields
        self.start_time_entry.setText(self.seconds_to_hms(start_time))
        self.end_time_entry.setText(self.seconds_to_hms(end_time))

        # Update selected duration
        selected_duration = end_time - start_time
        self.trim_duration_label.setText(
            f'Selected Duration: {self.seconds_to_hms(selected_duration)}')

        self._update_trimmed_filesize()
        self.schedule_preview_update()


    def on_start_slider_change(self, value):
        """Handle start slider value changed."""
        end_val = self.end_slider.value()
        if value >= end_val:
            self.end_slider.blockSignals(True)
            self.end_slider.setValue(min(value + 1, self.video_duration))
            self.end_slider.blockSignals(False)
        self.on_slider_change()


    def on_end_slider_change(self, value):
        """Handle end slider value changed."""
        start_val = self.start_slider.value()
        if value <= start_val:
            self.start_slider.blockSignals(True)
            self.start_slider.setValue(max(value - 1, 0))
            self.start_slider.blockSignals(False)
        self.on_slider_change()


    def hms_to_seconds(self, hms_str):
        """Convert HH:MM:SS format to seconds."""
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


    def on_start_entry_change(self, *_args):
        """Handle changes to start time entry field."""
        value_str = self.start_time_entry.text()
        seconds = self.hms_to_seconds(value_str)

        if seconds is not None and 0 <= seconds <= self.video_duration:
            self.start_slider.blockSignals(True)
            self.start_slider.setValue(seconds)
            self.start_slider.blockSignals(False)
            self.on_slider_change()
        else:
            current_time = self.start_slider.value()
            self.start_time_entry.setText(self.seconds_to_hms(current_time))


    def on_end_entry_change(self, *_args):
        """Handle changes to end time entry field."""
        value_str = self.end_time_entry.text()
        seconds = self.hms_to_seconds(value_str)

        if seconds is not None and 0 <= seconds <= self.video_duration:
            self.end_slider.blockSignals(True)
            self.end_slider.setValue(seconds)
            self.end_slider.blockSignals(False)
            self.on_slider_change()
        else:
            current_time = self.end_slider.value()
            self.end_time_entry.setText(self.seconds_to_hms(current_time))


    def on_volume_change(self, *_args):
        """Handle volume slider changes."""
        volume_percent = self.volume_slider.value()
        self.volume_entry.setText(str(volume_percent))


    def on_volume_entry_change(self, *_args):
        """Handle volume entry field changes."""
        try:
            volume_percent = int(self.volume_entry.text())
            volume_percent = max(0, min(200, volume_percent))
            self.volume_slider.blockSignals(True)
            self.volume_slider.setValue(volume_percent)
            self.volume_slider.blockSignals(False)
            self.volume_entry.setText(str(volume_percent))
        except ValueError:
            volume_percent = self.volume_slider.value()
            self.volume_entry.setText(str(volume_percent))


    def reset_volume(self):
        """Reset volume to 100%."""
        self._volume_int = 100
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(100)
        self.volume_slider.blockSignals(False)
        self.volume_entry.setText("100")


    def create_placeholder_image(self, width, height, text):
        """Create a placeholder QPixmap with text (replaces tkinter
        ImageTk.PhotoImage version)."""
        pix = QPixmap(width, height)
        pix.fill(QColor("#2d2d2d"))
        painter = QPainter(pix)
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Arial", 10))
        painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
        return pix


    def start_upload(self):
        """Start upload to Catbox.moe in a background thread."""
        if not self.last_output_file or not os.path.isfile(self.last_output_file):
            QMessageBox.critical(
                self, 'Error',
                'No file available to upload. '
                'Please download/process a video first.')
            return

        file_size_mb = os.path.getsize(self.last_output_file) / BYTES_PER_MB
        if file_size_mb > CATBOX_MAX_SIZE_MB:
            QMessageBox.critical(
                self, 'File Too Large',
                f"File size ({file_size_mb:.1f} MB) exceeds "
                f"Catbox.moe's 200MB limit.\n"
                f"Please trim the video or use a lower quality setting.")
            return

        self.upload_btn.setEnabled(False)
        self.upload_status_label.setText('Uploading...')
        self.upload_status_label.setStyleSheet("color: blue; font-size: 9pt;")
        self.upload_url_widget.setVisible(False)

        self.thread_pool.submit(self.upload_to_catbox)


    def upload_to_catbox(self):
        """Upload file to Catbox.moe and display the URL (runs in worker
        thread)."""
        try:
            with self.upload_lock:
                self.is_uploading = True
            logger.info(
                f"Starting upload to Catbox.moe: {self.last_output_file}")

            file_url = self.catbox_client.upload(self.last_output_file)

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
        """Handle successful upload (called on main thread)."""
        self.upload_status_label.setText('Upload complete!')
        self.upload_status_label.setStyleSheet(
            "color: green; font-size: 9pt;")

        self.upload_url_entry.setReadOnly(False)
        self.upload_url_entry.setText(file_url)
        self.upload_url_entry.setReadOnly(True)
        self.upload_url_widget.setVisible(True)

        self.upload_btn.setEnabled(True)

        # Save upload link to history
        filename = (os.path.basename(self.last_output_file)
                    if self.last_output_file else "unknown")
        self.save_upload_link(file_url, filename)

        QMessageBox.information(
            self, 'Upload Complete',
            f'File uploaded successfully!\n\nURL: {file_url}\n\n'
            f'The URL has been copied to your clipboard.')

        # Auto-copy to clipboard
        try:
            QApplication.clipboard().setText(file_url)
        except Exception:
            logger.warning("Failed to copy URL to clipboard")


    def _upload_failed(self, error_msg):
        """Handle failed upload (called on main thread)."""
        self.upload_status_label.setText('Upload failed')
        self.upload_status_label.setStyleSheet(
            "color: red; font-size: 9pt;")
        self.upload_btn.setEnabled(True)
        QMessageBox.critical(
            self, 'Upload Failed',
            f'Failed to upload file:\n\n{error_msg}')


    def copy_upload_url(self):
        """Copy upload URL to clipboard."""
        url = self.upload_url_entry.text()
        if url:
            QApplication.clipboard().setText(url)
            self.upload_status_label.setText('URL copied to clipboard!')
            self.upload_status_label.setStyleSheet(
                "color: green; font-size: 9pt;")
            logger.info("Upload URL copied to clipboard")

    # ==================================================================
    #  UPLOAD CALLBACKS (Uploader tab)
    # ==================================================================


    def browse_uploader_files(self):
        """Browse and select multiple files for upload in Uploader tab."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, 'Select Video Files', '',
            'Video files (*.mp4 *.avi *.mkv *.mov *.flv *.wmv *.webm *.m4v);;'
            'Audio files (*.mp3 *.m4a *.wav *.flac *.aac *.ogg);;'
            'All files (*.*)')

        if file_paths:
            for file_path in file_paths:
                file_size_mb = os.path.getsize(file_path) / BYTES_PER_MB
                if file_size_mb > CATBOX_MAX_SIZE_MB:
                    QMessageBox.warning(
                        self, 'File Too Large',
                        f'Skipped: {os.path.basename(file_path)}\n'
                        f'File size ({file_size_mb:.1f} MB) exceeds '
                        f'200MB limit.')
                    continue

                with self.uploader_lock:
                    already_in_queue = any(
                        item['path'] == file_path
                        for item in self.uploader_file_queue)
                if not already_in_queue:
                    self._add_file_to_uploader_queue(file_path)
                    logger.info(
                        f"Added file to upload queue: {file_path}")


    def _add_file_to_uploader_queue(self, file_path):
        """Add a file to the upload queue with UI widget."""
        file_frame = QWidget()
        file_frame.setStyleSheet(
            "border: 1px solid #555; border-radius: 2px; padding: 2px;")
        row_layout = QHBoxLayout(file_frame)
        row_layout.setContentsMargins(5, 2, 5, 2)
        row_layout.setSpacing(5)

        filename = os.path.basename(file_path)
        file_size_mb = os.path.getsize(file_path) / BYTES_PER_MB

        file_label = QLabel(f'{filename} ({file_size_mb:.1f} MB)')
        file_label.setStyleSheet(file_label.styleSheet() + "font-size: 9px;")
        file_label.setStyleSheet("border: none;")
        row_layout.addWidget(file_label, stretch=1)

        remove_btn = QPushButton("X")
        remove_btn.setFixedWidth(30)
        remove_btn.setStyleSheet("border: none;")
        remove_btn.clicked.connect(
            lambda checked, fp=file_path: self._remove_file_from_queue(fp))
        row_layout.addWidget(remove_btn)

        self.uploader_file_list_layout.addWidget(file_frame)

        with self.uploader_lock:
            self.uploader_file_queue.append(
                {'path': file_path, 'widget': file_frame})
        self._update_uploader_queue_count()

        with self.uploader_lock:
            is_uploading = self.uploader_is_uploading
            queue_len = len(self.uploader_file_queue)
        if queue_len > 0 and not is_uploading:
            self.uploader_upload_btn.setEnabled(True)


    def _remove_file_from_queue(self, file_path):
        """Remove a file from the upload queue."""
        widget_to_destroy = None
        with self.uploader_lock:
            for i, item in enumerate(self.uploader_file_queue):
                if item['path'] == file_path:
                    widget_to_destroy = item.get('widget')
                    self.uploader_file_queue.pop(i)
                    logger.info(f"Removed file from queue: {file_path}")
                    break
        if widget_to_destroy:
            widget_to_destroy.deleteLater()
        self._update_uploader_queue_count()
        with self.uploader_lock:
            if len(self.uploader_file_queue) == 0:
                self.uploader_upload_btn.setEnabled(False)


    def clear_uploader_queue(self):
        """Clear all files from upload queue."""
        with self.uploader_lock:
            is_uploading = self.uploader_is_uploading
        if is_uploading:
            QMessageBox.warning(
                self, 'Cannot Clear',
                'Cannot clear queue while uploads are in progress.')
            return

        widgets_to_destroy = []
        with self.uploader_lock:
            for item in self.uploader_file_queue:
                if item.get('widget'):
                    widgets_to_destroy.append(item['widget'])
            self.uploader_file_queue.clear()
        for widget in widgets_to_destroy:
            widget.deleteLater()
        self._update_uploader_queue_count()
        self.uploader_upload_btn.setEnabled(False)
        logger.info("Cleared all files from upload queue")


    def _update_uploader_queue_count(self):
        """Update file queue count label."""
        with self.uploader_lock:
            count = len(self.uploader_file_queue)
        s = 's' if count != 1 else ''
        self.uploader_queue_count_label.setText(f'({count} file{s})')


    def start_uploader_upload(self):
        """Start uploading all files in queue sequentially."""
        with self.uploader_lock:
            queue_empty = len(self.uploader_file_queue) == 0
        if queue_empty:
            QMessageBox.information(
                self, 'No Files',
                'No files in queue. Please add files first.')
            return

        with self.uploader_lock:
            is_uploading = self.uploader_is_uploading
        if is_uploading:
            return

        with self.uploader_lock:
            self.uploader_is_uploading = True
        self.uploader_current_index = 0
        self.uploader_upload_btn.setEnabled(False)
        self.uploader_url_widget.setVisible(False)

        self.thread_pool.submit(self._process_uploader_queue)


    def _process_uploader_queue(self):
        """Process upload queue sequentially (runs in worker thread)."""
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

            self._safe_after(
                0,
                lambda i=index, t=total_count, fn=filename: (
                    self.uploader_status_label.setText(
                        f'Uploading {i+1}/{t}: {fn}...'),
                    self.uploader_status_label.setStyleSheet(
                        "color: blue; font-size: 9pt;")))

            success = self._upload_single_file(file_path)

            if not success:
                continue

        self._safe_after(0, self._finish_uploader_queue)


    def _upload_single_file(self, file_path):
        """Upload a single file from the queue. Returns True if successful."""
        try:
            logger.info(f"Uploading file from queue: {file_path}")

            file_url = self.catbox_client.upload(file_path)

            filename = os.path.basename(file_path)
            self.save_upload_link(file_url, filename)

            self._safe_after(
                0, lambda url=file_url: self._show_upload_url(url))

            logger.info(f"Upload successful: {file_url}")
            return True

        except Exception as e:
            logger.exception(f"Upload failed for {file_path}: {e}")
            error_msg = str(e)
            filename = os.path.basename(file_path)
            full_error = f"Failed to upload {filename}:\n\n{error_msg}"
            self.sig_show_messagebox.emit('error', 'Upload Failed', full_error)
            return False


    def _show_upload_url(self, file_url):
        """Display the most recent upload URL."""
        self.uploader_url_entry.setReadOnly(False)
        self.uploader_url_entry.setText(file_url)
        self.uploader_url_entry.setReadOnly(True)
        self.uploader_url_widget.setVisible(True)

        try:
            QApplication.clipboard().setText(file_url)
        except Exception:
            logger.warning("Failed to copy URL to clipboard")


    def _finish_uploader_queue(self):
        """Clean up after queue upload completes."""
        widgets_to_destroy = []
        with self.uploader_lock:
            self.uploader_is_uploading = False
            for item in self.uploader_file_queue:
                if item.get('widget'):
                    widgets_to_destroy.append(item['widget'])
            count = len(self.uploader_file_queue)
            self.uploader_file_queue.clear()
        for widget in widgets_to_destroy:
            widget.deleteLater()
        self._update_uploader_queue_count()

        self.uploader_status_label.setText(
            f'All uploads complete! ({count} files)')
        self.uploader_status_label.setStyleSheet(
            "color: green; font-size: 9pt;")
        self.uploader_upload_btn.setEnabled(False)

        logger.info(f"Uploader queue finished: {count} files uploaded")


    def copy_uploader_url(self):
        """Copy upload URL to clipboard from Uploader tab."""
        url = self.uploader_url_entry.text()
        if url:
            QApplication.clipboard().setText(url)
            self.uploader_status_label.setText('URL copied to clipboard!')
            self.uploader_status_label.setStyleSheet(
                "color: green; font-size: 9pt;")
            logger.info("Upload URL copied to clipboard from Uploader tab")


    def _enable_upload_button(self, filepath):
        """Enable upload button after successful download (thread-safe)."""
        if filepath and os.path.isfile(filepath):
            self.last_output_file = filepath
            self._safe_after(0, lambda: self._do_enable_upload(filepath))


    def _do_enable_upload(self, filepath):
        """Actual upload button enable on main thread."""
        self.upload_btn.setEnabled(True)
        logger.info(f"Upload enabled for: {filepath}")

        if self.auto_upload_check.isChecked():
            url = self.url_entry.text().strip()
            if url and self.is_playlist_url(url):
                logger.info("Auto-upload skipped for playlist URL")
            else:
                logger.info("Auto-upload enabled, starting upload...")
                QTimer.singleShot(AUTO_UPLOAD_DELAY_MS, self.start_upload)

    # ==================================================================
    #  PREVIEW CALLBACKS
    # ==================================================================


    def schedule_preview_update(self):
        """Schedule preview update with debouncing to avoid excessive calls."""
        if self._shutting_down:
            return

        # Cancel any pending update
        if hasattr(self, '_preview_debounce_timer'):
            self._preview_debounce_timer.stop()
            self._preview_debounce_timer.timeout.disconnect()

        self._preview_debounce_timer.timeout.connect(self.update_previews)
        self._preview_debounce_timer.start()


    def update_previews(self):
        """Update both preview images."""
        if self._shutting_down:
            return

        if not self.current_video_url or self.video_duration == 0:
            return

        with self.preview_lock:
            if self.preview_thread_running:
                return
            self.preview_thread_running = True

        start_time = self.start_slider.value()
        end_time = self.end_slider.value()

        # Show loading indicators
        loading_pix = self.create_placeholder_image(
            PREVIEW_WIDTH, PREVIEW_HEIGHT, 'Loading...')
        self.start_preview_label.setPixmap(loading_pix)
        self.end_preview_label.setPixmap(loading_pix)

        try:
            self.thread_pool.submit(
                self._update_previews_thread, start_time, end_time)
        except RuntimeError:
            with self.preview_lock:
                self.preview_thread_running = False


    def _update_previews_thread(self, start_time, end_time):
        """Background thread to extract and update preview frames."""
        try:
            adjusted_end_time = end_time
            if (self.video_duration > 0
                    and end_time >= self.video_duration - 1):
                adjusted_end_time = max(0, self.video_duration - 3)
                logger.debug(
                    f"Adjusted end preview time from {end_time}s to "
                    f"{adjusted_end_time}s (near EOF)")

            logger.info(
                f"Extracting preview frames at {start_time}s and "
                f"{adjusted_end_time}s")

            # Extract start frame
            start_frame_path = self.extract_frame(start_time)
            if start_frame_path:
                self._update_preview_image(start_frame_path, 'start')
            else:
                error_pix = self.create_placeholder_image(
                    PREVIEW_WIDTH, PREVIEW_HEIGHT, 'Error')
                self.start_preview_image = error_pix
                self._safe_after(
                    0, lambda pix=error_pix: self._set_start_preview(pix))

            # Extract end frame
            end_frame_path = self.extract_frame(adjusted_end_time)
            if end_frame_path:
                self._update_preview_image(end_frame_path, 'end')
            else:
                error_pix = self.create_placeholder_image(
                    PREVIEW_WIDTH, PREVIEW_HEIGHT, 'Error')
                self.end_preview_image = error_pix
                self._safe_after(
                    0, lambda pix=error_pix: self._set_end_preview(pix))
        finally:
            with self.preview_lock:
                self.preview_thread_running = False


    def _update_preview_image(self, image_path, position):
        """Update preview image in UI."""
        try:
            with Image.open(image_path) as img:
                img.thumbnail(
                    (PREVIEW_WIDTH, PREVIEW_HEIGHT),
                    Image.Resampling.LANCZOS)
                img = img.convert("RGBA")
                data = img.tobytes("raw", "RGBA")
                qimg = QImage(
                    data, img.width, img.height,
                    QImage.Format.Format_RGBA8888)
                pixmap = QPixmap.fromImage(qimg)

            if position == 'start':
                self.start_preview_image = pixmap
                self._safe_after(
                    0, lambda p=pixmap: self._set_start_preview(p))
            else:
                self.end_preview_image = pixmap
                self._safe_after(
                    0, lambda p=pixmap: self._set_end_preview(p))

        except Exception as e:
            logger.error(
                f"Error updating preview image for {position}: {e}")


    def _set_start_preview(self, pixmap):
        """Set start preview image (called on main thread)."""
        self.start_preview_image = pixmap
        self.start_preview_label.setPixmap(pixmap)
        self.start_preview_label.setText('')


    def _set_end_preview(self, pixmap):
        """Set end preview image (called on main thread)."""
        self.end_preview_image = pixmap
        self.end_preview_label.setPixmap(pixmap)
        self.end_preview_label.setText('')


    def _clear_preview_cache(self):
        """Clear the preview frame cache, deleting cached files from disk."""
        logger.info("Clearing preview cache")
        for timestamp, file_path in self.preview_cache.items():
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except OSError as e:
                logger.debug(
                    f"Failed to delete cached preview file {file_path}: {e}")
        self.preview_cache.clear()


    def _cache_preview_frame(self, timestamp, file_path):
        """Add a frame to the cache with LRU eviction."""
        if timestamp in self.preview_cache:
            del self.preview_cache[timestamp]

        if len(self.preview_cache) >= PREVIEW_CACHE_SIZE:
            oldest_key, old_path = self.preview_cache.popitem(last=False)
            try:
                if os.path.exists(old_path):
                    os.remove(old_path)
            except OSError:
                pass

        self.preview_cache[timestamp] = file_path


    def _get_cached_frame(self, timestamp):
        """Get a cached frame if available."""
        if timestamp in self.preview_cache:
            self.preview_cache.move_to_end(timestamp)
            return self.preview_cache[timestamp]
        return None

    # ==================================================================
    #  URL / PATH CALLBACKS
    # ==================================================================


    def on_url_change(self, *_args):
        """Detect if input is URL or file path."""
        input_text = self.url_entry.text().strip()

        if not input_text:
            self.mode_label.setText("")
            self.local_file_path = None
            return

        # Clear filename field when URL/file changes
        self.filename_entry.clear()

        if self.is_local_file(input_text):
            self.local_file_path = input_text
            self.mode_label.setText(
                f'Mode: Local File | {Path(input_text).name}')
            self.mode_label.setStyleSheet("color: green; font-size: 9pt;")
        else:
            self.local_file_path = None
            self.mode_label.setText('Mode: YouTube Download')
            self.mode_label.setStyleSheet("color: green; font-size: 9pt;")

            # Auto-fetch file size estimate for valid YouTube URLs (debounced)
            is_valid, _ = self.validate_youtube_url(input_text)
            if is_valid:
                if (hasattr(self, '_size_fetch_timer')
                        and self._size_fetch_timer is not None):
                    self._size_fetch_timer.stop()
                self._size_fetch_timer = QTimer(self)
                self._size_fetch_timer.setSingleShot(True)
                self._size_fetch_timer.setInterval(1000)
                self._size_fetch_timer.timeout.connect(
                    lambda: self._fetch_file_size(input_text))
                self._size_fetch_timer.start()


    def is_local_file(self, input_text):
        """Check if input is a local file path."""
        if os.path.isfile(input_text):
            return True

        path = Path(input_text)
        video_extensions = {
            '.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm',
            '.wmv', '.m4v', '.ts', '.mpg', '.mpeg',
        }
        if path.suffix.lower() in video_extensions:
            return True

        return False


    def change_path(self):
        """Change download path with validation."""
        path = QFileDialog.getExistingDirectory(
            self, 'Select Download Folder', self.download_path)
        if path:
            is_valid, normalized_path, error_msg = (
                self.validate_download_path(path))
            if not is_valid:
                QMessageBox.critical(self, 'Error', error_msg)
                return
            path = normalized_path

            if not os.path.exists(path):
                QMessageBox.critical(
                    self, 'Error', f'Path does not exist: {path}')
                return

            if not os.path.isdir(path):
                QMessageBox.critical(
                    self, 'Error', f'Path is not a directory: {path}')
                return

            test_file = os.path.join(path, ".ytdl_write_test")
            try:
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
            except (IOError, OSError) as e:
                QMessageBox.critical(
                    self, 'Error',
                    f'Path is not writable:\n{path}\n\n{e}')
                return

            self.download_path = path
            self.path_label.setText(path)


    def open_download_folder(self):
        """Open the download folder in the system file manager."""
        try:
            if sys.platform == 'win32':
                os.startfile(self.download_path)
            elif sys.platform == 'darwin':
                subprocess.Popen(
                    ['open', self.download_path],
                    close_fds=True, start_new_session=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(
                    ['xdg-open', self.download_path],
                    close_fds=True, start_new_session=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            QMessageBox.critical(
                self, 'Error', f'Failed to open folder:\n{e}')


    def browse_local_file(self):
        """Open file dialog to select a local video file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, 'Select a video file', str(Path.home()),
            'Video files (*.mp4 *.mkv *.avi *.mov *.flv *.webm *.wmv *.m4v);;'
            'All files (*.*)')

        if filepath:
            self.url_entry.clear()
            self.url_entry.setText(filepath)
            self.local_file_path = filepath
            self.mode_label.setText(
                f'Mode: Local File | {Path(filepath).name}')
            self.mode_label.setStyleSheet("color: green; font-size: 9pt;")
            # Clear filename field for new file
            self.filename_entry.clear()
            logger.info(f"Local file selected: {filepath}")

    # ==================================================================
    #  Speed limit helper (ported for QLineEdit instead of StringVar)
    # ==================================================================


    def _get_speed_limit_args(self, speed_limit_entry=None, speed_limit_str=None):
        """Get yt-dlp speed limit arguments if speed limit is set.

        Args:
            speed_limit_entry: Optional QLineEdit to use (GUI thread only).
                Defaults to self.speed_limit_entry.
            speed_limit_str: Pre-captured speed limit string (thread-safe).
                If provided, speed_limit_entry is ignored.
        """
        if speed_limit_str is None:
            if speed_limit_entry is None:
                speed_limit_entry = self.speed_limit_entry
            speed_limit_str = speed_limit_entry.text().strip()
        if speed_limit_str:
            try:
                speed_limit = float(speed_limit_str)
                if speed_limit > 0:
                    rate_bytes = int(speed_limit * BYTES_PER_MB)
                    return ['--limit-rate', f'{rate_bytes}']
            except ValueError:
                pass
        return []


    # --- from _port_download.py ---

    def validate_youtube_url(self, url):
        """Validate if URL is a valid YouTube URL.

        Returns:
            tuple: (is_valid: bool, message: str)
        """
        if not url:
            return False, 'URL is empty'
        if len(url) > 2048:
            return False, 'URL is too long'

        try:
            parsed = urlparse(url)

            valid_domains = [
                'youtube.com', 'www.youtube.com', 'm.youtube.com',
                'youtu.be', 'www.youtu.be'
            ]

            if parsed.netloc not in valid_domains:
                return False, 'Not a YouTube URL. Please enter a valid YouTube link.'

            if 'youtu.be' in parsed.netloc:
                if not parsed.path or parsed.path == '/':
                    return False, 'Invalid YouTube short URL'
                return True, 'Valid YouTube URL'

            if 'youtube.com' in parsed.netloc:
                if '/watch' in parsed.path:
                    query_params = parse_qs(parsed.query)
                    if 'v' not in query_params:
                        return False, 'Missing video ID in URL'
                    return True, 'Valid YouTube URL'
                elif '/shorts/' in parsed.path:
                    return True, 'Valid YouTube Shorts URL'
                elif '/embed/' in parsed.path:
                    return True, 'Valid YouTube embed URL'
                elif '/v/' in parsed.path:
                    return True, 'Valid YouTube URL'
                elif '/playlist' in parsed.path or 'list=' in parsed.query:
                    return True, 'Valid YouTube Playlist URL'
                else:
                    return False, 'Unrecognized YouTube URL format'

            return False, 'Invalid URL format'

        except Exception as e:
            logger.error(f"URL validation error: {e}")
            return False, f"Invalid URL format: {str(e)}"


    def is_playlist_url(self, url):
        """Check if URL is a YouTube playlist."""
        try:
            parsed = urlparse(url)
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
            flat_params = {k: v[0] if len(v) == 1 else v for k, v in params.items()}
            new_query = urlencode(flat_params, doseq=True)
            return urlunparse((parsed.scheme, parsed.netloc, parsed.path,
                               parsed.params, new_query, parsed.fragment))
        except (ValueError, AttributeError):
            return url


    def sanitize_filename(filename):
        """Sanitize filename to prevent path traversal and command injection."""
        if not filename:
            return ""

        for char in ['/', '\\', '\x00']:
            filename = filename.replace(char, '')
        while '..' in filename:
            filename = filename.replace('..', '')

        shell_chars = ['$', '`', '|', ';', '&', '<', '>', '(', ')', '{', '}',
                       '[', ']', '!', '*', '?', '~', '^']
        for char in shell_chars:
            filename = filename.replace(char, '')

        filename = ''.join(c for c in filename if ord(c) >= 32 and ord(c) != 127)
        filename = filename.strip('. ')

        if len(filename) > MAX_FILENAME_LENGTH:
            filename = filename[:MAX_FILENAME_LENGTH]

        return filename


    def validate_download_path(path):
        """Validate download path to prevent path traversal attacks.

        Returns:
            tuple: (is_valid, normalized_path, error_message)
        """
        try:
            normalized = os.path.normpath(os.path.abspath(path))
            normalized_path = Path(normalized)

            if '..' in path or '..' in normalized:
                return (False, None, "Path contains directory traversal sequences")

            home_dir = Path.home()
            safe_dirs = [
                home_dir,
                Path('/tmp'),
                Path(os.path.expandvars('$TEMP')) if sys.platform == 'win32' else Path('/tmp'),
            ]

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


    def validate_config_json(config):
        """Validate configuration JSON structure.

        Returns:
            bool: True if config is valid, False otherwise
        """
        if not isinstance(config, dict):
            return False

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


    def validate_volume(volume):
        """Validate and clamp volume value to safe range."""
        try:
            vol = float(volume)
            return max(MIN_VOLUME, min(MAX_VOLUME, vol))
        except (ValueError, TypeError):
            return 1.0


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


    # ===================================================================
    #  Process / network utilities
    # ===================================================================

    def safe_process_cleanup(process, timeout=PROCESS_TERMINATE_TIMEOUT):
        """Safely terminate and cleanup a subprocess.

        Returns:
            bool: True if process was cleaned up successfully
        """
        if process is None:
            return True

        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    logger.warning(f"Process {process.pid} did not terminate, forcing kill")
                    process.kill()
                    process.wait()

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


    def retry_network_operation(self, operation, operation_name, *args, **kwargs):
        """Retry a network operation with exponential backoff."""
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                return operation(*args, **kwargs)
            except subprocess.TimeoutExpired:
                if attempt == MAX_RETRY_ATTEMPTS:
                    logger.error(f"{operation_name} failed after {MAX_RETRY_ATTEMPTS} attempts: timeout")
                    raise
                logger.warning(f"{operation_name} timeout (attempt {attempt}/{MAX_RETRY_ATTEMPTS}), retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY * attempt)
            except subprocess.CalledProcessError as e:
                if attempt == MAX_RETRY_ATTEMPTS:
                    logger.error(f"{operation_name} failed after {MAX_RETRY_ATTEMPTS} attempts: {e}")
                    raise
                logger.warning(f"{operation_name} failed (attempt {attempt}/{MAX_RETRY_ATTEMPTS}), retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY * attempt)
            except Exception as e:
                logger.error(f"{operation_name} failed with unexpected error: {e}")
                raise


    # ===================================================================
    #  Resource / dependency helpers
    # ===================================================================

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
                    return ['-c:v', 'h264_amf', '-quality', 'balanced',
                            '-rc', 'cqp', '-qp_i', '23', '-qp_p', '23']
                else:  # h264_nvenc
                    return ['-c:v', 'h264_nvenc', '-preset', 'p4',
                            '-rc', 'constqp', '-qp', '23']
            else:  # bitrate mode
                maxrate = int(target_bitrate * 1.5)
                bufsize = int(target_bitrate * 2)
                if self.hw_encoder == 'h264_amf':
                    return ['-c:v', 'h264_amf', '-quality', 'balanced',
                            '-b:v', str(target_bitrate), '-maxrate', str(maxrate),
                            '-bufsize', str(bufsize)]
                else:  # h264_nvenc
                    return ['-c:v', 'h264_nvenc', '-preset', 'p4',
                            '-b:v', str(target_bitrate), '-maxrate', str(maxrate),
                            '-bufsize', str(bufsize)]
        else:
            if mode == 'crf':
                return ['-c:v', 'libx264', '-crf', str(VIDEO_CRF), '-preset', 'ultrafast']
            else:  # bitrate mode
                maxrate = int(target_bitrate * 1.5)
                bufsize = int(target_bitrate * 2)
                return ['-c:v', 'libx264', '-b:v', str(target_bitrate),
                        '-maxrate', str(maxrate), '-bufsize', str(bufsize),
                        '-preset', 'ultrafast']


    # ===================================================================
    #  Temp directory management
    # ===================================================================

    def extract_frame(self, timestamp):
        """Extract a single frame at the given timestamp."""
        if not self.current_video_url:
            return None

        # Check cache first
        cached = self._get_cached_frame(timestamp)
        if cached and os.path.exists(cached):
            logger.debug(f"Using cached frame for timestamp {timestamp}s")
            return cached

        try:
            temp_file = os.path.join(self.temp_dir, f"frame_{timestamp}.jpg")

            if self.is_local_file(self.current_video_url):
                video_url = self.current_video_url
            else:
                def _get_stream_url():
                    get_url_cmd = [
                        self.ytdlp_path,
                        '-f', 'best[height<=480]/best',
                        '--no-playlist',
                        '-g',
                        self.current_video_url
                    ]
                    return subprocess.run(get_url_cmd, capture_output=True,
                                          encoding='utf-8', errors='replace',
                                          timeout=STREAM_FETCH_TIMEOUT, check=True,
                                          **_subprocess_kwargs)

                result = self.retry_network_operation(_get_stream_url,
                                                      f"Get stream URL for frame at {timestamp}s")
                video_url = result.stdout.strip().split('\n')[0]

                if not video_url:
                    logger.error("Failed to get stream URL - empty response")
                    return None

                if not (video_url.startswith('http://') or video_url.startswith('https://')):
                    logger.error(f"Invalid stream URL format: {video_url[:100]}")
                    return None

            def _extract_frame():
                cmd = [self.ffmpeg_path, '-nostdin']
                if video_url.startswith('http'):
                    cmd.extend([
                        '-reconnect', '1',
                        '-reconnect_streamed', '1',
                        '-reconnect_delay_max', '5',
                        '-timeout', '10000000',
                    ])
                cmd.extend([
                    '-ss', str(timestamp),
                    '-i', video_url,
                    '-vframes', '1',
                    '-q:v', '2',
                    '-y',
                    temp_file
                ])
                return subprocess.run(cmd, capture_output=True, timeout=STREAM_FETCH_TIMEOUT,
                                      check=True, **_subprocess_kwargs)

            self.retry_network_operation(_extract_frame, f"Extract frame at {timestamp}s")

            if os.path.exists(temp_file):
                self._cache_preview_frame(timestamp, temp_file)
                return temp_file

        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout while extracting frame at {timestamp}s")
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error extracting frame at {timestamp}s: {e}")
        except Exception as e:
            logger.error(f"Unexpected error extracting frame at {timestamp}s: {e}")

        return None


    # ===================================================================
    #  File helpers
    # ===================================================================

    def _find_latest_file(self):
        """Find the most recently created file in the download directory."""
        try:
            download_dir = Path(self.download_path)
            if not download_dir.exists():
                return None

            files = [f for f in download_dir.iterdir() if f.is_file()]
            if not files:
                return None

            latest_file = max(files, key=lambda f: f.stat().st_ctime)
            return str(latest_file)

        except Exception as e:
            logger.error(f"Error finding latest file: {e}")
            return None


    def cleanup_temp_files(self):
        """Clean up temporary preview files."""
        try:
            self._clear_preview_cache()
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temp directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {e}")


    def save_upload_link(self, link, filename=""):
        """Save uploaded video link to history file."""
        try:
            UPLOAD_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(UPLOAD_HISTORY_FILE, 'a', encoding='utf-8') as f:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{timestamp} | {filename} | {link}\n")
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


    # ===================================================================
    #  Command builders
    # ===================================================================

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

        trim_enabled = trim_start is not None and trim_end is not None
        if trim_enabled:
            start_hms = self.seconds_to_hms(trim_start)
            end_hms = self.seconds_to_hms(trim_end)
            cmd.extend([
                '--download-sections', f'*{start_hms}-{end_hms}',
                '--force-keyframes-at-cuts',
            ])

        needs_processing = trim_enabled or volume != 1.0
        if needs_processing:
            ffmpeg_args = self._get_video_encoder_args(mode='crf') + ['-c:a', 'aac', '-b:a', AUDIO_BITRATE]
            if volume != 1.0:
                ffmpeg_args.extend(['-af', f'volume={volume}'])
            cmd.extend(['--postprocessor-args', 'ffmpeg:' + ' '.join(ffmpeg_args)])

        cmd.extend(['-o', output_path, url])
        return cmd


    # ===================================================================
    #  Encoding helpers (size-constrained / two-pass / single-pass)
    # ===================================================================

    def _size_constrained_encode(self, input_file, output_file, target_bitrate, duration,
                                 volume_multiplier=1.0, scale_height=None,
                                 start_time=None, end_time=None):
        """Encode a video to hit a target bitrate (for 10MB size constraint).

        Uses single-pass with hardware encoding if available, or two-pass with
        software encoding as fallback.  Returns True on success, False on failure
        or cancellation.
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
        passlogfile = os.path.join(tempfile.gettempdir(),
                                   f'ytdl_2pass_{os.getpid()}_{int(time.time())}')

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

        Returns (height: int, video_bitrate_bps: int).
        """
        if duration_seconds <= 0:
            return (360, 100000)
        available_bitrate = int((TARGET_MAX_SIZE_BYTES * 8) / duration_seconds - TARGET_AUDIO_BITRATE_BPS)
        available_bitrate = max(available_bitrate, 100000)

        for height in SIZE_CONSTRAINED_RESOLUTIONS:
            if available_bitrate >= SIZE_CONSTRAINED_MIN_BITRATES[height]:
                return (height, available_bitrate)

        return (360, available_bitrate)


    # ===================================================================
    #  Download entry-point & speed-limit helper
    # ===================================================================

    def start_download(self):
        """Validate inputs and kick off a download in the thread pool."""
        url = self.url_entry.text().strip()

        if not url:
            self.sig_show_messagebox.emit('error', 'Error',
                                          'Please enter a YouTube URL or select a local file')
            return

        is_local = self.is_local_file(url)

        if is_local:
            if not os.path.isfile(url):
                self.sig_show_messagebox.emit('error', 'Error', f'File not found:\n{url}')
                return
        else:
            is_valid, message = self.validate_youtube_url(url)
            if not is_valid:
                self.sig_show_messagebox.emit('error', 'Invalid URL', message)
                logger.warning(f"Invalid URL rejected for download: {url}")
                return

            if self.is_playlist_url(url) and not self.is_pure_playlist_url(url):
                url = self.strip_playlist_params(url)
                self.is_playlist = False
            else:
                self.is_playlist = self.is_playlist_url(url)

        if not self.dependencies_ok:
            self.sig_show_messagebox.emit(
                'error', 'Error',
                'yt-dlp or ffmpeg is not installed.\n\nInstall with:\npip install yt-dlp\n\n'
                'and install ffmpeg from your package manager')
            return

        logger.info(f"Starting download for URL: {url}")

        with self.download_lock:
            self.is_downloading = True
            self.download_start_time = time.time()
            self.last_progress_time = time.time()

        self.download_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.setValue(0)
        self.progress_label.setText("0%")

        # Snapshot all widget values on the GUI thread before submitting to worker
        ui_state = {
            'quality': self.quality_combo.currentText(),
            'trim_enabled': self.trim_enabled_check.isChecked(),
            'start_time': self.start_slider.value(),
            'end_time': self.end_slider.value(),
            'filename': self.filename_entry.text().strip(),
            'volume_raw': self.volume_slider.value(),
            'keep_below_10mb': self.keep_below_10mb_check.isChecked(),
            'speed_limit': self.speed_limit_entry.text().strip(),
            'download_path': self.download_path,
        }

        # Submit download and timeout monitor to thread pool
        self.thread_pool.submit(self.download, url, ui_state)
        self.thread_pool.submit(self._monitor_download_timeout)


    def _monitor_download_timeout(self):
        """Monitor download for timeouts (absolute and progress-based)."""
        while True:
            time.sleep(TIMEOUT_CHECK_INTERVAL)

            if self._shutting_down:
                break

            with self.download_lock:
                is_still_downloading = self.is_downloading

            if not is_still_downloading:
                break

            current_time = time.time()

            if self.download_start_time:
                elapsed = current_time - self.download_start_time
                if elapsed > DOWNLOAD_TIMEOUT:
                    logger.error(f"Download exceeded absolute timeout ({DOWNLOAD_TIMEOUT}s)")
                    QTimer.singleShot(0, lambda: self._timeout_download(
                        'Download timeout (60 min limit exceeded)'))
                    break

            if self.last_progress_time:
                time_since_progress = current_time - self.last_progress_time
                if time_since_progress > DOWNLOAD_PROGRESS_TIMEOUT:
                    logger.error(f"Download stalled (no progress for {DOWNLOAD_PROGRESS_TIMEOUT}s)")
                    QTimer.singleShot(0, lambda: self._timeout_download(
                        'Download stalled (no progress for 10 minutes)'))
                    break


    def _timeout_download(self, reason):
        """Handle download timeout."""
        with self.download_lock:
            downloading = self.is_downloading
        if downloading:
            logger.warning(f"Timing out download: {reason}")
            self.update_status(reason, "red")
            self.stop_download()


    def stop_download(self):
        """Stop download gracefully, with forced termination as fallback."""
        with self.download_lock:
            process_to_cleanup = self.current_process
            is_active = self.is_downloading

        if process_to_cleanup and is_active:
            self.safe_process_cleanup(process_to_cleanup)

            with self.download_lock:
                self.is_downloading = False
            self.update_status('Download stopped', "orange")
            self.download_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.progress.setValue(0)
            self.progress_label.setText("0%")


    # ===================================================================
    #  Main download logic
    # ===================================================================

    def download(self, url, ui_state=None):
        """Download a YouTube video or process a local file.

        Args:
            url: The URL or local file path to download.
            ui_state: Dict of widget values snapshot from the GUI thread.
                      If None, falls back to reading widgets directly (for
                      compatibility with callers like download_clipboard_url).
        """
        keep_below_10mb = False
        temp_dir = None
        try:
            # Route to local file handler if needed
            if self.is_local_file(url):
                return self.download_local_file(url, ui_state)

            is_playlist_url = self.is_playlist_url(url)

            # Use pre-captured UI state (thread-safe) or fall back to direct read
            if ui_state:
                quality = ui_state['quality']
                trim_enabled = ui_state['trim_enabled']
            else:
                quality = self.quality_combo.currentText()
                trim_enabled = self.trim_enabled_check.isChecked()
            audio_only = quality.startswith("none") or quality == "none (Audio only)"

            self.update_status('Starting download...', "blue")

            # Validate trimming
            if trim_enabled:
                if self.video_duration <= 0:
                    self.update_status('Please fetch video duration first', "red")
                    self._reset_buttons()
                    with self.download_lock:
                        self.is_downloading = False
                    return

                start_time = int(float(ui_state['start_time'])) if ui_state else int(float(self.start_slider.value()))
                end_time = int(float(ui_state['end_time'])) if ui_state else int(float(self.end_slider.value()))

                if start_time >= end_time:
                    self.update_status('Invalid time range', "red")
                    self._reset_buttons()
                    with self.download_lock:
                        self.is_downloading = False
                    return

            if audio_only:
                _fn = ui_state['filename'] if ui_state else self.filename_entry.text().strip()
                custom_name = self.sanitize_filename(_fn)
                if custom_name:
                    base_name = custom_name
                else:
                    base_name = '%(title)s'

                if trim_enabled:
                    start_hms = self.seconds_to_hms(start_time).replace(':', '-')
                    end_hms = self.seconds_to_hms(end_time).replace(':', '-')
                    output_template = f'{base_name}_[{start_hms}_to_{end_hms}].%(ext)s'
                else:
                    output_template = f'{base_name}.%(ext)s'

                cmd = [
                    self.ytdlp_path,
                    '--concurrent-fragments', CONCURRENT_FRAGMENTS,
                    '--buffer-size', BUFFER_SIZE,
                    '--http-chunk-size', CHUNK_SIZE,
                    '-f', 'bestaudio',
                    '--extract-audio',
                    '--audio-format', 'mp3',
                    '--audio-quality', AUDIO_BITRATE,
                    '--newline',
                    '--progress',
                    '-o', os.path.join(ui_state['download_path'] if ui_state else self.download_path, output_template),
                ]

                ffmpeg_args = []

                if trim_enabled:
                    ffmpeg_args.extend(['-ss', str(start_time), '-to', str(end_time)])

                _vol = (ui_state['volume_raw'] / 100.0) if ui_state else (self.volume_slider.value() / 100.0)
                volume_multiplier = self.validate_volume(_vol)
                if volume_multiplier != 1.0:
                    ffmpeg_args.extend(['-af', f'volume={volume_multiplier}'])

                if ffmpeg_args:
                    cmd.extend(['--postprocessor-args', 'ffmpeg:' + ' '.join(ffmpeg_args)])

                _sl = ui_state['speed_limit'] if ui_state else None
                cmd.extend(self._get_speed_limit_args(speed_limit_str=_sl))

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

                keep_below_10mb = ui_state['keep_below_10mb'] if ui_state else self.keep_below_10mb_check.isChecked()

                if keep_below_10mb:
                    clip_duration = (end_time - start_time) if trim_enabled else self.video_duration
                    height, target_bitrate = self._calculate_optimal_quality(clip_duration)
                    height = str(height)
                    logger.info(f"10MB encode: auto-selected {height}p at {target_bitrate}bps "
                                f"for {clip_duration}s clip")
                else:
                    height = quality

                _vol = (ui_state['volume_raw'] / 100.0) if ui_state else (self.volume_slider.value() / 100.0)
                volume_multiplier = self.validate_volume(_vol)

                _fn = ui_state['filename'] if ui_state else self.filename_entry.text().strip()
                custom_name = self.sanitize_filename(_fn)
                if custom_name:
                    base_name = custom_name
                else:
                    base_name = '%(title)s'

                if trim_enabled:
                    start_hms_file = self.seconds_to_hms(start_time).replace(':', '-')
                    end_hms_file = self.seconds_to_hms(end_time).replace(':', '-')
                    output_template = f'{base_name}_{height}p_[{start_hms_file}_to_{end_hms_file}].%(ext)s'
                else:
                    output_template = f'{base_name}_{height}p.%(ext)s'

                if keep_below_10mb:
                    # --- Size-constrained path ---
                    temp_dir = tempfile.mkdtemp(prefix='ytdl_10mb_')
                    temp_output_template = os.path.join(temp_dir, '%(title)s.%(ext)s')

                    dl_bitrate_cap = max(target_bitrate * 2, 1000000)
                    dl_bitrate_cap_k = int(dl_bitrate_cap / 1000)
                    format_sel = (f'bestvideo[height<={height}][vbr<={dl_bitrate_cap_k}]'
                                  f'+bestaudio/bestvideo[height<={height}]+bestaudio'
                                  f'/best[height<={height}]')

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

                    needs_processing = trim_enabled or volume_multiplier != 1.0

                    if needs_processing:
                        ffmpeg_video_args = (self._get_video_encoder_args(mode='crf')
                                            + ['-c:a', 'aac', '-b:a', AUDIO_BITRATE])
                        if volume_multiplier != 1.0:
                            ffmpeg_video_args.extend(['-af', f'volume={volume_multiplier}'])
                        cmd.extend(['--postprocessor-args',
                                    'ffmpeg:' + ' '.join(ffmpeg_video_args)])

                    _sl2 = ui_state['speed_limit'] if ui_state else None
                    cmd.extend(self._get_speed_limit_args(speed_limit_str=_sl2))
                    if is_playlist_url:
                        cmd.append('--no-playlist')
                    _dp = ui_state['download_path'] if ui_state else self.download_path
                    cmd.extend([
                        '--newline', '--progress',
                        '-o', os.path.join(_dp, output_template),
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
            error_lines = []
            try:
                for line in self.current_process.stdout:
                    if not self.is_downloading:
                        break

                    if 'ERROR' in line or 'error' in line.lower():
                        if len(error_lines) < 100:
                            error_lines.append(line.strip())
                        logger.warning(f"yt-dlp: {line.strip()}")

                    if '[download]' in line or 'Downloading' in line:
                        progress_match = PROGRESS_REGEX.search(line)
                        if progress_match:
                            progress = float(progress_match.group(1))
                            self.update_progress(progress)

                            speed_match = SPEED_REGEX.search(line)
                            eta_match = ETA_REGEX.search(line)

                            if speed_match and eta_match:
                                status_msg = (f'Downloading... {progress:.1f}% '
                                              f'at {speed_match.group(1)} | '
                                              f'ETA: {eta_match.group(1)}')
                            elif speed_match:
                                status_msg = f'Downloading... {progress:.1f}% at {speed_match.group(1)}'
                            else:
                                status_msg = f'Downloading... {progress:.1f}%'

                            self.update_status(status_msg, "blue")
                            self.last_progress_time = time.time()
                        elif 'Destination' in line:
                            self.update_status('Starting download...', "blue")
                            self.last_progress_time = time.time()

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

            self.current_process.wait()

            if self.current_process.returncode == 0 and self.is_downloading:
                if not audio_only and keep_below_10mb and temp_dir:
                    temp_files = glob.glob(os.path.join(temp_dir, '*.mp4'))
                    if not temp_files:
                        self.update_status('Download failed', "red")
                        logger.error("Two-pass: no temp file found after yt-dlp download")
                    else:
                        temp_file = temp_files[0]
                        video_title = os.path.splitext(os.path.basename(temp_file))[0]
                        if custom_name:
                            final_base = custom_name
                        else:
                            final_base = self.sanitize_filename(video_title) or video_title

                        if trim_enabled:
                            final_name = f'{final_base}_{height}p_[{start_hms_file}_to_{end_hms_file}].mp4'
                        else:
                            final_name = f'{final_base}_{height}p.mp4'

                        _dp2 = ui_state['download_path'] if ui_state else self.download_path
                        final_output = os.path.join(_dp2, final_name)
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

                    shutil.rmtree(temp_dir, ignore_errors=True)
                else:
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
                if not audio_only and keep_below_10mb and temp_dir:
                    shutil.rmtree(temp_dir, ignore_errors=True)

        except FileNotFoundError as e:
            if self.is_downloading:
                error_msg = ('yt-dlp or ffmpeg is not installed.\n\nInstall with:\n'
                             'pip install yt-dlp\n\nand install ffmpeg from your package manager')
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


    # ===================================================================
    #  Local file processing
    # ===================================================================

    def download_local_file(self, filepath, ui_state=None):
        """Process local video file with trimming, quality adjustment, and volume control.

        Args:
            filepath: Path to the local file.
            ui_state: Dict of widget values snapshot from the GUI thread.
        """
        try:
            if ui_state:
                quality = ui_state['quality']
                trim_enabled = ui_state['trim_enabled']
            else:
                quality = self.quality_combo.currentText()
                trim_enabled = self.trim_enabled_check.isChecked()
            audio_only = quality.startswith("none") or quality == "none (Audio only)"

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

                start_time = int(float(ui_state['start_time'])) if ui_state else int(float(self.start_slider.value()))
                end_time = int(float(ui_state['end_time'])) if ui_state else int(float(self.end_slider.value()))

                if start_time >= end_time:
                    self.update_status('Invalid time range', "red")
                    self._reset_buttons()
                    with self.download_lock:
                        self.is_downloading = False
                    return

            _fn = ui_state['filename'] if ui_state else self.filename_entry.text().strip()
            custom_name = self.sanitize_filename(_fn)
            if custom_name:
                base_name = custom_name
            else:
                input_path = Path(filepath)
                base_name = input_path.stem

            if trim_enabled:
                start_hms = self.seconds_to_hms(start_time).replace(':', '-')
                end_hms = self.seconds_to_hms(end_time).replace(':', '-')
                output_name = f"{base_name}_[{start_hms}_to_{end_hms}]"
            else:
                if custom_name:
                    output_name = base_name
                else:
                    output_name = f"{base_name}_processed"

            _vol = (ui_state['volume_raw'] / 100.0) if ui_state else (self.volume_slider.value() / 100.0)
            volume_multiplier = self.validate_volume(_vol)
            _dp = ui_state['download_path'] if ui_state else self.download_path

            if audio_only:
                output_file = os.path.join(_dp, f"{output_name}.mp3")
                cmd = [self.ffmpeg_path, '-i', filepath]

                if trim_enabled:
                    cmd.extend(['-ss', str(start_time), '-to', str(end_time)])

                cmd.extend(['-vn', '-c:a', 'libmp3lame', '-b:a', AUDIO_BITRATE])

                if volume_multiplier != 1.0:
                    cmd.extend(['-af', f'volume={volume_multiplier}'])

                cmd.extend(['-progress', 'pipe:1', '-y', output_file])
            else:
                if quality.startswith("none") or quality == "none (Audio only)":
                    self.update_status('Please select a video quality', "red")
                    self._reset_buttons()
                    with self.download_lock:
                        self.is_downloading = False
                    return

                keep_below_10mb = ui_state['keep_below_10mb'] if ui_state else self.keep_below_10mb_check.isChecked()

                if keep_below_10mb:
                    clip_duration = (end_time - start_time) if trim_enabled else self.video_duration
                    if clip_duration <= 0:
                        self.update_status('Please fetch video duration first', "red")
                        self._reset_buttons()
                        with self.download_lock:
                            self.is_downloading = False
                        return
                    height, target_bitrate = self._calculate_optimal_quality(clip_duration)
                    height = str(height)
                    logger.info(f"10MB encode (local): auto-selected {height}p at "
                                f"{target_bitrate}bps for {clip_duration}s clip")
                else:
                    height = quality

                output_file = os.path.join(_dp, f"{output_name}_{height}p.mp4")

                if keep_below_10mb:
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

                    cmd.extend(['-vf', f'scale=-2:{height}']
                               + self._get_video_encoder_args(mode='crf')
                               + ['-c:a', 'aac', '-b:a', AUDIO_BITRATE])

                    if volume_multiplier != 1.0:
                        cmd.extend(['-af', f'volume={volume_multiplier}'])

                    cmd.extend(['-progress', 'pipe:1', '-y', output_file])

            logger.info(f"Processing local file: {' '.join(cmd)}")

            # Execute ffmpeg
            with self.download_lock:
                self.current_process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    encoding='utf-8', errors='replace', bufsize=1, **_subprocess_kwargs)

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


    # ===================================================================
    #  Upload-button enable helper (thread-safe)
    # ===================================================================


    # --- from _port_updates.py ---

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
                self.update_status('Checking for updates...', "blue")

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
                    self.sig_show_update_dialog.emit(latest_version, data)
                    return
                else:
                    logger.info(f"App is up to date: {APP_VERSION}")

            except Exception as e:
                logger.error(f"Error checking app updates: {e}")

            # Check yt-dlp update (PyPI for source, GitHub releases for bundled)
            try:
                ytdlp_current = self._get_ytdlp_version()
                if ytdlp_current:
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
                # Must create dialog on GUI thread; use a signal
                self.sig_show_ytdlp_update.emit(ytdlp_current, ytdlp_latest)
            elif not silent:
                self.sig_show_messagebox.emit(
                    'info', 'Up to Date',
                    f'You are running the latest version (v{APP_VERSION}).'
                )

        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            if not silent:
                self.sig_show_messagebox.emit(
                    'error', 'Update Error',
                    f'Failed to check for updates:\n{e}'
                )


    def _check_for_updates_clicked(self):
        """Handle Check for Updates button click."""
        self.thread_pool.submit(self._check_for_updates, False)


    def _show_update_dialog(self, latest_version, release_data):
        """Show update available dialog with options.

        Args:
            latest_version: The latest version string
            release_data: The GitHub release API response data
        """
        colors = THEMES[self.current_theme]

        dialog = QDialog(self)
        dialog.setWindowTitle('Update Available')
        dialog.setFixedSize(400, 200)
        dialog.setStyleSheet(
            f'background-color: {colors["bg"]}; color: {colors["fg"]};'
        )

        layout = QVBoxLayout(dialog)

        msg = (
            f'A new version is available!\n\n'
            f'Current: v{APP_VERSION}\n'
            f'Latest: v{latest_version}\n\n'
            f'Would you like to update?'
        )
        label = QLabel(msg)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)

        btn_layout = QHBoxLayout()

        update_btn = QPushButton('Update Now')
        releases_btn = QPushButton('Open Releases Page')
        later_btn = QPushButton('Later')

        def update_now():
            dialog.accept()
            self.thread_pool.submit(self._apply_update, release_data)

        def open_releases():
            dialog.accept()
            webbrowser.open(GITHUB_RELEASES_URL)

        update_btn.clicked.connect(update_now)
        releases_btn.clicked.connect(open_releases)
        later_btn.clicked.connect(dialog.reject)

        btn_layout.addWidget(update_btn)
        btn_layout.addWidget(releases_btn)
        btn_layout.addWidget(later_btn)
        layout.addLayout(btn_layout)

        dialog.exec()


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


    def _compute_git_blob_sha(self, content):
        """Compute the git blob SHA1 hash for content (same as git hash-object)."""
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


    def _apply_update(self, release_data):
        """Download and apply update, then restart the application.

        Routes to the appropriate strategy based on how the app is running:
        - Source (.py): replace modules, then restart via Python interpreter
        - Frozen portable (onefile): download new exe, rename-dance, restart
        - Frozen installed (onedir): direct user to GitHub releases page
        """
        if getattr(sys, 'frozen', False):
            if self._is_onedir_frozen():
                # Installed version -- can't self-update, point to installer
                self.sig_show_messagebox.emit(
                    'info', 'Update Complete',
                    'Your installed version cannot self-update.\n\n'
                    'The releases page will open so you can download the latest installer.'
                )
                QTimer.singleShot(0, lambda: webbrowser.open(GITHUB_RELEASES_URL))
            else:
                self._apply_update_frozen(release_data)
        else:
            self._apply_update_source(release_data)


    def _apply_update_source(self, release_data):
        """Download, verify, and replace .py source files, then auto-restart."""
        import urllib.request

        try:
            self.update_status('Downloading update...', "blue")

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

            # All verified -- backup and replace
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
            self.update_status('Update complete — restarting...', "green")
            logger.info("Restarting after source update...")

            def _do_restart():
                subprocess.Popen([sys.executable] + sys.argv)
                self.close()

            QTimer.singleShot(500, _do_restart)

        except Exception as e:
            logger.error(f"Error applying update: {e}")
            self.sig_show_messagebox.emit(
                'error', 'Update Failed',
                f'Failed to download update:\n{e}'
            )


    def _apply_update_frozen(self, release_data):
        """Self-update a frozen portable exe via download + rename-and-replace."""
        import urllib.request

        try:
            self.update_status('Downloading update...', "blue")

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
            self.sig_show_messagebox.emit(
                'error', 'Update Failed',
                f'Failed to download update:\n{e}'
            )


    def _apply_update_frozen_windows(self, download_url, headers, exe_path):
        """Windows portable exe update: rename-dance with .bat trampoline fallback."""
        import urllib.request

        new_exe = exe_path.with_suffix('.exe.new')
        old_exe = exe_path.with_name(exe_path.stem + '.old')

        logger.info(f"Downloading update: {download_url}")

        # Create progress dialog on GUI thread via signal
        progress_state = {'dialog': None, 'label': None, 'bar': None}

        def _create_progress_dialog():
            colors = THEMES[self.current_theme]
            dlg = QDialog(self)
            dlg.setWindowTitle('Downloading Update')
            dlg.setFixedSize(350, 100)
            dlg.setStyleSheet(
                f'background-color: {colors["bg"]}; color: {colors["fg"]};'
            )
            # Prevent user from closing the dialog
            dlg.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

            layout = QVBoxLayout(dlg)
            lbl = QLabel('Downloading update...')
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lbl)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            layout.addWidget(bar)

            progress_state['dialog'] = dlg
            progress_state['label'] = lbl
            progress_state['bar'] = bar
            dlg.show()

        def _update_progress_dialog(pct, mb, total_mb):
            if progress_state['label']:
                progress_state['label'].setText(
                    f'Downloading update... {mb:.1f}/{total_mb:.1f} MB ({pct}%)'
                )
            if progress_state['bar']:
                progress_state['bar'].setValue(pct)

        def _close_progress_dialog():
            if progress_state['dialog']:
                progress_state['dialog'].close()
                progress_state['dialog'] = None

        QTimer.singleShot(0, _create_progress_dialog)

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
                    QTimer.singleShot(
                        0,
                        lambda p=pct, m=mb, t=total_mb: _update_progress_dialog(p, m, t)
                    )
            content = b''.join(chunks)

        QTimer.singleShot(0, _close_progress_dialog)

        if len(content) < 1024:
            raise RuntimeError("Downloaded file is too small — likely corrupted.")

        new_exe.write_bytes(content)
        logger.info(f"Downloaded new exe: {new_exe} ({len(content):,} bytes)")

        # Rename dance: running.exe -> .old, .new -> running.exe
        try:
            if old_exe.exists():
                old_exe.unlink()
            exe_path.rename(old_exe)
            logger.info(f"Renamed running exe aside: {exe_path} -> {old_exe}")

            try:
                new_exe.rename(exe_path)
                logger.info(f"Moved new exe into place: {new_exe} -> {exe_path}")
            except Exception:
                # Restore if moving new exe into place fails
                if old_exe.exists() and not exe_path.exists():
                    old_exe.rename(exe_path)
                raise

            # Success -- tell user to reopen
            logger.info(f"Update applied: {exe_path}")
            self.update_status('Update installed!', "green")
            self.sig_show_messagebox.emit(
                'info', 'Update Installed',
                'Updated to the latest version.\n\nPlease close and reopen the app to use it.'
            )
            QTimer.singleShot(0, lambda: self.close())

        except OSError as rename_err:
            # Rename failed -- use bat to move file after we exit
            logger.warning(f"Rename failed ({rename_err}), falling back to bat trampoline")
            import time as _time
            bat_path = exe_path.parent / f'_update_{int(_time.time())}.bat'
            pid = os.getpid()
            bat_content = (
                '@echo off\r\n'
                f':wait\r\n'
                f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul && '
                f'(timeout /t 1 /nobreak >nul & goto wait)\r\n'
                'timeout /t 3 /nobreak >nul\r\n'
                f'move /y "{new_exe}" "{exe_path}"\r\n'
                'del "%~f0"\r\n'
            )
            bat_path.write_text(bat_content)
            logger.info(f"Wrote update trampoline: {bat_path}")
            subprocess.Popen(
                ['cmd', '/c', str(bat_path)],
                creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True
            )
            self.sig_show_messagebox.emit(
                'info', 'Update Installed',
                'Updated to the latest version.\n\nPlease close and reopen the app to use it.'
            )
            QTimer.singleShot(0, lambda: self.close())


    def _apply_update_frozen_linux(self, download_url, headers, exe_path):
        """Linux portable binary update: download tar.gz, extract, replace in place."""
        import urllib.request

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

            # Extract just the binary content (safe -- no path traversal)
            f = tar.extractfile(binary_member)
            if not f:
                raise RuntimeError("Could not read binary from archive.")
            binary_content = f.read()

        # Write to temp file next to exe, then atomically move into place
        with tempfile.NamedTemporaryFile(delete=False, dir=str(exe_path.parent)) as tmp:
            tmp.write(binary_content)
            tmp_path = Path(tmp.name)

        shutil.move(str(tmp_path), str(exe_path))
        os.chmod(str(exe_path), 0o755)
        logger.info(f"Replaced binary: {exe_path}")

        # Spawn new binary and shut down
        self.update_status('Update complete — restarting...', "green")

        def _do_restart():
            logger.info(f"Launching updated binary: {exe_path}")
            subprocess.Popen([str(exe_path)])
            self.close()

        QTimer.singleShot(500, _do_restart)


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


    # ======================================================================
    #  yt-dlp updates
    # ======================================================================


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


    def _apply_ytdlp_update_pip(self, pip_path):
        """Apply yt-dlp update using pip (when running from source)."""
        try:
            logger.info("Updating yt-dlp via pip...")
            self.update_status('Updating yt-dlp...', "blue")

            result = subprocess.run(
                [pip_path, 'install', '--upgrade', 'yt-dlp'],
                capture_output=True,
                timeout=120,
                **_subprocess_kwargs
            )

            if result.returncode == 0:
                new_version = self._get_ytdlp_version() or "unknown"
                logger.info(f"yt-dlp updated successfully to {new_version}")

                self.update_status(f'Current yt-dlp: {new_version}', "green")
                self.sig_show_messagebox.emit(
                    'info', 'yt-dlp Updated',
                    f'yt-dlp has been updated to version {new_version}.'
                )
            else:
                error_msg = (
                    result.stderr.decode('utf-8', errors='replace').strip()
                    or result.stdout.decode('utf-8', errors='replace').strip()
                )
                raise RuntimeError(error_msg or "pip returned non-zero exit code")

        except subprocess.TimeoutExpired:
            logger.error("yt-dlp update timed out")
            self.sig_show_messagebox.emit(
                'error', 'yt-dlp Update Failed',
                'Failed to update yt-dlp:\n\nUpdate timed out'
            )
        except Exception as e:
            logger.error(f"Error updating yt-dlp: {e}")
            self.sig_show_messagebox.emit(
                'error', 'yt-dlp Update Failed',
                f'Failed to update yt-dlp:\n\n{e}'
            )


    def _apply_ytdlp_update_binary(self, latest_version):
        """Download latest yt-dlp binary from GitHub releases with SHA256 verification."""
        import urllib.request

        try:
            logger.info("Downloading latest yt-dlp binary...")
            self.update_status('Updating yt-dlp...', "blue")

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

            self.update_status(f'Current yt-dlp: {new_version}', "green")
            self.sig_show_messagebox.emit(
                'info', 'yt-dlp Updated',
                f'yt-dlp has been updated to version {new_version}.'
            )

        except Exception as e:
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            logger.error(f"Error downloading yt-dlp binary: {e}")
            self.sig_show_messagebox.emit(
                'error', 'yt-dlp Update Failed',
                f'Failed to update yt-dlp:\n\n{e}'
            )


    def _show_ytdlp_update_dialog(self, current_version, latest_version):
        """Show yt-dlp update available dialog."""
        result = QMessageBox.question(
            self,
            'yt-dlp Update Available',
            f'A new version of yt-dlp is available!\n\n'
            f'Current: {current_version}\n'
            f'Latest: {latest_version}\n\n'
            f'This may fix download issues.\n'
            f'Update now?'
        )

        if result == QMessageBox.StandardButton.Yes:
            if getattr(sys, 'frozen', False):
                self.thread_pool.submit(self._apply_ytdlp_update_binary, latest_version)
            else:
                pip_path = self._get_pip_path()
                if pip_path:
                    self.thread_pool.submit(self._apply_ytdlp_update_pip, pip_path)
                else:
                    QMessageBox.warning(
                        self,
                        'Update Not Supported',
                        'Cannot auto-update yt-dlp in this mode.\n\n'
                        'Please update yt-dlp manually or download the latest app release.'
                    )


    # ======================================================================
    #  Persistence
    # ======================================================================


    def view_upload_history(self):
        """View upload link history in a dialog window."""
        colors = THEMES[self.current_theme]

        dialog = QDialog(self)
        dialog.setWindowTitle('Upload Link History')
        dialog.resize(800, 500)
        dialog.setStyleSheet(
            f'background-color: {colors["bg"]}; color: {colors["fg"]};'
        )

        layout = QVBoxLayout(dialog)

        # Read-only text area for history content
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(
            f'background-color: {colors["entry_bg"]}; '
            f'color: {colors["entry_fg"]}; '
            f'font-family: Consolas, monospace; font-size: 9pt;'
        )
        layout.addWidget(text_edit)

        # Load and display history
        try:
            if UPLOAD_HISTORY_FILE.exists():
                with open(UPLOAD_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content:
                        text_edit.setPlainText(content)
                    else:
                        text_edit.setPlainText('No upload history yet.')
            else:
                text_edit.setPlainText('No upload history yet.')
        except Exception as e:
            text_edit.setPlainText(f'Error loading history: {e}')

        # Button row
        btn_layout = QHBoxLayout()

        copy_btn = QPushButton('Copy All')
        clear_btn = QPushButton('Clear History')
        close_btn = QPushButton('Close')

        def copy_all():
            QApplication.clipboard().setText(text_edit.toPlainText())
            QMessageBox.information(dialog, 'Copied', 'History copied to clipboard!')

        def clear_history():
            confirm = QMessageBox.question(
                dialog, 'Clear History',
                'Are you sure you want to clear all upload history?'
            )
            if confirm == QMessageBox.StandardButton.Yes:
                try:
                    if UPLOAD_HISTORY_FILE.exists():
                        UPLOAD_HISTORY_FILE.unlink()
                    text_edit.setReadOnly(False)
                    text_edit.clear()
                    text_edit.setPlainText('No upload history yet.')
                    text_edit.setReadOnly(True)
                except Exception as e:
                    QMessageBox.critical(dialog, 'Error', f'Failed to clear history: {e}')

        copy_btn.clicked.connect(copy_all)
        clear_btn.clicked.connect(clear_history)
        close_btn.clicked.connect(dialog.close)

        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(clear_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        dialog.exec()


# ---------------------------------------------------------------------------
#  main()
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("YoutubeDownloader")

    window = YouTubeDownloader()
    window.show()

    # Apply dark title bar after show() so the window handle is valid
    if window.current_theme == 'dark':
        _set_dark_title_bar(window, dark=True)

    # Signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        window.close()

    signal.signal(signal.SIGINT, signal_handler)
    if sys.platform != 'win32':
        signal.signal(signal.SIGTERM, signal_handler)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()


