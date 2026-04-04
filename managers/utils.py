"""Pure utility functions extracted from YouTubeDownloader.

All functions are stateless — no Qt, no GUI, no instance state.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from constants import (
    BYTES_PER_MB,
    MAX_FILENAME_LENGTH,
    MAX_RETRY_ATTEMPTS,
    MAX_VOLUME,
    MIN_VOLUME,
    PROCESS_TERMINATE_TIMEOUT,
    RETRY_DELAY,
)

logger = logging.getLogger(__name__)

# Subprocess kwargs to hide console windows on Windows
_subprocess_kwargs: dict = {}
if sys.platform == "win32":
    _subprocess_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW


# ===================================================================
#  Filename / path validation
# ===================================================================


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and command injection."""
    if not filename:
        return ""

    for char in ["/", "\\", "\x00"]:
        filename = filename.replace(char, "")
    while ".." in filename:
        filename = filename.replace("..", "")

    shell_chars = [
        "$",
        "`",
        "|",
        ";",
        "&",
        "<",
        ">",
        "(",
        ")",
        "{",
        "}",
        "[",
        "]",
        "!",
        "*",
        "?",
        "~",
        "^",
    ]
    for char in shell_chars:
        filename = filename.replace(char, "")

    filename = "".join(c for c in filename if ord(c) >= 32 and ord(c) != 127)
    filename = filename.strip(". ")

    if len(filename) > MAX_FILENAME_LENGTH:
        filename = filename[:MAX_FILENAME_LENGTH]

    return filename


def validate_download_path(path: str) -> tuple[bool, str | None, str | None]:
    """Validate download path to prevent path traversal attacks.

    Returns:
        tuple: (is_valid, normalized_path, error_message)
    """
    try:
        normalized = os.path.normpath(os.path.abspath(path))
        normalized_path = Path(normalized)

        if ".." in path or ".." in normalized:
            return (False, None, "Path contains directory traversal sequences")

        home_dir = Path.home()
        safe_dirs = [
            home_dir,
            Path("/tmp"),
            Path(os.environ.get("TEMP", "/tmp")) if sys.platform == "win32" else Path("/tmp"),
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
            return (
                False,
                None,
                "Download path must be within home directory or temp folder",
            )

        return (True, str(normalized_path.resolve()), None)
    except Exception as e:
        return (False, None, f"Path validation error: {str(e)}")


def validate_volume(volume: float | str) -> float:
    """Validate and clamp volume value to safe range."""
    try:
        vol = float(volume)
        return max(MIN_VOLUME, min(MAX_VOLUME, vol))
    except (ValueError, TypeError):
        return 1.0


# ===================================================================
#  Process / network utilities
# ===================================================================


def safe_process_cleanup(
    process: subprocess.Popen | None,
    timeout: int = PROCESS_TERMINATE_TIMEOUT,
) -> bool:
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
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    logger.error(f"Process {process.pid} did not exit after kill")

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


def retry_network_operation(operation, operation_name: str, *args, **kwargs):
    """Retry a network operation with exponential backoff."""
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            return operation(*args, **kwargs)
        except subprocess.TimeoutExpired:
            if attempt == MAX_RETRY_ATTEMPTS:
                logger.error(
                    f"{operation_name} failed after {MAX_RETRY_ATTEMPTS} attempts: timeout"
                )
                raise
            logger.warning(
                f"{operation_name} timeout (attempt {attempt}/{MAX_RETRY_ATTEMPTS}), retrying in {RETRY_DELAY}s..."
            )
            time.sleep(RETRY_DELAY * attempt)
        except subprocess.CalledProcessError as e:
            if attempt == MAX_RETRY_ATTEMPTS:
                logger.error(f"{operation_name} failed after {MAX_RETRY_ATTEMPTS} attempts: {e}")
                raise
            logger.warning(
                f"{operation_name} failed (attempt {attempt}/{MAX_RETRY_ATTEMPTS}), retrying in {RETRY_DELAY}s..."
            )
            time.sleep(RETRY_DELAY * attempt)
        except Exception as e:
            logger.error(f"{operation_name} failed with unexpected error: {e}")
            raise


# ===================================================================
#  Time conversion
# ===================================================================


def hms_to_seconds(hms_str: str) -> int | None:
    """Convert HH:MM:SS format to seconds."""
    try:
        parts = hms_str.strip().split(":")
        if len(parts) != 3:
            return None
        hours, minutes, seconds = map(int, parts)
        if hours < 0 or not (0 <= minutes <= 59) or not (0 <= seconds <= 59):
            return None
        return hours * 3600 + minutes * 60 + seconds
    except (ValueError, AttributeError):
        return None


def seconds_to_hms(seconds: float | int) -> str:
    """Convert seconds to HH:MM:SS format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


# ===================================================================
#  URL validation & parsing
# ===================================================================


def validate_youtube_url(url: str) -> tuple[bool, str]:
    """Validate if URL is a valid YouTube URL.

    Returns:
        tuple: (is_valid: bool, message: str)
    """
    if not url:
        return False, "URL is empty"
    if len(url) > 2048:
        return False, "URL is too long"

    try:
        parsed = urlparse(url)

        valid_domains = [
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "youtu.be",
            "www.youtu.be",
        ]

        if parsed.netloc not in valid_domains:
            return False, "Not a YouTube URL. Please enter a valid YouTube link."

        if "youtu.be" in parsed.netloc:
            if not parsed.path or parsed.path == "/":
                return False, "Invalid YouTube short URL"
            return True, "Valid YouTube URL"

        if "youtube.com" in parsed.netloc:
            if "/watch" in parsed.path:
                query_params = parse_qs(parsed.query)
                if "v" not in query_params:
                    return False, "Missing video ID in URL"
                return True, "Valid YouTube URL"
            elif "/shorts/" in parsed.path:
                return True, "Valid YouTube Shorts URL"
            elif "/embed/" in parsed.path:
                return True, "Valid YouTube embed URL"
            elif "/v/" in parsed.path:
                return True, "Valid YouTube URL"
            elif "/playlist" in parsed.path or "list=" in parsed.query:
                return True, "Valid YouTube Playlist URL"
            else:
                return False, "Unrecognized YouTube URL format"

        return False, "Invalid URL format"

    except Exception as e:
        logger.error(f"URL validation error: {e}")
        return False, f"Invalid URL format: {str(e)}"


def is_playlist_url(url: str) -> bool:
    """Check if URL is a YouTube playlist."""
    try:
        parsed = urlparse(url)
        if "/playlist" in parsed.path:
            return True
        query_params = parse_qs(parsed.query)
        if "list=" in parsed.query and query_params.get("list"):
            return True
        return False
    except (ValueError, AttributeError):
        return False


def is_pure_playlist_url(url: str) -> bool:
    """Check if URL is a pure playlist URL (e.g. /playlist?list=YYY) without a video context."""
    try:
        parsed = urlparse(url)
        return "/playlist" in parsed.path
    except (ValueError, AttributeError):
        return False


def strip_playlist_params(url: str) -> str:
    """Strip playlist-related params (list, index) from a URL, keeping the video context."""
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        params.pop("list", None)
        params.pop("index", None)
        flat_params = {k: v[0] if len(v) == 1 else v for k, v in params.items()}
        new_query = urlencode(flat_params, doseq=True)
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment,
            )
        )
    except (ValueError, AttributeError):
        return url


def is_local_file(input_text: str) -> bool:
    """Check if input is a local file path."""
    if os.path.isfile(input_text):
        return True

    path = Path(input_text)
    media_extensions = {
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".flv",
        ".webm",
        ".wmv",
        ".m4v",
        ".ts",
        ".mpg",
        ".mpeg",
        ".mp3",
        ".aac",
        ".m4a",
        ".wav",
    }
    if path.suffix.lower() in media_extensions:
        return True

    return False


def get_speed_limit_args(speed_limit_str: str | None) -> list[str]:
    """Get yt-dlp speed limit arguments from a pre-captured string.

    Args:
        speed_limit_str: Speed limit value in MB/s (e.g. "5.0").
    """
    if speed_limit_str:
        try:
            speed_limit = float(speed_limit_str)
            if speed_limit > 0:
                rate_bytes = int(speed_limit * BYTES_PER_MB)
                return ["--limit-rate", f"{rate_bytes}"]
        except ValueError:
            pass
    return []
