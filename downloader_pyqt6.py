#!/usr/bin/env python3
"""YoutubeDownloader — PyQt6 rewrite (Part 1: GUI construction)"""

import glob
import json
import logging
import logging.handlers
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from constants import (
    APP_DATA_DIR,
    APP_VERSION,
    AUTO_UPLOAD_DELAY_MS,
    BYTES_PER_MB,
    CATBOX_MAX_SIZE_MB,
    CLIPBOARD_POLL_INTERVAL_MS,
    CLIPBOARD_URL_LIST_HEIGHT,
    CLIPBOARD_URLS_FILE,
    CONFIG_FILE,
    DEPENDENCY_CHECK_TIMEOUT,
    GITHUB_REPO,
    LOG_FILE,
    MAX_VIDEO_DURATION,
    MAX_WORKER_THREADS,
    PREVIEW_DEBOUNCE_MS,
    PREVIEW_HEIGHT,
    PREVIEW_WIDTH,
    PROGRESS_COMPLETE,
    SLIDER_LENGTH,
    STREAM_FETCH_TIMEOUT,
    TEMP_DIR_MAX_AGE,
    THEMES,
    UI_INITIAL_DELAY_MS,
    UPLOAD_HISTORY_FILE,
)

# Import from modular components
from managers import utils
from managers.clipboard_manager import ClipboardManager
from managers.download_manager import PROGRESS_REGEX, DownloadManager
from managers.encoding import EncodingService
from managers.trimming_manager import TrimmingManager
from managers.update_manager import UpdateManager
from managers.upload_manager import UploadManager
from managers.utils import _subprocess_kwargs

# Try to import dbus for KDE Klipper integration (Linux only)
DBUS_AVAILABLE = False
if sys.platform != "win32":
    try:
        import dbus

        DBUS_AVAILABLE = True
    except ImportError:
        pass

from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import (
    QDialog,
    QTextEdit,
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
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1 * 1024 * 1024, backupCount=0),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

_PLAYLIST_ITEM_RE = re.compile(r"downloading item (\d+) of (\d+)")
_EXTRACTING_URL_RE = re.compile(r"Extracting URL:\s+(\S+)")


def _excepthook(exc_type, exc_value, exc_tb):
    """Log unhandled exceptions to the log file before crashing."""
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
    sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = _excepthook

# ── Color constants (template convention) ──────────────────────────────
GREEN = ("#2e7d32", "#388e3c")  # (normal, hover) — primary action
BLUE = ("#1565c0", "#1976d2")  # (normal, hover) — secondary action
YELLOW = ("#f9a825", "#fbc02d")  # (normal, hover) — warning/attention
RED = ("#c62828", "#e53935")  # (normal, hover) — help/danger

# ---------------------------------------------------------------------------
#  QSS Stylesheets — dark and light, adapted from THEMES colors
# ---------------------------------------------------------------------------

_DARK_STYLE_BASE = """
QWidget { background-color: #1e1e1e; color: #dcdcdc; }
QGroupBox { border: 1px solid #444; border-radius: 4px; margin-top: 8px; padding-top: 14px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #dcdcdc; }
QTabWidget::pane { border: 1px solid #444; }
QTabBar { background: transparent; }
QTabBar::tab { background: #2d2d2d; color: #dcdcdc; padding: 6px 14px; border: 1px solid #444;
               border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; }
QTabBar::tab:selected { background: #1e1e1e; }
QTabBar::tab:!selected { margin-top: 2px; }
QTabBar::tab:disabled { background: transparent; border: none; color: transparent;
                        min-width: 40px; max-width: 40px; padding: 0; margin: 0; }
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
QTabBar { background: transparent; }
QTabBar::tab { background: #e0e0e0; color: #1e1e1e; padding: 6px 14px; border: 1px solid #bbb;
               border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; }
QTabBar::tab:selected { background: #f0f0f0; }
QTabBar::tab:!selected { margin-top: 2px; }
QTabBar::tab:disabled { background: transparent; border: none; color: transparent;
                        min-width: 40px; max-width: 40px; padding: 0; margin: 0; }
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
    return (
        _DARK_STYLE_BASE
        + f"""
QCheckBox::indicator {{ width: 18px; height: 18px; }}
QCheckBox::indicator:unchecked {{ image: url({unc}); }}
QCheckBox::indicator:checked {{ image: url({chk}); }}
"""
    )


def _set_dark_title_bar(window, dark=True):
    """Set dark/light window title bar on Windows via DWM API."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        import ctypes.wintypes

        hwnd = int(window.winId())
        rendering_policy = ctypes.c_int(1 if dark else 0)

        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Win11 22H2+)
        # Fallback DWMWA_USE_IMMERSIVE_DARK_MODE = 19 (Win10 20H1+)
        for attr in (20, 19):
            hr = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.wintypes.HWND(hwnd),
                ctypes.wintypes.DWORD(attr),
                ctypes.byref(rendering_policy),
                ctypes.wintypes.DWORD(ctypes.sizeof(rendering_policy)),
            )
            if hr == 0:
                logger.info(f"Dark title bar set via DWMWA attribute {attr}")
                # Force Windows to repaint the title bar
                try:
                    SWP_FRAMECHANGED = 0x0020
                    SWP_NOSIZE = 0x0001
                    SWP_NOMOVE = 0x0002
                    SWP_NOZORDER = 0x0004
                    ctypes.windll.user32.SetWindowPos(
                        ctypes.wintypes.HWND(hwnd),
                        None,
                        0,
                        0,
                        0,
                        0,
                        SWP_FRAMECHANGED | SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER,
                    )
                except Exception:
                    pass
                return
        logger.debug("DwmSetWindowAttribute failed for both attr 20 and 19")
    except Exception as e:
        logger.debug(f"Could not set dark title bar: {e}")


# ── Colored button helper ──────────────────────────────────────────────


def _colored_btn(
    text: str, colors: tuple[str, str], bold: bool = True, text_color: str = "white"
) -> QPushButton:
    btn = QPushButton(text)
    if bold:
        f = btn.font()
        f.setBold(True)
        btn.setFont(f)
    btn.setStyleSheet(
        f"QPushButton {{ background:{colors[0]}; color:{text_color}; border-radius:4px; padding:4px 10px; }}"
        f"QPushButton:hover {{ background:{colors[1]}; }}"
    )
    return btn


# ---------------------------------------------------------------------------
#  Main Window
# ---------------------------------------------------------------------------


class YouTubeDownloader(QMainWindow):
    """Main application window — PyQt6 rewrite."""

    # Signals for thread-safe GUI updates from worker threads
    sig_update_progress = pyqtSignal(float)  # value 0-100
    sig_update_status = pyqtSignal(str, str)  # message, color
    sig_reset_buttons = pyqtSignal()
    sig_show_messagebox = pyqtSignal(str, str, str)  # type, title, message
    sig_set_mode_label = pyqtSignal(str)  # trimmer mode indicator
    sig_set_video_info = pyqtSignal(str)  # trimmer video info
    sig_set_filesize_label = pyqtSignal(str)  # trimmer filesize
    sig_run_on_gui = pyqtSignal(object)  # generic callable for thread-safe GUI updates

    # ------------------------------------------------------------------
    #  __init__
    # ------------------------------------------------------------------
    def __init__(self):
        super().__init__()
        logger.info("Initializing YoutubeDownloader (PyQt6)")
        self.setWindowTitle("YoutubeDownloader")

        if sys.platform == "win32":
            self.resize(650, 710)
            self.setMinimumSize(650, 710)
        else:
            self.resize(900, 1140)
            self.setMinimumSize(750, 600)

        # Load config once for all init settings
        self._config = {}
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE) as f:
                    self._config = json.load(f)
        except Exception:
            pass

        # Restore saved window geometry if available
        _geo = self._config.get("window_geometry")
        if _geo:
            try:
                self.restoreGeometry(bytes.fromhex(_geo))
            except Exception:
                pass

        # Window icon
        try:
            icon_path = self._get_resource_path("icon.png")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            logger.error(f"Error setting window icon: {e}")

        self.widgets: dict[str, QWidget] = {}  # widget registry (template convention)

        # ---------- state variables ----------
        self.download_path = str(Path.home() / "Downloads")
        # Download state → download_mgr (current_process, is_downloading, etc.)
        self.video_duration = 0  # mirrored from trimming_mgr via signals
        self.video_title = None
        self.current_video_url = None
        self._shutting_down = False
        self._updating = False

        # Detect bundled executables (when packaged with PyInstaller)
        self.ffmpeg_path = self._get_bundled_executable("ffmpeg")
        self.ffprobe_path = self._get_bundled_executable("ffprobe")
        self.ytdlp_path = self._get_bundled_executable("yt-dlp")

        # Frame preview variables (state in trimming_mgr, created after temp_dir init)
        self.start_preview_image = None
        self.end_preview_image = None
        self.temp_dir = None  # set by _init_temp_directory
        self.preview_update_timer = None
        self.last_preview_update = 0

        # Volume control — stored as int 0-200 (mapping to 0.0-2.0)
        self._volume_int = 100  # 100 = 1.0 = 100%

        # Local file support
        self.local_file_path = None

        # Thread pool for background tasks (must be created before managers)
        self.thread_pool = ThreadPoolExecutor(
            max_workers=MAX_WORKER_THREADS, thread_name_prefix="ytdl_worker"
        )

        # Upload to Catbox.moe (state in UploadManager)
        self.upload_mgr = UploadManager(thread_pool=self.thread_pool)
        self.upload_mgr.sig_upload_status.connect(self._do_upload_status)
        self.upload_mgr.sig_uploader_status.connect(self._do_uploader_status)
        self.upload_mgr.sig_set_upload_url.connect(self._do_set_upload_url)
        self.upload_mgr.sig_set_uploader_url.connect(self._do_set_uploader_url)
        self.upload_mgr.sig_enable_upload_btn.connect(self._do_enable_upload_btn)
        self.upload_mgr.sig_show_messagebox.connect(self._do_show_messagebox)
        self.upload_mgr.sig_run_on_gui.connect(self._do_run_on_gui)
        self.upload_mgr.sig_upload_complete.connect(self._on_upload_complete)
        self.upload_mgr.sig_uploader_file_uploaded.connect(self._show_upload_url)
        self.upload_mgr.sig_uploader_queue_done.connect(self._on_uploader_queue_done)

        # Custom filename
        self.custom_filename = None

        # Playlist support
        self.is_playlist = False
        self.estimated_filesize = None

        # Initialize temp directory with cleanup on exit
        self._init_temp_directory()

        # Trimming manager (needs temp_dir)
        self.trimming_mgr = TrimmingManager(
            ytdlp_path=self.ytdlp_path,
            ffmpeg_path=self.ffmpeg_path,
            ffprobe_path=self.ffprobe_path,
            temp_dir=self.temp_dir,
        )
        self.trimming_mgr.sig_update_status.connect(self._do_update_status)
        self.trimming_mgr.sig_show_messagebox.connect(self._do_show_messagebox)
        self.trimming_mgr.sig_run_on_gui.connect(self._do_run_on_gui)
        self.trimming_mgr.sig_duration_fetched.connect(self._on_duration_fetched)
        self.trimming_mgr.sig_local_duration_fetched.connect(self._on_local_duration_fetched)
        self.trimming_mgr.sig_preview_ready.connect(self._on_preview_ready)
        self.trimming_mgr.sig_fetch_done.connect(self._on_fetch_done)

        # Clean up leftover files from previous self-updates
        self._cleanup_old_updates()

        # Check dependencies and detect HW encoder in background (avoid startup freeze)
        self.dependencies_ok = True  # assume ok until check completes
        self.hw_encoder = None
        self.encoding = EncodingService(
            ffmpeg_path=getattr(self, "ffmpeg_path", "ffmpeg"),
            hw_encoder=None,
        )
        self.clipboard_mgr = ClipboardManager(thread_pool=self.thread_pool)
        self.clipboard_mgr.sig_clipboard_progress.connect(self._do_clipboard_progress)
        self.clipboard_mgr.sig_clipboard_status.connect(self._do_clipboard_status)
        self.clipboard_mgr.sig_clipboard_total.connect(self._do_clipboard_total)
        self.clipboard_mgr.sig_update_url_status.connect(self._do_update_url_status)
        self.clipboard_mgr.sig_add_url_to_list.connect(self._do_add_url_to_list)
        self.clipboard_mgr.sig_show_messagebox.connect(self._do_show_messagebox)
        self.clipboard_mgr.sig_run_on_gui.connect(self._do_run_on_gui)
        self.clipboard_mgr.sig_downloads_finished.connect(self._on_clipboard_downloads_finished)

        self.download_mgr = DownloadManager(
            ytdlp_path=getattr(self, "ytdlp_path", "yt-dlp"),
            ffmpeg_path=getattr(self, "ffmpeg_path", "ffmpeg"),
            ffprobe_path=getattr(self, "ffprobe_path", "ffprobe"),
            encoding=self.encoding,
            thread_pool=self.thread_pool,
        )
        self.download_mgr.sig_update_progress.connect(self._do_update_progress)
        self.download_mgr.sig_update_status.connect(self._do_update_status)
        self.download_mgr.sig_reset_buttons.connect(self._do_reset_buttons)
        self.download_mgr.sig_show_messagebox.connect(self._do_show_messagebox)
        self.download_mgr.sig_run_on_gui.connect(self._do_run_on_gui)
        self.download_mgr.sig_enable_upload.connect(self._enable_upload_button)

        self.update_mgr = UpdateManager(
            ytdlp_path=getattr(self, "ytdlp_path", "yt-dlp"),
            thread_pool=self.thread_pool,
        )
        self.update_mgr.sig_show_update_dialog.connect(self._show_update_dialog)
        self.update_mgr.sig_show_ytdlp_update.connect(self._show_ytdlp_update_dialog)
        self.update_mgr.sig_show_messagebox.connect(self._do_show_messagebox)
        self.update_mgr.sig_update_status.connect(self._do_update_status)
        self.update_mgr.sig_run_on_gui.connect(self._do_run_on_gui)
        self.update_mgr.sig_request_close.connect(self.close)

        self.thread_pool.submit(self._init_dependencies_async)

        # Thread safety locks (download_lock → download_mgr; others → respective managers)
        self.config_lock = threading.Lock()

        # Clipboard Mode (state in clipboard_mgr, created after thread_pool)
        self.clipboard_url_widgets = {}
        self.klipper_interface = None
        self._clipboard_batch_process = None

        # Theme mode
        self.current_theme = self._load_theme_preference()

        # Uploader tab variables (state in upload_mgr)
        self.uploader_current_index = 0

        # Load persisted clipboard URLs
        self._load_clipboard_urls()

        # Try to connect to KDE Klipper
        if DBUS_AVAILABLE:
            try:
                bus = dbus.SessionBus()
                klipper = bus.get_object("org.kde.klipper", "/klipper")
                self.klipper_interface = dbus.Interface(klipper, "org.kde.klipper.klipper")
                logger.info("Connected to KDE Klipper clipboard manager")
            except Exception as e:
                logger.info(f"KDE Klipper not available: {e}")
                self.klipper_interface = None

        # Create clipboard download directory
        Path(self.clipboard_mgr.clipboard_download_path).mkdir(parents=True, exist_ok=True)

        # ---------- connect signals to slots ----------
        self.sig_update_progress.connect(self._do_update_progress)
        self.sig_update_status.connect(self._do_update_status)
        self.sig_reset_buttons.connect(self._do_reset_buttons)
        self.sig_show_messagebox.connect(self._do_show_messagebox)
        self.sig_set_mode_label.connect(self._do_set_mode_label)
        self.sig_set_video_info.connect(self._do_set_video_info)
        self.sig_set_filesize_label.connect(self._do_set_filesize_label)
        self.sig_run_on_gui.connect(self._do_run_on_gui)

        # ── Template GUI construction flow ───────────────────────
        self._build_groups()
        self._tabs = QTabWidget()
        self._build_tabs()

        # Spacer tab (visual gap before Settings / Help)
        self._tabs.addTab(QWidget(), "")
        _spacer_idx = self._tabs.count() - 1
        self._tabs.setTabEnabled(_spacer_idx, False)
        self._tabs.tabBar().setTabButton(
            _spacer_idx, self._tabs.tabBar().ButtonPosition.LeftSide, None
        )
        self._tabs.tabBar().setTabButton(
            _spacer_idx, self._tabs.tabBar().ButtonPosition.RightSide, None
        )

        self._build_settings_tab()
        self._build_help_tab()

        central = QWidget()
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self._tabs)
        self.setCentralWidget(central)

        self._load()
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
        self._preview_debounce_timer.timeout.connect(self.update_previews)

        # File size fetch debounce timer
        self._size_fetch_timer = QTimer(self)
        self._size_fetch_timer.setSingleShot(True)
        self._size_fetch_timer.setInterval(1000)
        self._size_fetch_timer.timeout.connect(self._auto_fetch_file_size)

        # Clipboard URL persistence debounce timer (coalesces rapid writes)
        self._clipboard_save_timer = QTimer(self)
        self._clipboard_save_timer.setSingleShot(True)
        self._clipboard_save_timer.setInterval(2000)
        self._clipboard_save_timer.timeout.connect(self._save_clipboard_urls)

        # Check for updates on startup if enabled
        if self._load_auto_check_updates_setting():
            QTimer.singleShot(
                2000,
                lambda: self.thread_pool.submit(self.update_mgr._check_for_updates, True),
            )

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

    # ══════════════════════════════════════════════════════════════
    #  Widget builder helpers (template convention)
    # ══════════════════════════════════════════════════════════════

    def _group(self, title: str, rows: list, tooltip: str = "") -> QGroupBox:
        box = QGroupBox(title)
        vbox = QVBoxLayout()
        for row in rows:
            if isinstance(row, QHBoxLayout):
                vbox.addLayout(row)
            elif isinstance(row, QWidget):
                vbox.addWidget(row)
        box.setLayout(vbox)
        if tooltip:
            box.setTitle(f"{title}  \u24d8")
            box.setToolTip(tooltip)
        return box

    def _int_row(self, key: str, label: str, lo: int, hi: int) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addStretch()
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setFixedWidth(90)
        self.widgets[key] = spin
        row.addWidget(spin)
        return row

    def _float_row(
        self, key: str, label: str, lo: float, hi: float, suffix: str = ""
    ) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addStretch()
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setDecimals(2)
        spin.setSingleStep(0.1)
        spin.setFixedWidth(90)
        if suffix:
            spin.setSuffix(f" {suffix}")
        self.widgets[key] = spin
        row.addWidget(spin)
        return row

    def _pct_row(self, key: str, label: str, lo: float, hi: float) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addStretch()
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setDecimals(1)
        spin.setSingleStep(1.0)
        spin.setSuffix(" %")
        spin.setFixedWidth(100)
        self.widgets[key] = spin
        row.addWidget(spin)
        return row

    def _bool_row(self, key: str, label: str) -> QHBoxLayout:
        row = QHBoxLayout()
        cb = QCheckBox(label)
        self.widgets[key] = cb
        row.addWidget(cb)
        row.addStretch()
        return row

    def _combo_row(self, key: str, label: str, items: list[str]) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addStretch()
        combo = QComboBox()
        combo.addItems(items)
        combo.setFixedWidth(120)
        self.widgets[key] = combo
        row.addWidget(combo)
        return row

    def _label_row(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: gray; font-size: 11px;")
        lbl.setWordWrap(True)
        return lbl

    # ------------------------------------------------------------------
    #  Template GUI construction methods
    # ------------------------------------------------------------------

    def _build_groups(self):
        """Build content pages for each tab. Store as self._*_page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        self.setup_clipboard_mode_ui(layout)
        layout.addStretch()
        self._clipboard_page = page

        page = QWidget()
        layout = QVBoxLayout(page)
        self._setup_trimmer_ui(layout)
        layout.addStretch()
        self._trimmer_page = page

        page = QWidget()
        layout = QVBoxLayout(page)
        self.setup_uploader_ui(layout)
        layout.addStretch()
        self._uploader_page = page

    def _build_tabs(self):
        """Add content tabs. Settings/Help tabs are added separately."""
        self._tabs.addTab(self._scroll_tab(self._clipboard_page), "Clipboard Mode")
        self._tabs.addTab(self._scroll_tab(self._trimmer_page), "Trimmer")
        self._tabs.addTab(self._scroll_tab(self._uploader_page), "Uploader")
        self._tabs.currentChanged.connect(self._on_tab_changed)

    def _add_tab(self, name: str, groups: list) -> None:
        """Add a scrollable tab containing QGroupBox widgets (template convention)."""
        page = QWidget()
        layout = QVBoxLayout(page)
        for g in groups:
            layout.addWidget(g)
        layout.addStretch()
        self._tabs.addTab(self._scroll_tab(page), name)

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
        self.url_entry.setPlaceholderText("Paste URL or browse a local file")
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
        self.quality_combo.addItems(
            ["1440", "1080", "720", "480", "360", "240", "none (Audio only)"]
        )
        self.quality_combo.setCurrentText("480")
        self.quality_combo.currentIndexChanged.connect(self.on_quality_change)
        quality_row.addWidget(self.quality_combo)

        self.audio_only_check = QCheckBox("Audio only")
        self.audio_only_check.stateChanged.connect(self._on_audio_only_toggle)
        quality_row.addWidget(self.audio_only_check)
        quality_row.addStretch()
        layout.addLayout(quality_row)

        # --- Volume section (below quality, above trim) ---
        vol_row = QHBoxLayout()
        vol_lbl = QLabel("Volume:")
        vol_lbl.setStyleSheet(vol_lbl.styleSheet() + "font-size: 11px; font-weight: bold;")
        vol_row.addWidget(vol_lbl)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 200)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(150)
        self.volume_slider.valueChanged.connect(self._on_volume_slider_change)
        vol_row.addWidget(self.volume_slider)

        self.volume_entry = QLineEdit("100")
        self.volume_entry.setFixedWidth(50)
        self.volume_entry.returnPressed.connect(self._on_volume_entry_change)
        vol_row.addWidget(self.volume_entry)

        self.volume_label = QLabel("%")
        self.volume_label.setStyleSheet(self.volume_label.styleSheet() + "font-size: 9px;")
        vol_row.addWidget(self.volume_label)

        self.reset_volume_btn = QPushButton("Reset to 100%")
        self.reset_volume_btn.setFixedWidth(100)
        self.reset_volume_btn.clicked.connect(self.reset_volume)
        vol_row.addWidget(self.reset_volume_btn)
        vol_row.addStretch()
        layout.addLayout(vol_row)

        # --- separator ---
        layout.addWidget(self._hsep())

        # --- Trim Video header (centered, prominent) ---
        tv_lbl = QLabel("Trim Video")
        tv_lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        tv_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(tv_lbl)

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

        # Keep below 10MB (below trim checkbox)
        tenm_row = QHBoxLayout()
        tenm_row.setContentsMargins(20, 0, 0, 0)
        self.keep_below_10mb_check = QCheckBox("Keep video below 10MB")
        self.keep_below_10mb_check.stateChanged.connect(self._on_keep_below_10mb_toggle)
        tenm_row.addWidget(self.keep_below_10mb_check)
        tenm_row.addStretch()
        layout.addLayout(tenm_row)

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
        _start_lbl = QLabel("Start Time:")
        _start_lbl.setFixedWidth(70)
        start_row.addWidget(_start_lbl)
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
        _end_lbl = QLabel("End Time:")
        _end_lbl.setFixedWidth(70)
        end_row.addWidget(_end_lbl)
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

        # --- Download / Stop / Speed limit ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.download_btn = _colored_btn("Download/Trim", BLUE)
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
        fn_row.addStretch()
        layout.addLayout(fn_row)
        fn_hint = QLabel("(optional - leave empty for auto generated name)")
        fn_hint.setStyleSheet("color: gray; font-size: 8pt;")
        fn_hint.setContentsMargins(100, 0, 0, 0)
        layout.addWidget(fn_hint)

        # --- Upload to Catbox.moe section ---
        layout.addWidget(self._hsep())
        upl_header = QLabel("Upload to Streaming Site")
        upl_header.setStyleSheet("font-size: 14px; font-weight: bold;")
        upl_header.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(upl_header)

        upl_row = QHBoxLayout()
        upl_row.addStretch()
        self.upload_btn = _colored_btn("Upload to Catbox.moe", GREEN)
        self.upload_btn.setEnabled(False)
        self.upload_btn.clicked.connect(self.start_upload)
        upl_row.addWidget(self.upload_btn)

        self.view_history_btn = QPushButton("View Upload History")
        self.view_history_btn.clicked.connect(self.view_upload_history)
        upl_row.addWidget(self.view_history_btn)
        upl_row.addStretch()
        layout.addLayout(upl_row)

        self.upload_status_label = QLabel("")
        self.upload_status_label.setStyleSheet("color: green; font-size: 9pt;")
        self.upload_status_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.upload_status_label)

        # Auto-upload checkbox (centered, tighter to buttons above)
        self.auto_upload_check = QCheckBox("Auto-upload after download/trim completes")
        self.auto_upload_check.setContentsMargins(0, -2, 0, 0)
        layout.addWidget(self.auto_upload_check, alignment=Qt.AlignmentFlag.AlignHCenter)

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
        self.clipboard_quality_combo.addItems(
            ["1440", "1080", "720", "480", "360", "240", "none (Audio only)"]
        )
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
            "Full Playlist Download (download all videos when given a playlist link)"
        )
        pl_row.addWidget(self.clipboard_full_playlist_check)
        pl_row.addStretch()
        layout.addLayout(pl_row)

        # Audio only toggle
        audio_row = QHBoxLayout()
        audio_row.setContentsMargins(20, 0, 0, 0)
        self.clipboard_audio_only_check = QCheckBox("Audio only, no video")
        self.clipboard_audio_only_check.stateChanged.connect(self._on_clipboard_audio_only_toggle)
        audio_row.addWidget(self.clipboard_audio_only_check)
        audio_row.addStretch()
        layout.addLayout(audio_row)

        # Output folder
        layout.addWidget(self._hsep())
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Save to:"))
        self.clipboard_path_label = QLabel(self.clipboard_mgr.clipboard_download_path)
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
        ctrl_row.addStretch()
        self.clipboard_download_btn = _colored_btn("Download All", BLUE)
        self.clipboard_download_btn.setEnabled(False)
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
        self.uploader_upload_btn = _colored_btn("Upload to Catbox.moe", GREEN)
        self.uploader_upload_btn.setEnabled(False)
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
    def _build_settings_tab(self):
        """Build all widgets for the Settings tab (compact, SwornTweaks-style)."""
        page = QWidget()
        layout = QVBoxLayout(page)

        # Version header
        ver_lbl = QLabel(f"YoutubeDownloader v{APP_VERSION}")
        ver_lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(ver_lbl)

        gh_lbl = QLabel(
            f'<a href="https://github.com/{GITHUB_REPO}" '
            f'style="color: gray;">github.com/{GITHUB_REPO}</a>'
        )
        gh_lbl.setStyleSheet("color: gray; font-size: 11px;")
        gh_lbl.setOpenExternalLinks(True)
        layout.addWidget(gh_lbl)
        layout.addSpacing(12)

        # Action buttons
        self.check_updates_btn = QPushButton("Check for Updates")
        self.check_updates_btn.clicked.connect(
            lambda: self.thread_pool.submit(self.update_mgr._check_for_updates, False)
        )
        layout.addWidget(self.check_updates_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        readme_btn = _colored_btn("Readme", BLUE)
        readme_btn.clicked.connect(
            lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}#readme")
        )
        layout.addWidget(readme_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addSpacing(12)

        # Settings checkboxes
        self.auto_check_updates_check = QCheckBox("Check for updates on startup")
        self.auto_check_updates_check.setChecked(self._load_auto_check_updates_setting())
        self.auto_check_updates_check.stateChanged.connect(self._save_auto_check_updates_setting)
        layout.addWidget(self.auto_check_updates_check)

        self.dark_mode_check = QCheckBox("Dark Mode")
        self.dark_mode_check.setChecked(self.current_theme == "dark")
        self.dark_mode_check.stateChanged.connect(self._toggle_theme)
        layout.addWidget(self.dark_mode_check)

        layout.addSpacing(8)

        # Takodachi image
        try:
            img_path = self._get_resource_path("takodachi.webp")
            if os.path.exists(img_path):
                qimg = QImage(img_path)
                if not qimg.isNull():
                    pix = QPixmap.fromImage(
                        qimg.scaled(
                            120,
                            120,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                    takodachi_label = QLabel()
                    takodachi_label.setPixmap(pix)
                    takodachi_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    layout.addWidget(takodachi_label)
        except Exception as e:
            logger.error(f"Error loading settings image: {e}")

        by_lbl = QLabel("by JJ")
        by_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        by_lbl.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(by_lbl)

        layout.addStretch()
        self._tabs.addTab(self._scroll_tab(page), "Settings")

    # ------------------------------------------------------------------
    #  Help tab construction
    # ------------------------------------------------------------------
    def _build_help_tab(self):
        """Build all widgets for the Help tab (SwornTweaks-style)."""
        page = QWidget()
        layout = QVBoxLayout(page)

        hdr = QLabel("YoutubeDownloader Help")
        hdr.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(hdr)

        # Button row — accent-colored like SwornTweaks
        btn_row = QHBoxLayout()
        readme_btn = _colored_btn("Readme", BLUE)
        readme_btn.clicked.connect(
            lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}#readme")
        )
        btn_row.addWidget(readme_btn)

        self._report_bug_btn = _colored_btn("Report Bug", YELLOW, text_color="#1e1e1e")
        self._report_bug_btn.clicked.connect(
            lambda: webbrowser.open(
                f"https://github.com/{GITHUB_REPO}/issues/new?template=bug_report.yml"
            )
        )
        btn_row.addWidget(self._report_bug_btn)

        log_btn = QPushButton("Open Log Folder")
        log_btn.clicked.connect(lambda: webbrowser.open(str(APP_DATA_DIR)))
        btn_row.addWidget(log_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addSpacing(6)

        # Help sections with thin separators like SwornTweaks
        sections = [
            (
                "Reporting Bugs",
                'Click "Report Bug" above to open the bug report form on GitHub. '
                'To help us find the issue, click "Open Log Folder" below and attach the '
                "youtubedownloader.log file to your report.",
            ),
            (
                "Clipboard Mode",
                "Copy any YouTube URL (Ctrl+C) and it will automatically appear in the detected "
                'URLs list. You can download them individually or click "Download All" to batch '
                'download. Enable "Auto-download" to start downloading as soon as a URL is detected.',
            ),
            (
                "Trimmer",
                "Paste a YouTube URL and select your desired quality. To trim a video, enable "
                '"Enable video trimming", click "Fetch Video Duration", then use the sliders or '
                "time fields to set start and end points. Frame previews show exactly what you're "
                "selecting.",
            ),
            (
                "Uploader",
                'Upload local video or audio files to Catbox.moe for easy sharing. Click "Add Files" '
                'to select files, then "Upload to Catbox.moe" to upload. URLs are automatically copied '
                "to your clipboard. You can also enable auto-upload in the Trimmer tab to upload after "
                "each download.",
            ),
            ("Settings", "Toggle dark mode, check for updates, and view app info."),
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

        layout.addStretch()
        self._tabs.addTab(self._scroll_tab(page), "Help")

    # ------------------------------------------------------------------
    #  Theme management
    # ------------------------------------------------------------------
    def _apply_theme(self):
        """Apply the current QSS theme to the entire application."""
        if self.current_theme == "dark":
            qss = _build_dark_style()
        else:
            qss = _LIGHT_STYLE
        QApplication.instance().setStyleSheet(qss)

        # Dark title bar on Windows
        _set_dark_title_bar(self, dark=(self.current_theme == "dark"))

        # Re-apply inline styles on preview labels based on theme
        colors = THEMES[self.current_theme]
        if hasattr(self, "start_preview_label"):
            self.start_preview_label.setStyleSheet(
                f"background: {colors['preview_bg']}; color: {colors['preview_fg']};"
            )
        if hasattr(self, "end_preview_label"):
            self.end_preview_label.setStyleSheet(
                f"background: {colors['preview_bg']}; color: {colors['preview_fg']};"
            )

        # Clipboard URL list scroll area background
        if hasattr(self, "clipboard_url_scroll"):
            self.clipboard_url_scroll.setStyleSheet(
                f"QScrollArea {{ border: 1px solid {colors['border']}; background: {colors['canvas_bg']}; }}"
            )
            self.clipboard_url_list_widget.setStyleSheet(f"background: {colors['canvas_bg']};")

        # Uploader file list
        if hasattr(self, "uploader_file_scroll"):
            self.uploader_file_scroll.setStyleSheet(
                f"QScrollArea {{ border: 1px solid {colors['border']}; background: {colors['canvas_bg']}; }}"
            )
            self.uploader_file_list_widget.setStyleSheet(f"background: {colors['canvas_bg']};")

    def _toggle_theme(self):
        """Toggle between light and dark theme."""
        self.current_theme = "dark" if self.current_theme == "light" else "light"
        # Keep checkbox in sync (if triggered programmatically)
        if hasattr(self, "dark_mode_check"):
            self.dark_mode_check.blockSignals(True)
            self.dark_mode_check.setChecked(self.current_theme == "dark")
            self.dark_mode_check.blockSignals(False)
        self._apply_theme()
        self._save_theme_preference()

    # ------------------------------------------------------------------
    #  closeEvent (replaces on_closing)
    # ------------------------------------------------------------------
    def closeEvent(self, event):
        """Handle window close with proper resource cleanup."""
        if self._updating:
            event.ignore()
            return
        logger.info("Application shutdown initiated...")

        # Cancel preview timer
        if hasattr(self, "_preview_debounce_timer") and self._preview_debounce_timer.isActive():
            self._preview_debounce_timer.stop()

        self._shutting_down = True
        self.download_mgr._shutting_down = True
        self.clipboard_mgr._shutting_down = True
        self.update_mgr._shutting_down = True

        # Stop clipboard timer
        if hasattr(self, "_clipboard_timer"):
            self._clipboard_timer.stop()

        # Flush any pending config writes
        if hasattr(self, "_config_save_timer") and self._config_save_timer.isActive():
            self._config_save_timer.stop()
            self._flush_config()

        # Save clipboard URLs before shutdown
        try:
            self._save_clipboard_urls()
        except Exception as e:
            logger.error(f"Error saving clipboard URLs: {e}")

        # Stop clipboard monitoring
        self.stop_clipboard_monitoring()

        # Stop clipboard downloads
        self.clipboard_mgr.clipboard_stop_event.set()

        # Force-kill any ongoing download process immediately (don't wait)
        with self.download_mgr.download_lock:
            process_to_cleanup = self.download_mgr.current_process
            self.download_mgr.is_downloading = False
            self.download_mgr.current_process = None

        if process_to_cleanup:
            logger.info("Force-killing active download process...")
            try:
                if process_to_cleanup.poll() is None:
                    process_to_cleanup.kill()
                if process_to_cleanup.stdout:
                    process_to_cleanup.stdout.close()
                if process_to_cleanup.stderr:
                    process_to_cleanup.stderr.close()
            except Exception as e:
                logger.error(f"Error killing process on exit: {e}")

        # Clean up temp files
        try:
            DownloadManager.cleanup_temp_files(self.temp_dir)
        except Exception as e:
            logger.error(f"Error cleaning temp files: {e}")

        # Clean up checkbox temp images
        if _checkbox_temp_dir and os.path.isdir(_checkbox_temp_dir):
            try:
                shutil.rmtree(_checkbox_temp_dir, ignore_errors=True)
            except Exception:
                pass

        # Shutdown thread pool
        logger.info("Shutting down thread pool...")
        try:
            self.thread_pool.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            self.thread_pool.shutdown(wait=False)
        except Exception as e:
            logger.error(f"Error shutting down thread pool: {e}")

        # Save window geometry
        try:
            self._save_config_key("window_geometry", self.saveGeometry().toHex().data().decode())
        except Exception as e:
            logger.error(f"Error saving window geometry: {e}")

        logger.info("Application shutdown complete")
        event.accept()

        # Force exit after a short delay — worker threads blocked on I/O
        # (e.g. subprocess pipe reads) can prevent Python from exiting
        # even after thread_pool.shutdown(wait=False).
        QTimer.singleShot(500, lambda: os._exit(0))

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
            status_label = widget_data.get("status_label")
            colors = {
                "pending": "gray",
                "downloading": "#ff8c00",
                "completed": "#00cc00",
                "failed": "#ff3333",
            }
            if status_label:
                status_label.setStyleSheet(
                    f"background: {colors.get(status, 'gray')}; border-radius: 6px; border: none;"
                )

    def _do_add_url_to_list(self, url: str):
        """Add a URL to the clipboard list (called on GUI thread via signal)."""
        self._add_url_to_clipboard_list(url)

    # ------------------------------------------------------------------
    #  Thread-safe helper (replaces _safe_after)
    # ------------------------------------------------------------------
    # -- Trimming manager signal slots --
    def _on_duration_fetched(self, duration, video_title):
        """Handle successful duration fetch from TrimmingManager."""
        self.video_duration = duration
        self.video_title = video_title or None
        self._update_duration_ui(video_title or None)
        url = self.url_entry.text().strip()
        self._fetch_file_size(url)

    def _on_local_duration_fetched(self, duration, video_title):
        """Handle successful local file duration fetch."""
        self.video_duration = duration
        self._update_duration_ui_local(video_title)

    def _on_preview_ready(self, image, position):
        """Handle preview frame ready from TrimmingManager.

        Receives a QImage (thread-safe) and converts to QPixmap on the GUI thread.
        """
        pixmap = QPixmap.fromImage(image)
        if position == "start":
            self.start_preview_image = pixmap
            self.start_preview_label.setPixmap(pixmap)
            self.start_preview_label.setText("")
        else:
            self.end_preview_image = pixmap
            self.end_preview_label.setPixmap(pixmap)
            self.end_preview_label.setText("")

    def _on_fetch_done(self):
        """Re-enable fetch button after duration fetch completes."""
        if self.trim_enabled_check.isChecked():
            self.fetch_duration_btn.setEnabled(True)

    def _on_clipboard_downloads_finished(self):
        """Handle clipboard download queue completion."""
        self._finish_clipboard_downloads()

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
        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(sys.executable)
            local_path = os.path.join(exe_dir, filename)
            if os.path.exists(local_path):
                return local_path
            bundle_dir = getattr(sys, "_MEIPASS", exe_dir)
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

    # ------------------------------------------------------------------
    #  Persistence methods (carried over from tkinter version)
    # ------------------------------------------------------------------
    def _load_clipboard_urls(self):
        """Load persisted clipboard URLs from previous session."""
        try:
            if CLIPBOARD_URLS_FILE.exists():
                with open(CLIPBOARD_URLS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not isinstance(data, dict):
                        raise ValueError("Invalid clipboard URLs file format: expected dict")
                    if "urls" not in data:
                        raise ValueError("Invalid clipboard URLs file format: missing 'urls' key")
                    if not isinstance(data["urls"], list):
                        raise ValueError(
                            "Invalid clipboard URLs file format: 'urls' must be a list"
                        )
                    self.persisted_clipboard_urls = data["urls"]
                    logger.info(
                        f"Loaded {len(self.persisted_clipboard_urls)} persisted clipboard URLs"
                    )
            else:
                self.persisted_clipboard_urls = []
        except Exception as e:
            logger.error(f"Error loading clipboard URLs: {e}")
            self.persisted_clipboard_urls = []

    def _save_clipboard_urls(self):
        """Save clipboard URLs to file for persistence between sessions."""
        try:
            CLIPBOARD_URLS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with self.clipboard_mgr.clipboard_lock:
                urls_to_save = [
                    {"url": item["url"], "status": item["status"]}
                    for item in self.clipboard_mgr.clipboard_url_list
                    if item["status"] in ["pending", "failed"]
                ]
            with open(CLIPBOARD_URLS_FILE, "w", encoding="utf-8") as f:
                json.dump({"urls": urls_to_save}, f, indent=2)
            logger.info(f"Saved {len(urls_to_save)} clipboard URLs")
        except Exception as e:
            logger.error(f"Error saving clipboard URLs: {e}")

    def _restore_clipboard_urls(self):
        """Restore persisted URLs to the UI (called after setup_ui)."""
        if hasattr(self, "persisted_clipboard_urls") and self.persisted_clipboard_urls:
            for url_data in self.persisted_clipboard_urls:
                url = url_data.get("url", "")
                status = url_data.get("status", "pending")
                url_exists = url and url not in self.clipboard_url_widgets
                if url_exists:
                    self._add_url_to_clipboard_list(url)
                    if status == "failed":
                        self._update_url_status(url, "failed")
            logger.info(f"Restored {len(self.persisted_clipboard_urls)} URLs to clipboard list")
            self.persisted_clipboard_urls = None

    def _load_auto_check_updates_setting(self):
        """Load auto-check updates setting from config."""
        return self._config.get("auto_check_updates", True)

    def _save_config_key(self, key, value):
        """Update a single key in the config file (debounced to avoid GUI stall)."""
        with self.config_lock:
            self._config[key] = value
        if not hasattr(self, "_config_save_timer"):
            self._config_save_timer = QTimer(self)
            self._config_save_timer.setSingleShot(True)
            self._config_save_timer.setInterval(500)
            self._config_save_timer.timeout.connect(self._flush_config)
        self._config_save_timer.start()

    def _flush_config(self):
        """Write the in-memory config dict to disk."""
        with self.config_lock:
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(self._config, f, indent=2)
            except Exception as e:
                logger.error(f"Error saving config: {e}")

    def _save_auto_check_updates_setting(self):
        """Save auto-check updates setting to config."""
        self._save_config_key("auto_check_updates", self.auto_check_updates_check.isChecked())

    def _load(self):
        """Load all persisted settings (template hook).

        NOTE: _load_theme_preference() and _load_clipboard_urls() are called
        earlier in __init__ (before UI construction) because they set state
        needed by the UI builders. _load() is a no-op here to satisfy the
        template convention; the actual loading is already done.
        """

    def _load_theme_preference(self):
        """Load saved theme preference from config."""
        theme = self._config.get("theme", "dark")
        return theme if theme in THEMES else "dark"

    def _save_theme_preference(self):
        """Save theme preference to config."""
        self._save_config_key("theme", self.current_theme)

    # ------------------------------------------------------------------
    #  Dependency / init methods (carried over, needed by __init__)
    # ------------------------------------------------------------------
    def _get_bundled_executable(self, name):
        """Get path to bundled executable (ffmpeg/ffprobe/yt-dlp) if available."""
        if getattr(sys, "frozen", False):
            if sys.platform == "win32":
                exe_name = f"{name}.exe"
            else:
                exe_name = name
            exe_dir = os.path.dirname(sys.executable)
            local_path = os.path.join(exe_dir, exe_name)
            if os.path.exists(local_path):
                logger.info(f"Using local {name}: {local_path}")
                return local_path
            bundle_dir = getattr(sys, "_MEIPASS", exe_dir)
            bundled_path = os.path.join(bundle_dir, exe_name)
            if os.path.exists(bundled_path):
                logger.info(f"Using bundled {name}: {bundled_path}")
                return bundled_path
        else:
            script_dir = Path(__file__).parent
            if sys.platform == "win32":
                venv_subdir = "Scripts"
                exe_name = f"{name}.exe"
            else:
                venv_subdir = "bin"
                exe_name = name
            venv_path = script_dir / "venv" / venv_subdir / exe_name
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
                result = subprocess.run(
                    [self.ytdlp_path, "--version"],
                    capture_output=True,
                    timeout=DEPENDENCY_CHECK_TIMEOUT,
                    **_subprocess_kwargs,
                )
                version = result.stdout.decode("utf-8", errors="replace").strip()
                if version:
                    logger.info(f"yt-dlp version: {version}")
                else:
                    logger.info(f"yt-dlp is available at: {self.ytdlp_path}")
            elif shutil.which(self.ytdlp_path):
                result = subprocess.run(
                    [self.ytdlp_path, "--version"],
                    capture_output=True,
                    timeout=DEPENDENCY_CHECK_TIMEOUT,
                    **_subprocess_kwargs,
                )
                logger.info(
                    f"yt-dlp version: {result.stdout.decode('utf-8', errors='replace').strip()}"
                )
            else:
                logger.error(f"yt-dlp not found at: {self.ytdlp_path}")
                return False

            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                timeout=DEPENDENCY_CHECK_TIMEOUT,
                **_subprocess_kwargs,
            )
            if result.returncode == 0:
                logger.info(f"ffmpeg is available at: {self.ffmpeg_path}")
            else:
                logger.error("ffmpeg check failed")
                return False

            result = subprocess.run(
                [self.ffprobe_path, "-version"],
                capture_output=True,
                timeout=DEPENDENCY_CHECK_TIMEOUT,
                **_subprocess_kwargs,
            )
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
        for encoder in ("h264_amf", "h264_nvenc"):
            try:
                probe_out = os.path.join(tempfile.gettempdir(), "ytdl_hwprobe.mp4")
                cmd = [
                    self.ffmpeg_path,
                    "-hide_banner",
                    "-y",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=64x64:rate=25:duration=1",
                    "-vf",
                    "format=nv12",
                    "-frames:v",
                    "10",
                    "-c:v",
                    encoder,
                    probe_out,
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=10, **_subprocess_kwargs)
                try:
                    os.remove(probe_out)
                except OSError:
                    pass
                if result.returncode == 0:
                    logger.info(f"Hardware encoder available: {encoder}")
                    return encoder
                else:
                    stderr = result.stderr.decode("utf-8", errors="replace").strip()
                    logger.info(f"Hardware encoder {encoder} not available: {stderr[-200:]}")
            except (subprocess.TimeoutExpired, OSError) as e:
                logger.info(f"Hardware encoder {encoder} probe failed: {e}")
        logger.info("No hardware encoder found, using libx264")
        return None

    def _init_dependencies_async(self):
        """Check dependencies and detect HW encoder in background thread."""
        deps_ok = self.check_dependencies()
        if not deps_ok:
            logger.warning("Dependencies check failed at startup")
        hw_enc = self._detect_hw_encoder()

        # Capture paths discovered during check_dependencies
        ytdlp = self.ytdlp_path
        ffmpeg = self.ffmpeg_path
        ffprobe = self.ffprobe_path

        def _apply_on_gui():
            self.dependencies_ok = deps_ok
            self.hw_encoder = hw_enc
            self.encoding.hw_encoder = hw_enc
            self.encoding.ffmpeg_path = ffmpeg
            self.update_mgr.ytdlp_path = ytdlp
            self.download_mgr.ytdlp_path = ytdlp
            self.download_mgr.ffmpeg_path = ffmpeg
            self.download_mgr.ffprobe_path = ffprobe

        self.update_mgr.sig_run_on_gui.emit(_apply_on_gui)

    def _init_temp_directory(self):
        """Initialize temp directory and schedule cleanup of orphaned ones."""
        self.temp_dir = tempfile.mkdtemp(prefix="ytdl_preview_")
        # Defer old-dir cleanup off the GUI thread to avoid blocking startup
        QTimer.singleShot(0, self._cleanup_old_temp_dirs)

    def _cleanup_old_temp_dirs(self):
        """Remove orphaned temp directories from previous crashes (deferred)."""
        temp_base = tempfile.gettempdir()
        old_dirs = glob.glob(os.path.join(temp_base, "ytdl_preview_*"))
        for old_dir in old_dirs:
            if old_dir == self.temp_dir:
                continue
            try:
                dir_age = time.time() - os.path.getmtime(old_dir)
                if dir_age > TEMP_DIR_MAX_AGE:
                    shutil.rmtree(old_dir, ignore_errors=True)
            except OSError:
                pass

    def _cleanup_old_updates(self):
        """Remove leftover files from previous self-updates."""
        try:
            if getattr(sys, "frozen", False):
                exe_dir = Path(sys.executable).parent
                for pattern in ("*.old", "_update_*.bat", "_update_*.sh"):
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

    def _do_run_on_gui(self, fn):
        """Execute a callable on the GUI thread (signal slot)."""
        fn()

    def _safe_after(self, delay, callback):
        """Schedule *callback* on the GUI thread.

        Uses a signal to reliably post to the GUI event loop from any thread
        (worker threads lack their own Qt event loop, so QTimer.singleShot
        fired from them may never execute).

        If *delay* > 0, the callback is wrapped in a QTimer.singleShot on the
        GUI thread so it fires after the requested milliseconds.
        """
        if self._shutting_down:
            return
        if delay > 0:
            self.sig_run_on_gui.emit(lambda: QTimer.singleShot(delay, callback))
        else:
            self.sig_run_on_gui.emit(callback)

    # ==================================================================
    #  CLIPBOARD CALLBACKS
    # ==================================================================

    def start_clipboard_monitoring(self):
        """Start clipboard monitoring using QTimer polling."""
        with self.clipboard_mgr.clipboard_lock:
            if self.clipboard_mgr.clipboard_monitoring:
                return
            self.clipboard_mgr.clipboard_monitoring = True
            logger.info("Clipboard monitoring started (QTimer polling)")
            try:
                content = QApplication.clipboard().text()
                self.clipboard_mgr.clipboard_last_content = content.strip() if content else ""
            except Exception:
                self.clipboard_mgr.clipboard_last_content = ""
        self._clipboard_timer.start()

    def stop_clipboard_monitoring(self):
        """Stop clipboard monitoring."""
        with self.clipboard_mgr.clipboard_lock:
            if not self.clipboard_mgr.clipboard_monitoring:
                return
            self.clipboard_mgr.clipboard_monitoring = False
            logger.info("Clipboard monitoring stopped")
        self._clipboard_timer.stop()

    def _detect_clipboard_backend(self) -> str:
        """Probe clipboard backends and return the name of the first working one."""
        if self.klipper_interface:
            try:
                self.klipper_interface.getClipboardContents()
                logger.info("Clipboard backend: klipper")
                return "klipper"
            except Exception:
                pass
        if PYPERCLIP_AVAILABLE:
            try:
                pyperclip.paste()
                logger.info("Clipboard backend: pyperclip")
                return "pyperclip"
            except Exception:
                pass
        try:
            QApplication.clipboard().text()
            logger.info("Clipboard backend: qt")
            return "qt"
        except Exception:
            pass
        logger.warning("No clipboard backend available")
        return "qt"  # fallback even if probe failed

    def _read_clipboard_content(self) -> str | None:
        """Read clipboard using the detected backend."""
        backend = getattr(self, "_clipboard_backend", None)
        if backend is None:
            self._clipboard_backend = self._detect_clipboard_backend()
            backend = self._clipboard_backend

        try:
            if backend == "klipper" and self.klipper_interface:
                return str(self.klipper_interface.getClipboardContents())
            elif backend == "pyperclip" and PYPERCLIP_AVAILABLE:
                return pyperclip.paste()
            else:
                return QApplication.clipboard().text()
        except Exception:
            return None

    def _poll_clipboard(self):
        """Poll clipboard for new YouTube URLs (called by QTimer)."""
        with self.clipboard_mgr.clipboard_lock:
            if not self.clipboard_mgr.clipboard_monitoring:
                return

        clipboard_content = None

        try:
            clipboard_content = self._read_clipboard_content()

            # Normalize
            if clipboard_content:
                clipboard_content = clipboard_content.strip()

            if clipboard_content and clipboard_content != self.clipboard_mgr.clipboard_last_content:
                self.clipboard_mgr.clipboard_last_content = clipboard_content

                is_valid, message = utils.validate_youtube_url(clipboard_content)
                logger.info(
                    f"Clipboard changed: {clipboard_content[:80]}"
                    if is_valid
                    else "Clipboard changed (not a YouTube URL)"
                )

                if is_valid:
                    url_exists = clipboard_content in self.clipboard_url_widgets

                    if not url_exists:
                        self._add_url_to_clipboard_list(clipboard_content)
                        logger.info(f"New YouTube URL detected and added: {clipboard_content}")

                        if self.clipboard_auto_download_check.isChecked():
                            logger.info(
                                f"Auto-download enabled, starting download: {clipboard_content}"
                            )
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
        status_label.setStyleSheet("background: gray; border-radius: 6px; border: none;")
        row_layout.addWidget(status_label)

        # URL text
        url_display = url if len(url) <= 60 else url[:57] + "..."
        url_label = QLabel(url_display)
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
            "url": url,
            "status": "pending",
            "widget": url_frame,
            "status_label": status_label,
        }

        with self.clipboard_mgr.clipboard_lock:
            # Cap the list to prevent unbounded memory growth
            if len(self.clipboard_mgr.clipboard_url_list) >= 500:
                oldest = self.clipboard_mgr.clipboard_url_list.pop(0)
                self.clipboard_url_widgets.pop(oldest["url"], None)
                if oldest.get("widget"):
                    oldest["widget"].deleteLater()
            self.clipboard_mgr.clipboard_url_list.append(url_data)
            self.clipboard_url_widgets[url] = url_data
            has_urls = len(self.clipboard_mgr.clipboard_url_list) > 0

        self._update_clipboard_url_count()
        is_downloading = not self.clipboard_mgr.clipboard_stop_event.is_set()
        if has_urls and not is_downloading:
            self.clipboard_download_btn.setEnabled(True)

        # Schedule debounced persistence write
        self._clipboard_save_timer.start()

    def _remove_url_from_list(self, url):
        """Remove URL from clipboard list."""
        widget_to_destroy = None
        list_is_empty = False

        with self.clipboard_mgr.clipboard_lock:
            for i, item in enumerate(self.clipboard_mgr.clipboard_url_list):
                if item["url"] == url:
                    widget_to_destroy = item["widget"]
                    self.clipboard_mgr.clipboard_url_list.pop(i)
                    if url in self.clipboard_url_widgets:
                        del self.clipboard_url_widgets[url]
                    list_is_empty = len(self.clipboard_mgr.clipboard_url_list) == 0
                    break

        if widget_to_destroy:
            widget_to_destroy.deleteLater()
            self._update_clipboard_url_count()
            if list_is_empty:
                self.clipboard_download_btn.setEnabled(False)
            logger.info(f"Removed URL: {url}")
            self._clipboard_save_timer.start()

    def clear_all_clipboard_urls(self):
        """Clear all URLs from clipboard list."""
        is_downloading = not self.clipboard_mgr.clipboard_stop_event.is_set()
        if is_downloading:
            QMessageBox.warning(
                self,
                "Cannot Clear",
                "Cannot clear URLs while downloads are in progress.",
            )
            return

        with self.clipboard_mgr.clipboard_lock:
            widgets_to_destroy = [
                item["widget"]
                for item in self.clipboard_mgr.clipboard_url_list
                if item.get("widget")
            ]
            self.clipboard_mgr.clipboard_url_list.clear()
            self.clipboard_url_widgets.clear()

        for widget in widgets_to_destroy:
            widget.deleteLater()

        self._update_clipboard_url_count()
        self.clipboard_download_btn.setEnabled(False)
        logger.info("Cleared all clipboard URLs")
        self._clipboard_save_timer.start()

    def _update_clipboard_url_count(self):
        """Update URL count label."""
        with self.clipboard_mgr.clipboard_lock:
            count = len(self.clipboard_mgr.clipboard_url_list)
        s = "s" if count != 1 else ""
        self.clipboard_url_count_label.setText(f"({count} URL{s})")

    def _update_url_status(self, url, status):
        """Update visual status of URL: pending (gray), downloading (blue),
        completed (green), failed (red)."""
        if url in self.clipboard_url_widgets:
            item = self.clipboard_url_widgets[url]
            status_label = item.get("status_label")

            color_map = {
                "pending": "gray",
                "downloading": "blue",
                "completed": "green",
                "failed": "red",
            }
            color = color_map.get(status, "gray")
            if status_label:
                status_label.setStyleSheet(
                    f"background: {color}; border-radius: 6px; border: none;"
                )

            with self.clipboard_mgr.clipboard_lock:
                for item_data in self.clipboard_mgr.clipboard_url_list:
                    if item_data["url"] == url:
                        item_data["status"] = status
                        break

    def start_clipboard_downloads(self):
        """Start downloading all pending URLs sequentially."""
        is_downloading = not self.clipboard_mgr.clipboard_stop_event.is_set()
        if is_downloading:
            return

        with self.clipboard_mgr.clipboard_lock:
            pending_urls = [
                item
                for item in self.clipboard_mgr.clipboard_url_list
                if item["status"] == "pending"
            ]

        if not pending_urls:
            QMessageBox.information(self, "No URLs", "No pending URLs to download.")
            return

        self.clipboard_mgr.clipboard_stop_event.clear()  # mark as downloading
        self.clipboard_download_btn.setEnabled(False)
        self.clipboard_stop_btn.setEnabled(True)

        total_count = len(pending_urls)
        self.clipboard_total_label.setText(f"Completed: 0/{total_count} videos")

        # Snapshot clipboard widget values on GUI thread for thread safety
        clip_state = {
            "quality": self.clipboard_quality_combo.currentText(),
            "full_playlist": self.clipboard_full_playlist_check.isChecked(),
            "audio_only": self.clipboard_audio_only_check.isChecked(),
            "speed_limit": self.clipboard_speed_limit_entry.text().strip(),
            "download_path": self.clipboard_mgr.clipboard_download_path,
        }
        logger.info(f"Starting clipboard batch download: {total_count} URLs")
        self.thread_pool.submit(self._process_clipboard_queue, clip_state)

    def _process_clipboard_queue(self, clip_state=None):
        """Process clipboard download queue (runs in worker thread).

        Uses a single yt-dlp --batch-file process for multiple non-playlist URLs.
        Falls back to per-URL processing for playlist URLs or single URLs.
        """
        with self.clipboard_mgr.clipboard_lock:
            pending_urls = [
                item["url"]
                for item in self.clipboard_mgr.clipboard_url_list
                if item["status"] == "pending"
            ]
        total_count = len(pending_urls)
        if not pending_urls:
            self._safe_after(0, self._finish_clipboard_downloads)
            return

        full_playlist = clip_state.get("full_playlist", False) if clip_state else False
        has_playlists = full_playlist and any(utils.is_playlist_url(u) for u in pending_urls)

        # Batch mode: multiple non-playlist URLs
        if len(pending_urls) > 1 and not has_playlists:
            self._process_clipboard_queue_batch(pending_urls, clip_state, total_count)
        else:
            # Per-URL fallback for single URL or playlist mode
            self._process_clipboard_queue_sequential(pending_urls, clip_state, total_count)

        self._safe_after(0, self._finish_clipboard_downloads)

    def _process_clipboard_queue_sequential(self, pending_urls, clip_state, total_count):
        """Per-URL sequential download (original approach)."""
        for index, url in enumerate(pending_urls):
            if self.clipboard_mgr.clipboard_stop_event.is_set():
                logger.info("Clipboard downloads stopped by user")
                break

            self._safe_after(0, lambda u=url: self._update_url_status(u, "downloading"))
            self._safe_after(
                0,
                lambda i=index, t=total_count: self.clipboard_total_label.setText(
                    f"Completed: {i}/{t} videos"
                ),
            )
            self._safe_after(
                0,
                lambda u=url: self.update_clipboard_status(f"Downloading: {u[:50]}...", "blue"),
            )

            success = self._download_clipboard_url(url, check_stop=True, clip_state=clip_state)

            if success:
                self._safe_after(0, lambda u=url: self._update_url_status(u, "completed"))
            else:
                self._safe_after(0, lambda u=url: self._update_url_status(u, "failed"))

            completed = index + 1
            self._safe_after(
                0,
                lambda c=completed, t=total_count: self.clipboard_total_label.setText(
                    f"Completed: {c}/{t} videos"
                ),
            )

    def _process_clipboard_queue_batch(self, pending_urls, clip_state, total_count):
        """Download multiple URLs via a single yt-dlp --batch-file process."""
        batch_file_path = None
        process = None
        try:
            # Write batch file
            fd, batch_file_path = tempfile.mkstemp(prefix="ytdl_batch_", suffix=".txt")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for url in pending_urls:
                    f.write(url + "\n")

            # Build command
            quality = clip_state["quality"] if clip_state else "1080"
            if "none" in quality.lower() or quality == "none (Audio only)":
                quality = "none"
            audio_only = quality.startswith("none") or clip_state.get("audio_only", False)
            _cdp = clip_state["download_path"] if clip_state else ""

            if audio_only:
                output_path = os.path.join(_cdp, "%(title)s.%(ext)s")
                cmd = self.download_mgr.build_batch_audio_ytdlp_command(
                    batch_file_path, output_path, volume=1.0
                )
            else:
                output_path = os.path.join(_cdp, f"%(title)s_{quality}p.%(ext)s")
                cmd = self.download_mgr.build_batch_video_ytdlp_command(
                    batch_file_path, output_path, quality, volume=1.0
                )

            # Speed limit — insert before --batch-file
            speed_args = utils.get_speed_limit_args(
                clip_state.get("speed_limit") if clip_state else None
            )
            if speed_args and "--batch-file" in cmd:
                bf_idx = cmd.index("--batch-file")
                for i, arg in enumerate(speed_args):
                    cmd.insert(bf_idx + i, arg)

            # --no-playlist for individual video URLs
            cmd.insert(1, "--no-playlist")

            logger.info(f"Batch clipboard download: {total_count} URLs, cmd={' '.join(cmd[:8])}...")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **_subprocess_kwargs,
            )
            self._clipboard_batch_process = process

            # Parse multiplexed stdout
            url_set = set(pending_urls)
            current_url = None
            current_had_error = False
            completed_count = 0

            for line in process.stdout:
                if self.clipboard_mgr.clipboard_stop_event.is_set():
                    utils.safe_process_cleanup(process)
                    logger.info("Batch clipboard download stopped by user")
                    break

                # Detect URL transition via "Extracting URL:"
                m = _EXTRACTING_URL_RE.search(line)
                if m:
                    extracted_url = m.group(1)
                    if extracted_url in url_set:
                        # Finalize previous URL
                        if current_url and not current_had_error:
                            completed_count += 1
                            self._safe_after(
                                0, lambda u=current_url: self._update_url_status(u, "completed")
                            )
                            self._safe_after(
                                0,
                                lambda c=completed_count, t=total_count: (
                                    self.clipboard_total_label.setText(f"Completed: {c}/{t} videos")
                                ),
                            )

                        # Start tracking new URL
                        current_url = extracted_url
                        current_had_error = False
                        self._safe_after(
                            0, lambda u=current_url: self._update_url_status(u, "downloading")
                        )
                        self._safe_after(0, lambda: self.clipboard_progress.setValue(0))
                        self._safe_after(
                            0,
                            lambda u=current_url: self.update_clipboard_status(
                                f"Downloading: {u[:50]}...", "blue"
                            ),
                        )

                # Detect errors
                if "ERROR" in line and current_url:
                    current_had_error = True
                    self._safe_after(0, lambda u=current_url: self._update_url_status(u, "failed"))

                # Parse progress
                if "[download]" in line or "Downloading" in line:
                    progress_match = PROGRESS_REGEX.search(line)
                    if progress_match:
                        progress = float(progress_match.group(1))
                        self._safe_after(0, lambda p=progress: self.update_clipboard_progress(p))

                # Phase status updates
                if "[Merger]" in line or "Merging" in line:
                    self._safe_after(
                        0,
                        lambda: self.update_clipboard_status("Merging video and audio...", "blue"),
                    )
                elif "[ExtractAudio]" in line:
                    self._safe_after(
                        0,
                        lambda: self.update_clipboard_status("Extracting audio...", "blue"),
                    )

            # Finalize last URL
            if process.poll() is None:
                process.wait()

            if current_url and not current_had_error:
                completed_count += 1
                self._safe_after(0, lambda u=current_url: self._update_url_status(u, "completed"))
                self._safe_after(
                    0,
                    lambda c=completed_count, t=total_count: self.clipboard_total_label.setText(
                        f"Completed: {c}/{t} videos"
                    ),
                )

            logger.info(f"Batch clipboard download done: {completed_count}/{total_count} completed")

        except Exception as e:
            logger.exception(f"Batch clipboard download error: {e}")
        finally:
            self._clipboard_batch_process = None
            if process:
                utils.safe_process_cleanup(process)
            if batch_file_path:
                try:
                    os.unlink(batch_file_path)
                except OSError:
                    pass

    def _download_clipboard_url(
        self, url, check_stop=False, check_stop_auto=False, clip_state=None
    ):
        """Download single URL or playlist from clipboard mode (blocking, runs
        in thread). Returns True if successful.

        Args:
            clip_state: Dict of clipboard widget values snapshot from GUI thread.
        """
        process = None
        try:
            if not clip_state:
                logger.warning("_download_clipboard_url called without clip_state")
                clip_state = {
                    "quality": "1080",
                    "audio_only": False,
                    "full_playlist": False,
                    "download_path": self.clipboard_mgr.clipboard_download_path,
                }
            quality = clip_state["quality"]
            if "none" in quality.lower() or quality == "none (Audio only)":
                quality = "none"

            audio_only = quality.startswith("none") or clip_state.get("audio_only", False)
            is_playlist_url = utils.is_playlist_url(url)
            full_playlist_enabled = clip_state["full_playlist"]

            download_as_playlist = is_playlist_url and full_playlist_enabled

            self._safe_after(0, lambda: self.clipboard_progress.setValue(0))
            self._safe_after(0, lambda: self.clipboard_progress_label.setText("0%"))

            # Build output path template
            _cdp = clip_state["download_path"]
            if audio_only:
                if download_as_playlist:
                    output_path = os.path.join(_cdp, "%(playlist_index)s-%(title)s.%(ext)s")
                else:
                    output_path = os.path.join(_cdp, "%(title)s.%(ext)s")
            else:
                if download_as_playlist:
                    output_path = os.path.join(
                        _cdp, f"%(playlist_index)s-%(title)s_{quality}p.%(ext)s"
                    )
                else:
                    output_path = os.path.join(_cdp, f"%(title)s_{quality}p.%(ext)s")

            # Build yt-dlp command
            if audio_only:
                cmd = self.download_mgr.build_audio_ytdlp_command(url, output_path, volume=1.0)
            else:
                cmd = self.download_mgr.build_video_ytdlp_command(
                    url, output_path, quality, volume=1.0
                )

            if is_playlist_url and not full_playlist_enabled:
                cmd.insert(1, "--no-playlist")

            # Speed limit — insert before the "--" separator so yt-dlp sees them
            _csl = clip_state["speed_limit"] if clip_state else None
            speed_args = utils.get_speed_limit_args(_csl)
            if speed_args and "--" in cmd:
                sep_idx = cmd.index("--")
                for i, arg in enumerate(speed_args):
                    cmd.insert(sep_idx + i, arg)
            else:
                cmd.extend(speed_args)

            if download_as_playlist:
                logger.info(f"Clipboard full playlist download starting: {url}")
            elif is_playlist_url:
                logger.info(f"Clipboard single video from playlist starting: {url}")
            else:
                logger.info(f"Clipboard download starting: {url}")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **_subprocess_kwargs,
            )

            current_phase = "video" if not audio_only else "audio"
            playlist_item_info = ""

            for line in process.stdout:
                # Check stop flags
                if check_stop:
                    if self.clipboard_mgr.clipboard_stop_event.is_set():
                        utils.safe_process_cleanup(process)
                        return False
                if check_stop_auto:
                    with self.clipboard_mgr.auto_download_lock:
                        is_auto_downloading = self.clipboard_mgr.clipboard_auto_downloading
                    if not is_auto_downloading:
                        utils.safe_process_cleanup(process)
                        return False

                line_lower = line.lower()

                # Detect phase changes
                if "downloading video" in line_lower or (
                    "video" in line_lower and "downloading" in line_lower
                ):
                    current_phase = "video"
                elif "downloading audio" in line_lower or (
                    "audio" in line_lower and "downloading" in line_lower
                ):
                    current_phase = "audio"

                # Detect playlist item progress
                if download_as_playlist and "downloading item" in line_lower:
                    item_match = _PLAYLIST_ITEM_RE.search(line_lower)
                    if item_match:
                        playlist_item_info = f" [{item_match.group(1)}/{item_match.group(2)}]"

                if "[download]" in line or "Downloading" in line:
                    progress_match = PROGRESS_REGEX.search(line)
                    if progress_match:
                        progress = float(progress_match.group(1))
                        self._safe_after(0, lambda p=progress: self.update_clipboard_progress(p))

                        phase = current_phase
                        pinfo = playlist_item_info
                        self._safe_after(
                            0,
                            lambda p=progress, ph=phase, pi=pinfo: self.update_clipboard_status(
                                f"Downloading {ph}{pi}... {p:.1f}%", "blue"
                            ),
                        )

                elif "[Merger]" in line or "Merging" in line:
                    self._safe_after(
                        0,
                        lambda: self.update_clipboard_status("Merging video and audio...", "blue"),
                    )
                elif "[ffmpeg]" in line:
                    self._safe_after(
                        0,
                        lambda: self.update_clipboard_status("Processing with ffmpeg...", "blue"),
                    )
                elif "[ExtractAudio]" in line:
                    self._safe_after(
                        0,
                        lambda: self.update_clipboard_status("Extracting audio...", "blue"),
                    )

            process.wait()

            if process.returncode == 0:
                self._safe_after(0, lambda: self.update_clipboard_progress(PROGRESS_COMPLETE))
                logger.info(f"Clipboard download completed: {url}")
                return True
            else:
                logger.error(f"Clipboard download failed: {url}, returncode={process.returncode}")
                return False

        except Exception as e:
            logger.exception(f"Error downloading clipboard URL {url}: {e}")
            return False
        finally:
            if process:
                utils.safe_process_cleanup(process)

    def _finish_clipboard_downloads(self):
        """Clean up after batch downloads complete."""
        self.clipboard_mgr.clipboard_stop_event.set()
        with self.clipboard_mgr.clipboard_lock:
            has_urls = len(self.clipboard_mgr.clipboard_url_list) > 0
            completed = sum(
                1 for item in self.clipboard_mgr.clipboard_url_list if item["status"] == "completed"
            )
            failed = sum(
                1 for item in self.clipboard_mgr.clipboard_url_list if item["status"] == "failed"
            )

        self.clipboard_download_btn.setEnabled(has_urls)
        self.clipboard_stop_btn.setEnabled(False)

        if failed > 0:
            self.update_clipboard_status(f"Completed: {completed} | Failed: {failed}", "orange")
        else:
            self.update_clipboard_status(f"All downloads complete! ({completed} videos)", "green")

        logger.info(f"Clipboard batch download finished: {completed} completed, {failed} failed")

    def stop_clipboard_downloads(self):
        """Stop clipboard batch downloads and auto-downloads."""
        was_downloading = not self.clipboard_mgr.clipboard_stop_event.is_set()
        self.clipboard_mgr.clipboard_stop_event.set()
        # Terminate batch process if running
        if self._clipboard_batch_process:
            utils.safe_process_cleanup(self._clipboard_batch_process)
            self._clipboard_batch_process = None
        if was_downloading:
            logger.info("Clipboard batch downloads stopped by user")
        with self.clipboard_mgr.auto_download_lock:
            if self.clipboard_mgr.clipboard_auto_downloading:
                self.clipboard_mgr.clipboard_auto_downloading = False
                stopped = True
        if stopped:
            logger.info("Clipboard auto-downloads stopped by user")
            self.update_clipboard_status("Downloads stopped by user", "orange")
            self.clipboard_stop_btn.setEnabled(False)

    def _auto_download_single_url(self, url):
        """Auto-download single URL when detected (if auto-download enabled)."""
        with self.clipboard_mgr.auto_download_lock:
            with self.clipboard_mgr.clipboard_lock:
                downloading_count = sum(
                    1
                    for item in self.clipboard_mgr.clipboard_url_list
                    if item["status"] == "downloading"
                )
            if downloading_count > 0:
                logger.info(f"URL queued (another download in progress): {url}")
                return

            self.clipboard_mgr.clipboard_auto_downloading = True
            self._update_url_status(url, "downloading")

        self.clipboard_stop_btn.setEnabled(True)
        self._update_auto_download_total()
        # Snapshot clipboard widget values on GUI thread for thread safety
        clip_state = {
            "quality": self.clipboard_quality_combo.currentText(),
            "full_playlist": self.clipboard_full_playlist_check.isChecked(),
            "audio_only": self.clipboard_audio_only_check.isChecked(),
            "speed_limit": self.clipboard_speed_limit_entry.text().strip(),
            "download_path": self.clipboard_mgr.clipboard_download_path,
        }
        self.thread_pool.submit(self._auto_download_worker, url, clip_state)

    def _auto_download_worker(self, url, clip_state=None):
        """Worker thread for auto-downloading single URL."""
        with self.clipboard_mgr.auto_download_lock:
            is_auto_downloading = self.clipboard_mgr.clipboard_auto_downloading
        if not is_auto_downloading:
            self._safe_after(0, lambda: self._update_url_status(url, "pending"))
            return

        self._safe_after(
            0,
            lambda: self.update_clipboard_status(f"Auto-downloading: {url[:50]}...", "blue"),
        )

        success = self._download_clipboard_url(url, check_stop_auto=True, clip_state=clip_state)

        with self.clipboard_mgr.auto_download_lock:
            is_auto_downloading = self.clipboard_mgr.clipboard_auto_downloading
        if not is_auto_downloading:
            self._safe_after(0, lambda: self._update_url_status(url, "pending"))
            self._safe_after(
                0,
                lambda: self.update_clipboard_status("Auto-download stopped", "orange"),
            )
            return

        self._safe_after(0, lambda: self._handle_auto_download_complete(url, success))

    def _handle_auto_download_complete(self, url, success):
        """Handle auto-download completion — runs on main thread."""
        if success:
            self._update_url_status(url, "completed")
            self._update_auto_download_total()
            self.update_clipboard_status(f"Auto-download complete: {url[:50]}...", "green")
            self._remove_url_from_list(url)
            logger.info(f"Auto-download completed and removed: {url}")
        else:
            self._update_url_status(url, "failed")
            self._update_auto_download_total()
            self.update_clipboard_status(f"Auto-download failed: {url[:50]}...", "red")
            logger.info(f"Auto-download failed: {url}")

        self._check_pending_auto_downloads()

    def _disable_stop_if_idle(self):
        """Disable stop button if no downloads in progress."""
        is_downloading = not self.clipboard_mgr.clipboard_stop_event.is_set()
        with self.clipboard_mgr.auto_download_lock:
            is_auto_downloading = self.clipboard_mgr.clipboard_auto_downloading
        if not is_downloading and not is_auto_downloading:
            self.clipboard_stop_btn.setEnabled(False)

    def _check_pending_auto_downloads(self):
        """Check if there are pending URLs that need to be auto-downloaded."""
        with self.clipboard_mgr.auto_download_lock:
            self.clipboard_mgr.clipboard_auto_downloading = False

        if self.clipboard_auto_download_check.isChecked():
            with self.clipboard_mgr.clipboard_lock:
                next_pending_url = None
                for item in self.clipboard_mgr.clipboard_url_list:
                    if item["status"] == "pending":
                        next_pending_url = item["url"]
                        break

            if next_pending_url:
                self._auto_download_single_url(next_pending_url)
        else:
            self._disable_stop_if_idle()

    def _update_auto_download_total(self):
        """Update total progress for auto-downloads."""
        with self.clipboard_mgr.clipboard_lock:
            total = len(self.clipboard_mgr.clipboard_url_list)
            completed = sum(
                1
                for item in self.clipboard_mgr.clipboard_url_list
                if item["status"] in ["completed", "failed"]
            )
        self.clipboard_mgr.sig_clipboard_total.emit(f"Completed: {completed}/{total} videos")

    def update_clipboard_progress(self, value):
        """Update clipboard mode progress bar (thread-safe via signal)."""
        try:
            self.clipboard_mgr.sig_clipboard_progress.emit(max(0.0, min(100.0, float(value))))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid progress value: {value} - {e}")

    def update_clipboard_status(self, message, color):
        """Update clipboard mode status label (thread-safe via signal)."""
        self.clipboard_mgr.sig_clipboard_status.emit(str(message), str(color))

    def _pick_directory(self, current_path, title="Select Download Folder"):
        """Show a directory picker dialog and validate the selection.

        Returns the validated path string, or None if cancelled/invalid.
        """
        path = QFileDialog.getExistingDirectory(self, title, current_path)
        if not path:
            return None

        is_valid, normalized_path, error_msg = utils.validate_download_path(path)
        if not is_valid:
            QMessageBox.critical(self, "Error", error_msg)
            return None
        path = normalized_path

        if not os.path.exists(path):
            QMessageBox.critical(self, "Error", f"Path does not exist: {path}")
            return None

        if not os.path.isdir(path):
            QMessageBox.critical(self, "Error", f"Path is not a directory: {path}")
            return None

        test_file = os.path.join(path, ".ytdl_write_test")
        try:
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
        except (IOError, OSError) as e:
            QMessageBox.critical(self, "Error", f"Path is not writable:\n{path}\n\n{e}")
            return None

        return path

    def change_clipboard_path(self):
        """Change clipboard mode download path."""
        path = self._pick_directory(self.clipboard_mgr.clipboard_download_path)
        if path:
            self.clipboard_mgr.clipboard_download_path = path
            self.clipboard_path_label.setText(path)
            logger.info(f"Clipboard download path changed to: {path}")

    def _open_folder(self, path):
        """Open a folder in the system file manager."""
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(
                    ["open", path],
                    close_fds=True,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(
                    ["xdg-open", path],
                    close_fds=True,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open folder:\n{e}")

    def open_clipboard_folder(self):
        """Open clipboard mode download folder."""
        self._open_folder(self.clipboard_mgr.clipboard_download_path)

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
            QMessageBox.critical(self, "Error", "Please enter a YouTube URL or select a local file")
            return

        if utils.is_local_file(url):
            if not os.path.isfile(url):
                QMessageBox.critical(self, "Error", f"File not found:\n{url}")
                return
            self.local_file_path = url
        else:
            is_valid, message = utils.validate_youtube_url(url)
            if not is_valid:
                QMessageBox.critical(self, "Invalid URL", message)
                logger.warning(f"Invalid URL rejected: {url}")
                return
            self.local_file_path = None

            if utils.is_playlist_url(url):
                if utils.is_pure_playlist_url(url):
                    self.is_playlist = True
                    self.trim_enabled_check.setChecked(False)
                    self.toggle_trim()
                    self.video_info_label.setText(
                        "Playlist detected - Trimming and upload disabled for playlists"
                    )
                    self.video_info_label.setStyleSheet("color: orange;")
                    self.filesize_label.setText("")
                    logger.info("Playlist URL detected - trimming disabled")
                    return
                else:
                    url = utils.strip_playlist_params(url)
                    self.url_entry.clear()
                    self.url_entry.setText(url)
                    self.is_playlist = False
                    self.video_info_label.setText(
                        "Playlist parameters removed - downloading single video"
                    )
                    self.video_info_label.setStyleSheet("color: green;")
                    logger.info(f"Stripped playlist params from video URL: {url}")
            else:
                self.is_playlist = False

        with self.trimming_mgr.fetch_lock:
            is_fetching = self.trimming_mgr.is_fetching_duration
        if is_fetching or self.download_mgr.is_downloading:
            return

        if self.current_video_url != url:
            self.current_video_url = url
            self.trimming_mgr.current_video_url = url
            self.trimming_mgr.clear_preview_cache()
        else:
            self.current_video_url = url
            self.trimming_mgr.current_video_url = url

        with self.trimming_mgr.fetch_lock:
            self.trimming_mgr.is_fetching_duration = True
        self.fetch_duration_btn.setEnabled(False)
        self.sig_update_status.emit("Fetching video duration...", "blue")

        self.thread_pool.submit(self.trimming_mgr.fetch_video_duration, url)

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
        self.start_time_entry.setText(utils.seconds_to_hms(0))
        self.end_time_entry.setText(utils.seconds_to_hms(self.video_duration))

        self.trim_duration_label.setText(
            f"Selected Duration: {utils.seconds_to_hms(self.video_duration)}"
        )

        if video_title:
            self.video_info_label.setText(f"Title: {video_title}")
            self.video_info_label.setStyleSheet("color: green;")

        QTimer.singleShot(UI_INITIAL_DELAY_MS, self.update_previews)

    def _update_duration_ui_local(self, video_title):
        """Update duration-related UI for local files on the main thread."""
        self._update_duration_ui()
        if video_title:
            self.video_info_label.setText(f"File: {video_title}")
            self.video_info_label.setStyleSheet("color: green;")

    def _auto_fetch_file_size(self):
        """Called by debounce timer on GUI thread — reads URL and dispatches fetch."""
        url = self.url_entry.text().strip()
        if url:
            self._fetch_file_size(url)

    def _fetch_file_size(self, url, quality=None, audio_only=None):
        """Fetch estimated file size for the video (runs in background thread)."""
        # Use provided values (thread-safe) or read from widgets (GUI thread only)
        # Capture widget values on GUI thread before submitting to thread pool
        _quality = quality if quality is not None else self.quality_combo.currentText()
        _audio_only = audio_only if audio_only is not None else self.audio_only_check.isChecked()
        _ytdlp_path = self.ytdlp_path  # capture immutable snapshot for closure

        def _fetch():
            try:
                quality = _quality

                if _audio_only or quality.startswith("none") or quality == "none (Audio only)":
                    format_selector = "bestaudio"
                else:
                    format_selector = (
                        f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]"
                    )

                cmd = [_ytdlp_path, "--dump-json", "-f", format_selector, url]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=STREAM_FETCH_TIMEOUT,
                    **_subprocess_kwargs,
                )

                if result.returncode == 0:
                    info = json.loads(result.stdout)
                    filesize = info.get("filesize") or info.get("filesize_approx")

                    if filesize:
                        filesize_mb = filesize / BYTES_PER_MB
                        self._safe_after(
                            0,
                            lambda: self._update_filesize_display(filesize, filesize_mb),
                        )
                    else:
                        self._safe_after(0, lambda: self._update_filesize_display(None, None))
                else:
                    self._safe_after(0, lambda: self._update_filesize_display(None, None))
            except Exception as e:
                logger.debug(f"Could not fetch file size: {e}")
                self._safe_after(0, lambda: self._update_filesize_display(None, None))

        self.thread_pool.submit(_fetch)

    def _update_filesize_display(self, filesize_bytes, filesize_mb):
        """Update file size display on main thread."""
        if filesize_bytes and filesize_mb:
            self.filesize_label.setText(f"Estimated size: {filesize_mb:.1f} MB")
            self.estimated_filesize = filesize_bytes
        elif filesize_mb is None and filesize_bytes is None:
            self.filesize_label.setText("Estimated size: Unknown")
            self.estimated_filesize = None

        self._update_trimmed_filesize()

    def _on_keep_below_10mb_toggle(self, *_args):
        """Enable/disable quality dropdown based on 10MB checkbox state."""
        if self.keep_below_10mb_check.isChecked():
            self.quality_combo.setEnabled(False)
        else:
            self.quality_combo.setEnabled(True)

    def _on_audio_only_toggle(self, *_args):
        """Toggle audio-only mode — syncs with quality combo and 10MB."""
        if self.audio_only_check.isChecked():
            self.quality_combo.blockSignals(True)
            self.quality_combo.setCurrentText("none (Audio only)")
            self.quality_combo.blockSignals(False)
            self.quality_combo.setEnabled(False)
            self.keep_below_10mb_check.setChecked(False)
            self.keep_below_10mb_check.setEnabled(False)
        else:
            self.quality_combo.blockSignals(True)
            self.quality_combo.setCurrentText("480")
            self.quality_combo.blockSignals(False)
            self.quality_combo.setEnabled(True)
            self.keep_below_10mb_check.setEnabled(True)
        # Re-fetch filesize for the new mode
        url = self.current_video_url or self.url_entry.text().strip()
        if url and not self.is_playlist:
            is_valid, _ = utils.validate_youtube_url(url)
            if is_valid:
                self.filesize_label.setText("Calculating size...")
                self._fetch_file_size(url)

    def _on_clipboard_audio_only_toggle(self, *_args):
        """Toggle audio-only mode in clipboard — disables quality dropdown."""
        if self.clipboard_audio_only_check.isChecked():
            self.clipboard_quality_combo.setEnabled(False)
        else:
            self.clipboard_quality_combo.setEnabled(True)

    def on_quality_change(self, *_args):
        """Handle quality selection changes — re-fetch file size with new
        quality."""
        quality = self.quality_combo.currentText()
        if quality.startswith("none") or "none (Audio only)" in quality:
            # Sync: selecting audio-only quality checks the audio-only box
            if not self.audio_only_check.isChecked():
                self.audio_only_check.setChecked(True)
            return  # _on_audio_only_toggle handles the rest
        else:
            self.keep_below_10mb_check.setEnabled(True)

        url = self.current_video_url or self.url_entry.text().strip()
        if url and not self.is_playlist:
            is_valid, _ = utils.validate_youtube_url(url)
            if is_valid:
                self.filesize_label.setText("Calculating size...")
                self._fetch_file_size(url)

    def _update_trimmed_filesize(self):
        """Update file size estimate based on trim selection using linear
        calculation."""
        if not self.estimated_filesize or not self.trim_enabled_check.isChecked():
            if self.estimated_filesize:
                filesize_mb = self.estimated_filesize / BYTES_PER_MB
                self.filesize_label.setText(f"Estimated size: {filesize_mb:.1f} MB")
            return

        start_time = self.start_slider.value()
        end_time = self.end_slider.value()
        selected_duration = end_time - start_time

        if self.video_duration > 0:
            duration_percentage = selected_duration / self.video_duration
            trimmed_size = self.estimated_filesize * duration_percentage
            trimmed_size_mb = trimmed_size / BYTES_PER_MB
            self.filesize_label.setText(f"Estimated size (trimmed): {trimmed_size_mb:.1f} MB")

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
        self.start_time_entry.setText(utils.seconds_to_hms(start_time))
        self.end_time_entry.setText(utils.seconds_to_hms(end_time))

        # Update selected duration
        selected_duration = end_time - start_time
        self.trim_duration_label.setText(
            f"Selected Duration: {utils.seconds_to_hms(selected_duration)}"
        )

        self._update_trimmed_filesize()
        self.schedule_preview_update()

    def on_start_slider_change(self, value):
        """Handle start slider value changed."""
        self.on_slider_change()

    def on_end_slider_change(self, value):
        """Handle end slider value changed."""
        self.on_slider_change()

    def on_start_entry_change(self, *_args):
        """Handle changes to start time entry field."""
        value_str = self.start_time_entry.text()
        seconds = utils.hms_to_seconds(value_str)

        if seconds is not None and 0 <= seconds <= self.video_duration:
            self.start_slider.blockSignals(True)
            self.start_slider.setValue(seconds)
            self.start_slider.blockSignals(False)
            self.on_slider_change()
        else:
            current_time = self.start_slider.value()
            self.start_time_entry.setText(utils.seconds_to_hms(current_time))

    def on_end_entry_change(self, *_args):
        """Handle changes to end time entry field."""
        value_str = self.end_time_entry.text()
        seconds = utils.hms_to_seconds(value_str)

        if seconds is not None and 0 <= seconds <= self.video_duration:
            self.end_slider.blockSignals(True)
            self.end_slider.setValue(seconds)
            self.end_slider.blockSignals(False)
            self.on_slider_change()
        else:
            current_time = self.end_slider.value()
            self.end_time_entry.setText(utils.seconds_to_hms(current_time))

    def reset_volume(self):
        """Reset volume to 100%."""
        self._volume_int = 100
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(100)
        self.volume_slider.blockSignals(False)
        self.volume_entry.setText("100")

    def start_upload(self):
        """Start upload to Catbox.moe in a background thread."""
        ok, error = self.upload_mgr.start_upload_if_valid()
        if not ok:
            if error:
                QMessageBox.critical(self, "Error", error)
            return

        self.upload_btn.setEnabled(False)
        self.upload_status_label.setText("Uploading...")
        self.upload_status_label.setStyleSheet("color: blue; font-size: 9pt;")
        self.upload_url_widget.setVisible(False)

        self.thread_pool.submit(self.upload_mgr.upload_to_catbox)

    def _on_upload_complete(self, file_url, filename):
        """Handle successful upload (signal slot from UploadManager)."""
        self.upload_status_label.setText("Upload complete!")
        self.upload_status_label.setStyleSheet("color: green; font-size: 9pt;")

        self.upload_url_entry.setReadOnly(False)
        self.upload_url_entry.setText(file_url)
        self.upload_url_entry.setReadOnly(True)
        self.upload_url_widget.setVisible(True)

        self.upload_btn.setEnabled(True)

        QMessageBox.information(
            self,
            "Upload Complete",
            f"File uploaded successfully!\n\nURL: {file_url}\n\n"
            f"The URL has been copied to your clipboard.",
        )

        try:
            QApplication.clipboard().setText(file_url)
        except Exception:
            logger.warning("Failed to copy URL to clipboard")

    def copy_upload_url(self):
        """Copy upload URL to clipboard."""
        url = self.upload_url_entry.text()
        if url:
            QApplication.clipboard().setText(url)
            self.upload_status_label.setText("URL copied to clipboard!")
            self.upload_status_label.setStyleSheet("color: green; font-size: 9pt;")
            logger.info("Upload URL copied to clipboard")

    # ==================================================================
    #  UPLOAD CALLBACKS (Uploader tab)
    # ==================================================================

    def browse_uploader_files(self):
        """Browse and select multiple files for upload in Uploader tab."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Video Files",
            "",
            "Video files (*.mp4 *.avi *.mkv *.mov *.flv *.wmv *.webm *.m4v);;"
            "Audio files (*.mp3 *.m4a *.wav *.flac *.aac *.ogg);;"
            "All files (*.*)",
        )

        if file_paths:
            for file_path in file_paths:
                file_size_mb = os.path.getsize(file_path) / BYTES_PER_MB
                if file_size_mb > CATBOX_MAX_SIZE_MB:
                    QMessageBox.warning(
                        self,
                        "File Too Large",
                        f"Skipped: {os.path.basename(file_path)}\n"
                        f"File size ({file_size_mb:.1f} MB) exceeds "
                        f"200MB limit.",
                    )
                    continue

                if self.upload_mgr.add_to_queue(file_path):
                    self._add_file_to_uploader_queue(file_path)
                    logger.info(f"Added file to upload queue: {file_path}")

    def _add_file_to_uploader_queue(self, file_path):
        """Add a file to the upload queue with UI widget."""
        file_frame = QWidget()
        file_frame.setStyleSheet("border: 1px solid #555; border-radius: 2px; padding: 2px;")
        row_layout = QHBoxLayout(file_frame)
        row_layout.setContentsMargins(5, 2, 5, 2)
        row_layout.setSpacing(5)

        filename = os.path.basename(file_path)
        file_size_mb = os.path.getsize(file_path) / BYTES_PER_MB

        file_label = QLabel(f"{filename} ({file_size_mb:.1f} MB)")
        file_label.setStyleSheet("border: none;")
        row_layout.addWidget(file_label, stretch=1)

        remove_btn = QPushButton("X")
        remove_btn.setFixedWidth(30)
        remove_btn.setStyleSheet("border: none;")
        remove_btn.clicked.connect(lambda checked, fp=file_path: self._remove_file_from_queue(fp))
        row_layout.addWidget(remove_btn)

        self.uploader_file_list_layout.addWidget(file_frame)
        self.upload_mgr.set_widget_for_queue_item(file_path, file_frame)
        self._update_uploader_queue_count()

        count = self.upload_mgr.queue_count()
        with self.upload_mgr.uploader_lock:
            is_uploading = self.upload_mgr.uploader_is_uploading
        if count > 0 and not is_uploading:
            self.uploader_upload_btn.setEnabled(True)

    def _remove_file_from_queue(self, file_path):
        """Remove a file from the upload queue."""
        widget = self.upload_mgr.remove_from_queue(file_path)
        if widget:
            widget.deleteLater()
        logger.info(f"Removed file from queue: {file_path}")
        self._update_uploader_queue_count()
        if self.upload_mgr.queue_count() == 0:
            self.uploader_upload_btn.setEnabled(False)

    def clear_uploader_queue(self):
        """Clear all files from upload queue."""
        with self.upload_mgr.uploader_lock:
            is_uploading = self.upload_mgr.uploader_is_uploading
        if is_uploading:
            QMessageBox.warning(
                self,
                "Cannot Clear",
                "Cannot clear queue while uploads are in progress.",
            )
            return

        widgets_to_destroy = self.upload_mgr.clear_queue()
        for widget in widgets_to_destroy:
            widget.deleteLater()
        self._update_uploader_queue_count()
        self.uploader_upload_btn.setEnabled(False)
        logger.info("Cleared all files from upload queue")

    def _update_uploader_queue_count(self):
        """Update file queue count label."""
        count = self.upload_mgr.queue_count()
        s = "s" if count != 1 else ""
        self.uploader_queue_count_label.setText(f"({count} file{s})")

    def start_uploader_upload(self):
        """Start uploading all files in queue sequentially."""
        ok, error = self.upload_mgr.start_queue_upload()
        if not ok:
            if error:
                QMessageBox.information(self, "No Files", error)
            return

        self.uploader_upload_btn.setEnabled(False)
        self.uploader_url_widget.setVisible(False)

        self.thread_pool.submit(self.upload_mgr.process_uploader_queue)

    def _show_upload_url(self, file_url):
        """Display the most recent upload URL (signal slot)."""
        self.uploader_url_entry.setReadOnly(False)
        self.uploader_url_entry.setText(file_url)
        self.uploader_url_entry.setReadOnly(True)
        self.uploader_url_widget.setVisible(True)

        try:
            QApplication.clipboard().setText(file_url)
        except Exception:
            logger.warning("Failed to copy URL to clipboard")

    def _on_uploader_queue_done(self, count):
        """Clean up after queue upload completes (signal slot)."""
        with self.upload_mgr.uploader_lock:
            queue_len = len(self.upload_mgr.uploader_file_queue)
            was_stopped = not self.upload_mgr.uploader_is_uploading

        if was_stopped:
            # Stopped mid-way — keep remaining items in queue
            self.uploader_status_label.setText(
                f"Upload stopped ({count} of {queue_len} files uploaded)"
            )
            self.uploader_status_label.setStyleSheet("color: orange; font-size: 9pt;")
            self.uploader_upload_btn.setEnabled(True)
        else:
            # Completed normally — clear queue
            widgets = self.upload_mgr.clear_queue()
            for widget in widgets:
                widget.deleteLater()
            self._update_uploader_queue_count()
            self.uploader_status_label.setText(f"All uploads complete! ({count} files)")
            self.uploader_status_label.setStyleSheet("color: green; font-size: 9pt;")
            self.uploader_upload_btn.setEnabled(False)

        logger.info(f"Uploader queue finished: {count} files uploaded")

    def copy_uploader_url(self):
        """Copy upload URL to clipboard from Uploader tab."""
        url = self.uploader_url_entry.text()
        if url:
            QApplication.clipboard().setText(url)
            self.uploader_status_label.setText("URL copied to clipboard!")
            self.uploader_status_label.setStyleSheet("color: green; font-size: 9pt;")
            logger.info("Upload URL copied to clipboard from Uploader tab")

    def _enable_upload_button(self, filepath):
        """Enable upload button after successful download (thread-safe)."""
        self.upload_mgr.enable_upload_button(filepath)
        if filepath and os.path.isfile(filepath):
            self._safe_after(0, lambda: self._do_enable_upload(filepath))

    def _do_enable_upload(self, filepath):
        """Actual upload button enable on main thread."""
        self.upload_btn.setEnabled(True)
        logger.info(f"Upload enabled for: {filepath}")

        if self.auto_upload_check.isChecked():
            url = self.url_entry.text().strip()
            if url and utils.is_playlist_url(url):
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

        # Restart the single-shot timer (signal connected once in __init__)
        self._preview_debounce_timer.start()

    def update_previews(self):
        """Update both preview images."""
        if self._shutting_down:
            return

        if not self.current_video_url or self.video_duration == 0:
            return

        with self.trimming_mgr.preview_lock:
            if self.trimming_mgr.preview_thread_running:
                return
            self.trimming_mgr.preview_thread_running = True

        start_time = self.start_slider.value()
        end_time = self.end_slider.value()

        # Show loading indicators (reuse cached pixmap)
        if not hasattr(self, "_loading_placeholder"):
            self._loading_placeholder = self.create_placeholder_pixmap(
                PREVIEW_WIDTH, PREVIEW_HEIGHT, "Loading..."
            )
        self.start_preview_label.setPixmap(self._loading_placeholder)
        self.end_preview_label.setPixmap(self._loading_placeholder)

        try:
            self.thread_pool.submit(self.trimming_mgr.update_previews_thread, start_time, end_time)
        except RuntimeError:
            with self.trimming_mgr.preview_lock:
                self.trimming_mgr.preview_thread_running = False

    def on_url_change(self, *_args):
        """Detect if input is URL or file path."""
        input_text = self.url_entry.text().strip()

        if not input_text:
            self.mode_label.setText("")
            self.local_file_path = None
            return

        # Clear filename field when URL/file changes
        self.filename_entry.clear()

        # Reset trim data for new URL — stale slider values from a previous
        # video cause invalid byte-range requests (HTTP 416).
        # Keep trim checkbox state so user doesn't have to re-check it.
        self.video_duration = 0
        self.trimming_mgr.video_duration = 0
        self.estimated_filesize = None
        self.start_slider.setValue(0)
        self.end_slider.setValue(0)
        self.filesize_label.setText("")
        self.video_info_label.setText("")
        self.fetch_duration_btn.setEnabled(self.trim_enabled_check.isChecked())

        if utils.is_local_file(input_text):
            self.local_file_path = input_text
            self.mode_label.setText(f"Mode: Local File | {Path(input_text).name}")
            self.mode_label.setStyleSheet("color: green; font-size: 9pt;")
        else:
            self.local_file_path = None
            self.mode_label.setText("Mode: YouTube Download")
            self.mode_label.setStyleSheet("color: green; font-size: 9pt;")

            # Auto-fetch file size estimate for valid YouTube URLs (debounced)
            is_valid, _ = utils.validate_youtube_url(input_text)
            if is_valid:
                self._size_fetch_timer.start()

    def change_path(self):
        """Change download path with validation."""
        path = self._pick_directory(self.download_path)
        if path:
            self.download_path = path
            self.path_label.setText(path)

    def open_download_folder(self):
        """Open the download folder in the system file manager."""
        self._open_folder(self.download_path)

    def browse_local_file(self):
        """Open file dialog to select a local video file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select a media file",
            str(Path.home()),
            "Media files (*.mp4 *.mkv *.avi *.mov *.flv *.webm *.wmv *.m4v *.mp3 *.aac *.m4a *.wav);;"
            "Video files (*.mp4 *.mkv *.avi *.mov *.flv *.webm *.wmv *.m4v);;"
            "Audio files (*.mp3 *.aac *.m4a *.wav);;"
            "All files (*.*)",
        )

        if filepath:
            self.url_entry.clear()
            self.url_entry.setText(filepath)
            self.local_file_path = filepath

            audio_extensions = {".mp3", ".aac", ".m4a", ".wav"}
            if Path(filepath).suffix.lower() in audio_extensions:
                self.audio_only_check.setChecked(True)
                self.mode_label.setText(f"Mode: Local Audio | {Path(filepath).name}")
            else:
                self.audio_only_check.setChecked(False)
                self.mode_label.setText(f"Mode: Local File | {Path(filepath).name}")
            self.mode_label.setStyleSheet("color: green; font-size: 9pt;")
            # Clear filename field for new file
            self.filename_entry.clear()
            logger.info(f"Local file selected: {filepath}")

    # ===================================================================
    #  Download entry-point
    # ===================================================================

    def start_download(self):
        """Validate inputs and kick off a download in the thread pool."""
        url = self.url_entry.text().strip()

        if not url:
            self.sig_show_messagebox.emit(
                "error", "Error", "Please enter a YouTube URL or select a local file"
            )
            return

        is_local = utils.is_local_file(url)

        if is_local:
            if not os.path.isfile(url):
                self.sig_show_messagebox.emit("error", "Error", f"File not found:\n{url}")
                return
        else:
            is_valid, message = utils.validate_youtube_url(url)
            if not is_valid:
                self.sig_show_messagebox.emit("error", "Invalid URL", message)
                logger.warning(f"Invalid URL rejected for download: {url}")
                return

            if utils.is_playlist_url(url) and not utils.is_pure_playlist_url(url):
                url = utils.strip_playlist_params(url)
                self.is_playlist = False
            else:
                self.is_playlist = utils.is_playlist_url(url)

        if not self.dependencies_ok:
            self.sig_show_messagebox.emit(
                "error",
                "Error",
                "yt-dlp or ffmpeg is not installed.\n\nInstall with:\npip install yt-dlp\n\n"
                "and install ffmpeg from your package manager",
            )
            return

        logger.info(f"Starting download for URL: {url}")

        with self.download_mgr.download_lock:
            self.download_mgr.is_downloading = True
            self.download_mgr.download_start_time = time.time()
            self.download_mgr.last_progress_time = time.time()
            self.download_mgr._download_has_progress = False
            self.download_mgr._trim_download_active = self.trim_enabled_check.isChecked()
            self.download_mgr.video_duration = self.video_duration
            self.download_mgr.video_title = self.video_title

        self.download_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.setValue(0)
        self.progress_label.setText("0%")

        # Snapshot all widget values on the GUI thread before submitting to worker
        ui_state = {
            "quality": self.quality_combo.currentText(),
            "trim_enabled": self.trim_enabled_check.isChecked(),
            "start_time": self.start_slider.value(),
            "end_time": self.end_slider.value(),
            "filename": self.filename_entry.text().strip(),
            "volume_raw": self.volume_slider.value(),
            "keep_below_10mb": self.keep_below_10mb_check.isChecked(),
            "audio_only": self.audio_only_check.isChecked(),
            "speed_limit": self.speed_limit_entry.text().strip(),
            "download_path": self.download_path,
        }

        # Submit download to thread pool; timeout monitor as daemon thread (no pool slot)
        self.thread_pool.submit(self.download_mgr.download, url, ui_state)
        monitor = threading.Thread(target=self.download_mgr._monitor_download_timeout, daemon=True)
        monitor.start()

    # ======================================================================
    #  Persistence
    # ======================================================================

    def view_upload_history(self):
        """View upload link history in a dialog window."""
        colors = THEMES[self.current_theme]

        dialog = QDialog(self)
        dialog.setWindowTitle("Upload Link History")
        dialog.resize(800, 500)
        dialog.setStyleSheet(f"background-color: {colors['bg']}; color: {colors['fg']};")

        layout = QVBoxLayout(dialog)

        # Read-only text area for history content
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(
            f"background-color: {colors['entry_bg']}; "
            f"color: {colors['entry_fg']}; "
            f"font-family: Consolas, monospace; font-size: 9pt;"
        )
        layout.addWidget(text_edit)

        # Load and display history
        try:
            if UPLOAD_HISTORY_FILE.exists():
                with open(UPLOAD_HISTORY_FILE, "r", encoding="utf-8") as f:
                    content = f.read()
                    if content:
                        text_edit.setPlainText(content)
                    else:
                        text_edit.setPlainText("No upload history yet.")
            else:
                text_edit.setPlainText("No upload history yet.")
        except Exception as e:
            text_edit.setPlainText(f"Error loading history: {e}")

        # Button row
        btn_layout = QHBoxLayout()

        copy_btn = QPushButton("Copy All")
        clear_btn = QPushButton("Clear History")
        close_btn = QPushButton("Close")

        def copy_all():
            QApplication.clipboard().setText(text_edit.toPlainText())
            QMessageBox.information(dialog, "Copied", "History copied to clipboard!")

        def clear_history():
            confirm = QMessageBox.question(
                dialog,
                "Clear History",
                "Are you sure you want to clear all upload history?",
            )
            if confirm == QMessageBox.StandardButton.Yes:
                try:
                    if UPLOAD_HISTORY_FILE.exists():
                        UPLOAD_HISTORY_FILE.unlink()
                    text_edit.setReadOnly(False)
                    text_edit.clear()
                    text_edit.setPlainText("No upload history yet.")
                    text_edit.setReadOnly(True)
                except Exception as e:
                    QMessageBox.critical(dialog, "Error", f"Failed to clear history: {e}")

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
    if window.current_theme == "dark":
        _set_dark_title_bar(window, dark=True)

    # Signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        window.close()

    signal.signal(signal.SIGINT, signal_handler)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, signal_handler)

    sys.exit(app.exec())


if __name__ == "__main__":
    # Suppress PyInstaller _MEI temp dir cleanup errors on Windows.
    # PyInstaller's atexit handler raises a noisy error if the _MEI dir
    # can't be removed (e.g. DLLs still locked after self-update).
    # Register our own handler first to silently attempt the cleanup.
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        import atexit

        _mei = getattr(sys, "_MEIPASS", None)
        if _mei:
            atexit.register(lambda: shutil.rmtree(_mei, ignore_errors=True))

    main()
