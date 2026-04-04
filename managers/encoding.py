"""FFmpeg encoding service extracted from YouTubeDownloader.

Handles video encoding: CRF/bitrate modes, single/two-pass, size-constrained,
hardware acceleration detection. No Qt dependency — uses callbacks for progress.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

from constants import (
    AUDIO_BITRATE,
    SIZE_CONSTRAINED_MIN_BITRATES,
    SIZE_CONSTRAINED_RESOLUTIONS,
    TARGET_AUDIO_BITRATE_BPS,
    TARGET_MAX_SIZE_BYTES,
    VIDEO_CRF,
)
from managers.utils import _subprocess_kwargs, safe_process_cleanup

logger = logging.getLogger(__name__)


@dataclass
class EncodeCallbacks:
    """Callbacks for encoding progress reporting and cancellation."""

    on_progress: Callable[[float], None]
    on_status: Callable[[str, str], None]
    is_cancelled: Callable[[], bool]
    process_lock: threading.Lock
    set_process: Callable[[subprocess.Popen | None], None]
    on_heartbeat: Callable[[], None]


class EncodingService:
    """FFmpeg encoding operations."""

    def __init__(self, ffmpeg_path: str, hw_encoder: str | None):
        self.ffmpeg_path = ffmpeg_path
        self.hw_encoder = hw_encoder

    def get_video_encoder_args(
        self, mode: str = "crf", target_bitrate: int | None = None
    ) -> list[str]:
        """Get video encoder arguments based on available hardware.

        Args:
            mode: 'crf' for quality-based, 'bitrate' for target bitrate
            target_bitrate: Required when mode='bitrate'
        """
        if mode == "bitrate" and target_bitrate is None:
            raise ValueError("target_bitrate required when mode='bitrate'")
        if self.hw_encoder:
            if mode == "crf":
                if self.hw_encoder == "h264_amf":
                    return [
                        "-c:v",
                        "h264_amf",
                        "-quality",
                        "balanced",
                        "-rc",
                        "cqp",
                        "-qp_i",
                        "23",
                        "-qp_p",
                        "23",
                    ]
                else:  # h264_nvenc
                    return [
                        "-c:v",
                        "h264_nvenc",
                        "-preset",
                        "p4",
                        "-rc",
                        "constqp",
                        "-qp",
                        "23",
                    ]
            else:  # bitrate mode
                maxrate = int(target_bitrate * 1.5)
                bufsize = int(target_bitrate * 2)
                if self.hw_encoder == "h264_amf":
                    return [
                        "-c:v",
                        "h264_amf",
                        "-quality",
                        "balanced",
                        "-b:v",
                        str(target_bitrate),
                        "-maxrate",
                        str(maxrate),
                        "-bufsize",
                        str(bufsize),
                    ]
                else:  # h264_nvenc
                    return [
                        "-c:v",
                        "h264_nvenc",
                        "-preset",
                        "p4",
                        "-b:v",
                        str(target_bitrate),
                        "-maxrate",
                        str(maxrate),
                        "-bufsize",
                        str(bufsize),
                    ]
        else:
            if mode == "crf":
                return [
                    "-c:v",
                    "libx264",
                    "-crf",
                    str(VIDEO_CRF),
                    "-preset",
                    "ultrafast",
                ]
            else:  # bitrate mode
                maxrate = int(target_bitrate * 1.5)
                bufsize = int(target_bitrate * 2)
                return [
                    "-c:v",
                    "libx264",
                    "-b:v",
                    str(target_bitrate),
                    "-maxrate",
                    str(maxrate),
                    "-bufsize",
                    str(bufsize),
                    "-preset",
                    "ultrafast",
                ]

    def run_ffmpeg_with_progress(
        self,
        cmd: list[str],
        duration: float,
        status_prefix: str,
        cb: EncodeCallbacks,
    ) -> bool:
        """Run an ffmpeg command, parsing progress output. Returns True on success."""
        logger.info(f"{status_prefix}: {' '.join(cmd)}")
        cb.on_heartbeat()
        cb.on_progress(0)
        cb.on_status(f"{status_prefix}...", "blue")

        with cb.process_lock:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **_subprocess_kwargs,
            )
            cb.set_process(proc)

        stderr_lines: deque[str] = deque(maxlen=200)
        has_stdout_progress = threading.Event()

        def _drain_stderr():
            try:
                for line in proc.stderr:
                    stderr_lines.append(line)
                    cb.on_heartbeat()
                    if not has_stdout_progress.is_set():
                        cb.on_status(f"{status_prefix}... seeking to position", "blue")
            except (ValueError, OSError):
                pass

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        for line in proc.stdout:
            if cb.is_cancelled():
                safe_process_cleanup(proc)
                return False
            if "out_time_ms=" in line:
                has_stdout_progress.set()
                try:
                    time_ms = int(line.split("=")[1].strip())
                    current = time_ms / 1_000_000
                    if duration > 0:
                        pct = min(100, (current / duration) * 100)
                        cb.on_progress(pct)
                        cb.on_status(f"{status_prefix}... {pct:.0f}%", "blue")
                except (ValueError, IndexError):
                    pass
            cb.on_heartbeat()

        proc.wait()
        stderr_thread.join(timeout=5)

        if proc.returncode != 0:
            stderr_text = "".join(stderr_lines)
            logger.error(f"{status_prefix} failed (rc {proc.returncode}): {stderr_text}")
            safe_process_cleanup(proc)
            return False
        safe_process_cleanup(proc)
        return True

    def encode_single_pass(
        self,
        input_file: str,
        output_file: str,
        target_bitrate: int,
        duration: float,
        cb: EncodeCallbacks,
        volume_multiplier: float = 1.0,
        scale_height: int | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> bool:
        """Single-pass encode using hardware encoder with bitrate target."""
        input_args = [self.ffmpeg_path, "-y", "-i", input_file]
        if start_time is not None and end_time is not None:
            input_args.extend(["-ss", str(start_time), "-to", str(end_time)])

        vf_args = ["-vf", f"scale=-2:{scale_height}"] if scale_height else []
        enc_args = self.get_video_encoder_args(mode="bitrate", target_bitrate=target_bitrate)
        audio_args = ["-c:a", "aac", "-b:a", AUDIO_BITRATE]
        if volume_multiplier != 1.0:
            audio_args.extend(["-af", f"volume={volume_multiplier}"])

        cmd = input_args + vf_args + enc_args + audio_args + ["-progress", "pipe:1", output_file]

        cb.on_status("Encoding (GPU)...", "blue")
        return self.run_ffmpeg_with_progress(cmd, duration, "Encoding (GPU)", cb)

    def encode_two_pass(
        self,
        input_file: str,
        output_file: str,
        target_bitrate: int,
        duration: float,
        cb: EncodeCallbacks,
        volume_multiplier: float = 1.0,
        scale_height: int | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> bool:
        """Two-pass encode using software (libx264) with bitrate target."""
        passlogfile = os.path.join(
            tempfile.gettempdir(), f"ytdl_2pass_{os.getpid()}_{int(time.time())}"
        )

        input_args = [self.ffmpeg_path, "-y", "-i", input_file]
        if start_time is not None and end_time is not None:
            input_args.extend(["-ss", str(start_time), "-to", str(end_time)])

        vf_args = ["-vf", f"scale=-2:{scale_height}"] if scale_height else []
        enc_args = self.get_video_encoder_args(mode="bitrate", target_bitrate=target_bitrate)

        try:
            # --- Pass 1 ---
            cb.on_status("Encoding pass 1/2 (analysing)...", "blue")
            pass1_cmd = (
                input_args
                + vf_args
                + enc_args
                + [
                    "-pass",
                    "1",
                    "-passlogfile",
                    passlogfile,
                    "-an",
                    "-f",
                    "null",
                    os.devnull,
                    "-progress",
                    "pipe:1",
                ]
            )
            if not self.run_ffmpeg_with_progress(pass1_cmd, duration, "Two-pass pass 1", cb):
                return False

            # --- Pass 2 ---
            cb.on_status("Encoding pass 2/2...", "blue")
            pass2_cmd = (
                input_args
                + vf_args
                + enc_args
                + [
                    "-pass",
                    "2",
                    "-passlogfile",
                    passlogfile,
                    "-c:a",
                    "aac",
                    "-b:a",
                    AUDIO_BITRATE,
                ]
            )
            if volume_multiplier != 1.0:
                pass2_cmd.extend(["-af", f"volume={volume_multiplier}"])
            pass2_cmd.extend(["-progress", "pipe:1", output_file])

            return self.run_ffmpeg_with_progress(pass2_cmd, duration, "Two-pass pass 2", cb)

        finally:
            for suffix in ["", "-0.log", "-0.log.mbtree"]:
                p = passlogfile + suffix
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

    def size_constrained_encode(
        self,
        input_file: str,
        output_file: str,
        target_bitrate: int,
        duration: float,
        cb: EncodeCallbacks,
        volume_multiplier: float = 1.0,
        scale_height: int | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> bool:
        """Encode a video to hit a target bitrate (for 10MB size constraint).

        Uses single-pass with hardware encoding if available, or two-pass with
        software encoding as fallback.
        """
        if self.hw_encoder:
            return self.encode_single_pass(
                input_file,
                output_file,
                target_bitrate,
                duration,
                cb,
                volume_multiplier,
                scale_height,
                start_time,
                end_time,
            )
        else:
            return self.encode_two_pass(
                input_file,
                output_file,
                target_bitrate,
                duration,
                cb,
                volume_multiplier,
                scale_height,
                start_time,
                end_time,
            )

    @staticmethod
    def calculate_optimal_quality(
        duration_seconds: float,
    ) -> tuple[int, int]:
        """Calculate optimal resolution and video bitrate to keep output below 10MB.

        Returns (height, video_bitrate_bps).
        """
        if duration_seconds <= 0:
            return (360, 100000)
        available_bitrate = int(
            (TARGET_MAX_SIZE_BYTES * 8) / duration_seconds - TARGET_AUDIO_BITRATE_BPS
        )
        available_bitrate = max(available_bitrate, 100000)

        for height in SIZE_CONSTRAINED_RESOLUTIONS:
            if available_bitrate >= SIZE_CONSTRAINED_MIN_BITRATES[height]:
                return (height, available_bitrate)

        return (360, available_bitrate)
