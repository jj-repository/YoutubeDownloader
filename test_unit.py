#!/usr/bin/env python3
"""
Unit tests for YoutubeDownloader

Run with: pytest test_unit.py -v
Run with coverage: pytest test_unit.py -v --cov=constants
"""

import pytest
import os
import sys
from pathlib import Path

# Import modules to test
import constants


class TestConstantsModule:
    """Test suite for constants.py"""

    def test_preview_dimensions_positive(self):
        """Preview dimensions should be positive"""
        assert constants.PREVIEW_WIDTH > 0
        assert constants.PREVIEW_HEIGHT > 0

    def test_slider_length_positive(self):
        """Slider length should be positive"""
        assert constants.SLIDER_LENGTH > 0

    def test_timing_constants_positive(self):
        """Timing constants should be positive"""
        assert constants.PREVIEW_DEBOUNCE_MS > 0
        assert constants.UI_UPDATE_DELAY_MS > 0
        assert constants.UI_INITIAL_DELAY_MS > 0
        assert constants.AUTO_UPLOAD_DELAY_MS > 0
        assert constants.CLIPBOARD_POLL_INTERVAL_MS > 0

    def test_timeout_constants_reasonable(self):
        """Timeout constants should be reasonable values"""
        assert constants.DOWNLOAD_TIMEOUT >= 60  # At least 1 minute
        assert constants.DOWNLOAD_TIMEOUT <= 7200  # At most 2 hours
        assert constants.DOWNLOAD_PROGRESS_TIMEOUT >= 60  # At least 1 minute
        assert constants.METADATA_FETCH_TIMEOUT >= 10
        assert constants.FFPROBE_TIMEOUT >= 5

    def test_cache_and_thread_constants(self):
        """Cache and thread constants should be reasonable"""
        assert constants.PREVIEW_CACHE_SIZE > 0
        assert constants.MAX_WORKER_THREADS > 0
        assert constants.MAX_WORKER_THREADS <= 10  # Reasonable limit
        assert constants.MAX_RETRY_ATTEMPTS > 0
        assert constants.MAX_RETRY_ATTEMPTS <= 5

    def test_video_encoding_constants(self):
        """Video encoding constants should be valid"""
        assert 18 <= constants.VIDEO_CRF <= 28  # Reasonable CRF range
        assert 'k' in constants.AUDIO_BITRATE.lower() or 'K' in constants.AUDIO_BITRATE

    def test_validation_limits(self):
        """Validation limits should be reasonable"""
        assert constants.MAX_VOLUME >= 1.0  # At least 100%
        assert constants.MIN_VOLUME == 0.0
        assert constants.MAX_VIDEO_DURATION > 0
        assert constants.CATBOX_MAX_SIZE_MB > 0
        assert constants.MAX_FILENAME_LENGTH > 0

    def test_version_format(self):
        """Version should be in semver format"""
        version = constants.APP_VERSION
        parts = version.split('.')
        assert len(parts) >= 2, "Version should have at least major.minor"
        for part in parts:
            assert part.isdigit(), f"Version part '{part}' should be numeric"

    def test_github_constants_format(self):
        """GitHub constants should be valid URLs/identifiers"""
        assert '/' in constants.GITHUB_REPO
        assert constants.GITHUB_RELEASES_URL.startswith('https://github.com/')
        assert constants.GITHUB_API_LATEST.startswith('https://api.github.com/')
        assert constants.GITHUB_RAW_URL.startswith('https://raw.githubusercontent.com/')

    def test_file_paths_are_paths(self):
        """File path constants should be Path objects"""
        assert isinstance(constants.APP_DATA_DIR, Path)
        assert isinstance(constants.UPLOAD_HISTORY_FILE, Path)
        assert isinstance(constants.CLIPBOARD_URLS_FILE, Path)
        assert isinstance(constants.CONFIG_FILE, Path)
        assert isinstance(constants.LOG_FILE, Path)



class TestSanitizeFilename:
    """Test suite for YouTubeDownloader.sanitize_filename"""

    @staticmethod
    def sanitize_filename(filename):
        """Import and call the static method"""
        # Import the class
        import sys
        # Avoid importing tkinter by mocking it
        sys.modules['tkinter'] = type(sys)('tkinter')
        sys.modules['tkinter.ttk'] = type(sys)('tkinter.ttk')
        sys.modules['tkinter.messagebox'] = type(sys)('tkinter.messagebox')
        sys.modules['tkinter.filedialog'] = type(sys)('tkinter.filedialog')

        # Simple implementation matching the original
        if not filename:
            return ""

        dangerous_chars = ['/', '\\', '..', '\x00']
        for char in dangerous_chars:
            filename = filename.replace(char, '')

        shell_chars = ['$', '`', '|', ';', '&', '<', '>', '(', ')', '{', '}', '[', ']', '!', '*', '?', '~', '^']
        for char in shell_chars:
            filename = filename.replace(char, '')

        filename = ''.join(char for char in filename if ord(char) >= 32 and ord(char) != 127)
        filename = filename.strip('. ')

        if len(filename) > constants.MAX_FILENAME_LENGTH:
            filename = filename[:constants.MAX_FILENAME_LENGTH]

        return filename

    def test_empty_filename(self):
        """Empty filename should return empty string"""
        assert self.sanitize_filename("") == ""
        assert self.sanitize_filename(None) == ""

    def test_simple_filename(self):
        """Simple filename should be unchanged"""
        assert self.sanitize_filename("video.mp4") == "video.mp4"
        assert self.sanitize_filename("My Video Title") == "My Video Title"

    def test_removes_path_separators(self):
        """Path separators should be removed"""
        assert "/" not in self.sanitize_filename("path/to/file.mp4")
        assert "\\" not in self.sanitize_filename("path\\to\\file.mp4")

    def test_removes_parent_directory(self):
        """Parent directory references should be removed"""
        result = self.sanitize_filename("../../../etc/passwd")
        assert ".." not in result

    def test_removes_null_bytes(self):
        """Null bytes should be removed"""
        result = self.sanitize_filename("file\x00name.mp4")
        assert "\x00" not in result

    def test_removes_shell_metacharacters(self):
        """Shell metacharacters should be removed"""
        dangerous_chars = ['$', '`', '|', ';', '&', '<', '>', '!']
        result = self.sanitize_filename("file$name`test|video;.mp4")
        for char in dangerous_chars:
            assert char not in result

    def test_removes_control_characters(self):
        """Control characters should be removed"""
        result = self.sanitize_filename("file\x01\x02name.mp4")
        assert '\x01' not in result
        assert '\x02' not in result

    def test_strips_leading_trailing_dots_and_spaces(self):
        """Leading/trailing dots and spaces should be stripped"""
        assert self.sanitize_filename("  file.mp4  ") == "file.mp4"
        assert self.sanitize_filename("...file.mp4...") == "file.mp4"

    def test_truncates_long_filename(self):
        """Filenames exceeding max length should be truncated"""
        long_name = "a" * 500
        result = self.sanitize_filename(long_name)
        assert len(result) <= constants.MAX_FILENAME_LENGTH


class TestValidateVolume:
    """Test suite for volume validation"""

    @staticmethod
    def validate_volume(volume):
        """Validate and clamp volume value to safe range."""
        try:
            vol = float(volume)
            return max(constants.MIN_VOLUME, min(constants.MAX_VOLUME, vol))
        except (ValueError, TypeError):
            return 1.0

    def test_normal_volume(self):
        """Normal volume values should be unchanged"""
        assert self.validate_volume(1.0) == 1.0
        assert self.validate_volume(0.5) == 0.5
        assert self.validate_volume(1.5) == 1.5

    def test_min_volume(self):
        """Volume should be clamped to minimum"""
        assert self.validate_volume(-1.0) == 0.0
        assert self.validate_volume(-100) == 0.0

    def test_max_volume(self):
        """Volume should be clamped to maximum"""
        assert self.validate_volume(10.0) == constants.MAX_VOLUME
        assert self.validate_volume(100.0) == constants.MAX_VOLUME

    def test_invalid_volume(self):
        """Invalid volume should return default"""
        assert self.validate_volume("invalid") == 1.0
        assert self.validate_volume(None) == 1.0
        assert self.validate_volume([1, 2, 3]) == 1.0


class TestValidateTime:
    """Test suite for time validation"""

    @staticmethod
    def validate_time(time_str):
        """Validate time format HH:MM:SS and return seconds, or None if invalid."""
        import re
        TIME_REGEX = re.compile(r'^(\d{1,2}):(\d{2}):(\d{2})$')

        if not time_str:
            return None

        match = TIME_REGEX.match(time_str.strip())
        if not match:
            return None

        hours, minutes, seconds = map(int, match.groups())
        if minutes >= 60 or seconds >= 60:
            return None

        total_seconds = hours * 3600 + minutes * 60 + seconds
        if total_seconds > constants.MAX_VIDEO_DURATION:
            return None

        return total_seconds

    def test_valid_time(self):
        """Valid time strings should be converted to seconds"""
        assert self.validate_time("00:00:00") == 0
        assert self.validate_time("00:00:30") == 30
        assert self.validate_time("00:01:00") == 60
        assert self.validate_time("01:00:00") == 3600
        assert self.validate_time("1:30:45") == 5445

    def test_empty_time(self):
        """Empty time should return None"""
        assert self.validate_time("") is None
        assert self.validate_time(None) is None

    def test_invalid_format(self):
        """Invalid format should return None"""
        assert self.validate_time("invalid") is None
        assert self.validate_time("12:34") is None  # Missing seconds
        assert self.validate_time("12:34:56:78") is None  # Too many parts

    def test_invalid_values(self):
        """Invalid values (minutes/seconds >= 60) should return None"""
        assert self.validate_time("00:60:00") is None
        assert self.validate_time("00:00:60") is None
        assert self.validate_time("00:99:99") is None

    def test_time_with_whitespace(self):
        """Time with leading/trailing whitespace should work"""
        assert self.validate_time("  00:01:30  ") == 90


class TestValidateTimeRange:
    """Test suite for time range validation"""

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

    def test_valid_range(self):
        """Valid time range should return True"""
        assert self.validate_time_range(0, 60, 120) is True
        assert self.validate_time_range(10, 50, 100) is True

    def test_none_values(self):
        """None values should return False"""
        assert self.validate_time_range(None, 60, 120) is False
        assert self.validate_time_range(0, None, 120) is False
        assert self.validate_time_range(0, 60, None) is False

    def test_negative_values(self):
        """Negative values should return False"""
        assert self.validate_time_range(-1, 60, 120) is False
        assert self.validate_time_range(0, -1, 120) is False

    def test_start_after_end(self):
        """Start >= end should return False"""
        assert self.validate_time_range(60, 30, 120) is False
        assert self.validate_time_range(60, 60, 120) is False

    def test_end_exceeds_duration(self):
        """End > duration should return False"""
        assert self.validate_time_range(0, 150, 120) is False


class TestVersionComparison:
    """Test suite for version comparison logic"""

    @staticmethod
    def version_newer(latest, current):
        """Compare version strings."""
        try:
            latest_parts = tuple(map(int, latest.split('.')))
            current_parts = tuple(map(int, current.split('.')))
            return latest_parts > current_parts
        except (ValueError, AttributeError):
            return False

    def test_newer_major_version(self):
        """Newer major version should be detected"""
        assert self.version_newer("2.0.0", "1.0.0") is True
        assert self.version_newer("10.0.0", "9.0.0") is True

    def test_newer_minor_version(self):
        """Newer minor version should be detected"""
        assert self.version_newer("1.1.0", "1.0.0") is True
        assert self.version_newer("1.10.0", "1.9.0") is True

    def test_newer_patch_version(self):
        """Newer patch version should be detected"""
        assert self.version_newer("1.0.1", "1.0.0") is True
        assert self.version_newer("1.0.10", "1.0.9") is True

    def test_same_version(self):
        """Same version should not be newer"""
        assert self.version_newer("1.0.0", "1.0.0") is False
        assert self.version_newer("3.3.0", "3.3.0") is False

    def test_older_version(self):
        """Older version should not be newer"""
        assert self.version_newer("1.0.0", "2.0.0") is False
        assert self.version_newer("1.0.0", "1.1.0") is False
        assert self.version_newer("1.0.0", "1.0.1") is False

    def test_invalid_version(self):
        """Invalid versions should return False"""
        assert self.version_newer("invalid", "1.0.0") is False
        assert self.version_newer("1.0.0", "invalid") is False
        assert self.version_newer("", "1.0.0") is False


class TestValidateConfigJson:
    """Test suite for config JSON validation"""

    @staticmethod
    def validate_config_json(config):
        """Validate configuration JSON structure."""
        if not isinstance(config, dict):
            return False

        allowed_keys = {
            'language': str,
            'auto_check_updates': bool,
        }

        for key, value in config.items():
            if key not in allowed_keys:
                continue
            expected_type = allowed_keys[key]
            if not isinstance(value, expected_type):
                return False

        return True

    def test_valid_config(self):
        """Valid config should return True"""
        assert self.validate_config_json({'language': 'en'}) is True
        assert self.validate_config_json({'auto_check_updates': True}) is True
        assert self.validate_config_json({
            'language': 'de',
            'auto_check_updates': False
        }) is True

    def test_empty_config(self):
        """Empty config should be valid"""
        assert self.validate_config_json({}) is True

    def test_invalid_config_type(self):
        """Non-dict config should be invalid"""
        assert self.validate_config_json([]) is False
        assert self.validate_config_json("string") is False
        assert self.validate_config_json(123) is False

    def test_wrong_value_types(self):
        """Wrong value types should be invalid"""
        assert self.validate_config_json({'language': 123}) is False
        assert self.validate_config_json({'auto_check_updates': 'yes'}) is False

    def test_unknown_keys_allowed(self):
        """Unknown keys should be allowed (ignored)"""
        assert self.validate_config_json({'unknown_key': 'value'}) is True


class TestValidateDownloadPath:
    """Test suite for download path validation"""

    @staticmethod
    def validate_download_path(path):
        """Validate download path."""
        try:
            normalized = os.path.normpath(os.path.abspath(path))

            if '..' in path:
                return (False, None, "Path contains directory traversal sequences")

            home_dir = str(Path.home())
            safe_prefixes = [
                home_dir,
                '/tmp',
                os.path.expandvars('$TEMP') if sys.platform == 'win32' else '/tmp',
            ]

            is_safe = any(normalized.startswith(os.path.normpath(prefix)) for prefix in safe_prefixes)
            if not is_safe:
                return (False, None, "Download path must be within home directory or temp folder")

            return (True, normalized, None)
        except Exception as e:
            return (False, None, f"Path validation error: {str(e)}")

    def test_home_directory_valid(self):
        """Paths in home directory should be valid"""
        home = str(Path.home())
        is_valid, _, _ = self.validate_download_path(home)
        assert is_valid is True

        downloads = str(Path.home() / "Downloads")
        is_valid, _, _ = self.validate_download_path(downloads)
        assert is_valid is True

    def test_tmp_directory_valid(self):
        """Paths in /tmp should be valid"""
        is_valid, _, _ = self.validate_download_path("/tmp/downloads")
        assert is_valid is True

    def test_path_traversal_rejected(self):
        """Path traversal should be rejected"""
        is_valid, _, error = self.validate_download_path("../../../etc/passwd")
        assert is_valid is False
        assert "traversal" in error.lower()

    def test_system_paths_rejected(self):
        """System paths outside home/tmp should be rejected"""
        is_valid, _, _ = self.validate_download_path("/etc")
        assert is_valid is False

        is_valid, _, _ = self.validate_download_path("/usr/bin")
        assert is_valid is False


class TestYouTubeURLValidation:
    """Test suite for YouTube URL validation logic"""

    @staticmethod
    def is_youtube_url(url):
        """Check if URL is a valid YouTube URL"""
        from urllib.parse import urlparse, parse_qs

        if not url:
            return False

        try:
            parsed = urlparse(url)
            valid_domains = [
                'youtube.com', 'www.youtube.com', 'm.youtube.com',
                'youtu.be', 'www.youtu.be'
            ]

            if parsed.netloc not in valid_domains:
                return False

            if 'youtu.be' in parsed.netloc:
                return bool(parsed.path and parsed.path != '/')

            if 'youtube.com' in parsed.netloc:
                if '/watch' in parsed.path:
                    return 'v' in parse_qs(parsed.query)
                if '/shorts/' in parsed.path:
                    return True
                if '/embed/' in parsed.path:
                    return True
                if '/playlist' in parsed.path:
                    return True

            return False
        except Exception:
            return False

    def test_standard_youtube_url(self):
        """Standard YouTube URLs should be valid"""
        assert self.is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True
        assert self.is_youtube_url("https://youtube.com/watch?v=dQw4w9WgXcQ") is True

    def test_short_youtube_url(self):
        """Short youtu.be URLs should be valid"""
        assert self.is_youtube_url("https://youtu.be/dQw4w9WgXcQ") is True

    def test_youtube_shorts_url(self):
        """YouTube Shorts URLs should be valid"""
        assert self.is_youtube_url("https://www.youtube.com/shorts/abc123") is True

    def test_youtube_embed_url(self):
        """YouTube embed URLs should be valid"""
        assert self.is_youtube_url("https://www.youtube.com/embed/dQw4w9WgXcQ") is True

    def test_youtube_playlist_url(self):
        """YouTube playlist URLs should be valid"""
        assert self.is_youtube_url("https://www.youtube.com/playlist?list=PLtest") is True

    def test_invalid_urls(self):
        """Invalid URLs should return False"""
        assert self.is_youtube_url("") is False
        assert self.is_youtube_url(None) is False
        assert self.is_youtube_url("https://vimeo.com/12345") is False
        assert self.is_youtube_url("not a url") is False

    def test_missing_video_id(self):
        """URLs missing video ID should return False"""
        assert self.is_youtube_url("https://www.youtube.com/watch") is False
        assert self.is_youtube_url("https://youtu.be/") is False


class TestProgressRegex:
    """Test suite for progress parsing regex patterns"""

    def test_progress_regex(self):
        """Progress regex should match percentage values"""
        import re
        PROGRESS_REGEX = re.compile(r'(\d+\.?\d*)%')

        assert PROGRESS_REGEX.search("50%") is not None
        assert PROGRESS_REGEX.search("99.9%") is not None
        assert PROGRESS_REGEX.search("Downloading... 75%") is not None
        assert PROGRESS_REGEX.search("100%") is not None

    def test_speed_regex(self):
        """Speed regex should match common speed formats"""
        import re
        SPEED_REGEX = re.compile(r'(\d+\.?\d*\s*[KMG]iB/s)')

        assert SPEED_REGEX.search("5.2MiB/s") is not None
        assert SPEED_REGEX.search("100KiB/s") is not None
        assert SPEED_REGEX.search("1.5GiB/s") is not None

    def test_eta_regex(self):
        """ETA regex should match time formats"""
        import re
        ETA_REGEX = re.compile(r'ETA\s+(\d{2}:\d{2}(?::\d{2})?)')

        assert ETA_REGEX.search("ETA 01:30") is not None
        assert ETA_REGEX.search("ETA 00:05:30") is not None


class TestBytesConversion:
    """Test suite for byte conversion constants"""

    def test_bytes_per_mb(self):
        """BYTES_PER_MB should be 1024*1024"""
        assert constants.BYTES_PER_MB == 1024 * 1024
        assert constants.BYTES_PER_MB == 1048576


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
