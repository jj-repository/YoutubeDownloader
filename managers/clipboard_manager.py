"""ClipboardManager — Clipboard monitoring state and batch download orchestration.

Extracted from YouTubeDownloader (downloader_pyqt6.py).
Owns clipboard URL state and threading locks; emits signals for all GUI updates.

NOTE: The main window currently accesses internal state directly. Methods on
this class serve as the intended public API for future consolidation.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class ClipboardManager(QObject):
    """Manages clipboard URL collection state and download coordination."""

    # ── Signals ───────────────────────────────────────────────────────────
    sig_clipboard_progress = pyqtSignal(float)  # 0-100
    sig_clipboard_status = pyqtSignal(str, str)  # message, color
    sig_clipboard_total = pyqtSignal(str)  # total label text
    sig_update_url_status = pyqtSignal(str, str)  # url, new_status
    sig_add_url_to_list = pyqtSignal(str)  # url to add to UI
    sig_show_messagebox = pyqtSignal(str, str, str)
    sig_run_on_gui = pyqtSignal(object)  # callable for GUI thread
    sig_downloads_finished = pyqtSignal()  # queue complete

    def __init__(self, thread_pool: ThreadPoolExecutor, parent=None):
        super().__init__(parent)
        self.thread_pool = thread_pool

        # State
        # Lock ordering: auto_download_lock -> clipboard_lock (never reverse)
        self.clipboard_lock = threading.Lock()
        self.auto_download_lock = threading.Lock()
        self.clipboard_monitoring = False
        self.clipboard_last_content = ""
        self.clipboard_url_list: deque[dict] = deque()  # [{"url": str, "status": str}]
        self.completed_count = 0
        self.failed_count = 0
        self.clipboard_download_path = str(Path.home() / "Downloads")
        self.clipboard_stop_event = threading.Event()  # set = stopped
        self.clipboard_stop_event.set()  # initially stopped
        self.clipboard_auto_downloading = False
        self._shutting_down = False
        self._clipboard_backend: str | None = None
        self.klipper_interface = None  # set by main window if dbus available

    def set_klipper_interface(self, interface):
        """Set the KDE Klipper D-Bus interface (called by main window after init)."""
        self.klipper_interface = interface

    def _detect_clipboard_backend(self) -> str:
        """Probe clipboard backends and return the name of the first working one."""
        if self.klipper_interface:
            try:
                self.klipper_interface.getClipboardContents()
                logger.info("Clipboard backend: klipper")
                return "klipper"
            except Exception:
                pass
        try:
            import pyperclip

            pyperclip.paste()
            logger.info("Clipboard backend: pyperclip")
            return "pyperclip"
        except Exception:
            pass
        try:
            from PyQt6.QtWidgets import QApplication

            QApplication.clipboard().text()
            logger.info("Clipboard backend: qt")
            return "qt"
        except Exception:
            pass
        logger.warning("No clipboard backend available")
        return "qt"

    def read_clipboard_content(self) -> str | None:
        """Read clipboard using the detected backend."""
        if self._clipboard_backend is None:
            self._clipboard_backend = self._detect_clipboard_backend()

        try:
            if self._clipboard_backend == "klipper" and self.klipper_interface:
                return str(self.klipper_interface.getClipboardContents())
            elif self._clipboard_backend == "pyperclip":
                import pyperclip

                return pyperclip.paste()
            else:
                from PyQt6.QtWidgets import QApplication

                return QApplication.clipboard().text()
        except Exception:
            return None
