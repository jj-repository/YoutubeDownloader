"""TrimmingManager — Video metadata, duration fetching, and preview frame extraction.

Extracted from YouTubeDownloader (downloader_pyqt6.py).
Owns video state and background workers; emits signals for all GUI updates.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from collections import OrderedDict
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPainter

from constants import (
    FFPROBE_TIMEOUT,
    MAX_VIDEO_DURATION,
    METADATA_FETCH_TIMEOUT,
    PREVIEW_CACHE_SIZE,
    PREVIEW_HEIGHT,
    PREVIEW_WIDTH,
    STREAM_FETCH_TIMEOUT,
    TEMP_DIR_MAX_AGE,
)
from managers.utils import _subprocess_kwargs, is_local_file, retry_network_operation

logger = logging.getLogger(__name__)


class TrimmingManager(QObject):
    """Manages video metadata fetching, duration parsing, and preview frame extraction."""

    sig_update_status = pyqtSignal(str, str)  # message, color
    sig_show_messagebox = pyqtSignal(str, str, str)  # type, title, message
    sig_run_on_gui = pyqtSignal(object)  # callable for GUI thread
    sig_duration_fetched = pyqtSignal(int, str)  # duration_seconds, video_title_or_empty
    sig_local_duration_fetched = pyqtSignal(int, str)  # duration_seconds, video_title
    sig_preview_ready = pyqtSignal(object, str)  # QPixmap, position ("start"|"end")
    sig_fetch_done = pyqtSignal()  # fetch button re-enable

    def __init__(
        self,
        ytdlp_path: str,
        ffmpeg_path: str,
        ffprobe_path: str,
        temp_dir: str,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.ytdlp_path = ytdlp_path
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.temp_dir = temp_dir

        # Video metadata state
        self.video_duration: int = 0
        self.video_title: str | None = None
        self.current_video_url: str | None = None

        # Cached direct stream URL (avoids repeated yt-dlp -g calls per frame)
        self._stream_url_cache: tuple[str, str] | None = None  # (video_url, stream_url)

        # Preview cache (LRU)
        self.preview_cache: OrderedDict[int, str] = OrderedDict()

        # Thread safety
        self.preview_lock = threading.Lock()
        self.fetch_lock = threading.Lock()
        self.is_fetching_duration = False
        self.preview_thread_running = False

    def cleanup_old_temp_dirs(self):
        """Remove orphaned temp directories from previous crashes."""
        import glob
        import shutil
        import tempfile
        import time

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

    # ------------------------------------------------------------------
    #  Duration fetching
    # ------------------------------------------------------------------

    def fetch_video_duration(self, url: str) -> None:
        """Fetch video duration and title from a URL or local file.

        Runs in a worker thread.  On success, sets ``self.video_duration``
        and ``self.video_title``, then emits ``sig_duration_fetched``.
        On error, emits ``sig_show_messagebox`` and ``sig_update_status``.
        Always clears ``is_fetching_duration`` and emits ``sig_fetch_done``
        in the finally block.
        """
        try:
            if is_local_file(url):
                return self._fetch_local_file_duration(url)

            def _fetch_metadata():
                cmd = [
                    self.ytdlp_path,
                    "--print",
                    "%(duration_string)s\n%(title)s",
                    "--",
                    url,
                ]
                return subprocess.run(
                    cmd,
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=METADATA_FETCH_TIMEOUT,
                    **_subprocess_kwargs,
                )

            result = retry_network_operation(_fetch_metadata, "Fetch metadata")

            if result.returncode == 0:
                lines = result.stdout.strip().splitlines()
                duration_str = lines[0] if lines else ""
                parts = duration_str.split(":")

                if len(parts) == 1:
                    duration = int(parts[0])
                elif len(parts) == 2:
                    mins, secs = int(parts[0]), int(parts[1])
                    if mins < 0 or secs < 0 or secs >= 60:
                        raise ValueError(f"Invalid time values in duration: {duration_str}")
                    duration = mins * 60 + secs
                elif len(parts) == 3:
                    hours, mins, secs = int(parts[0]), int(parts[1]), int(parts[2])
                    if hours < 0 or mins < 0 or secs < 0 or mins >= 60 or secs >= 60:
                        raise ValueError(f"Invalid time values in duration: {duration_str}")
                    duration = hours * 3600 + mins * 60 + secs
                else:
                    raise ValueError(f"Invalid duration format: {duration_str}")

                if duration < 0:
                    raise ValueError(f"Negative duration: {duration}")
                if duration > MAX_VIDEO_DURATION:
                    logger.warning(
                        f"Duration {duration}s exceeds max, capping to {MAX_VIDEO_DURATION}s"
                    )
                    duration = MAX_VIDEO_DURATION

                self.video_duration = duration

                video_title: str | None = None
                if len(lines) >= 2 and lines[1].strip():
                    video_title = lines[1].strip()
                    self.video_title = video_title
                    logger.info(f"Video title: {video_title}")

                self.sig_duration_fetched.emit(self.video_duration, video_title or "")
                self.sig_update_status.emit("Duration fetched successfully", "green")
                logger.info(f"Successfully fetched video duration: {self.video_duration}s")
            else:
                raise Exception(f"yt-dlp returned error: {result.stderr}")

        except subprocess.TimeoutExpired:
            error_msg = "Request timed out. Please check your internet connection."
            self.sig_show_messagebox.emit("error", "Error", error_msg)
            self.sig_update_status.emit("Duration fetch timed out", "red")
            logger.error("Timeout fetching video duration")
        except ValueError as e:
            error_msg = f"Invalid duration format received: {e}"
            self.sig_show_messagebox.emit("error", "Error", error_msg)
            self.sig_update_status.emit("Invalid duration format", "red")
            logger.error(f"Duration parsing error: {e}")
        except Exception as e:
            err_msg = f"Failed to fetch video duration:\n{e}"
            self.sig_show_messagebox.emit("error", "Error", err_msg)
            self.sig_update_status.emit("Failed to fetch duration", "red")
            logger.exception(f"Unexpected error fetching duration: {e}")
        finally:
            with self.fetch_lock:
                self.is_fetching_duration = False
            self.sig_fetch_done.emit()

    def _fetch_local_file_duration(self, filepath: str) -> None:
        """Fetch duration from a local file using ffprobe.

        Runs in a worker thread.  On success, sets ``self.video_duration``
        and emits ``sig_local_duration_fetched(duration, title)``.
        """
        try:
            cmd = [
                self.ffprobe_path,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                "--",
                filepath,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=FFPROBE_TIMEOUT,
                check=True,
                **_subprocess_kwargs,
            )
            duration_seconds = float(result.stdout.strip())
            duration = int(duration_seconds)
            if duration < 0:
                raise ValueError(f"Negative duration: {duration}")
            if duration > MAX_VIDEO_DURATION:
                logger.warning(
                    f"Duration {duration}s exceeds max, capping to {MAX_VIDEO_DURATION}s"
                )
                duration = MAX_VIDEO_DURATION
            self.video_duration = duration

            video_title = Path(filepath).stem
            self.video_title = video_title

            self.sig_local_duration_fetched.emit(self.video_duration, video_title)
            self.sig_update_status.emit("Duration fetched successfully", "green")
            logger.info(f"Local file duration: {self.video_duration}s")

        except subprocess.CalledProcessError as e:
            self.sig_show_messagebox.emit("error", "Error", "Failed to read video file.")
            self.sig_update_status.emit("Failed to read file", "red")
            logger.error(f"ffprobe error: {e}")
        except ValueError as e:
            self.sig_show_messagebox.emit("error", "Error", "Invalid video file format")
            self.sig_update_status.emit("Invalid video file format", "red")
            logger.error(f"Duration parsing error: {e}")
        except Exception as e:
            self.sig_show_messagebox.emit("error", "Error", "Failed to read file.")
            self.sig_update_status.emit("Failed to read file", "red")
            logger.exception(f"Unexpected error reading local file: {e}")
        finally:
            with self.fetch_lock:
                self.is_fetching_duration = False
            self.sig_fetch_done.emit()

    # ------------------------------------------------------------------
    #  Frame extraction
    # ------------------------------------------------------------------

    def extract_frame(self, timestamp: int) -> str | None:
        """Extract a single video frame at *timestamp* seconds.

        Uses an LRU cache and returns the path to a temporary JPEG file,
        or ``None`` on failure.  For remote URLs the direct stream URL is
        resolved via yt-dlp first.
        """
        if not self.current_video_url:
            return None

        # Check cache first
        cached = self._get_cached_frame(timestamp)
        if cached and os.path.exists(cached):
            logger.debug(f"Using cached frame for timestamp {timestamp}s")
            return cached

        try:
            temp_file = os.path.join(self.temp_dir, f"frame_{timestamp}.jpg")

            if is_local_file(self.current_video_url):
                video_url = self.current_video_url
            else:
                # Use cached stream URL if available for this video
                cache = self._stream_url_cache
                if cache and cache[0] == self.current_video_url:
                    video_url = cache[1]
                else:

                    def _get_stream_url():
                        get_url_cmd = [
                            self.ytdlp_path,
                            "-f",
                            "best[height<=480]/best",
                            "--no-playlist",
                            "-g",
                            "--",
                            self.current_video_url,
                        ]
                        return subprocess.run(
                            get_url_cmd,
                            capture_output=True,
                            encoding="utf-8",
                            errors="replace",
                            timeout=STREAM_FETCH_TIMEOUT,
                            check=True,
                            **_subprocess_kwargs,
                        )

                    result = retry_network_operation(
                        _get_stream_url, f"Get stream URL for frame at {timestamp}s"
                    )
                    video_url = result.stdout.strip().split("\n")[0]

                    if not video_url:
                        logger.error("Failed to get stream URL - empty response")
                        return None

                    if not (video_url.startswith("http://") or video_url.startswith("https://")):
                        logger.error(f"Invalid stream URL format: {video_url[:100]}")
                        return None

                    self._stream_url_cache = (self.current_video_url, video_url)

            def _extract_frame():
                cmd = [self.ffmpeg_path, "-nostdin"]
                if video_url.startswith("http"):
                    cmd.extend(
                        [
                            "-reconnect",
                            "1",
                            "-reconnect_streamed",
                            "1",
                            "-reconnect_delay_max",
                            "5",
                            "-timeout",
                            "10000000",
                        ]
                    )
                cmd.extend(
                    [
                        "-ss",
                        str(timestamp),
                        "-i",
                        video_url,
                        "-vframes",
                        "1",
                        "-q:v",
                        "2",
                        "-y",
                        temp_file,
                    ]
                )
                return subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=STREAM_FETCH_TIMEOUT,
                    check=True,
                    **_subprocess_kwargs,
                )

            retry_network_operation(_extract_frame, f"Extract frame at {timestamp}s")

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

    # ------------------------------------------------------------------
    #  Preview update
    # ------------------------------------------------------------------

    def update_previews_thread(self, start_time: int, end_time: int) -> None:
        """Extract start/end preview frames and emit ``sig_preview_ready``.

        Runs in a worker thread.  Adjusts *end_time* when it is within
        1 second of ``video_duration`` to avoid EOF issues.
        """
        try:
            adjusted_end_time = end_time
            if self.video_duration > 0 and end_time >= self.video_duration - 1:
                adjusted_end_time = max(0, self.video_duration - 3)
                logger.debug(
                    f"Adjusted end preview time from {end_time}s to {adjusted_end_time}s (near EOF)"
                )

            logger.info(f"Extracting preview frames at {start_time}s and {adjusted_end_time}s")

            # --- Start frame ---
            start_frame_path = self.extract_frame(start_time)
            if start_frame_path:
                image = self._path_to_image(start_frame_path)
                self.sig_preview_ready.emit(image, "start")
            else:
                self.sig_preview_ready.emit(self._error_image(), "start")

            # --- End frame ---
            end_frame_path = self.extract_frame(adjusted_end_time)
            if end_frame_path:
                image = self._path_to_image(end_frame_path)
                self.sig_preview_ready.emit(image, "end")
            else:
                self.sig_preview_ready.emit(self._error_image(), "end")
        finally:
            with self.preview_lock:
                self.preview_thread_running = False

    # ------------------------------------------------------------------
    #  Cache helpers
    # ------------------------------------------------------------------

    def clear_preview_cache(self) -> None:
        """Clear the preview frame cache, deleting cached files from disk."""
        logger.info("Clearing preview cache")
        self._stream_url_cache = None
        with self.preview_lock:
            for _timestamp, file_path in self.preview_cache.items():
                try:
                    if os.path.exists(file_path):
                        os.unlink(file_path)
                except OSError as e:
                    logger.debug(f"Failed to delete cached preview file {file_path}: {e}")
            self.preview_cache.clear()

    def _cache_preview_frame(self, timestamp: int, file_path: str) -> None:
        """Add a frame to the cache with LRU eviction."""
        with self.preview_lock:
            if timestamp in self.preview_cache:
                del self.preview_cache[timestamp]

            if len(self.preview_cache) >= PREVIEW_CACHE_SIZE:
                _oldest_key, old_path = self.preview_cache.popitem(last=False)
                try:
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except OSError:
                    pass

            self.preview_cache[timestamp] = file_path

    def _get_cached_frame(self, timestamp: int) -> str | None:
        """Get a cached frame path if available, promoting it in the LRU."""
        with self.preview_lock:
            if timestamp in self.preview_cache:
                self.preview_cache.move_to_end(timestamp)
                return self.preview_cache[timestamp]
            return None

    # ------------------------------------------------------------------
    #  Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _path_to_image(image_path: str) -> QImage:
        """Load an image file and scale to preview size (thread-safe).

        Returns QImage (not QPixmap) so it can be created from worker threads.
        The GUI-thread handler converts to QPixmap for display.
        """
        img = QImage(image_path)
        if img.isNull():
            return TrimmingManager._error_image()
        return img.scaled(
            PREVIEW_WIDTH,
            PREVIEW_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    _cached_error_image: QImage | None = None
    _error_image_lock = threading.Lock()

    @classmethod
    def _error_image(cls) -> QImage:
        """Return a cached error placeholder ``QImage`` (thread-safe)."""
        if cls._cached_error_image is None:
            with cls._error_image_lock:
                if cls._cached_error_image is None:
                    img = QImage(PREVIEW_WIDTH, PREVIEW_HEIGHT, QImage.Format.Format_ARGB32)
                    img.fill(QColor("#2d2d2d"))
                    painter = QPainter(img)
                    painter.setPen(QColor("#ffffff"))
                    painter.setFont(QFont("Arial", 10))
                    painter.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, "Error")
                    painter.end()
                    cls._cached_error_image = img
        return cls._cached_error_image
