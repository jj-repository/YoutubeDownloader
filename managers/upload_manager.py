"""UploadManager — Catbox upload logic and queue management.

Extracted from YouTubeDownloader (downloader_pyqt6.py).
All GUI operations are dispatched via signals to the main window thread.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QObject, pyqtSignal

from constants import BYTES_PER_MB, CATBOX_MAX_SIZE_MB, UPLOAD_HISTORY_FILE

logger = logging.getLogger(__name__)


class UploadManager(QObject):
    """Manages Catbox.moe uploads for both trimmer and uploader tabs."""

    # Trimmer tab status
    sig_upload_status = pyqtSignal(str, str)  # msg, color
    # Uploader tab status
    sig_uploader_status = pyqtSignal(str, str)  # msg, color
    # Enable/disable trimmer upload button
    sig_enable_upload_btn = pyqtSignal(bool)
    # Show a message box (type, title, message)
    sig_show_messagebox = pyqtSignal(str, str, str)
    # Execute callable on the GUI thread
    sig_run_on_gui = pyqtSignal(object)
    # Trimmer upload completed (file_url, filename)
    sig_upload_complete = pyqtSignal(str, str)
    # Single file from uploader queue done (file_url)
    sig_uploader_file_uploaded = pyqtSignal(str)
    # Uploader queue finished (count of files uploaded, completed_normally)
    sig_uploader_queue_done = pyqtSignal(int, bool)

    def __init__(self, thread_pool: ThreadPoolExecutor, parent=None):
        super().__init__(parent)
        self.thread_pool = thread_pool

        self.catbox_client = None  # lazy-initialized on first upload

        self.upload_lock = threading.Lock()
        self.uploader_lock = threading.RLock()
        self.is_uploading = False
        self.uploader_is_uploading = False
        self.last_output_file: str | None = None
        self.uploader_file_queue: list[dict] = []  # [{"path": str, "widget": QWidget|None}]
        self._upload_save_count = 0

        # Trim upload history at startup to prevent unbounded growth
        self._trim_history_on_startup()

    def _trim_history_on_startup(self):
        """Cap upload history file at 500 lines on startup."""
        try:
            if not UPLOAD_HISTORY_FILE.exists():
                return
            with open(UPLOAD_HISTORY_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > 500:
                with open(UPLOAD_HISTORY_FILE, "w", encoding="utf-8") as f:
                    f.writelines(lines[-500:])
                logger.info(f"Trimmed upload history from {len(lines)} to 500 entries at startup")
        except Exception as e:
            logger.error(f"Error trimming upload history at startup: {e}")

    def _get_catbox_client(self):
        """Lazy-initialize and return the CatboxClient."""
        if self.catbox_client is None:
            from catboxpy.catbox import CatboxClient

            self.catbox_client = CatboxClient()
        return self.catbox_client

    # ------------------------------------------------------------------
    # Trimmer upload
    # ------------------------------------------------------------------

    def upload_to_catbox(self):
        """Background worker. Uploads last_output_file to Catbox.moe."""
        try:
            filepath = self.last_output_file
            if not filepath:
                return
            with self.upload_lock:
                self.is_uploading = True
            logger.info(f"Starting upload to Catbox.moe: {filepath}")
            file_url = self._get_catbox_client().upload(filepath)
            if not file_url or not file_url.startswith("https://"):
                raise RuntimeError(f"Unexpected upload URL: {file_url!r}")
            filename = os.path.basename(filepath)
            self.save_upload_link(file_url, filename)
            self.sig_upload_complete.emit(file_url, filename)
            logger.info(f"Upload successful: {file_url}")
        except Exception as e:
            error_msg = str(e)
            self.sig_upload_status.emit("Upload failed", "red")
            self.sig_enable_upload_btn.emit(True)
            self.sig_show_messagebox.emit(
                "error",
                "Upload Failed",
                f"Failed to upload file:\n\n{error_msg}",
            )
            logger.exception(f"Upload failed: {e}")
        finally:
            with self.upload_lock:
                self.is_uploading = False

    def enable_upload_button(self, filepath: str):
        """Thread-safe bridge — sets last_output_file and enables the button."""
        if filepath and os.path.isfile(filepath):
            self.last_output_file = filepath
            self.sig_enable_upload_btn.emit(True)
            logger.info(f"Upload enabled for: {filepath}")

    def start_upload_if_valid(self) -> tuple[bool, str]:
        """Validate file availability and size. Returns (ok, error_msg)."""
        if not self.last_output_file or not os.path.isfile(self.last_output_file):
            return (
                False,
                "No file available to upload. Please download/process a video first.",
            )
        file_size_mb = os.path.getsize(self.last_output_file) / BYTES_PER_MB
        if file_size_mb > CATBOX_MAX_SIZE_MB:
            return False, (
                f"File size ({file_size_mb:.1f} MB) exceeds Catbox.moe's 200MB limit.\n"
                f"Please trim the video or use a lower quality setting."
            )
        return True, ""

    # ------------------------------------------------------------------
    # Uploader queue
    # ------------------------------------------------------------------

    def process_uploader_queue(self):
        """Background worker. Iterates the queue snapshot and uploads each file."""
        with self.uploader_lock:
            queue_snapshot = list(self.uploader_file_queue)
        total_count = len(queue_snapshot)
        uploaded_count = 0

        completed_normally = False
        try:
            for index, item in enumerate(queue_snapshot):
                with self.uploader_lock:
                    if not self.uploader_is_uploading:
                        logger.info("Uploader queue processing stopped by user")
                        break

                file_path = item["path"]
                filename = os.path.basename(file_path)
                self.sig_uploader_status.emit(
                    f"Uploading {index + 1}/{total_count}: {filename}...", "blue"
                )

                if self.upload_single_file(file_path):
                    uploaded_count += 1
            else:
                # Loop finished without break — all items processed
                completed_normally = True
        finally:
            with self.uploader_lock:
                self.uploader_is_uploading = False

        self.sig_uploader_queue_done.emit(uploaded_count, completed_normally)

    def upload_single_file(self, file_path: str) -> bool:
        """Upload a single file to Catbox. Returns True on success."""
        try:
            logger.info(f"Uploading file from queue: {file_path}")
            file_url = self._get_catbox_client().upload(file_path)
            if not file_url or not file_url.startswith("https://"):
                raise RuntimeError(f"Unexpected upload URL: {file_url!r}")
            filename = os.path.basename(file_path)
            self.save_upload_link(file_url, filename)
            self.sig_uploader_file_uploaded.emit(file_url)
            logger.info(f"Upload successful: {file_url}")
            return True
        except Exception as e:
            logger.exception(f"Upload failed for {file_path}: {e}")
            error_msg = str(e)
            filename = os.path.basename(file_path)
            self.sig_show_messagebox.emit(
                "error",
                "Upload Failed",
                f"Failed to upload {filename}:\n\n{error_msg}",
            )
            return False

    def start_queue_upload(self) -> tuple[bool, str]:
        """Validate queue and mark uploading. Returns (ok, error_msg)."""
        with self.uploader_lock:
            if len(self.uploader_file_queue) == 0:
                return False, "No files in queue. Please add files first."
            if self.uploader_is_uploading:
                return False, ""
            self.uploader_is_uploading = True
        return True, ""

    def stop_queue_upload(self):
        """Signal the queue loop to stop after the current file."""
        with self.uploader_lock:
            self.uploader_is_uploading = False

    def add_to_queue(self, file_path: str) -> bool:
        """Add a file to the upload queue. Returns True if added, False if duplicate."""
        with self.uploader_lock:
            if any(item["path"] == file_path for item in self.uploader_file_queue):
                return False
            self.uploader_file_queue.append({"path": file_path, "widget": None})
        return True

    def remove_from_queue(self, file_path: str):
        """Remove a file from the queue. Returns the widget to destroy (or None)."""
        widget = None
        with self.uploader_lock:
            for i, item in enumerate(self.uploader_file_queue):
                if item["path"] == file_path:
                    widget = item.get("widget")
                    self.uploader_file_queue.pop(i)
                    break
        return widget

    def clear_queue(self) -> list:
        """Clear the queue. Returns list of widgets to destroy."""
        widgets = []
        with self.uploader_lock:
            for item in self.uploader_file_queue:
                if item.get("widget"):
                    widgets.append(item["widget"])
            self.uploader_file_queue.clear()
        return widgets

    def queue_count(self) -> int:
        """Thread-safe queue length."""
        with self.uploader_lock:
            return len(self.uploader_file_queue)

    def set_widget_for_queue_item(self, file_path: str, widget):
        """Associate a widget with a queue entry (called from main thread)."""
        with self.uploader_lock:
            for item in self.uploader_file_queue:
                if item["path"] == file_path:
                    item["widget"] = widget
                    break

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_upload_link(self, link, filename=""):
        """Append an upload link to the history file, trimming when needed."""
        try:
            UPLOAD_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(UPLOAD_HISTORY_FILE, "a", encoding="utf-8") as f:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{timestamp} | {filename} | {link}\n")
            self._upload_save_count += 1
            if self._upload_save_count >= 100:
                self._upload_save_count = 0
                try:
                    with open(UPLOAD_HISTORY_FILE, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    if len(lines) > 1000:
                        with open(UPLOAD_HISTORY_FILE, "w", encoding="utf-8") as f:
                            f.writelines(lines[-500:])
                        logger.info("Trimmed upload history to last 500 entries")
                except Exception as trim_err:
                    logger.error(f"Error trimming upload history: {trim_err}")
            logger.info(f"Saved upload link to history: {link}")
        except Exception as e:
            logger.error(f"Error saving upload link: {e}")
