"""ClipboardManager — Clipboard monitoring state and batch download orchestration.

Extracted from YouTubeDownloader (downloader_pyqt6.py).
Owns clipboard URL state and threading locks; emits signals for all GUI updates.

NOTE: The main window currently accesses internal state directly. Methods on
this class serve as the intended public API for future consolidation.
"""

from __future__ import annotations

import logging
import threading
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
        self.clipboard_lock = threading.Lock()
        self.auto_download_lock = threading.Lock()
        self.clipboard_monitoring = False
        self.clipboard_last_content = ""
        self.clipboard_url_list: list[dict] = []  # [{"url": str, "status": str}]
        self.clipboard_download_path = str(Path.home() / "Downloads")
        self.clipboard_stop_event = threading.Event()  # set = stopped
        self.clipboard_stop_event.set()  # initially stopped
        self.clipboard_auto_downloading = False
        self._shutting_down = False
