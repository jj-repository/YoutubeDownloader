"""Download orchestration manager extracted from YouTubeDownloader.

Handles command building, trimmed downloads (byte-range seeking + local ffmpeg),
timeout monitoring, and the main download() method. Uses Qt signals for all GUI
updates — no direct widget access.
"""

from __future__ import annotations

import glob
import logging
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PyQt6.QtCore import QObject, pyqtSignal

from constants import (
    AUDIO_BITRATE,
    BUFFER_SIZE,
    CHUNK_SIZE,
    CONCURRENT_FRAGMENTS,
    DEPENDENCY_CHECK_TIMEOUT,
    DOWNLOAD_PROGRESS_TIMEOUT,
    DOWNLOAD_PROGRESS_TIMEOUT_TRIM,
    DOWNLOAD_TIMEOUT,
    METADATA_FETCH_TIMEOUT,
    PROGRESS_COMPLETE,
    VOLUME_CHANGE_THRESHOLD,
)
from managers.encoding import EncodeCallbacks, EncodingService
from managers.utils import (
    _subprocess_kwargs,
    get_speed_limit_args,
    is_local_file,
    is_playlist_url,
    safe_process_cleanup,
    sanitize_filename,
    seconds_to_hms,
    validate_volume,
)

logger = logging.getLogger(__name__)

# Regex patterns for parsing yt-dlp progress output
PROGRESS_REGEX = re.compile(r"(\d+\.?\d*)%")
SPEED_REGEX = re.compile(r"(\d+\.?\d*\s*[KMG]iB/s)")
ETA_REGEX = re.compile(r"ETA\s+(\d{2}:\d{2}(?::\d{2})?)")


class DownloadManager(QObject):
    """Manages download orchestration, command building, and trimmed downloads.

    All GUI updates are done via signals — this class never touches widgets directly.
    """

    sig_update_progress = pyqtSignal(float)
    sig_update_status = pyqtSignal(str, str)
    sig_reset_buttons = pyqtSignal()
    sig_show_messagebox = pyqtSignal(str, str, str)
    sig_run_on_gui = pyqtSignal(object)
    sig_enable_upload = pyqtSignal(str)

    # Trim padding constants
    _TRIM_PADDING_BEFORE = 30  # seconds before start for keyframe alignment
    _TRIM_PADDING_AFTER = 10  # seconds after end for safety

    def __init__(
        self,
        ytdlp_path: str,
        ffmpeg_path: str,
        ffprobe_path: str,
        encoding: EncodingService,
        thread_pool: ThreadPoolExecutor,
        parent=None,
    ):
        super().__init__(parent)
        self.ytdlp_path = ytdlp_path
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.encoding = encoding
        self.thread_pool = thread_pool

        # Download state
        self.download_lock = threading.Lock()
        self.is_downloading = False
        self.current_process: subprocess.Popen | None = None
        self.last_progress_time: float | None = None
        self.download_start_time: float | None = None
        self._download_has_progress = False
        self._trim_download_active = False
        self._last_status_update: float = 0

        # Video metadata (set by main window before download)
        self.video_duration: float = 0
        self.video_title: str | None = None

        # Dependency state (set by init_dependencies_async)
        self.dependencies_ok: bool = True
        self.hw_encoder: str | None = None

    # ------------------------------------------------------------------
    #  Dependency checks
    # ------------------------------------------------------------------

    def check_dependencies(self) -> bool:
        """Check if yt-dlp, ffmpeg, and ffprobe are available."""
        try:
            ytdlp_found = (
                os.path.isfile(self.ytdlp_path) and os.access(self.ytdlp_path, os.X_OK)
            ) or shutil.which(self.ytdlp_path)
            if ytdlp_found:
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

    def detect_hw_encoder(self, deps_ok: bool = True) -> tuple[str | None, str | None]:
        """Probe for hardware H.264 encoders.

        Probe order: NVENC (NVIDIA) → AMF (AMD, Windows) → VAAPI (AMD/Intel, Linux).
        Returns (encoder_name, vaapi_device) where vaapi_device is only set for VAAPI.
        """
        if not deps_ok:
            return None, None

        # NVENC and AMF: standard probe via test encode
        for encoder in ("h264_nvenc", "h264_amf"):
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
                    return encoder, None
                else:
                    stderr = result.stderr.decode("utf-8", errors="replace").strip()
                    logger.info(f"Hardware encoder {encoder} not available: {stderr[-200:]}")
            except (subprocess.TimeoutExpired, OSError) as e:
                logger.info(f"Hardware encoder {encoder} probe failed: {e}")

        # VAAPI: Linux only (AMD/Intel integrated GPUs)
        if sys.platform != "win32":
            vaapi_device = "/dev/dri/renderD128"
            try:
                probe_out = os.path.join(tempfile.gettempdir(), "ytdl_hwprobe.mp4")
                cmd = [
                    self.ffmpeg_path,
                    "-hide_banner",
                    "-y",
                    "-loglevel",
                    "error",
                    "-vaapi_device",
                    vaapi_device,
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=64x64:rate=25:duration=1",
                    "-vf",
                    "format=nv12,hwupload",
                    "-frames:v",
                    "10",
                    "-c:v",
                    "h264_vaapi",
                    probe_out,
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=10, **_subprocess_kwargs)
                try:
                    os.remove(probe_out)
                except OSError:
                    pass
                if result.returncode == 0:
                    logger.info(f"Hardware encoder available: h264_vaapi (device={vaapi_device})")
                    return "h264_vaapi", vaapi_device
                else:
                    stderr = result.stderr.decode("utf-8", errors="replace").strip()
                    logger.info(f"Hardware encoder h264_vaapi not available: {stderr[-200:]}")
            except (subprocess.TimeoutExpired, OSError) as e:
                logger.info(f"Hardware encoder h264_vaapi probe failed: {e}")

        logger.info("No hardware encoder found, using libx264")
        return None, None

    def init_dependencies_async(self) -> None:
        """Check dependencies and detect HW encoder (call from thread pool)."""
        deps_ok = self.check_dependencies()
        if not deps_ok:
            logger.warning("Dependencies check failed at startup")
        hw_enc, vaapi_device = self.detect_hw_encoder(deps_ok)

        def _apply_on_gui():
            self.dependencies_ok = deps_ok
            self.hw_encoder = hw_enc
            self.encoding.hw_encoder = hw_enc
            self.encoding.vaapi_device = vaapi_device

        self.sig_run_on_gui.emit(_apply_on_gui)

    # ------------------------------------------------------------------
    #  Thread-safe helpers
    # ------------------------------------------------------------------

    def update_progress(self, value: float) -> None:
        """Update progress bar via signal (thread-safe)."""
        try:
            value = float(value)
            value = max(0, min(100, value))
            self.sig_update_progress.emit(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid progress value: {value} - {e}")

    def update_status(self, message: str, color: str) -> None:
        """Update status label via signal (thread-safe)."""
        self.sig_update_status.emit(str(message), str(color))

    def _make_encode_callbacks(self) -> EncodeCallbacks:
        """Create EncodeCallbacks wired to this manager's state."""
        return EncodeCallbacks(
            on_progress=lambda v: self.sig_update_progress.emit(v),
            on_status=lambda m, c: self.sig_update_status.emit(m, c),
            is_cancelled=lambda: not self.is_downloading,
            process_lock=self.download_lock,
            set_process=lambda p: setattr(self, "current_process", p),
            on_heartbeat=lambda: setattr(self, "last_progress_time", time.time()),
        )

    # ------------------------------------------------------------------
    #  File helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_latest_file(download_path: str) -> str | None:
        """Find the most recently created file in the download directory."""
        try:
            download_dir = Path(download_path)
            if not download_dir.exists():
                return None

            latest = None
            with os.scandir(download_dir) as entries:
                latest = max(
                    (e for e in entries if e.is_file()),
                    key=lambda e: e.stat().st_ctime,
                    default=None,
                )
            return str(latest.path) if latest else None

        except Exception as e:
            logger.error(f"Error finding latest file: {e}")
            return None

    @staticmethod
    def cleanup_temp_files(temp_dir: str | None) -> None:
        """Clean up a temporary directory."""
        try:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned up temp directory: {temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {e}")

    # ------------------------------------------------------------------
    #  Command builders
    # ------------------------------------------------------------------

    def build_base_ytdlp_command(self) -> list[str]:
        """Build base yt-dlp command with common options."""
        return [
            self.ytdlp_path,
            "--concurrent-fragments",
            CONCURRENT_FRAGMENTS,
            "--buffer-size",
            BUFFER_SIZE,
            "--http-chunk-size",
            CHUNK_SIZE,
            "--newline",
            "--progress",
        ]

    def build_audio_ytdlp_command(
        self, url: str, output_path: str, volume: float = 1.0
    ) -> list[str]:
        """Build yt-dlp command for audio-only download.

        Args:
            url: YouTube URL
            output_path: Full output path with filename template
            volume: Volume multiplier (default 1.0)
        """
        volume = float(volume)
        cmd = self.build_base_ytdlp_command()
        cmd.extend(
            [
                "-f",
                "bestaudio",
                "--extract-audio",
                "--audio-format",
                "mp3",
                "--audio-quality",
                AUDIO_BITRATE,
            ]
        )

        if volume != 1.0:
            cmd.extend(["--postprocessor-args", f"ffmpeg:-af volume={volume}"])

        cmd.extend(["-o", output_path, "--", url])
        return cmd

    def build_video_ytdlp_command(
        self,
        url: str,
        output_path: str,
        quality: str,
        volume: float = 1.0,
        trim_start: float | None = None,
        trim_end: float | None = None,
    ) -> list[str]:
        """Build yt-dlp command for video download with optional trimming.

        Args:
            url: YouTube URL
            output_path: Full output path with filename template
            quality: Video height (e.g., '1080', '720')
            volume: Volume multiplier (default 1.0)
            trim_start: Start time in seconds (optional)
            trim_end: End time in seconds (optional)
        """
        volume = float(volume)
        cmd = self.build_base_ytdlp_command()
        cmd.extend(
            [
                "-f",
                f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]",
                "--merge-output-format",
                "mp4",
            ]
        )

        trim_enabled = trim_start is not None and trim_end is not None
        if trim_enabled:
            start_hms = seconds_to_hms(trim_start)
            end_hms = seconds_to_hms(trim_end)
            cmd.extend(
                [
                    "--download-sections",
                    f"*{start_hms}-{end_hms}",
                    "--force-keyframes-at-cuts",
                ]
            )

        needs_processing = trim_enabled or volume != 1.0
        if needs_processing:
            ffmpeg_args = self.encoding.get_crf_args_for_postprocessor() + [
                "-c:a",
                "aac",
                "-b:a",
                AUDIO_BITRATE,
            ]
            if volume != 1.0:
                ffmpeg_args.extend(["-af", f"volume={volume}"])
            cmd.extend(["--postprocessor-args", "ffmpeg:" + " ".join(ffmpeg_args)])

        cmd.extend(["-o", output_path, "--", url])
        return cmd

    def build_batch_audio_ytdlp_command(
        self, batch_file_path: str, output_path: str, volume: float = 1.0
    ) -> list[str]:
        """Build yt-dlp command for batch audio download via --batch-file."""
        cmd = self.build_base_ytdlp_command()
        cmd.extend(
            [
                "-f",
                "bestaudio",
                "--extract-audio",
                "--audio-format",
                "mp3",
                "--audio-quality",
                AUDIO_BITRATE,
            ]
        )
        if volume != 1.0:
            cmd.extend(["--postprocessor-args", f"ffmpeg:-af volume={volume}"])
        cmd.extend(["-o", output_path, "--batch-file", batch_file_path])
        return cmd

    def build_batch_video_ytdlp_command(
        self, batch_file_path: str, output_path: str, quality: str, volume: float = 1.0
    ) -> list[str]:
        """Build yt-dlp command for batch video download via --batch-file."""
        cmd = self.build_base_ytdlp_command()
        cmd.extend(
            [
                "-f",
                f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]",
                "--merge-output-format",
                "mp4",
            ]
        )
        if volume != 1.0:
            ffmpeg_args = self.encoding.get_crf_args_for_postprocessor() + [
                "-c:a",
                "aac",
                "-b:a",
                AUDIO_BITRATE,
            ]
            ffmpeg_args.extend(["-af", f"volume={volume}"])
            cmd.extend(["--postprocessor-args", "ffmpeg:" + " ".join(ffmpeg_args)])
        cmd.extend(["-o", output_path, "--batch-file", batch_file_path])
        return cmd

    # ------------------------------------------------------------------
    #  Trimmed download via byte-range seeking + local ffmpeg trim
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_sidx(data: bytes):
        """Parse SIDX box from fMP4 header data.

        Returns (init_end, segments) where segments is a list of
        (byte_offset, byte_size, start_time_sec, duration_sec), or None.
        """
        pos = 0
        while pos < len(data) - 8:
            box_size = struct.unpack(">I", data[pos : pos + 4])[0]
            box_type = data[pos + 4 : pos + 8]
            if box_size < 8:
                break
            if box_type == b"sidx":
                sidx_end = pos + box_size
                p = pos + 8  # skip size + type
                version = data[p]
                p += 4  # version(1) + flags(3)
                p += 4  # reference_id
                timescale = struct.unpack(">I", data[p : p + 4])[0]
                p += 4
                if timescale == 0:
                    return None
                if version == 0:
                    p += 4  # earliest_presentation_time
                    first_offset = struct.unpack(">I", data[p : p + 4])[0]
                    p += 4
                else:
                    p += 8  # earliest_presentation_time (64-bit)
                    first_offset = struct.unpack(">Q", data[p : p + 8])[0]
                    p += 8
                p += 2  # reserved
                ref_count = struct.unpack(">H", data[p : p + 2])[0]
                p += 2

                seg_offset = sidx_end + first_offset
                cur_time = 0.0
                segments = []
                for _ in range(ref_count):
                    if p + 12 > len(data):
                        break
                    ref_info = struct.unpack(">I", data[p : p + 4])[0]
                    ref_size = ref_info & 0x7FFFFFFF
                    seg_dur = struct.unpack(">I", data[p + 4 : p + 8])[0]
                    p += 12
                    dur_sec = seg_dur / timescale
                    segments.append((seg_offset, ref_size, cur_time, dur_sec))
                    seg_offset += ref_size
                    cur_time += dur_sec

                return sidx_end, segments
            pos += box_size
        return None

    def _get_stream_urls(self, url: str, format_spec: str) -> tuple[str, str | None]:
        """Get direct video and audio stream URLs using yt-dlp -g."""
        cmd = [self.ytdlp_path, "-g", "-f", format_spec, "--", url]
        logger.info(f"Fetching stream URLs: {' '.join(cmd)}")
        self.update_status("Fetching stream URLs...", "blue")
        result = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=METADATA_FETCH_TIMEOUT,
            **_subprocess_kwargs,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to get stream URLs: {result.stderr.strip()}")
        urls = result.stdout.strip().split("\n")
        for u in urls:
            if not u.startswith("https://"):
                raise RuntimeError(f"Rejected non-HTTPS stream URL: {u[:80]}")
        return (urls[0], urls[1]) if len(urls) >= 2 else (urls[0], None)

    _HTTP_RANGE_MAX_SIZE = 512 * 1024  # 512KB — enough for SIDX/moof headers

    def _http_range_read(self, url: str, start: int, end: int) -> bytes:
        """Download a byte range from a URL.

        Reads in chunks and checks is_downloading between them so the
        user can cancel during slow CDN responses (e.g. 10-hour videos).
        """
        requested_size = end - start + 1
        if requested_size > self._HTTP_RANGE_MAX_SIZE:
            raise ValueError(
                f"Requested range {requested_size} exceeds max {self._HTTP_RANGE_MAX_SIZE}"
            )
        req = urllib.request.Request(url)
        req.add_header("Range", f"bytes={start}-{end}")
        chunks = []
        expected_size = requested_size
        total_read = 0
        with urllib.request.urlopen(req, timeout=DOWNLOAD_PROGRESS_TIMEOUT_TRIM // 10) as resp:
            while True:
                if not self.is_downloading:
                    return b"".join(chunks)
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                total_read += len(chunk)
                if total_read > expected_size * 2:
                    raise RuntimeError(f"Response exceeded expected size ({expected_size} bytes)")
                chunks.append(chunk)
                self.last_progress_time = time.time()
        return b"".join(chunks)

    def _download_stream_segment(
        self,
        stream_url: str,
        start_time: float,
        end_time: float,
        output_path: str,
        label: str,
        progress_base: float = 0,
    ) -> float:
        """Download init + relevant byte range from a YouTube stream.

        For fMP4: parses SIDX for exact segment boundaries.
        For webm/other: estimates from clen/dur with generous padding.
        Returns the timestamp (seconds) where the downloaded data starts.
        Raises RuntimeError with a user-friendly message on network errors.
        """
        try:
            return self._download_stream_segment_inner(
                stream_url, start_time, end_time, output_path, label, progress_base
            )
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise RuntimeError(
                f"Network error downloading {label}: {e}\n\n"
                f"This can happen with very long videos. Try again or use a shorter trim range."
            ) from e

    def _download_stream_segment_inner(
        self,
        stream_url: str,
        start_time: float,
        end_time: float,
        output_path: str,
        label: str,
        progress_base: float = 0,
    ) -> float:
        """Inner implementation of stream segment download."""
        params = parse_qs(urlparse(stream_url).query)
        clen = int(params.get("clen", ["0"])[0])
        dur = float(params.get("dur", ["0"])[0])
        if not clen or dur <= 0:
            raise RuntimeError(f"Missing clen/dur in {label} URL")

        pad_before = self._TRIM_PADDING_BEFORE
        pad_after = self._TRIM_PADDING_AFTER
        target_start = max(0, start_time - pad_before)
        target_end = min(dur, end_time + pad_after)

        # Download header (enough for init + SIDX/Cues)
        header_size = min(clen, 512 * 1024)  # 512KB
        self.update_status(f"Fetching {label} index...", "blue")
        self.last_progress_time = time.time()
        header_data = self._http_range_read(stream_url, 0, header_size - 1)

        # Try SIDX parsing for precise segment boundaries
        sidx_result = self._parse_sidx(header_data)
        if sidx_result:
            init_end, segments = sidx_result
            init_data = header_data[:init_end]

            # Find segments covering our padded time range
            first_idx = last_idx = None
            for i, (_, _, seg_t, seg_d) in enumerate(segments):
                if first_idx is None and seg_t + seg_d > target_start:
                    first_idx = i
                if seg_t < target_end:
                    last_idx = i

            if first_idx is not None and last_idx is not None:
                data_start = segments[first_idx][0]
                last = segments[last_idx]
                data_end = last[0] + last[1] - 1
                actual_start = segments[first_idx][2]
                logger.info(
                    f"{label} SIDX: segments {first_idx}-{last_idx} of "
                    f"{len(segments)}, bytes {data_start}-{data_end} "
                    f"({(data_end - data_start + 1) / 1024 / 1024:.1f} MB), "
                    f"time {actual_start:.1f}s-{last[2] + last[3]:.1f}s"
                )
            else:
                sidx_result = None  # no matching segments, fall back

        if not sidx_result:
            # Fallback: estimate byte positions from bitrate
            init_data = header_data
            bps = clen / dur
            data_start = max(len(header_data), int(target_start * bps))
            data_end = min(clen - 1, int(target_end * bps))
            actual_start = target_start
            logger.info(
                f"{label} estimated: bytes {data_start}-{data_end} "
                f"({(data_end - data_start + 1) / 1024 / 1024:.1f} MB)"
            )

        if data_start >= data_end:
            raise RuntimeError(
                f"Invalid byte range for {label}: {data_start}-{data_end}. "
                f"Trim range may exceed video duration — fetch duration first."
            )

        # Download data range with progress
        total_data = data_end - data_start + 1
        self.update_status(f"Downloading {label}...", "blue")
        req = urllib.request.Request(stream_url)
        req.add_header("Range", f"bytes={data_start}-{data_end}")
        with urllib.request.urlopen(req, timeout=120) as resp:
            with open(output_path, "wb", buffering=256 * 1024) as f:
                f.write(init_data)
                downloaded = 0
                while True:
                    if not self.is_downloading:
                        return actual_start
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    pct = min(100, downloaded * 100 / total_data)
                    now = time.time()
                    if now - self._last_status_update > 0.25:
                        self.update_progress(progress_base + pct * 0.45)
                        self.update_status(
                            f"Downloading {label}... {downloaded / 1024 / 1024:.1f} MB",
                            "blue",
                        )
                        self._last_status_update = now
                    self.last_progress_time = now

        file_size = len(init_data) + downloaded
        logger.info(f"{label} downloaded: {file_size / 1024 / 1024:.1f} MB")
        return actual_start

    def _download_trimmed_via_ffmpeg(
        self,
        url: str,
        format_spec: str,
        start_time: float,
        end_time: float,
        output_path: str,
        volume_multiplier: float = 1.0,
        copy_codec: bool = False,
    ) -> bool:
        """Download a trimmed segment by fetching only the relevant byte ranges.

        Step 1: yt-dlp -g to get direct stream URLs.
        Step 2: Download init segment + relevant data via HTTP Range requests
                (uses SIDX for precise segment boundaries on fMP4).
        Step 3: Merge video+audio with ffmpeg -c copy.
        Step 4: Precise local trim with ffmpeg.
        """
        temp_dir = tempfile.mkdtemp(prefix="ytdl_trim_")
        try:
            return self._do_trimmed_download(
                url,
                format_spec,
                start_time,
                end_time,
                output_path,
                volume_multiplier,
                copy_codec,
                temp_dir,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _do_trimmed_download(
        self,
        url: str,
        format_spec: str,
        start_time: float,
        end_time: float,
        output_path: str,
        volume_multiplier: float,
        copy_codec: bool,
        temp_dir: str,
    ) -> bool:
        """Inner implementation for trimmed downloads."""
        video_url, audio_url = self._get_stream_urls(url, format_spec)
        duration = end_time - start_time

        # Download video stream segment
        video_temp = os.path.join(temp_dir, "video.mp4")
        v_start = self._download_stream_segment(
            video_url, start_time, end_time, video_temp, "video", progress_base=0
        )
        if not self.is_downloading:
            return False

        # Download audio stream segment (if separate)
        source_file = video_temp
        if audio_url:
            audio_ext = "webm" if "mime=audio%2Fwebm" in audio_url else "m4a"
            audio_temp = os.path.join(temp_dir, f"audio.{audio_ext}")
            self._download_stream_segment(
                audio_url,
                start_time,
                end_time,
                audio_temp,
                "audio",
                progress_base=45,
            )
            if not self.is_downloading:
                return False

            # Merge video + audio
            merged = os.path.join(temp_dir, "merged.mp4")
            self.update_status("Merging streams...", "blue")
            merge_cmd = [
                self.ffmpeg_path,
                "-y",
                "-i",
                video_temp,
                "-i",
                audio_temp,
                "-c",
                "copy",
                "-map",
                "0:v",
                "-map",
                "1:a",
                merged,
            ]
            logger.info(f"Merging: {' '.join(merge_cmd)}")
            merge_result = subprocess.run(
                merge_cmd,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=DOWNLOAD_PROGRESS_TIMEOUT_TRIM,
                **_subprocess_kwargs,
            )
            if merge_result.returncode != 0:
                logger.error(f"Merge failed: {merge_result.stderr}")
                return False
            source_file = merged

        # Precise trim on local file
        # Data starts at ~v_start seconds; we want start_time..end_time
        ss_offset = start_time - v_start
        volume_changed = abs(volume_multiplier - 1.0) >= VOLUME_CHANGE_THRESHOLD
        needs_audio_encode = not copy_codec and volume_changed
        ffmpeg_cmd = [self.ffmpeg_path, "-y", "-i", source_file]
        ffmpeg_cmd.extend(["-ss", str(max(0, ss_offset)), "-t", str(duration)])

        if needs_audio_encode:
            # Volume-only change: copy video stream, re-encode audio only
            ffmpeg_cmd.extend(["-c:v", "copy"])
            ffmpeg_cmd.extend(["-c:a", "aac", "-b:a", AUDIO_BITRATE])
            ffmpeg_cmd.extend(["-af", f"volume={volume_multiplier}"])
        else:
            ffmpeg_cmd.extend(["-c", "copy"])

        ffmpeg_cmd.extend(["-progress", "pipe:1", output_path])
        return self.encoding.run_ffmpeg_with_progress(
            ffmpeg_cmd, duration, "Trimming video", self._make_encode_callbacks()
        )

    def _download_audio_trimmed(
        self,
        url: str,
        start_time: float,
        end_time: float,
        output_path: str,
        volume_multiplier: float = 1.0,
    ) -> bool:
        """Download and trim audio-only using byte-range seeking.

        Step 1: Get audio stream URL via yt-dlp -g (prefers m4a for SIDX support).
        Step 2: Download relevant byte range via HTTP Range requests.
        Step 3: ffmpeg converts to MP3 with precise trim.
        """
        temp_dir = tempfile.mkdtemp(prefix="ytdl_atrim_")
        try:
            # Prefer m4a (fMP4 container) which has SIDX for precise seeking.
            # webm byte-range downloads produce corrupt files because we can't
            # parse webm Cues for exact Cluster boundaries.
            audio_url, _ = self._get_stream_urls(url, "bestaudio[ext=m4a]/bestaudio")

            audio_ext = "webm" if "mime=audio%2Fwebm" in audio_url else "m4a"
            audio_temp = os.path.join(temp_dir, f"audio.{audio_ext}")
            a_start = self._download_stream_segment(
                audio_url,
                start_time,
                end_time,
                audio_temp,
                "audio",
                progress_base=0,
            )
            if not self.is_downloading:
                return False

            duration = end_time - start_time
            ss_offset = max(0, start_time - a_start)

            ffmpeg_cmd = [self.ffmpeg_path, "-y", "-i", audio_temp]
            ffmpeg_cmd.extend(["-ss", str(ss_offset), "-t", str(duration)])
            ffmpeg_cmd.extend(["-vn", "-c:a", "libmp3lame", "-b:a", AUDIO_BITRATE])
            if volume_multiplier != 1.0:
                ffmpeg_cmd.extend(["-af", f"volume={volume_multiplier}"])
            ffmpeg_cmd.extend(["-progress", "pipe:1", output_path])

            return self.encoding.run_ffmpeg_with_progress(
                ffmpeg_cmd,
                duration,
                "Converting to MP3",
                self._make_encode_callbacks(),
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    #  Timeout monitoring
    # ------------------------------------------------------------------

    def _monitor_download_timeout_tick(self) -> None:
        """Single timeout check (called by GUI QTimer each interval)."""
        if not self.is_downloading:
            return

        current_time = time.time()

        if self.download_start_time and not self._download_has_progress:
            elapsed = int(current_time - self.download_start_time)
            self.update_status(f"Preparing download... ({elapsed}s elapsed)", "blue")

        if self.download_start_time:
            elapsed = current_time - self.download_start_time
            if elapsed > DOWNLOAD_TIMEOUT:
                logger.error(f"Download exceeded absolute timeout ({DOWNLOAD_TIMEOUT}s)")
                self._timeout_download("Download timeout (60 min limit exceeded)")
                return

        if self.last_progress_time:
            time_since_progress = current_time - self.last_progress_time
            progress_timeout = (
                DOWNLOAD_PROGRESS_TIMEOUT_TRIM
                if self._trim_download_active
                else DOWNLOAD_PROGRESS_TIMEOUT
            )
            if time_since_progress > progress_timeout:
                timeout_min = progress_timeout // 60
                logger.error(f"Download stalled (no progress for {progress_timeout}s)")
                self._timeout_download(f"Download stalled (no progress for {timeout_min} minutes)")

    def _timeout_download(self, reason: str) -> None:
        """Handle download timeout. Safe to call from any thread."""
        with self.download_lock:
            downloading = self.is_downloading
            process = self.current_process
        if downloading:
            logger.warning(f"Timing out download: {reason}")
            # Kill process directly (thread-safe, no GUI involved)
            safe_process_cleanup(process)
            with self.download_lock:
                self.is_downloading = False
                self.current_process = None
            # Update UI via signals (thread-safe)
            self.update_status(reason, "red")
            self.sig_reset_buttons.emit()
            self.sig_show_messagebox.emit(
                "error",
                "Download Timed Out",
                f"{reason}\n\nPlease try again.",
            )

    # ------------------------------------------------------------------
    #  Stop download
    # ------------------------------------------------------------------

    def stop_download(self) -> None:
        """Stop download gracefully, with forced termination as fallback."""
        with self.download_lock:
            process_to_cleanup = self.current_process
            is_active = self.is_downloading

        if not is_active:
            return

        if process_to_cleanup:
            safe_process_cleanup(process_to_cleanup)

        with self.download_lock:
            self.is_downloading = False
            self.current_process = None
        self.update_status("Download stopped", "orange")
        self.sig_reset_buttons.emit()

    # ------------------------------------------------------------------
    #  yt-dlp output parsing
    # ------------------------------------------------------------------

    def _parse_ytdlp_output(self, process: subprocess.Popen) -> list[str]:
        """Parse yt-dlp stdout for progress, status, and errors.

        Returns list of error lines collected during parsing.
        """
        error_lines: list[str] = []
        try:
            for line in process.stdout:
                if not self.is_downloading:
                    break

                if line.startswith("ERROR:") or "[error]" in line.lower():
                    if len(error_lines) < 100:
                        error_lines.append(line.strip())
                    logger.warning(f"yt-dlp: {line.strip()}")

                if "[download]" in line or "Downloading" in line:
                    self._download_has_progress = True
                    progress_match = PROGRESS_REGEX.search(line)
                    if progress_match:
                        progress = float(progress_match.group(1))
                        self.last_progress_time = time.time()

                        now = self.last_progress_time
                        if now - self._last_status_update >= 0.25 or progress >= PROGRESS_COMPLETE:
                            self._last_status_update = now
                            self.update_progress(progress)

                            speed_match = SPEED_REGEX.search(line)
                            eta_match = ETA_REGEX.search(line)

                            if speed_match and eta_match:
                                status_msg = (
                                    f"Downloading... {progress:.1f}% "
                                    f"at {speed_match.group(1)} | "
                                    f"ETA: {eta_match.group(1)}"
                                )
                            elif speed_match:
                                status_msg = (
                                    f"Downloading... {progress:.1f}% at {speed_match.group(1)}"
                                )
                            else:
                                status_msg = f"Downloading... {progress:.1f}%"

                            self.update_status(status_msg, "blue")
                    elif "Destination" in line:
                        self.update_status("Starting download...", "blue")
                        self.last_progress_time = time.time()

                elif "[info]" in line and "Downloading" in line:
                    self.update_status("Preparing download...", "blue")
                    self.last_progress_time = time.time()
                elif "[ExtractAudio]" in line:
                    self.update_status("Extracting audio...", "blue")
                    self.last_progress_time = time.time()
                elif "[Merger]" in line or "Merging" in line:
                    self.update_status("Merging video and audio...", "blue")
                    self.last_progress_time = time.time()
                elif "[ffmpeg]" in line:
                    self.update_status("Processing with ffmpeg...", "blue")
                    self.last_progress_time = time.time()
                elif "Post-processing" in line or "Postprocessing" in line:
                    self.update_status("Post-processing...", "blue")
                    self.last_progress_time = time.time()
                elif "has already been downloaded" in line:
                    self.update_status("File already exists, skipping...", "orange")
                    self.last_progress_time = time.time()
        except OSError as e:
            if self.is_downloading:
                logger.warning(f"Pipe error while reading process output: {e}")
        return error_lines

    # ------------------------------------------------------------------
    #  Download sub-paths (extracted from download() for readability)
    # ------------------------------------------------------------------

    def _download_audio_trimmed_path(
        self,
        url: str,
        ui_state: dict,
        start_time: int,
        end_time: int,
    ) -> None:
        """Audio-only trimmed download: byte-range download + local ffmpeg."""
        _fn = ui_state["filename"] if ui_state else ""
        custom_name = sanitize_filename(_fn)
        _vol = (ui_state["volume_raw"] / 100.0) if ui_state else 1.0
        volume_multiplier = validate_volume(_vol)

        start_hms_file = seconds_to_hms(start_time).replace(":", "-")
        end_hms_file = seconds_to_hms(end_time).replace(":", "-")
        if custom_name:
            final_base = custom_name
        else:
            title = self.video_title or "video"
            final_base = sanitize_filename(title) or title
        final_name = f"{final_base}_[{start_hms_file}_to_{end_hms_file}].mp3"
        _dp = ui_state["download_path"] if ui_state else ""
        final_output = os.path.join(_dp, final_name)

        success = self._download_audio_trimmed(
            url,
            start_time,
            end_time,
            final_output,
            volume_multiplier=volume_multiplier,
        )

        if success and self.is_downloading:
            self.update_progress(PROGRESS_COMPLETE)
            self.update_status("Download complete!", "green")
            logger.info(f"Audio trim completed: {final_output}")
            self.sig_enable_upload.emit(final_output)
        elif self.is_downloading:
            self.update_status("Download failed", "red")

    def _download_video_trimmed_10mb_path(
        self,
        url: str,
        ui_state: dict,
        start_time: int,
        end_time: int,
        height: int,
        target_bitrate: int,
    ) -> None:
        """Video trimmed + 10MB constraint: ffmpeg trim -> temp, then size-constrained encode."""
        _fn = ui_state["filename"] if ui_state else ""
        custom_name = sanitize_filename(_fn)
        _vol = (ui_state["volume_raw"] / 100.0) if ui_state else 1.0
        volume_multiplier = validate_volume(_vol)

        start_hms_file = seconds_to_hms(start_time).replace(":", "-")
        end_hms_file = seconds_to_hms(end_time).replace(":", "-")
        format_spec = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        temp_dir = tempfile.mkdtemp(prefix="ytdl_10mb_")
        temp_file = os.path.join(temp_dir, "trimmed_segment.mp4")

        try:
            dl_ok = self._download_trimmed_via_ffmpeg(
                url,
                format_spec,
                start_time,
                end_time,
                temp_file,
                copy_codec=True,
            )

            if dl_ok and self.is_downloading:
                _dp = ui_state["download_path"] if ui_state else ""
                title = self.video_title or "video"
                safe_title = sanitize_filename(title) or title
                if custom_name:
                    safe_title = custom_name
                final_name = f"{safe_title}_{height}p_[{start_hms_file}_to_{end_hms_file}].mp4"
                final_output = os.path.join(_dp, final_name)

                clip_duration = end_time - start_time
                success = self.encoding.size_constrained_encode(
                    temp_file,
                    final_output,
                    target_bitrate,
                    clip_duration,
                    self._make_encode_callbacks(),
                    volume_multiplier=volume_multiplier,
                    scale_height=height,
                )
                if success and self.is_downloading:
                    self.update_progress(PROGRESS_COMPLETE)
                    self.update_status("Download complete!", "green")
                    logger.info(f"Trimmed 10MB download completed: {final_output}")
                    self.sig_enable_upload.emit(final_output)
                elif self.is_downloading:
                    self.update_status("Download failed", "red")
                    self.sig_show_messagebox.emit(
                        "error",
                        "Download Failed",
                        "Trimmed download failed.\n\nPlease try again.",
                    )
            elif self.is_downloading:
                self.update_status("Download failed", "red")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _download_video_trimmed_path(
        self,
        url: str,
        ui_state: dict,
        start_time: int,
        end_time: int,
        height: str | int,
    ) -> None:
        """Video trimmed (no 10MB): direct ffmpeg trim via yt-dlp -g + ffmpeg -ss."""
        _fn = ui_state["filename"] if ui_state else ""
        custom_name = sanitize_filename(_fn)
        _vol = (ui_state["volume_raw"] / 100.0) if ui_state else 1.0
        volume_multiplier = validate_volume(_vol)

        start_hms_file = seconds_to_hms(start_time).replace(":", "-")
        end_hms_file = seconds_to_hms(end_time).replace(":", "-")
        format_spec = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        _dp = ui_state["download_path"] if ui_state else ""
        if custom_name:
            final_base = custom_name
        else:
            title = self.video_title or "video"
            final_base = sanitize_filename(title) or title
        final_name = f"{final_base}_{height}p_[{start_hms_file}_to_{end_hms_file}].mp4"
        final_output = os.path.join(_dp, final_name)

        success = self._download_trimmed_via_ffmpeg(
            url,
            format_spec,
            start_time,
            end_time,
            final_output,
            volume_multiplier=volume_multiplier,
        )

        if success and self.is_downloading:
            self.update_progress(PROGRESS_COMPLETE)
            self.update_status("Download complete!", "green")
            logger.info(f"Trimmed download completed: {final_output}")
            self.sig_enable_upload.emit(final_output)
        elif self.is_downloading:
            self.update_status("Download failed", "red")

    def _post_ytdlp_10mb_encode(
        self,
        temp_dir: str,
        download_path: str,
        height: int,
        target_bitrate: int,
        volume_multiplier: float,
        custom_name: str,
        clip_duration: float,
    ) -> None:
        """Post-yt-dlp 10MB encode: find temp file and run size-constrained encode."""
        temp_files = glob.glob(os.path.join(temp_dir, "*.mp4"))
        if not temp_files:
            self.update_status("Download failed", "red")
            logger.error("Two-pass: no temp file found after yt-dlp download")
            return

        temp_file = temp_files[0]
        video_title = os.path.splitext(os.path.basename(temp_file))[0]
        if custom_name:
            final_base = custom_name
        else:
            final_base = sanitize_filename(video_title) or video_title

        final_name = f"{final_base}_{height}p.mp4"
        final_output = os.path.join(download_path, final_name)

        success = self.encoding.size_constrained_encode(
            temp_file,
            final_output,
            target_bitrate,
            clip_duration,
            self._make_encode_callbacks(),
            volume_multiplier=volume_multiplier,
            scale_height=height,
        )

        if success and self.is_downloading:
            self.update_progress(PROGRESS_COMPLETE)
            self.update_status("Download complete!", "green")
            logger.info(f"Two-pass download completed: {final_output}")
            self.sig_enable_upload.emit(final_output)
        elif self.is_downloading:
            self.update_status("Download failed", "red")
            logger.error("Two-pass encoding failed")

    # ------------------------------------------------------------------
    #  Main download logic
    # ------------------------------------------------------------------

    def download(self, url: str, ui_state: dict | None = None) -> None:
        """Download a YouTube video or process a local file.

        Args:
            url: The URL or local file path to download.
            ui_state: Dict of widget values snapshot from the GUI thread.
                      If None, falls back to reading widgets directly (for
                      compatibility with callers like download_clipboard_url).
        """
        keep_below_10mb = False
        temp_dir = None
        cmd = []
        start_hms_file = ""
        end_hms_file = ""
        try:
            # Route to local file handler if needed
            if is_local_file(url):
                return self.download_local_file(url, ui_state)

            is_playlist = is_playlist_url(url)

            # Use pre-captured UI state (thread-safe)
            if ui_state:
                quality = ui_state["quality"]
                trim_enabled = ui_state["trim_enabled"]
            else:
                quality = ""
                trim_enabled = False
            audio_only = (
                quality.startswith("none")
                or quality == "none (Audio only)"
                or (ui_state and ui_state.get("audio_only", False))
            )

            self.update_status("Starting download...", "blue")

            # Validate trimming
            if trim_enabled:
                if self.video_duration <= 0:
                    self.update_status("Please fetch video duration first", "red")
                    self.sig_reset_buttons.emit()
                    with self.download_lock:
                        self.is_downloading = False
                    return

                start_time = int(float(ui_state["start_time"])) if ui_state else 0
                end_time = int(float(ui_state["end_time"])) if ui_state else 0

                if start_time >= end_time:
                    self.update_status("Invalid time range", "red")
                    self.sig_reset_buttons.emit()
                    with self.download_lock:
                        self.is_downloading = False
                    return

            if audio_only:
                _fn = ui_state["filename"] if ui_state else ""
                custom_name = sanitize_filename(_fn)
                _vol = (ui_state["volume_raw"] / 100.0) if ui_state else 1.0
                volume_multiplier = validate_volume(_vol)

                if trim_enabled:
                    self._download_audio_trimmed_path(url, ui_state, start_time, end_time)
                    return

                # --- Audio-only, no trim: standard yt-dlp download ---
                if custom_name:
                    base_name = custom_name
                else:
                    base_name = "%(title)s"
                output_template = f"{base_name}.%(ext)s"
                _dp = ui_state["download_path"] if ui_state else ""
                output_path = os.path.join(_dp, output_template)

                cmd = self.build_audio_ytdlp_command(url, output_path, volume=volume_multiplier)

                _sl = ui_state["speed_limit"] if ui_state else None
                sl_args = get_speed_limit_args(_sl)
                if sl_args or is_playlist:
                    # Insert before the trailing ["--", url]
                    tail = cmd[-2:]  # ["--", url]
                    cmd = cmd[:-2]
                    if sl_args:
                        cmd.extend(sl_args)
                    if is_playlist:
                        cmd.append("--no-playlist")
                    cmd.extend(tail)
            else:
                keep_below_10mb = ui_state["keep_below_10mb"] if ui_state else False

                if keep_below_10mb:
                    clip_duration = (end_time - start_time) if trim_enabled else self.video_duration
                    height, target_bitrate = self.encoding.calculate_optimal_quality(clip_duration)
                    height = int(height)
                    logger.info(
                        f"10MB encode: auto-selected {height}p at {target_bitrate}bps "
                        f"for {clip_duration}s clip"
                    )
                else:
                    height = quality

                _vol = (ui_state["volume_raw"] / 100.0) if ui_state else 1.0
                volume_multiplier = validate_volume(_vol)

                _fn = ui_state["filename"] if ui_state else ""
                custom_name = sanitize_filename(_fn)
                if custom_name:
                    base_name = custom_name
                else:
                    base_name = "%(title)s"

                if trim_enabled:
                    start_hms_file = seconds_to_hms(start_time).replace(":", "-")
                    end_hms_file = seconds_to_hms(end_time).replace(":", "-")
                    output_template = (
                        f"{base_name}_{height}p_[{start_hms_file}_to_{end_hms_file}].%(ext)s"
                    )
                else:
                    output_template = f"{base_name}_{height}p.%(ext)s"

                if trim_enabled and keep_below_10mb:
                    self._download_video_trimmed_10mb_path(
                        url, ui_state, start_time, end_time, height, target_bitrate
                    )
                    return

                elif trim_enabled:
                    self._download_video_trimmed_path(url, ui_state, start_time, end_time, height)
                    return

                elif keep_below_10mb:
                    # --- Size-constrained path (no trim) ---
                    temp_dir = tempfile.mkdtemp(prefix="ytdl_10mb_")
                    temp_output_template = os.path.join(temp_dir, "%(title)s.%(ext)s")

                    dl_bitrate_cap = max(target_bitrate * 2, 1000000)
                    dl_bitrate_cap_k = int(dl_bitrate_cap / 1000)
                    format_sel = (
                        f"bestvideo[height<={height}][vbr<={dl_bitrate_cap_k}]"
                        f"+bestaudio/bestvideo[height<={height}]+bestaudio"
                        f"/best[height<={height}]"
                    )

                    cmd = self.build_base_ytdlp_command()
                    cmd.extend(["-f", format_sel, "--merge-output-format", "mp4"])

                    _sl = ui_state["speed_limit"] if ui_state else None
                    cmd.extend(get_speed_limit_args(_sl))
                    if is_playlist:
                        cmd.append("--no-playlist")
                    cmd.extend(["-o", temp_output_template, "--", url])
                else:
                    # --- Normal single-pass path (no trim) ---
                    temp_dir = None
                    _dp = ui_state["download_path"] if ui_state else ""
                    output_path = os.path.join(_dp, output_template)

                    cmd = self.build_video_ytdlp_command(
                        url, output_path, height, volume=volume_multiplier
                    )

                    _sl2 = ui_state["speed_limit"] if ui_state else None
                    sl_args = get_speed_limit_args(_sl2)
                    if sl_args or is_playlist:
                        # Insert before the trailing ["--", url]
                        tail = cmd[-2:]  # ["--", url]
                        cmd = cmd[:-2]
                        if sl_args:
                            cmd.extend(sl_args)
                        if is_playlist:
                            cmd.append("--no-playlist")
                        cmd.extend(tail)

            logger.info(f"Download command: {' '.join(cmd)}")

            with self.download_lock:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    **_subprocess_kwargs,
                )
                self.current_process = proc

            error_lines = self._parse_ytdlp_output(proc)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                safe_process_cleanup(proc)

            if proc.returncode == 0 and self.is_downloading:
                if not audio_only and keep_below_10mb and temp_dir:
                    _dp2 = ui_state["download_path"] if ui_state else ""
                    self._post_ytdlp_10mb_encode(
                        temp_dir,
                        _dp2,
                        height,
                        target_bitrate,
                        volume_multiplier,
                        custom_name,
                        self.video_duration,
                    )
                else:
                    self.update_progress(PROGRESS_COMPLETE)
                    self.update_status("Download complete!", "green")
                    logger.info(f"Download completed successfully: {url}")
                    download_path = ui_state["download_path"] if ui_state else ""
                    latest_file = self._find_latest_file(download_path)
                    if latest_file:
                        self.sig_enable_upload.emit(latest_file)

            elif self.is_downloading:
                self.update_status("Download failed", "red")
                logger.error(f"Download failed with return code {proc.returncode}")
                if error_lines:
                    logger.error(f"yt-dlp errors: {'; '.join(error_lines)}")
                error_detail = error_lines[-1] if error_lines else "Unknown error"
                self.sig_show_messagebox.emit(
                    "error",
                    "Download Failed",
                    f"Download failed.\n\n{error_detail}\n\nPlease try again.",
                )
                if temp_dir:
                    shutil.rmtree(temp_dir, ignore_errors=True)

        except FileNotFoundError as e:
            if self.is_downloading:
                error_msg = (
                    "yt-dlp or ffmpeg is not installed.\n\nInstall with:\n"
                    "pip install yt-dlp\n\nand install ffmpeg from your package manager"
                )
                self.update_status(error_msg, "red")
                logger.error(f"Dependency not found: {e}")
        except PermissionError as e:
            if self.is_downloading:
                error_msg = "Permission denied. Check write permissions for download folder."
                self.update_status(error_msg, "red")
                logger.error(f"Permission error: {e}")
        except OSError as e:
            if self.is_downloading:
                error_msg = f"OS error: {e}"
                self.update_status(error_msg, "red")
                logger.error(f"OS error during download: {e}")
        except Exception as e:
            if self.is_downloading:
                self.update_status(f"Error: {e}", "red")
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
            self.sig_reset_buttons.emit()

    # ------------------------------------------------------------------
    #  Local file processing
    # ------------------------------------------------------------------

    def download_local_file(self, filepath: str, ui_state: dict | None = None) -> None:
        """Process local video or audio file with trimming, quality adjustment, and volume control.

        Args:
            filepath: Path to the local file.
            ui_state: Dict of widget values snapshot from the GUI thread.
        """
        try:
            self._download_has_progress = True

            # Local audio files are always processed as audio-only
            audio_extensions = {".mp3", ".aac", ".m4a", ".wav"}
            is_audio_file = Path(filepath).suffix.lower() in audio_extensions

            if ui_state:
                quality = ui_state["quality"]
                trim_enabled = ui_state["trim_enabled"]
            else:
                quality = "720"
                trim_enabled = False
            audio_only = (
                is_audio_file
                or quality.startswith("none")
                or quality == "none (Audio only)"
                or (ui_state and ui_state.get("audio_only", False))
            )

            start_time = None
            end_time = None

            self.update_status("Processing local file...", "blue")

            # Validate trimming
            if trim_enabled:
                if self.video_duration <= 0:
                    self.update_status("Please fetch video duration first", "red")
                    self.sig_reset_buttons.emit()
                    with self.download_lock:
                        self.is_downloading = False
                    return

                start_time = int(float(ui_state["start_time"])) if ui_state else 0
                end_time = int(float(ui_state["end_time"])) if ui_state else 0

                if start_time >= end_time:
                    self.update_status("Invalid time range", "red")
                    self.sig_reset_buttons.emit()
                    with self.download_lock:
                        self.is_downloading = False
                    return

            _fn = ui_state["filename"] if ui_state else ""
            custom_name = sanitize_filename(_fn)
            if custom_name:
                base_name = custom_name
            else:
                input_path = Path(filepath)
                base_name = sanitize_filename(input_path.stem) or input_path.stem

            if trim_enabled:
                start_hms = seconds_to_hms(start_time).replace(":", "-")
                end_hms = seconds_to_hms(end_time).replace(":", "-")
                output_name = f"{base_name}_[{start_hms}_to_{end_hms}]"
            else:
                if custom_name:
                    output_name = base_name
                else:
                    output_name = f"{base_name}_processed"

            _vol = (ui_state["volume_raw"] / 100.0) if ui_state else 1.0
            volume_multiplier = validate_volume(_vol)
            _dp = ui_state["download_path"] if ui_state else ""

            if audio_only:
                output_file = os.path.join(_dp, f"{output_name}.mp3")
                cmd = [self.ffmpeg_path]

                if trim_enabled:
                    cmd.extend(["-ss", str(start_time), "-to", str(end_time)])

                cmd.extend(["-i", filepath])

                cmd.extend(["-vn", "-c:a", "libmp3lame", "-b:a", AUDIO_BITRATE])

                if volume_multiplier != 1.0:
                    cmd.extend(["-af", f"volume={volume_multiplier}"])

                cmd.extend(["-progress", "pipe:1", "-y", output_file])
            else:
                if quality.startswith("none") or quality == "none (Audio only)":
                    self.update_status("Please select a video quality", "red")
                    self.sig_reset_buttons.emit()
                    with self.download_lock:
                        self.is_downloading = False
                    return

                keep_below_10mb = ui_state["keep_below_10mb"] if ui_state else False

                if keep_below_10mb:
                    clip_duration = (end_time - start_time) if trim_enabled else self.video_duration
                    if clip_duration <= 0:
                        self.update_status("Please fetch video duration first", "red")
                        self.sig_reset_buttons.emit()
                        with self.download_lock:
                            self.is_downloading = False
                        return
                    height, target_bitrate = self.encoding.calculate_optimal_quality(clip_duration)
                    height = int(height)
                    logger.info(
                        f"10MB encode (local): auto-selected {height}p at "
                        f"{target_bitrate}bps for {clip_duration}s clip"
                    )
                else:
                    height = int(quality)

                output_file = os.path.join(_dp, f"{output_name}_{height}p.mp4")

                if keep_below_10mb:
                    success = self.encoding.size_constrained_encode(
                        filepath,
                        output_file,
                        target_bitrate,
                        clip_duration,
                        self._make_encode_callbacks(),
                        volume_multiplier=volume_multiplier,
                        scale_height=height,
                        start_time=start_time if trim_enabled else None,
                        end_time=end_time if trim_enabled else None,
                    )

                    if success and self.is_downloading:
                        self.update_progress(PROGRESS_COMPLETE)
                        self.update_status("Processing complete!", "green")
                        logger.info(f"Two-pass local file processing complete: {output_file}")
                        self.sig_enable_upload.emit(output_file)
                    elif self.is_downloading:
                        self.update_status("Processing failed", "red")
                    return
                else:
                    cmd = [self.ffmpeg_path]
                    if self.encoding.hw_encoder == "h264_vaapi" and self.encoding.vaapi_device:
                        cmd.extend(["-vaapi_device", self.encoding.vaapi_device])

                    if trim_enabled:
                        cmd.extend(["-ss", str(start_time), "-to", str(end_time)])

                    cmd.extend(["-i", filepath])

                    cmd.extend(
                        self.encoding.build_vf_args(height)
                        + self.encoding.get_video_encoder_args(mode="crf")
                        + ["-c:a", "aac", "-b:a", AUDIO_BITRATE]
                    )

                    if volume_multiplier != 1.0:
                        cmd.extend(["-af", f"volume={volume_multiplier}"])

                    cmd.extend(["-progress", "pipe:1", "-y", output_file])

            logger.info(f"Processing local file: {' '.join(cmd)}")

            # Execute ffmpeg
            with self.download_lock:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    **_subprocess_kwargs,
                )
                self.current_process = proc

            total_duration = self.video_duration if not trim_enabled else (end_time - start_time)

            # Drain stderr in background to prevent pipe deadlock
            stderr_lines = deque(maxlen=200)

            def _drain_stderr():
                try:
                    for line in proc.stderr:
                        stderr_lines.append(line)
                        self.last_progress_time = time.time()
                except (ValueError, OSError):
                    pass

            stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
            stderr_thread.start()

            for line in proc.stdout:
                if not self.is_downloading:
                    break

                if "out_time_ms=" in line:
                    try:
                        time_ms = int(line.split("=")[1].strip())
                        current_time = time_ms / 1000000
                        self.last_progress_time = time.time()

                        if total_duration > 0:
                            now = self.last_progress_time
                            if now - self._last_status_update >= 0.25:
                                self._last_status_update = now
                                progress = min(100, (current_time / total_duration) * 100)
                                self.update_progress(progress)
                                self.update_status(f"Processing... {progress:.1f}%", "blue")
                    except (ValueError, IndexError):
                        pass

            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                safe_process_cleanup(proc)
            stderr_thread.join(timeout=5)

            if proc.returncode == 0 and self.is_downloading:
                self.update_progress(PROGRESS_COMPLETE)
                self.update_status("Processing complete!", "green")
                logger.info(f"Local file processed: {output_file}")
                self.sig_enable_upload.emit(output_file)

            elif self.is_downloading:
                stderr = "".join(stderr_lines)
                self.update_status("Processing failed", "red")
                logger.error(f"ffmpeg failed: {stderr}")

        except FileNotFoundError as e:
            if self.is_downloading:
                self.update_status("ffmpeg not found. Please ensure it is installed.", "red")
                logger.error(f"ffmpeg not found: {e}")
        except Exception as e:
            if self.is_downloading:
                self.update_status(f"Error: {e}", "red")
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
            self.sig_reset_buttons.emit()
