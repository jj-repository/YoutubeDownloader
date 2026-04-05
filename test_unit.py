#!/usr/bin/env python3
"""
Unit tests for YoutubeDownloader

Run with: pytest test_unit.py -v
Run with coverage: pytest test_unit.py -v --cov=constants --cov=managers
"""

import re
import struct
from pathlib import Path

import pytest

import constants
from managers.download_manager import DownloadManager
from managers.encoding import EncodingService
from managers.utils import (
    get_speed_limit_args,
    hms_to_seconds,
    is_local_file,
    is_playlist_url,
    is_pure_playlist_url,
    sanitize_filename,
    seconds_to_hms,
    strip_playlist_params,
    validate_download_path,
    validate_volume,
    validate_youtube_url,
)

# ─── Constants ────────────────────────────────────────────────────────────


class TestConstantsModule:
    """Test suite for constants.py"""

    def test_preview_dimensions_positive(self):
        assert constants.PREVIEW_WIDTH > 0
        assert constants.PREVIEW_HEIGHT > 0

    def test_timing_constants_positive(self):
        assert constants.PREVIEW_DEBOUNCE_MS > 0
        assert constants.CLIPBOARD_POLL_INTERVAL_MS > 0

    def test_timeout_constants(self):
        assert constants.DOWNLOAD_TIMEOUT == 3600
        assert constants.DOWNLOAD_PROGRESS_TIMEOUT == 600
        assert constants.METADATA_FETCH_TIMEOUT == 30
        assert constants.FFPROBE_TIMEOUT == 10

    def test_cache_and_thread_constants(self):
        assert constants.MAX_WORKER_THREADS == 8
        assert constants.MAX_RETRY_ATTEMPTS == 3

    def test_version_format(self):
        """Version should be X.XX (exactly 2 parts)."""
        parts = constants.APP_VERSION.split(".")
        assert len(parts) == 2, "Version should be major.minor (X.XX)"
        for part in parts:
            assert part.isdigit()

    def test_github_constants_format(self):
        assert "/" in constants.GITHUB_REPO
        assert constants.GITHUB_RELEASES_URL.startswith("https://github.com/")
        assert constants.GITHUB_API_LATEST.startswith("https://api.github.com/")

    def test_file_paths_are_paths(self):
        assert isinstance(constants.APP_DATA_DIR, Path)
        assert isinstance(constants.CONFIG_FILE, Path)
        assert isinstance(constants.LOG_FILE, Path)

    def test_bytes_per_mb(self):
        assert constants.BYTES_PER_MB == 1024 * 1024


# ─── managers/utils.py ────────────────────────────────────────────────────


class TestHmsToSeconds:
    """Test hms_to_seconds from production code."""

    def test_valid_times(self):
        assert hms_to_seconds("00:00:00") == 0
        assert hms_to_seconds("00:00:30") == 30
        assert hms_to_seconds("00:01:00") == 60
        assert hms_to_seconds("01:00:00") == 3600
        assert hms_to_seconds("1:30:45") == 5445
        assert hms_to_seconds("23:59:59") == 86399

    def test_large_hours(self):
        assert hms_to_seconds("99:00:00") == 99 * 3600

    def test_empty_and_none(self):
        assert hms_to_seconds("") is None
        assert hms_to_seconds(None) is None

    def test_invalid_format(self):
        assert hms_to_seconds("invalid") is None
        assert hms_to_seconds("12:34") is None
        assert hms_to_seconds("12:34:56:78") is None

    def test_invalid_values(self):
        assert hms_to_seconds("00:60:00") is None
        assert hms_to_seconds("00:00:60") is None

    def test_whitespace(self):
        assert hms_to_seconds("  01:00:00  ") == 3600

    def test_non_string(self):
        assert hms_to_seconds(12345) is None
        assert hms_to_seconds([1, 2, 3]) is None


class TestSecondsToHms:
    """Test seconds_to_hms from production code."""

    def test_zero(self):
        assert seconds_to_hms(0) == "00:00:00"

    def test_basic_values(self):
        assert seconds_to_hms(30) == "00:00:30"
        assert seconds_to_hms(60) == "00:01:00"
        assert seconds_to_hms(3600) == "01:00:00"
        assert seconds_to_hms(3661) == "01:01:01"

    def test_max_normal(self):
        assert seconds_to_hms(86399) == "23:59:59"

    def test_large_hours(self):
        assert seconds_to_hms(360000) == "100:00:00"

    def test_float_truncation(self):
        assert seconds_to_hms(90.7) == "00:01:30"

    def test_negative_clamped_to_zero(self):
        assert seconds_to_hms(-1) == "00:00:00"
        assert seconds_to_hms(-3661) == "00:00:00"

    def test_roundtrip(self):
        for secs in [0, 30, 90, 3600, 5445, 86399]:
            assert hms_to_seconds(seconds_to_hms(secs)) == secs


class TestIsLocalFile:
    """Test is_local_file from production code."""

    def test_empty(self):
        assert is_local_file("") is False

    def test_nonexistent_video_extension(self):
        assert is_local_file("/tmp/nonexistent_test_file_12345.mp4") is True

    def test_nonexistent_audio_extension(self):
        assert is_local_file("/tmp/nonexistent_test_file_12345.mp3") is True
        assert is_local_file("/tmp/nonexistent_test_file_12345.wav") is True

    def test_unknown_extension(self):
        assert is_local_file("/tmp/nonexistent_test_file_12345.xyz") is False

    def test_url_not_local(self):
        assert is_local_file("https://youtube.com/watch?v=abc") is False

    def test_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("data")
        assert is_local_file(str(f)) is True


class TestIsPlaylistUrl:
    """Test is_playlist_url from production code."""

    def test_playlist_path(self):
        assert is_playlist_url("https://youtube.com/playlist?list=PLtest") is True

    def test_watch_with_list(self):
        assert is_playlist_url("https://youtube.com/watch?v=abc&list=PLtest") is True

    def test_regular_watch(self):
        assert is_playlist_url("https://youtube.com/watch?v=abc") is False

    def test_empty(self):
        assert is_playlist_url("") is False


class TestIsPurePlaylistUrl:
    """Test is_pure_playlist_url from production code."""

    def test_pure_playlist(self):
        assert is_pure_playlist_url("https://youtube.com/playlist?list=PLtest") is True

    def test_watch_with_list_not_pure(self):
        assert is_pure_playlist_url("https://youtube.com/watch?v=abc&list=PLtest") is False


class TestStripPlaylistParams:
    """Test strip_playlist_params from production code."""

    def test_strips_list_and_index(self):
        url = "https://youtube.com/watch?v=abc&list=PLtest&index=3"
        result = strip_playlist_params(url)
        assert "list=" not in result
        assert "index=" not in result
        assert "v=abc" in result

    def test_preserves_video_id(self):
        url = "https://youtube.com/watch?v=dQw4w9WgXcQ&list=PLtest"
        result = strip_playlist_params(url)
        assert "dQw4w9WgXcQ" in result

    def test_no_params_unchanged(self):
        url = "https://youtube.com/watch?v=abc"
        result = strip_playlist_params(url)
        assert "v=abc" in result


class TestGetSpeedLimitArgs:
    """Test get_speed_limit_args from production code."""

    def test_none(self):
        assert get_speed_limit_args(None) == []

    def test_empty(self):
        assert get_speed_limit_args("") == []

    def test_zero(self):
        assert get_speed_limit_args("0") == []
        assert get_speed_limit_args("0.0") == []

    def test_valid_limit(self):
        result = get_speed_limit_args("1")
        assert result[0] == "--limit-rate"
        assert int(result[1]) == 1048576  # 1 MB/s

    def test_fractional(self):
        result = get_speed_limit_args("0.5")
        assert result[0] == "--limit-rate"
        assert int(result[1]) == 524288  # 0.5 MB/s

    def test_negative(self):
        assert get_speed_limit_args("-1") == []

    def test_non_numeric(self):
        assert get_speed_limit_args("abc") == []


class TestSanitizeFilename:
    """Test sanitize_filename from production code."""

    def test_empty(self):
        assert sanitize_filename("") == ""
        assert sanitize_filename(None) == ""

    def test_simple(self):
        assert sanitize_filename("video.mp4") == "video.mp4"

    def test_removes_path_separators(self):
        result = sanitize_filename("path/to/file.mp4")
        assert "/" not in result

    def test_removes_parent_directory(self):
        result = sanitize_filename("../../../etc/passwd")
        assert ".." not in result

    def test_removes_null_bytes(self):
        assert "\x00" not in sanitize_filename("file\x00name.mp4")

    def test_removes_shell_metacharacters(self):
        result = sanitize_filename("file$name`test|video;.mp4")
        for char in ["$", "`", "|", ";"]:
            assert char not in result

    def test_all_dots(self):
        assert sanitize_filename("...") == ""

    def test_all_spaces(self):
        assert sanitize_filename("   ") == ""

    def test_truncates_long(self):
        result = sanitize_filename("a" * 500)
        assert len(result) <= constants.MAX_FILENAME_LENGTH

    def test_unicode_preserved(self):
        assert "日本語" in sanitize_filename("日本語ビデオ.mp4")


class TestValidateVolume:
    """Test validate_volume from production code."""

    def test_normal(self):
        assert validate_volume(1.0) == 1.0
        assert validate_volume(0.5) == 0.5

    def test_clamped_min(self):
        assert validate_volume(-1.0) == 0.0

    def test_clamped_max(self):
        assert validate_volume(10.0) == constants.MAX_VOLUME

    def test_invalid(self):
        assert validate_volume("invalid") == 1.0
        assert validate_volume(None) == 1.0


class TestValidateDownloadPath:
    """Test validate_download_path from production code."""

    def test_home_valid(self):
        is_valid, _, _ = validate_download_path(str(Path.home()))
        assert is_valid is True

    def test_tmp_valid(self):
        is_valid, _, _ = validate_download_path("/tmp/downloads")
        assert is_valid is True

    def test_path_traversal_rejected(self):
        is_valid, _, error = validate_download_path("../../../etc/passwd")
        assert is_valid is False

    def test_system_paths_rejected(self):
        is_valid, _, _ = validate_download_path("/etc")
        assert is_valid is False


class TestYouTubeURLValidation:
    """Test validate_youtube_url from production code."""

    def test_standard(self):
        is_valid, _ = validate_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert is_valid is True

    def test_short(self):
        is_valid, _ = validate_youtube_url("https://youtu.be/dQw4w9WgXcQ")
        assert is_valid is True

    def test_shorts(self):
        is_valid, _ = validate_youtube_url("https://www.youtube.com/shorts/abc123")
        assert is_valid is True

    def test_embed(self):
        is_valid, _ = validate_youtube_url("https://www.youtube.com/embed/dQw4w9WgXcQ")
        assert is_valid is True

    def test_playlist(self):
        is_valid, _ = validate_youtube_url("https://www.youtube.com/playlist?list=PLtest")
        assert is_valid is True

    def test_mobile(self):
        is_valid, _ = validate_youtube_url("https://m.youtube.com/watch?v=dQw4w9WgXcQ")
        assert is_valid is True

    def test_invalid(self):
        assert validate_youtube_url("")[0] is False
        assert validate_youtube_url(None)[0] is False
        assert validate_youtube_url("https://vimeo.com/12345")[0] is False
        assert validate_youtube_url("not a url")[0] is False

    def test_missing_video_id(self):
        assert validate_youtube_url("https://www.youtube.com/watch")[0] is False
        assert validate_youtube_url("https://youtu.be/")[0] is False

    def test_url_too_long(self):
        long_url = "https://www.youtube.com/watch?v=abc" + "x" * 2050
        is_valid, msg = validate_youtube_url(long_url)
        assert is_valid is False
        assert "too long" in msg.lower()


# ─── managers/encoding.py ─────────────────────────────────────────────────


class TestEncodingService:
    """Test EncodingService methods."""

    def test_crf_software(self):
        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder=None)
        args = enc.get_video_encoder_args(mode="crf")
        assert "-c:v" in args
        assert "libx264" in args
        assert "-crf" in args

    def test_crf_nvenc(self):
        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder="h264_nvenc")
        args = enc.get_video_encoder_args(mode="crf")
        assert "h264_nvenc" in args

    def test_crf_amf(self):
        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder="h264_amf")
        args = enc.get_video_encoder_args(mode="crf")
        assert "h264_amf" in args

    def test_bitrate_software(self):
        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder=None)
        args = enc.get_video_encoder_args(mode="bitrate", target_bitrate=2000000)
        assert "-b:v" in args
        assert "-maxrate" in args

    def test_bitrate_nvenc(self):
        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder="h264_nvenc")
        args = enc.get_video_encoder_args(mode="bitrate", target_bitrate=1000000)
        assert "h264_nvenc" in args
        assert "-b:v" in args

    def test_bitrate_amf(self):
        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder="h264_amf")
        args = enc.get_video_encoder_args(mode="bitrate", target_bitrate=2000000)
        assert "h264_amf" in args
        assert "-b:v" in args
        assert "-maxrate" in args

    def test_crf_values(self):
        """CRF mode should include the VIDEO_CRF constant."""
        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder=None)
        args = enc.get_video_encoder_args(mode="crf")
        assert str(constants.VIDEO_CRF) in args

    def test_bitrate_maxrate_calculation(self):
        """maxrate should be 1.5x target_bitrate."""
        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder=None)
        args = enc.get_video_encoder_args(mode="bitrate", target_bitrate=2000000)
        maxrate_idx = args.index("-maxrate") + 1
        assert int(args[maxrate_idx]) == 3000000  # 2M * 1.5

    def test_calculate_optimal_quality_zero_duration(self):
        res, bitrate = EncodingService.calculate_optimal_quality(0)
        assert res == 360
        assert bitrate == 100000

    def test_calculate_optimal_quality_negative(self):
        res, bitrate = EncodingService.calculate_optimal_quality(-5)
        assert res == 360

    def test_calculate_optimal_quality_short(self):
        """1-second clip should get 1080p (huge available bitrate)."""
        res, bitrate = EncodingService.calculate_optimal_quality(1)
        assert res == 1080

    def test_calculate_optimal_quality_long(self):
        """10000-second clip should get 360p (low bitrate)."""
        res, bitrate = EncodingService.calculate_optimal_quality(10000)
        assert res == 360

    def test_calculate_optimal_quality_medium(self):
        """~80s clip: bitrate determines resolution tier."""
        res, bitrate = EncodingService.calculate_optimal_quality(80)
        assert res in [1080, 720, 480, 360]

    def test_calculate_optimal_quality_returns_tuple(self):
        result = EncodingService.calculate_optimal_quality(60)
        assert isinstance(result, tuple)

    def test_calculate_optimal_quality_returns_typed_tuple(self):
        result = EncodingService.calculate_optimal_quality(60)
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], (int, float))

    def test_bitrate_mode_requires_target(self):
        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder=None)
        with pytest.raises(ValueError, match="target_bitrate required"):
            enc.get_video_encoder_args(mode="bitrate", target_bitrate=None)


# ─── managers/download_manager.py ─────────────────────────────────────────


class TestParseSidx:
    """Test DownloadManager._parse_sidx with crafted binary data."""

    @staticmethod
    def _make_sidx_box(version=0, timescale=1000, first_offset=0, segments=None):
        """Build a minimal SIDX box for testing."""
        if segments is None:
            segments = [(10000, 5000)]  # (ref_size, seg_duration)

        # SIDX box content
        if version == 0:
            ver_flags = struct.pack(">I", 0)  # version=0, flags=0
            ref_id = struct.pack(">I", 1)
            ts = struct.pack(">I", timescale)
            earliest_pts = struct.pack(">I", 0)
            fo = struct.pack(">I", first_offset)
        else:
            ver_flags = struct.pack(">I", 0x01000000)  # version=1, flags=0
            ref_id = struct.pack(">I", 1)
            ts = struct.pack(">I", timescale)
            earliest_pts = struct.pack(">Q", 0)
            fo = struct.pack(">Q", first_offset)

        reserved_refcount = struct.pack(">HH", 0, len(segments))

        refs = b""
        for ref_size, seg_dur in segments:
            # ref_type=0 (bit 31=0), ref_size in lower 31 bits
            refs += struct.pack(">III", ref_size, seg_dur, 0x90000000)

        body = ver_flags + ref_id + ts + earliest_pts + fo + reserved_refcount + refs
        box_size = 8 + len(body)
        return struct.pack(">I", box_size) + b"sidx" + body

    def test_basic_sidx(self):
        data = self._make_sidx_box(
            version=0, timescale=1000, first_offset=0, segments=[(50000, 5000), (60000, 5000)]
        )
        result = DownloadManager._parse_sidx(data)
        assert result is not None
        sidx_end, segments = result
        assert len(segments) == 2
        # Each segment should have (offset, size, start_time, duration)
        assert len(segments[0]) == 4
        assert segments[0][1] == 50000  # ref_size
        assert segments[1][1] == 60000

    def test_no_sidx_returns_none(self):
        # A box that is NOT sidx
        data = struct.pack(">I", 12) + b"ftyp" + b"\x00\x00\x00\x00"
        assert DownloadManager._parse_sidx(data) is None

    def test_empty_data(self):
        assert DownloadManager._parse_sidx(b"") is None

    def test_truncated_data(self):
        assert DownloadManager._parse_sidx(b"\x00\x00") is None

    def test_sidx_v1(self):
        data = self._make_sidx_box(
            version=1, timescale=44100, first_offset=100, segments=[(8000, 44100)]
        )
        result = DownloadManager._parse_sidx(data)
        assert result is not None
        _, segments = result
        assert len(segments) == 1

    def test_sidx_after_other_box(self):
        """SIDX preceded by another box should still be found."""
        ftyp = struct.pack(">I", 12) + b"ftyp" + b"\x00\x00\x00\x00"
        sidx = self._make_sidx_box(segments=[(1000, 500)])
        data = ftyp + sidx
        result = DownloadManager._parse_sidx(data)
        assert result is not None


class TestFindLatestFile:
    """Test DownloadManager._find_latest_file."""

    def test_empty_directory(self, tmp_path):
        assert DownloadManager._find_latest_file(str(tmp_path)) is None

    def test_nonexistent_directory(self):
        assert DownloadManager._find_latest_file("/nonexistent/path/xyz") is None

    def test_finds_latest(self, tmp_path):
        f1 = tmp_path / "one.mp4"
        f1.write_text("data1")
        f2 = tmp_path / "two.mp4"
        f2.write_text("data2")
        result = DownloadManager._find_latest_file(str(tmp_path))
        assert result is not None
        # Should return one of the files (exact ordering depends on filesystem ctime)
        assert result.endswith(".mp4")

    def test_ignores_directories(self, tmp_path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        assert DownloadManager._find_latest_file(str(tmp_path)) is None


class TestCleanupTempFiles:
    """Test DownloadManager.cleanup_temp_files."""

    def test_none_input(self):
        DownloadManager.cleanup_temp_files(None)  # should not raise

    def test_nonexistent_path(self):
        DownloadManager.cleanup_temp_files("/nonexistent/xyz")  # should not raise

    def test_cleans_directory(self, tmp_path):
        d = tmp_path / "temp_ytdl"
        d.mkdir()
        (d / "file.tmp").write_text("data")
        DownloadManager.cleanup_temp_files(str(d))
        assert not d.exists()


# ─── managers/update_manager.py ───────────────────────────────────────────


class TestVersionNewer:
    """Test UpdateManager._version_newer using the production code."""

    @pytest.fixture
    def version_newer(self):
        from managers.update_manager import UpdateManager

        return UpdateManager._version_newer

    def test_newer_major(self, version_newer):
        assert version_newer("2.0.0", "1.0.0") is True

    def test_newer_minor(self, version_newer):
        assert version_newer("1.1.0", "1.0.0") is True

    def test_newer_patch(self, version_newer):
        assert version_newer("1.0.1", "1.0.0") is True

    def test_same(self, version_newer):
        assert version_newer("1.0.0", "1.0.0") is False

    def test_older(self, version_newer):
        assert version_newer("1.0.0", "2.0.0") is False

    def test_two_part_version(self, version_newer):
        """X.XX format used by this project."""
        assert version_newer("5.15", "5.14") is True
        assert version_newer("5.14", "5.14") is False
        assert version_newer("5.13", "5.14") is False

    def test_different_lengths(self, version_newer):
        assert version_newer("3.1.2", "3.1") is True
        assert version_newer("3.1", "3.1.2") is False

    def test_invalid(self, version_newer):
        assert version_newer("invalid", "1.0.0") is False
        assert version_newer("1.0.0", "invalid") is False
        assert version_newer("", "1.0.0") is False
        assert version_newer(None, "1.0.0") is False


# ─── Regex (test against production patterns) ────────────────────────────


class TestProgressRegex:
    """Test regex patterns from production download_manager."""

    def test_progress_regex(self):
        from managers.download_manager import PROGRESS_REGEX

        assert PROGRESS_REGEX.search("50%") is not None
        assert PROGRESS_REGEX.search("99.9%") is not None
        assert PROGRESS_REGEX.search("[download]  42.3% ...") is not None

    def test_speed_regex(self):
        from managers.download_manager import SPEED_REGEX

        assert SPEED_REGEX.search("5.2MiB/s") is not None
        assert SPEED_REGEX.search("100KiB/s") is not None

    def test_eta_regex(self):
        from managers.download_manager import ETA_REGEX

        assert ETA_REGEX.search("ETA 01:30") is not None
        assert ETA_REGEX.search("ETA 00:05:30") is not None


# ─── managers/download_manager.py (integration) ──────────────────────────


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication once for the entire test session."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture
def download_mgr(qapp):
    """Create a DownloadManager instance for testing."""
    from concurrent.futures import ThreadPoolExecutor

    pool = ThreadPoolExecutor(max_workers=1)
    enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder=None)
    mgr = DownloadManager(
        ytdlp_path="yt-dlp",
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        encoding=enc,
        thread_pool=pool,
    )
    yield mgr
    pool.shutdown(wait=False)


class TestUpdateProgress:
    """Test DownloadManager.update_progress clamping."""

    def test_clamps_to_zero(self, download_mgr):
        from unittest.mock import MagicMock

        spy = MagicMock()
        download_mgr.sig_update_progress.connect(spy)
        download_mgr.update_progress(-5)
        spy.assert_called_once_with(0)

    def test_clamps_to_hundred(self, download_mgr):
        from unittest.mock import MagicMock

        spy = MagicMock()
        download_mgr.sig_update_progress.connect(spy)
        download_mgr.update_progress(150)
        spy.assert_called_once_with(100)

    def test_normal_value(self, download_mgr):
        from unittest.mock import MagicMock

        spy = MagicMock()
        download_mgr.sig_update_progress.connect(spy)
        download_mgr.update_progress(42.5)
        spy.assert_called_once_with(42.5)

    def test_invalid_string(self, download_mgr):
        from unittest.mock import MagicMock

        spy = MagicMock()
        download_mgr.sig_update_progress.connect(spy)
        download_mgr.update_progress("not_a_number")
        spy.assert_not_called()


class TestBuildBaseCommand:
    """Test DownloadManager.build_base_ytdlp_command."""

    def test_starts_with_ytdlp_path(self, download_mgr):
        cmd = download_mgr.build_base_ytdlp_command()
        assert cmd[0] == "yt-dlp"

    def test_includes_concurrent_fragments(self, download_mgr):
        cmd = download_mgr.build_base_ytdlp_command()
        assert "--concurrent-fragments" in cmd
        idx = cmd.index("--concurrent-fragments")
        assert cmd[idx + 1] == constants.CONCURRENT_FRAGMENTS

    def test_includes_newline_progress(self, download_mgr):
        cmd = download_mgr.build_base_ytdlp_command()
        assert "--newline" in cmd
        assert "--progress" in cmd


class TestBuildAudioCommand:
    """Test DownloadManager.build_audio_ytdlp_command."""

    def test_audio_format(self, download_mgr):
        cmd = download_mgr.build_audio_ytdlp_command("https://youtu.be/test", "/tmp/out.mp3")
        assert "-f" in cmd
        assert "bestaudio" in cmd
        assert "--extract-audio" in cmd
        assert "--audio-format" in cmd
        assert "mp3" in cmd

    def test_audio_output_and_url(self, download_mgr):
        cmd = download_mgr.build_audio_ytdlp_command("https://youtu.be/test", "/tmp/out.mp3")
        assert cmd[-1] == "https://youtu.be/test"
        assert cmd[-2] == "--"
        assert cmd[-3] == "/tmp/out.mp3"
        assert cmd[-4] == "-o"

    def test_audio_no_volume_arg_at_default(self, download_mgr):
        cmd = download_mgr.build_audio_ytdlp_command(
            "https://youtu.be/test", "/tmp/out.mp3", volume=1.0
        )
        assert not any("volume=" in arg for arg in cmd)

    def test_audio_volume_arg(self, download_mgr):
        cmd = download_mgr.build_audio_ytdlp_command(
            "https://youtu.be/test", "/tmp/out.mp3", volume=0.5
        )
        assert any("volume=0.5" in arg for arg in cmd)


class TestBuildVideoCommand:
    """Test DownloadManager.build_video_ytdlp_command."""

    def test_video_quality_in_format(self, download_mgr):
        cmd = download_mgr.build_video_ytdlp_command("https://youtu.be/test", "/tmp/out.mp4", "720")
        fmt_idx = cmd.index("-f") + 1
        assert "720" in cmd[fmt_idx]

    def test_video_merge_format(self, download_mgr):
        cmd = download_mgr.build_video_ytdlp_command(
            "https://youtu.be/test", "/tmp/out.mp4", "1080"
        )
        assert "--merge-output-format" in cmd
        assert "mp4" in cmd

    def test_video_no_trim_by_default(self, download_mgr):
        cmd = download_mgr.build_video_ytdlp_command("https://youtu.be/test", "/tmp/out.mp4", "720")
        assert "--download-sections" not in cmd
        assert "--force-keyframes-at-cuts" not in cmd

    def test_video_with_trim(self, download_mgr):
        cmd = download_mgr.build_video_ytdlp_command(
            "https://youtu.be/test",
            "/tmp/out.mp4",
            "720",
            trim_start=60,
            trim_end=120,
        )
        assert "--download-sections" in cmd
        assert "--force-keyframes-at-cuts" in cmd
        sections_idx = cmd.index("--download-sections") + 1
        assert "00:01:00" in cmd[sections_idx]
        assert "00:02:00" in cmd[sections_idx]

    def test_video_trim_adds_encoder_args(self, download_mgr):
        cmd = download_mgr.build_video_ytdlp_command(
            "https://youtu.be/test",
            "/tmp/out.mp4",
            "720",
            trim_start=0,
            trim_end=30,
        )
        assert "--postprocessor-args" in cmd
        pp_idx = cmd.index("--postprocessor-args") + 1
        assert "libx264" in cmd[pp_idx]

    def test_video_volume_adds_filter(self, download_mgr):
        cmd = download_mgr.build_video_ytdlp_command(
            "https://youtu.be/test", "/tmp/out.mp4", "720", volume=1.5
        )
        assert "--postprocessor-args" in cmd
        pp_idx = cmd.index("--postprocessor-args") + 1
        assert "volume=1.5" in cmd[pp_idx]

    def test_video_no_processing_at_defaults(self, download_mgr):
        cmd = download_mgr.build_video_ytdlp_command("https://youtu.be/test", "/tmp/out.mp4", "720")
        assert "--postprocessor-args" not in cmd

    def test_video_url_is_last(self, download_mgr):
        cmd = download_mgr.build_video_ytdlp_command("https://youtu.be/test", "/tmp/out.mp4", "720")
        assert cmd[-1] == "https://youtu.be/test"


class TestBuildBatchCommands:
    """Test DownloadManager batch command builders."""

    def test_batch_audio_uses_batch_file(self, download_mgr):
        cmd = download_mgr.build_batch_audio_ytdlp_command("/tmp/batch.txt", "/tmp/%(title)s.mp3")
        assert "--batch-file" in cmd
        assert cmd[cmd.index("--batch-file") + 1] == "/tmp/batch.txt"
        assert "--" not in cmd

    def test_batch_audio_has_audio_format(self, download_mgr):
        cmd = download_mgr.build_batch_audio_ytdlp_command("/tmp/batch.txt", "/tmp/%(title)s.mp3")
        assert "bestaudio" in cmd
        assert "--extract-audio" in cmd

    def test_batch_video_uses_batch_file(self, download_mgr):
        cmd = download_mgr.build_batch_video_ytdlp_command(
            "/tmp/batch.txt", "/tmp/%(title)s.mp4", "720"
        )
        assert "--batch-file" in cmd
        assert "--" not in cmd

    def test_batch_video_has_quality(self, download_mgr):
        cmd = download_mgr.build_batch_video_ytdlp_command(
            "/tmp/batch.txt", "/tmp/%(title)s.mp4", "720"
        )
        fmt_idx = cmd.index("-f") + 1
        assert "720" in cmd[fmt_idx]

    def test_batch_video_has_merge_format(self, download_mgr):
        cmd = download_mgr.build_batch_video_ytdlp_command(
            "/tmp/batch.txt", "/tmp/%(title)s.mp4", "1080"
        )
        assert "--merge-output-format" in cmd
        assert "mp4" in cmd

    def test_batch_includes_newline_progress(self, download_mgr):
        cmd = download_mgr.build_batch_audio_ytdlp_command("/tmp/batch.txt", "/tmp/out.mp3")
        assert "--newline" in cmd
        assert "--progress" in cmd


class TestExtractingUrlRegex:
    """Test _EXTRACTING_URL_RE regex for batch output parsing."""

    _RE = re.compile(r"Extracting URL:\s+(\S+)")

    def test_youtube_video(self):
        line = "[youtube] Extracting URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        m = self._RE.search(line)
        assert m is not None
        assert m.group(1) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_youtube_playlist(self):
        line = "[youtube:tab] Extracting URL: https://www.youtube.com/playlist?list=PLtest"
        m = self._RE.search(line)
        assert m is not None
        assert "playlist" in m.group(1)

    def test_no_match(self):
        line = "[download] 45.3% of 10.00MiB"
        m = self._RE.search(line)
        assert m is None


# ─── managers/upload_manager.py ───────────────────────────────────────────


class TestUploadManager:
    """Test UploadManager state management."""

    @pytest.fixture
    def mgr(self):
        from concurrent.futures import ThreadPoolExecutor

        from managers.upload_manager import UploadManager

        pool = ThreadPoolExecutor(max_workers=1)
        m = UploadManager(thread_pool=pool)
        yield m
        pool.shutdown(wait=False)

    def test_initial_state(self, mgr):
        assert mgr.catbox_client is None
        assert mgr.is_uploading is False
        assert mgr.last_output_file is None
        assert mgr.uploader_file_queue == []

    def test_add_to_queue(self, mgr):
        mgr.add_to_queue("/tmp/test.mp4")
        assert len(mgr.uploader_file_queue) == 1
        assert mgr.uploader_file_queue[0]["path"] == "/tmp/test.mp4"

    def test_add_duplicate_to_queue(self, mgr):
        mgr.add_to_queue("/tmp/test.mp4")
        mgr.add_to_queue("/tmp/test.mp4")
        assert len(mgr.uploader_file_queue) == 1

    def test_remove_from_queue(self, mgr):
        mgr.add_to_queue("/tmp/a.mp4")
        mgr.add_to_queue("/tmp/b.mp4")
        mgr.remove_from_queue("/tmp/a.mp4")
        assert len(mgr.uploader_file_queue) == 1
        assert mgr.uploader_file_queue[0]["path"] == "/tmp/b.mp4"

    def test_clear_queue(self, mgr):
        mgr.add_to_queue("/tmp/a.mp4")
        mgr.add_to_queue("/tmp/b.mp4")
        mgr.clear_queue()
        assert mgr.uploader_file_queue == []


# ─── managers/clipboard_manager.py ────────────────────────────────────────


class TestClipboardManager:
    """Test ClipboardManager state management."""

    @pytest.fixture
    def mgr(self):
        from concurrent.futures import ThreadPoolExecutor

        from managers.clipboard_manager import ClipboardManager

        pool = ThreadPoolExecutor(max_workers=1)
        m = ClipboardManager(thread_pool=pool)
        yield m
        pool.shutdown(wait=False)

    def test_initial_state(self, mgr):
        assert mgr.clipboard_monitoring is False
        assert mgr.clipboard_stop_event.is_set()  # initially stopped
        assert len(mgr.clipboard_url_list) == 0
        assert mgr.clipboard_last_content == ""

    def test_lock_acquisition(self, mgr):
        """Locks should be acquirable without deadlock."""
        with mgr.clipboard_lock:
            pass
        with mgr.auto_download_lock:
            pass


# ─── managers/utils.py — process/network utilities ────────────────────────


class TestSafeProcessCleanup:
    """Test safe_process_cleanup with mock subprocesses."""

    def test_none_input(self):
        from managers.utils import safe_process_cleanup

        assert safe_process_cleanup(None) is True

    def test_already_exited(self):
        from unittest.mock import MagicMock

        from managers.utils import safe_process_cleanup

        proc = MagicMock()
        proc.poll.return_value = 0  # already exited
        assert safe_process_cleanup(proc) is True
        proc.terminate.assert_not_called()

    def test_terminate_succeeds(self):
        from unittest.mock import MagicMock

        from managers.utils import safe_process_cleanup

        proc = MagicMock()
        proc.poll.return_value = None  # still running
        proc.wait.return_value = None
        assert safe_process_cleanup(proc) is True
        proc.terminate.assert_called_once()

    def test_terminate_timeout_then_kill(self):
        import subprocess
        from unittest.mock import MagicMock

        from managers.utils import safe_process_cleanup

        proc = MagicMock()
        proc.poll.return_value = None
        proc.wait.side_effect = [subprocess.TimeoutExpired("cmd", 5), None]
        assert safe_process_cleanup(proc) is True
        proc.kill.assert_called_once()

    def test_closes_pipes(self):
        from unittest.mock import MagicMock

        from managers.utils import safe_process_cleanup

        proc = MagicMock()
        proc.poll.return_value = 0
        safe_process_cleanup(proc)
        proc.stdout.close.assert_called_once()
        proc.stderr.close.assert_called_once()
        proc.stdin.close.assert_called_once()

    def test_exception_returns_false(self):
        from unittest.mock import MagicMock

        from managers.utils import safe_process_cleanup

        proc = MagicMock()
        proc.poll.side_effect = OSError("bad fd")
        assert safe_process_cleanup(proc) is False


class TestRetryNetworkOperation:
    """Test retry_network_operation with mock callables."""

    def test_succeeds_first_try(self):
        from managers.utils import retry_network_operation

        result = retry_network_operation(lambda: 42, "test_op")
        assert result == 42

    def test_retries_on_timeout(self):
        import subprocess
        from unittest.mock import MagicMock

        from managers.utils import retry_network_operation

        op = MagicMock(side_effect=[subprocess.TimeoutExpired("cmd", 5), "ok"])
        result = retry_network_operation(op, "test_op")
        assert result == "ok"
        assert op.call_count == 2

    def test_retries_on_called_process_error(self):
        import subprocess
        from unittest.mock import MagicMock

        from managers.utils import retry_network_operation

        op = MagicMock(
            side_effect=[
                subprocess.CalledProcessError(1, "cmd"),
                "ok",
            ]
        )
        result = retry_network_operation(op, "test_op")
        assert result == "ok"

    def test_raises_on_unexpected_error(self):
        from managers.utils import retry_network_operation

        with pytest.raises(ValueError, match="bad"):
            retry_network_operation(
                lambda: (_ for _ in ()).throw(ValueError("bad")),
                "test_op",
            )

    def test_exhausts_retries(self):
        import subprocess
        from unittest.mock import MagicMock

        from managers.utils import retry_network_operation

        op = MagicMock(side_effect=subprocess.TimeoutExpired("cmd", 5))
        with pytest.raises(subprocess.TimeoutExpired):
            retry_network_operation(op, "test_op")


# ─── managers/update_manager.py — SHA verification ───────────────────────


class TestComputeGitBlobSha:
    """Test _compute_git_blob_sha against known git hash-object output."""

    @pytest.fixture
    def updater(self):
        from managers.update_manager import UpdateManager

        mgr = UpdateManager.__new__(UpdateManager)
        return mgr

    def test_known_hash(self, updater):
        # hashlib.sha1(b"blob 5\x00hello") — Python git-blob computation
        result = updater._compute_git_blob_sha(b"hello")
        assert result == "b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0"

    def test_empty_content(self, updater):
        # echo -n "" | git hash-object --stdin => e69de29bb2d1d6434b8b29ae775ad8c2e48c5391
        result = updater._compute_git_blob_sha(b"")
        assert result == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"

    def test_binary_content(self, updater):
        content = bytes(range(256))
        result = updater._compute_git_blob_sha(content)
        assert isinstance(result, str) and len(result) == 40


class TestParseYtdlpVersion:
    """Test _parse_ytdlp_version."""

    @pytest.fixture
    def updater(self):
        from managers.update_manager import UpdateManager

        mgr = UpdateManager.__new__(UpdateManager)
        return mgr

    def test_normal_version(self, updater):
        assert updater._parse_ytdlp_version("2026.02.04") == (2026, 2, 4)

    def test_two_part(self, updater):
        assert updater._parse_ytdlp_version("2026.02") == (2026, 2)

    def test_invalid(self, updater):
        assert updater._parse_ytdlp_version("invalid") == (0,)

    def test_none(self, updater):
        assert updater._parse_ytdlp_version(None) == (0,)

    def test_empty(self, updater):
        assert updater._parse_ytdlp_version("") == (0,)


# ─── managers/trimming_manager.py — cache and error image ────────────────


class TestTrimmingManagerCache:
    """Test TrimmingManager preview cache LRU behavior."""

    @pytest.fixture
    def mgr(self):
        from managers.trimming_manager import TrimmingManager

        m = TrimmingManager.__new__(TrimmingManager)
        m.preview_cache = __import__("collections").OrderedDict()
        m.preview_lock = __import__("threading").Lock()
        return m

    def test_cache_add_and_get(self, mgr, tmp_path):
        path = str(tmp_path / "frame_5.png")
        mgr._cache_preview_frame(5, path)
        assert mgr._get_cached_frame(5) == path

    def test_cache_miss(self, mgr):
        assert mgr._get_cached_frame(999) is None

    def test_cache_eviction(self, mgr, tmp_path):
        # Fill beyond PREVIEW_CACHE_SIZE (default 50)
        for i in range(55):
            mgr._cache_preview_frame(i, str(tmp_path / f"frame_{i}.png"))
        # Earliest entries should be evicted
        assert mgr._get_cached_frame(0) is None
        assert mgr._get_cached_frame(54) is not None

    def test_clear_cache(self, mgr, tmp_path):
        path = str(tmp_path / "frame_1.png")
        mgr._cache_preview_frame(1, path)
        mgr.clear_preview_cache()
        assert mgr._get_cached_frame(1) is None


class TestTrimmingManagerErrorImage:
    """Test _error_image returns valid QImage."""

    def test_error_image_valid(self):
        from managers.trimming_manager import TrimmingManager

        # Reset cached image for clean test
        TrimmingManager._cached_error_image = None
        img = TrimmingManager._error_image()
        assert not img.isNull()
        assert img.width() == constants.PREVIEW_WIDTH
        assert img.height() == constants.PREVIEW_HEIGHT

    def test_error_image_cached(self):
        from managers.trimming_manager import TrimmingManager

        TrimmingManager._cached_error_image = None
        img1 = TrimmingManager._error_image()
        img2 = TrimmingManager._error_image()
        assert img1 is img2


# ─── TQ-5: Download timeout and stop ────────────────────────────────────


class TestDownloadTimeout:
    """Test _monitor_download_timeout and stop_download."""

    def test_timeout_monitor_exits_when_not_downloading(self, download_mgr):
        """Timeout monitor should exit its loop when is_downloading becomes False."""
        from unittest.mock import patch

        download_mgr.is_downloading = False
        download_mgr._shutting_down = False

        # _monitor_download_timeout sleeps TIMEOUT_CHECK_INTERVAL then checks
        # is_downloading — with it already False it should exit immediately
        with patch("managers.download_manager.time.sleep"):
            download_mgr._monitor_download_timeout()
        # If we get here without hanging, the monitor exited correctly

    def test_timeout_monitor_exits_on_shutdown(self, download_mgr):
        """Timeout monitor should break when _shutting_down is set."""
        from unittest.mock import patch

        download_mgr.is_downloading = True
        download_mgr._shutting_down = True

        with patch("managers.download_manager.time.sleep"):
            download_mgr._monitor_download_timeout()

    def test_stop_download_noop_when_not_downloading(self, download_mgr):
        """stop_download should be a no-op when nothing is active."""
        download_mgr.is_downloading = False
        download_mgr.current_process = None
        download_mgr.stop_download()  # should not raise
        assert download_mgr.is_downloading is False

    def test_stop_download_sets_not_downloading(self, download_mgr):
        """stop_download should set is_downloading to False and clean up the process."""
        from unittest.mock import MagicMock, patch

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = None

        download_mgr.is_downloading = True
        download_mgr.current_process = mock_proc

        with patch("managers.download_manager.safe_process_cleanup") as mock_cleanup:
            mock_cleanup.return_value = True
            download_mgr.stop_download()

        assert download_mgr.is_downloading is False
        mock_cleanup.assert_called_once_with(mock_proc)

    def test_stop_download_no_cleanup_when_process_is_none(self, download_mgr):
        """stop_download should skip cleanup when current_process is None."""
        from unittest.mock import patch

        download_mgr.is_downloading = True
        download_mgr.current_process = None

        with patch("managers.download_manager.safe_process_cleanup") as mock_cleanup:
            download_mgr.stop_download()

        mock_cleanup.assert_not_called()

    def test_absolute_timeout_detection(self, download_mgr):
        """Monitor should call _timeout_download when elapsed exceeds DOWNLOAD_TIMEOUT."""
        from unittest.mock import patch

        download_mgr.is_downloading = True
        download_mgr._shutting_down = False
        download_mgr._download_has_progress = True
        download_mgr.last_progress_time = None

        # download started 3601 seconds ago (exceeds 3600s timeout)
        download_mgr.download_start_time = 1000.0

        call_count = 0
        original_is_downloading = True

        def fake_sleep(_):
            pass

        def fake_time():
            nonlocal call_count, original_is_downloading
            call_count += 1
            # Return time that exceeds the absolute timeout
            return 1000.0 + 3601

        with (
            patch("managers.download_manager.time.sleep", side_effect=fake_sleep),
            patch("managers.download_manager.time.time", side_effect=fake_time),
            patch.object(download_mgr, "_timeout_download") as mock_timeout,
        ):
            # _timeout_download will be called but we need the loop to break.
            # After _timeout_download is called, the method breaks out of the loop.
            download_mgr._monitor_download_timeout()

        mock_timeout.assert_called_once()
        assert (
            "timeout" in mock_timeout.call_args[0][0].lower()
            or "60 min" in mock_timeout.call_args[0][0].lower()
        )

    def test_timeout_download_cleans_up_process(self, download_mgr):
        """_timeout_download should kill the process and reset state."""
        from unittest.mock import MagicMock, patch

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = None

        download_mgr.is_downloading = True
        download_mgr.current_process = mock_proc

        with patch("managers.download_manager.safe_process_cleanup") as mock_cleanup:
            mock_cleanup.return_value = True
            download_mgr._timeout_download("Test timeout")

        assert download_mgr.is_downloading is False
        assert download_mgr.current_process is None
        mock_cleanup.assert_called_once_with(mock_proc)


# ─── TQ-6: Upload validation ────────────────────────────────────────────


class TestUploadValidation:
    """Test start_upload_if_valid, save_upload_link, and _get_catbox_client."""

    @pytest.fixture
    def upload_mgr(self, qapp):
        from concurrent.futures import ThreadPoolExecutor

        from managers.upload_manager import UploadManager

        pool = ThreadPoolExecutor(max_workers=1)
        m = UploadManager(thread_pool=pool)
        yield m
        pool.shutdown(wait=False)

    def test_start_upload_no_file_set(self, upload_mgr):
        """Should return failure when last_output_file is None."""
        upload_mgr.last_output_file = None
        ok, msg = upload_mgr.start_upload_if_valid()
        assert ok is False
        assert "No file" in msg

    def test_start_upload_nonexistent_file(self, upload_mgr):
        """Should return failure for a non-existent file path."""
        upload_mgr.last_output_file = "/tmp/nonexistent_file_xyz_12345.mp4"
        ok, msg = upload_mgr.start_upload_if_valid()
        assert ok is False
        assert "No file" in msg

    def test_start_upload_file_over_200mb(self, upload_mgr, tmp_path):
        """Should return failure for files over 200MB."""
        from unittest.mock import patch

        test_file = tmp_path / "big_video.mp4"
        test_file.write_text("data")
        upload_mgr.last_output_file = str(test_file)

        # 201 MB in bytes
        with patch("os.path.getsize", return_value=201 * 1024 * 1024):
            ok, msg = upload_mgr.start_upload_if_valid()

        assert ok is False
        assert "200MB" in msg or "200" in msg

    def test_start_upload_valid_file(self, upload_mgr, tmp_path):
        """Should return success for a valid file under 200MB."""
        from unittest.mock import patch

        test_file = tmp_path / "small_video.mp4"
        test_file.write_text("data")
        upload_mgr.last_output_file = str(test_file)

        # 50 MB in bytes
        with patch("os.path.getsize", return_value=50 * 1024 * 1024):
            ok, msg = upload_mgr.start_upload_if_valid()

        assert ok is True
        assert msg == ""

    def test_save_upload_link_writes_correct_format(self, upload_mgr, tmp_path):
        """save_upload_link should write timestamp | filename | link format."""
        from unittest.mock import patch

        history_file = tmp_path / "upload_history.txt"

        with patch("managers.upload_manager.UPLOAD_HISTORY_FILE", history_file):
            upload_mgr.save_upload_link("https://files.catbox.moe/abc123.mp4", "video.mp4")

        content = history_file.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        assert len(lines) == 1
        parts = lines[0].split(" | ")
        assert len(parts) == 3
        assert parts[1] == "video.mp4"
        assert parts[2] == "https://files.catbox.moe/abc123.mp4"

    def test_save_upload_link_appends(self, upload_mgr, tmp_path):
        """Multiple saves should append to the file."""
        from unittest.mock import patch

        history_file = tmp_path / "upload_history.txt"

        with patch("managers.upload_manager.UPLOAD_HISTORY_FILE", history_file):
            upload_mgr.save_upload_link("https://catbox.moe/1.mp4", "a.mp4")
            upload_mgr.save_upload_link("https://catbox.moe/2.mp4", "b.mp4")

        content = history_file.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        assert len(lines) == 2

    def test_get_catbox_client_lazy_init(self, upload_mgr):
        """_get_catbox_client should lazily create a CatboxClient on first call."""
        from unittest.mock import MagicMock, patch

        assert upload_mgr.catbox_client is None

        mock_client = MagicMock()
        # CatboxClient is imported inside the method via from catboxpy.catbox import CatboxClient
        # We patch the import target in the catboxpy module
        with patch.dict(
            "sys.modules",
            {
                "catboxpy": MagicMock(),
                "catboxpy.catbox": MagicMock(CatboxClient=lambda: mock_client),
            },
        ):
            result = upload_mgr._get_catbox_client()

        assert result is mock_client
        assert upload_mgr.catbox_client is mock_client

    def test_get_catbox_client_returns_cached(self, upload_mgr):
        """Second call to _get_catbox_client should return the cached instance."""
        from unittest.mock import MagicMock

        mock_client = MagicMock()
        upload_mgr.catbox_client = mock_client
        result = upload_mgr._get_catbox_client()
        assert result is mock_client


# ─── TQ-10: Encoding execution ──────────────────────────────────────────


class TestEncodingExecution:
    """Test size_constrained_encode routing and run_ffmpeg_with_progress parsing."""

    def test_size_constrained_routes_to_single_pass_with_hw_encoder(self):
        """When hw_encoder is set, size_constrained_encode should call encode_single_pass."""
        from unittest.mock import MagicMock, patch

        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder="h264_nvenc")
        cb = MagicMock()

        with patch.object(enc, "encode_single_pass", return_value=True) as mock_sp:
            with patch.object(enc, "encode_two_pass", return_value=True) as mock_tp:
                result = enc.size_constrained_encode("input.mp4", "output.mp4", 2000000, 60.0, cb)

        assert result is True
        mock_sp.assert_called_once()
        mock_tp.assert_not_called()

    def test_size_constrained_routes_to_two_pass_without_hw_encoder(self):
        """When hw_encoder is None, size_constrained_encode should call encode_two_pass."""
        from unittest.mock import MagicMock, patch

        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder=None)
        cb = MagicMock()

        with patch.object(enc, "encode_single_pass", return_value=True) as mock_sp:
            with patch.object(enc, "encode_two_pass", return_value=True) as mock_tp:
                result = enc.size_constrained_encode("input.mp4", "output.mp4", 2000000, 60.0, cb)

        assert result is True
        mock_tp.assert_called_once()
        mock_sp.assert_not_called()

    def test_size_constrained_passes_all_args(self):
        """All arguments should be forwarded to the underlying encode method."""
        from unittest.mock import MagicMock, patch

        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder="h264_amf")
        cb = MagicMock()

        with patch.object(enc, "encode_single_pass", return_value=True) as mock_sp:
            enc.size_constrained_encode(
                "in.mp4",
                "out.mp4",
                1500000,
                30.0,
                cb,
                volume_multiplier=0.8,
                scale_height=720,
                start_time=10.0,
                end_time=40.0,
            )

        mock_sp.assert_called_once_with(
            "in.mp4",
            "out.mp4",
            1500000,
            30.0,
            cb,
            0.8,
            720,
            10.0,
            40.0,
        )

    def test_run_ffmpeg_progress_line_parsing(self):
        """run_ffmpeg_with_progress should parse out_time_ms lines into progress."""
        import threading
        from unittest.mock import MagicMock, patch

        from managers.encoding import EncodeCallbacks

        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder=None)

        progress_values = []

        def track_progress(val):
            progress_values.append(val)

        cb = EncodeCallbacks(
            on_progress=track_progress,
            on_status=MagicMock(),
            is_cancelled=lambda: False,
            process_lock=threading.Lock(),
            set_process=MagicMock(),
            on_heartbeat=MagicMock(),
        )

        # Simulate ffmpeg stdout with out_time_ms lines
        stdout_lines = [
            "out_time_ms=15000000\n",  # 15s of 30s = 50%
            "out_time_ms=30000000\n",  # 30s of 30s = 100%
        ]

        mock_proc = MagicMock()
        mock_proc.stdout = iter(stdout_lines)
        mock_proc.stderr = iter([])
        mock_proc.wait.return_value = None
        mock_proc.returncode = 0

        with patch("managers.encoding.subprocess.Popen", return_value=mock_proc):
            result = enc.run_ffmpeg_with_progress(
                ["ffmpeg", "-i", "input.mp4", "output.mp4"],
                duration=30.0,
                status_prefix="Encoding",
                cb=cb,
            )

        assert result is True
        # First call is on_progress(0) at start, then parsed values
        assert 0 in progress_values
        # Should have parsed ~50% and ~100%
        parsed = [v for v in progress_values if v > 0]
        assert len(parsed) >= 2
        assert any(abs(v - 50.0) < 1.0 for v in parsed)
        assert any(abs(v - 100.0) < 1.0 for v in parsed)

    def test_run_ffmpeg_cancellation_callback(self):
        """Cancellation callback should stop ffmpeg and return False."""
        import threading
        from unittest.mock import MagicMock, patch

        from managers.encoding import EncodeCallbacks

        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder=None)

        cb = EncodeCallbacks(
            on_progress=MagicMock(),
            on_status=MagicMock(),
            is_cancelled=lambda: True,  # always cancelled
            process_lock=threading.Lock(),
            set_process=MagicMock(),
            on_heartbeat=MagicMock(),
        )

        stdout_lines = ["out_time_ms=5000000\n"]

        mock_proc = MagicMock()
        mock_proc.stdout = iter(stdout_lines)
        mock_proc.stderr = iter([])
        mock_proc.wait.return_value = None
        mock_proc.returncode = 0
        mock_proc.poll.return_value = None

        with (
            patch("managers.encoding.subprocess.Popen", return_value=mock_proc),
            patch("managers.encoding.safe_process_cleanup") as mock_cleanup,
        ):
            mock_cleanup.return_value = True
            result = enc.run_ffmpeg_with_progress(
                ["ffmpeg", "-i", "input.mp4", "output.mp4"],
                duration=30.0,
                status_prefix="Encoding",
                cb=cb,
            )

        assert result is False
        mock_cleanup.assert_called_once_with(mock_proc)

    def test_run_ffmpeg_nonzero_exit_returns_false(self):
        """Non-zero exit code should return False."""
        import threading
        from unittest.mock import MagicMock, patch

        from managers.encoding import EncodeCallbacks

        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder=None)

        cb = EncodeCallbacks(
            on_progress=MagicMock(),
            on_status=MagicMock(),
            is_cancelled=lambda: False,
            process_lock=threading.Lock(),
            set_process=MagicMock(),
            on_heartbeat=MagicMock(),
        )

        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.stderr = iter(["error: something failed\n"])
        mock_proc.wait.return_value = None
        mock_proc.returncode = 1
        mock_proc.poll.return_value = 1

        with (
            patch("managers.encoding.subprocess.Popen", return_value=mock_proc),
            patch("managers.encoding.safe_process_cleanup") as mock_cleanup,
        ):
            mock_cleanup.return_value = True
            result = enc.run_ffmpeg_with_progress(
                ["ffmpeg", "-i", "input.mp4", "output.mp4"],
                duration=30.0,
                status_prefix="Encoding",
                cb=cb,
            )

        assert result is False


# ─── TQ-4: Download method ──────────────────────────────────────────────


class TestDownloadMethod:
    """Test download() method code paths and state transitions."""

    def _make_ui_state(self, **overrides):
        """Create a default ui_state dict with optional overrides."""
        state = {
            "quality": "720",
            "trim_enabled": False,
            "audio_only": False,
            "keep_below_10mb": False,
            "filename": "",
            "volume_raw": 100,
            "download_path": "/tmp",
            "speed_limit": None,
            "start_time": "0",
            "end_time": "60",
        }
        state.update(overrides)
        return state

    @staticmethod
    def _make_mock_proc(stdout_lines=None, returncode=0):
        """Create a mock Popen process with iterable stdout that supports .close()."""
        from unittest.mock import MagicMock

        mock_proc = MagicMock()
        mock_stdout = MagicMock()
        mock_stdout.__iter__ = MagicMock(return_value=iter(stdout_lines or []))
        mock_proc.stdout = mock_stdout
        mock_proc.stderr = MagicMock()
        mock_proc.wait.return_value = None
        mock_proc.returncode = returncode
        return mock_proc

    def test_audio_only_path_taken(self, download_mgr):
        """When audio_only is True, the command should contain audio extraction flags."""
        from unittest.mock import patch

        ui_state = self._make_ui_state(quality="none (Audio only)", audio_only=True)
        download_mgr.is_downloading = True
        download_mgr.video_duration = 120

        mock_proc = self._make_mock_proc()
        captured_cmd = []

        def capture_popen(cmd, **kwargs):
            captured_cmd.extend(cmd)
            return mock_proc

        with (
            patch("managers.download_manager.subprocess.Popen", side_effect=capture_popen),
            patch.object(download_mgr, "_find_latest_file", return_value=None),
        ):
            download_mgr.download("https://www.youtube.com/watch?v=test123", ui_state)

        assert "--extract-audio" in captured_cmd
        assert "--audio-format" in captured_cmd
        assert "mp3" in captured_cmd
        assert "bestaudio" in captured_cmd
        # State should be reset after download
        assert download_mgr.is_downloading is False

    def test_trimmed_path_taken(self, download_mgr):
        """When trim_enabled is True, the trimmed ffmpeg path should be used."""
        from unittest.mock import patch

        ui_state = self._make_ui_state(trim_enabled=True, start_time="10", end_time="30")
        download_mgr.is_downloading = True
        download_mgr.video_duration = 120

        with patch.object(
            download_mgr, "_download_trimmed_via_ffmpeg", return_value=True
        ) as mock_trim:
            download_mgr.download("https://www.youtube.com/watch?v=test123", ui_state)

        mock_trim.assert_called_once()
        # Verify start_time and end_time were passed
        call_args = mock_trim.call_args
        assert call_args[0][2] == 10  # start_time
        assert call_args[0][3] == 30  # end_time
        assert download_mgr.is_downloading is False

    def test_10mb_path_taken(self, download_mgr):
        """When keep_below_10mb is True (no trim), should use size-constrained path."""
        from unittest.mock import patch

        ui_state = self._make_ui_state(keep_below_10mb=True)
        download_mgr.is_downloading = True
        download_mgr.video_duration = 120

        mock_proc = self._make_mock_proc()
        captured_cmd = []

        def capture_popen(cmd, **kwargs):
            captured_cmd.extend(cmd)
            return mock_proc

        with patch("managers.download_manager.subprocess.Popen", side_effect=capture_popen):
            with patch.object(download_mgr.encoding, "size_constrained_encode", return_value=True):
                download_mgr.download("https://www.youtube.com/watch?v=test123", ui_state)

        # The command uses a temp dir, not the final output path
        # size_constrained_encode is called after yt-dlp finishes
        assert download_mgr.is_downloading is False

    def test_state_transition_downloading_to_done(self, download_mgr):
        """is_downloading should start True and end False after download completes."""
        from unittest.mock import patch

        ui_state = self._make_ui_state()
        download_mgr.is_downloading = True
        download_mgr.video_duration = 120

        mock_proc = self._make_mock_proc()

        with (
            patch("managers.download_manager.subprocess.Popen", return_value=mock_proc),
            patch.object(download_mgr, "_find_latest_file", return_value=None),
        ):
            download_mgr.download("https://www.youtube.com/watch?v=test123", ui_state)

        assert download_mgr.is_downloading is False
        assert download_mgr.current_process is None

    def test_state_transition_on_exception(self, download_mgr):
        """is_downloading should be reset to False even when download raises."""
        from unittest.mock import patch

        ui_state = self._make_ui_state()
        download_mgr.is_downloading = True
        download_mgr.video_duration = 120

        with patch(
            "managers.download_manager.subprocess.Popen",
            side_effect=FileNotFoundError("yt-dlp not found"),
        ):
            download_mgr.download("https://www.youtube.com/watch?v=test123", ui_state)

        assert download_mgr.is_downloading is False

    def test_local_file_routes_to_download_local_file(self, download_mgr):
        """A local file path should be routed to download_local_file."""
        from unittest.mock import patch

        with patch.object(download_mgr, "download_local_file") as mock_local:
            download_mgr.download("/tmp/existing_video.mp4", None)

        mock_local.assert_called_once_with("/tmp/existing_video.mp4", None)


# ─── H-5: _parse_ytdlp_output ────────────────────────────────────────────


class TestParseYtdlpOutput:
    """Test DownloadManager._parse_ytdlp_output with representative yt-dlp lines."""

    def _make_mock_process(self, lines):
        """Create a mock process with stdout yielding the given lines."""
        from unittest.mock import MagicMock

        proc = MagicMock()
        proc.stdout = iter(lines)
        return proc

    def test_progress_line_updates_progress(self, download_mgr):
        """A [download] line with percentage should emit progress."""
        from unittest.mock import MagicMock

        download_mgr.is_downloading = True
        download_mgr.last_progress_time = 0
        spy = MagicMock()
        download_mgr.sig_update_progress.connect(spy)

        proc = self._make_mock_process(["[download]  42.5% of 10.00MiB at 1.50MiB/s ETA 00:04\n"])
        errors = download_mgr._parse_ytdlp_output(proc)

        assert errors == []
        spy.assert_called()
        # The emitted value should be ~42.5
        emitted_val = spy.call_args[0][0]
        assert 42.0 <= emitted_val <= 43.0

    def test_error_lines_collected(self, download_mgr):
        """Lines containing ERROR should be collected."""
        download_mgr.is_downloading = True
        download_mgr.last_progress_time = 0

        proc = self._make_mock_process(
            [
                "ERROR: Video unavailable\n",
                "[download] Some normal line\n",
                "error: network issue\n",
            ]
        )
        errors = download_mgr._parse_ytdlp_output(proc)

        assert len(errors) == 2
        assert "Video unavailable" in errors[0]
        assert "network issue" in errors[1]

    def test_already_downloaded_status(self, download_mgr):
        """'has already been downloaded' should update status."""
        from unittest.mock import MagicMock

        download_mgr.is_downloading = True
        download_mgr.last_progress_time = 0
        spy = MagicMock()
        download_mgr.sig_update_status.connect(spy)

        proc = self._make_mock_process(["File has already been downloaded\n"])
        download_mgr._parse_ytdlp_output(proc)

        spy.assert_called()
        msg = spy.call_args[0][0]
        assert "already exists" in msg

    def test_stops_on_is_downloading_false(self, download_mgr):
        """Parsing should stop when is_downloading becomes False."""
        download_mgr.is_downloading = False
        download_mgr.last_progress_time = 0

        proc = self._make_mock_process(
            [
                "[download]  10.0% of 10.00MiB\n",
                "[download]  20.0% of 10.00MiB\n",
            ]
        )
        errors = download_mgr._parse_ytdlp_output(proc)
        assert errors == []

    def test_merger_status(self, download_mgr):
        """[Merger] line should update status to merging."""
        from unittest.mock import MagicMock

        download_mgr.is_downloading = True
        download_mgr.last_progress_time = 0
        spy = MagicMock()
        download_mgr.sig_update_status.connect(spy)

        proc = self._make_mock_process(["[Merger] Merging formats into output.mkv\n"])
        download_mgr._parse_ytdlp_output(proc)

        spy.assert_called()
        msg = spy.call_args[0][0]
        assert "Merging" in msg

    def test_speed_and_eta_in_status(self, download_mgr):
        """Progress lines with speed+ETA should include both in status."""
        from unittest.mock import MagicMock

        download_mgr.is_downloading = True
        download_mgr.last_progress_time = 0
        spy = MagicMock()
        download_mgr.sig_update_status.connect(spy)

        proc = self._make_mock_process(["[download]  75.0% of 100.00MiB at 5.00MiB/s ETA 00:05\n"])
        download_mgr._parse_ytdlp_output(proc)

        msg = spy.call_args[0][0]
        assert "75.0%" in msg
        assert "5.00MiB/s" in msg
        assert "ETA" in msg


# ─── H-6: _download_stream_segment_inner ──────────────────────────────────


class TestDownloadStreamSegmentInner:
    """Test DownloadManager._download_stream_segment_inner with mocked HTTP."""

    def _make_stream_url(self, clen=1000000, dur=60.0):
        return f"https://rr.google.com/videoplayback?clen={clen}&dur={dur}"

    def test_missing_clen_raises(self, download_mgr):
        """Missing clen parameter should raise RuntimeError."""
        download_mgr.is_downloading = True
        download_mgr.last_progress_time = 0
        url = "https://rr.google.com/videoplayback?dur=60.0"
        with pytest.raises(RuntimeError, match="Missing clen/dur"):
            download_mgr._download_stream_segment_inner(url, 10.0, 20.0, "/tmp/out.mp4", "video")

    def test_missing_dur_raises(self, download_mgr):
        """dur=0 should raise RuntimeError."""
        download_mgr.is_downloading = True
        download_mgr.last_progress_time = 0
        url = "https://rr.google.com/videoplayback?clen=1000000&dur=0"
        with pytest.raises(RuntimeError, match="Missing clen/dur"):
            download_mgr._download_stream_segment_inner(url, 10.0, 20.0, "/tmp/out.mp4", "video")

    def test_estimation_fallback(self, download_mgr, tmp_path):
        """Without SIDX, should fall back to bitrate estimation."""
        from unittest.mock import MagicMock, patch

        download_mgr.is_downloading = True
        download_mgr.last_progress_time = 0

        fake_header = b"\x00" * 1024
        call_count = [0]

        def mock_urlopen(req, timeout=None):
            call_count[0] += 1
            resp = MagicMock()
            if call_count[0] == 1:
                # Header fetch via _http_range_read — chunked read
                resp.read = MagicMock(side_effect=[fake_header, b""])
            else:
                # Data fetch — return chunk then empty
                resp.read = MagicMock(side_effect=[b"x" * 1024, b""])
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        out_file = str(tmp_path / "segment.mp4")
        url = self._make_stream_url(clen=1000000, dur=60.0)

        with patch("managers.download_manager.urllib.request.urlopen", side_effect=mock_urlopen):
            actual_start = download_mgr._download_stream_segment_inner(
                url, 10.0, 20.0, out_file, "video"
            )

        # Estimation fallback: actual_start = max(0, start - padding)
        assert actual_start == max(0, 10.0 - download_mgr._TRIM_PADDING_BEFORE)
        assert Path(out_file).exists()

    def test_invalid_byte_range_raises(self, download_mgr, tmp_path):
        """When estimated start >= end, should raise RuntimeError."""
        from unittest.mock import MagicMock, patch

        download_mgr.is_downloading = True
        download_mgr.last_progress_time = 0

        # dur=0.001: bps = 1024/0.001 = 1024000. header_size=1024.
        # target_start=max(0, 50-30)=20, target_end=min(0.001, 60+10)=0.001
        # data_start=max(1024, int(20*1024000))=20480000 > data_end=int(0.001*1024000)=1024
        url = self._make_stream_url(clen=1024, dur=0.001)

        fake_header = b"\x00" * 1024

        def mock_urlopen(req, timeout=None):
            resp = MagicMock()
            resp.read = MagicMock(side_effect=[fake_header, b""])
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        with patch("managers.download_manager.urllib.request.urlopen", side_effect=mock_urlopen):
            with pytest.raises(RuntimeError, match="Invalid byte range"):
                download_mgr._download_stream_segment_inner(
                    url, 50.0, 60.0, str(tmp_path / "out.mp4"), "video"
                )


# ─── H-7: _verify_file_against_github ─────────────────────────────────────


class TestVerifyFileAgainstGithub:
    """Test UpdateManager._verify_file_against_github integrity checks."""

    @pytest.fixture
    def update_mgr(self, qapp):
        from concurrent.futures import ThreadPoolExecutor

        from managers.update_manager import UpdateManager

        pool = ThreadPoolExecutor(max_workers=1)
        mgr = UpdateManager(ytdlp_path="yt-dlp", thread_pool=pool)
        yield mgr
        pool.shutdown(wait=False)

    def test_matching_hashes_pass(self, update_mgr):
        """Matching git SHA-1 and SHA-256 should not raise."""
        import hashlib
        import json
        from unittest.mock import MagicMock, patch

        content = b"print('hello world')\n"
        git_sha = update_mgr._compute_git_blob_sha(content)
        sha256 = hashlib.sha256(content).hexdigest()

        # Mock GitHub API response
        api_resp = MagicMock()
        api_resp.read.return_value = json.dumps({"sha": git_sha}).encode()
        api_resp.__enter__ = MagicMock(return_value=api_resp)
        api_resp.__exit__ = MagicMock(return_value=False)

        # Mock SHA256SUMS response
        sha256sums_resp = MagicMock()
        sha256sums_resp.read.return_value = f"{sha256}  test.py\n".encode()
        sha256sums_resp.__enter__ = MagicMock(return_value=sha256sums_resp)
        sha256sums_resp.__exit__ = MagicMock(return_value=False)

        call_count = [0]

        def mock_urlopen(req, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return api_resp
            return sha256sums_resp

        release_data = {"tag_name": "v1.0"}
        headers = {"Authorization": "token fake"}

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            # Should not raise
            update_mgr._verify_file_against_github(
                "v1.0", "test.py", content, headers, release_data
            )

    def test_sha1_mismatch_raises(self, update_mgr):
        """Git blob SHA-1 mismatch should raise RuntimeError."""
        import json
        from unittest.mock import MagicMock, patch

        content = b"print('hello world')\n"

        api_resp = MagicMock()
        api_resp.read.return_value = json.dumps({"sha": "deadbeef" * 5}).encode()
        api_resp.__enter__ = MagicMock(return_value=api_resp)
        api_resp.__exit__ = MagicMock(return_value=False)

        def mock_urlopen(req, timeout=None):
            return api_resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with pytest.raises(RuntimeError, match="Integrity check failed"):
                update_mgr._verify_file_against_github(
                    "v1.0", "test.py", content, {"Authorization": "token fake"}
                )

    def test_sha256_mismatch_raises(self, update_mgr):
        """SHA-256 mismatch should raise RuntimeError."""
        import json
        from unittest.mock import MagicMock, patch

        content = b"print('hello world')\n"
        git_sha = update_mgr._compute_git_blob_sha(content)

        api_resp = MagicMock()
        api_resp.read.return_value = json.dumps({"sha": git_sha}).encode()
        api_resp.__enter__ = MagicMock(return_value=api_resp)
        api_resp.__exit__ = MagicMock(return_value=False)

        sha256sums_resp = MagicMock()
        sha256sums_resp.read.return_value = b"0000000000000000  test.py\n"
        sha256sums_resp.__enter__ = MagicMock(return_value=sha256sums_resp)
        sha256sums_resp.__exit__ = MagicMock(return_value=False)

        call_count = [0]

        def mock_urlopen(req, timeout=None):
            call_count[0] += 1
            return api_resp if call_count[0] == 1 else sha256sums_resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with pytest.raises(RuntimeError, match="SHA-256 verification failed"):
                update_mgr._verify_file_against_github(
                    "v1.0",
                    "test.py",
                    content,
                    {"Authorization": "token fake"},
                    {"tag_name": "v1.0"},
                )

    def test_missing_sha256sums_raises(self, update_mgr):
        """Missing SHA256SUMS should raise RuntimeError (mandatory abort)."""
        import json
        from unittest.mock import MagicMock, patch

        content = b"print('hello world')\n"
        git_sha = update_mgr._compute_git_blob_sha(content)

        api_resp = MagicMock()
        api_resp.read.return_value = json.dumps({"sha": git_sha}).encode()
        api_resp.__enter__ = MagicMock(return_value=api_resp)
        api_resp.__exit__ = MagicMock(return_value=False)

        call_count = [0]

        def mock_urlopen(req, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return api_resp
            raise urllib.error.HTTPError("http://example.com", 404, "Not Found", {}, None)

        import urllib.error

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with pytest.raises(RuntimeError, match="SHA256SUMS missing"):
                update_mgr._verify_file_against_github(
                    "v1.0",
                    "test.py",
                    content,
                    {"Authorization": "token fake"},
                    {"tag_name": "v1.0"},
                )


# ─── Gap 1: _http_range_read ───────────────────────────────────────────


class TestHttpRangeRead:
    """Test DownloadManager._http_range_read with mocked urllib."""

    def test_normal_read_returns_bytes(self, download_mgr):
        """Normal read should return the exact bytes from the response."""
        from unittest.mock import MagicMock, patch

        download_mgr.is_downloading = True
        download_mgr.last_progress_time = 0

        payload = b"hello world data"
        resp = MagicMock()
        resp.read = MagicMock(side_effect=[payload, b""])
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)

        with patch("managers.download_manager.urllib.request.urlopen", return_value=resp):
            result = download_mgr._http_range_read("https://example.com/video", 0, len(payload) - 1)

        assert result == payload

    def test_oversized_response_raises(self, download_mgr):
        """Response exceeding 2x expected size should raise RuntimeError."""
        from unittest.mock import MagicMock, patch

        download_mgr.is_downloading = True
        download_mgr.last_progress_time = 0

        # Expected range: 0-99 => expected_size = 100
        # Send 201 bytes (> 100*2) to trigger the guard
        oversized = b"x" * 201
        resp = MagicMock()
        resp.read = MagicMock(side_effect=[oversized, b""])
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)

        with patch("managers.download_manager.urllib.request.urlopen", return_value=resp):
            with pytest.raises(RuntimeError, match="exceeded expected size"):
                download_mgr._http_range_read("https://example.com/video", 0, 99)

    def test_cancellation_stops_reading(self, download_mgr):
        """Setting is_downloading=False should stop reading mid-stream."""
        from unittest.mock import MagicMock, patch

        download_mgr.is_downloading = False  # already cancelled
        download_mgr.last_progress_time = 0

        resp = MagicMock()
        # Should never even read because is_downloading is False on first check
        resp.read = MagicMock(side_effect=[b"data", b"more", b""])
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)

        with patch("managers.download_manager.urllib.request.urlopen", return_value=resp):
            result = download_mgr._http_range_read("https://example.com/video", 0, 999)

        # Should return empty or partial data since cancelled immediately
        assert result == b""


# ─── Gap 2: _get_stream_urls ──────────────────────────────────────────


class TestGetStreamUrls:
    """Test DownloadManager._get_stream_urls with mocked subprocess."""

    def test_two_url_output(self, download_mgr):
        """Two-line output should return (video_url, audio_url)."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://video.url\nhttps://audio.url\n"
        mock_result.stderr = ""

        with patch("managers.download_manager.subprocess.run", return_value=mock_result):
            video, audio = download_mgr._get_stream_urls(
                "https://youtu.be/test", "bestvideo+bestaudio"
            )

        assert video == "https://video.url"
        assert audio == "https://audio.url"

    def test_one_url_output(self, download_mgr):
        """Single-line output should return (url, None)."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://combined.url\n"
        mock_result.stderr = ""

        with patch("managers.download_manager.subprocess.run", return_value=mock_result):
            video, audio = download_mgr._get_stream_urls("https://youtu.be/test", "best")

        assert video == "https://combined.url"
        assert audio is None

    def test_nonzero_exit_raises(self, download_mgr):
        """Non-zero exit code should raise RuntimeError."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ERROR: video not found"

        with patch("managers.download_manager.subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="Failed to get stream URLs"):
                download_mgr._get_stream_urls("https://youtu.be/test", "bestvideo+bestaudio")


# ─── Gap 3: download_local_file ───────────────────────────────────────


class TestDownloadLocalFile:
    """Test DownloadManager.download_local_file routing and command building."""

    @staticmethod
    def _make_ui_state(**overrides):
        state = {
            "quality": "720",
            "trim_enabled": False,
            "audio_only": False,
            "keep_below_10mb": False,
            "filename": "",
            "volume_raw": 100,
            "download_path": "/tmp",
            "speed_limit": None,
            "start_time": "0",
            "end_time": "60",
        }
        state.update(overrides)
        return state

    def test_audio_only_builds_correct_command(self, download_mgr, tmp_path):
        """Audio-only local file should build ffmpeg command with mp3 output."""
        from unittest.mock import MagicMock, patch

        download_mgr.is_downloading = True
        download_mgr.video_duration = 120

        # Create a mock audio file path
        audio_file = str(tmp_path / "test.mp3")

        ui_state = self._make_ui_state(quality="none (Audio only)", audio_only=True)
        captured_cmd = []

        mock_stdout = MagicMock()
        mock_stdout.__iter__ = MagicMock(return_value=iter([]))
        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        mock_proc.stderr = MagicMock(__iter__=MagicMock(return_value=iter([])))
        mock_proc.wait.return_value = None
        mock_proc.returncode = 0

        def capture_popen(cmd, **kwargs):
            captured_cmd.extend(cmd)
            return mock_proc

        with patch("managers.download_manager.subprocess.Popen", side_effect=capture_popen):
            download_mgr.download_local_file(audio_file, ui_state)

        assert "ffmpeg" in captured_cmd[0]
        assert "-vn" in captured_cmd
        assert "libmp3lame" in captured_cmd
        assert audio_file in captured_cmd

    def test_video_with_trim_calls_encoding(self, download_mgr, tmp_path):
        """Video path with trim should include -ss and -to in the ffmpeg command."""
        from unittest.mock import MagicMock, patch

        download_mgr.is_downloading = True
        download_mgr.video_duration = 120

        video_file = str(tmp_path / "test.mp4")
        ui_state = self._make_ui_state(
            quality="720",
            trim_enabled=True,
            start_time="10",
            end_time="30",
        )

        captured_cmd = []

        mock_stdout = MagicMock()
        mock_stdout.__iter__ = MagicMock(return_value=iter([]))
        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        mock_proc.stderr = MagicMock(__iter__=MagicMock(return_value=iter([])))
        mock_proc.wait.return_value = None
        mock_proc.returncode = 0

        def capture_popen(cmd, **kwargs):
            captured_cmd.extend(cmd)
            return mock_proc

        with patch("managers.download_manager.subprocess.Popen", side_effect=capture_popen):
            download_mgr.download_local_file(video_file, ui_state)

        assert "-ss" in captured_cmd
        assert "-to" in captured_cmd
        ss_idx = captured_cmd.index("-ss")
        assert captured_cmd[ss_idx + 1] == "10"
        to_idx = captured_cmd.index("-to")
        assert captured_cmd[to_idx + 1] == "30"

    def test_10mb_routes_to_size_constrained(self, download_mgr, tmp_path):
        """keep_below_10mb should route to encoding.size_constrained_encode."""
        from unittest.mock import patch

        download_mgr.is_downloading = True
        download_mgr.video_duration = 120

        video_file = str(tmp_path / "test.mp4")
        ui_state = self._make_ui_state(quality="720", keep_below_10mb=True)

        with patch.object(
            download_mgr.encoding, "size_constrained_encode", return_value=True
        ) as mock_encode:
            download_mgr.download_local_file(video_file, ui_state)

        mock_encode.assert_called_once()


# ─── Gap 4: _get_expected_sha256 ──────────────────────────────────────


class TestGetExpectedSha256:
    """Test UpdateManager._get_expected_sha256 SHA256SUMS parsing."""

    @pytest.fixture
    def update_mgr(self, qapp):
        from concurrent.futures import ThreadPoolExecutor

        from managers.update_manager import UpdateManager

        pool = ThreadPoolExecutor(max_workers=1)
        mgr = UpdateManager(ytdlp_path="yt-dlp", thread_pool=pool)
        yield mgr
        pool.shutdown(wait=False)

    def test_matching_filename_returns_hash(self, update_mgr):
        """Should return the hash for a matching filename."""
        from unittest.mock import MagicMock, patch

        sha256sums = "abc123def456  downloader_pyqt6.py\n789fed012345  constants.py\n"
        resp = MagicMock()
        resp.read.return_value = sha256sums.encode()
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=resp):
            result = update_mgr._get_expected_sha256({"tag_name": "v1.0"}, "constants.py", {})

        assert result == "789fed012345"

    def test_nonmatching_filename_returns_none(self, update_mgr):
        """Should return None when the filename is not in SHA256SUMS."""
        from unittest.mock import MagicMock, patch

        sha256sums = "abc123def456  downloader_pyqt6.py\n"
        resp = MagicMock()
        resp.read.return_value = sha256sums.encode()
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=resp):
            result = update_mgr._get_expected_sha256({"tag_name": "v2.0"}, "nonexistent.py", {})

        assert result is None

    def test_network_error_returns_none(self, update_mgr):
        """Network errors should return None gracefully."""
        import urllib.error
        from unittest.mock import patch

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            result = update_mgr._get_expected_sha256({"tag_name": "v3.0"}, "constants.py", {})

        assert result is None

    def test_caching_prevents_second_fetch(self, update_mgr):
        """Second call with same tag should use cached SHA256SUMS, not fetch again."""
        from unittest.mock import MagicMock, patch

        sha256sums = "abc123  test.py\ndef456  other.py\n"
        resp = MagicMock()
        resp.read.return_value = sha256sums.encode()
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=resp) as mock_urlopen:
            r1 = update_mgr._get_expected_sha256({"tag_name": "v4.0"}, "test.py", {})
            r2 = update_mgr._get_expected_sha256({"tag_name": "v4.0"}, "other.py", {})

        assert r1 == "abc123"
        assert r2 == "def456"
        # urlopen should only be called once (cached for second call)
        assert mock_urlopen.call_count == 1


# ─── Gap 5: _check_for_updates ────────────────────────────────────────


class TestCheckForUpdates:
    """Test UpdateManager._check_for_updates with mocked network."""

    @pytest.fixture
    def update_mgr(self, qapp):
        from concurrent.futures import ThreadPoolExecutor

        from managers.update_manager import UpdateManager

        pool = ThreadPoolExecutor(max_workers=1)
        mgr = UpdateManager(ytdlp_path="yt-dlp", thread_pool=pool)
        yield mgr
        pool.shutdown(wait=False)

    def test_newer_version_emits_signal(self, update_mgr):
        """A newer version should emit sig_show_update_dialog."""
        import json
        from unittest.mock import MagicMock, patch

        spy = MagicMock()
        update_mgr.sig_show_update_dialog.connect(spy)

        api_data = {"tag_name": "v99.99"}
        resp = MagicMock()
        resp.read.return_value = json.dumps(api_data).encode()
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=resp):
            update_mgr._check_for_updates(silent=True)

        spy.assert_called_once()
        assert spy.call_args[0][0] == "99.99"

    def test_same_version_silent_does_nothing(self, update_mgr):
        """Same version in silent mode should not emit update or messagebox signals."""
        import json
        from unittest.mock import MagicMock, patch

        from constants import APP_VERSION

        update_spy = MagicMock()
        update_mgr.sig_show_update_dialog.connect(update_spy)
        msgbox_spy = MagicMock()
        update_mgr.sig_show_messagebox.connect(msgbox_spy)

        api_data = {"tag_name": f"v{APP_VERSION}"}
        resp = MagicMock()
        resp.read.return_value = json.dumps(api_data).encode()
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)

        # Also mock yt-dlp version check
        ytdlp_resp = MagicMock()
        ytdlp_data = {"tag_name": "2026.01.01"}
        ytdlp_resp.read.return_value = json.dumps(ytdlp_data).encode()
        ytdlp_resp.__enter__ = MagicMock(return_value=ytdlp_resp)
        ytdlp_resp.__exit__ = MagicMock(return_value=False)

        call_count = [0]

        def mock_urlopen(req, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return resp
            return ytdlp_resp

        with (
            patch("urllib.request.urlopen", side_effect=mock_urlopen),
            patch.object(update_mgr, "_get_ytdlp_version", return_value="2026.01.01"),
        ):
            update_mgr._check_for_updates(silent=True)

        update_spy.assert_not_called()
        msgbox_spy.assert_not_called()

    def test_network_error_handled_gracefully(self, update_mgr):
        """Network error should not raise, and in silent mode no messagebox."""
        import urllib.error
        from unittest.mock import MagicMock, patch

        msgbox_spy = MagicMock()
        update_mgr.sig_show_messagebox.connect(msgbox_spy)

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("no network"),
        ):
            # Should not raise
            update_mgr._check_for_updates(silent=True)

        # In silent mode, no messagebox
        msgbox_spy.assert_not_called()


# ─── Gap 6: fetch_video_duration ──────────────────────────────────────


class TestFetchVideoDuration:
    """Test TrimmingManager.fetch_video_duration parsing logic."""

    @pytest.fixture
    def trimming_mgr(self, qapp):
        from managers.trimming_manager import TrimmingManager

        mgr = TrimmingManager(
            ytdlp_path="yt-dlp",
            ffmpeg_path="ffmpeg",
            ffprobe_path="ffprobe",
            temp_dir="/tmp",
        )
        return mgr

    def test_hms_format(self, trimming_mgr):
        """H:MM:SS format should be parsed correctly."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "1:30:45\nTest Video Title\n"
        mock_result.stderr = ""

        spy = MagicMock()
        trimming_mgr.sig_duration_fetched.connect(spy)

        with patch(
            "managers.trimming_manager.retry_network_operation",
            return_value=mock_result,
        ):
            trimming_mgr.fetch_video_duration("https://youtu.be/test")

        assert trimming_mgr.video_duration == 5445  # 1*3600 + 30*60 + 45
        spy.assert_called_once_with(5445, "Test Video Title")

    def test_seconds_only_format(self, trimming_mgr):
        """Single-number format (seconds only) should be parsed."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "120\nShort Video\n"
        mock_result.stderr = ""

        spy = MagicMock()
        trimming_mgr.sig_duration_fetched.connect(spy)

        with patch(
            "managers.trimming_manager.retry_network_operation",
            return_value=mock_result,
        ):
            trimming_mgr.fetch_video_duration("https://youtu.be/test")

        assert trimming_mgr.video_duration == 120
        spy.assert_called_once_with(120, "Short Video")

    def test_mm_ss_format(self, trimming_mgr):
        """MM:SS format should be parsed correctly."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "5:30\nSome Title\n"
        mock_result.stderr = ""

        spy = MagicMock()
        trimming_mgr.sig_duration_fetched.connect(spy)

        with patch(
            "managers.trimming_manager.retry_network_operation",
            return_value=mock_result,
        ):
            trimming_mgr.fetch_video_duration("https://youtu.be/test")

        assert trimming_mgr.video_duration == 330  # 5*60 + 30

    def test_over_24h_capped(self, trimming_mgr):
        """Duration >24h should be capped to 86400."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "25:00:00\nLong Video\n"
        mock_result.stderr = ""

        spy = MagicMock()
        trimming_mgr.sig_duration_fetched.connect(spy)

        with patch(
            "managers.trimming_manager.retry_network_operation",
            return_value=mock_result,
        ):
            trimming_mgr.fetch_video_duration("https://youtu.be/test")

        assert trimming_mgr.video_duration == 86400

    def test_error_emits_messagebox(self, trimming_mgr):
        """Non-zero return code should emit error messagebox."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ERROR: video unavailable"

        msgbox_spy = MagicMock()
        trimming_mgr.sig_show_messagebox.connect(msgbox_spy)

        with patch(
            "managers.trimming_manager.retry_network_operation",
            return_value=mock_result,
        ):
            trimming_mgr.fetch_video_duration("https://youtu.be/test")

        msgbox_spy.assert_called_once()
        assert msgbox_spy.call_args[0][0] == "error"

    def test_timeout_handled(self, trimming_mgr):
        """TimeoutExpired should be caught and emit error signals."""
        import subprocess
        from unittest.mock import MagicMock, patch

        msgbox_spy = MagicMock()
        trimming_mgr.sig_show_messagebox.connect(msgbox_spy)

        with patch(
            "managers.trimming_manager.retry_network_operation",
            side_effect=subprocess.TimeoutExpired("yt-dlp", 30),
        ):
            trimming_mgr.fetch_video_duration("https://youtu.be/test")

        msgbox_spy.assert_called_once()
        assert "timed out" in msgbox_spy.call_args[0][2].lower()


# ─── Gap 7: extract_frame ─────────────────────────────────────────────


class TestExtractFrame:
    """Test TrimmingManager.extract_frame with mocked subprocess."""

    @pytest.fixture
    def trimming_mgr(self, qapp):
        import collections
        import threading

        from managers.trimming_manager import TrimmingManager

        mgr = TrimmingManager(
            ytdlp_path="yt-dlp",
            ffmpeg_path="ffmpeg",
            ffprobe_path="ffprobe",
            temp_dir="/tmp",
        )
        mgr.preview_cache = collections.OrderedDict()
        mgr.preview_lock = threading.Lock()
        return mgr

    def test_cache_hit_returns_without_subprocess(self, trimming_mgr, tmp_path):
        """Cached frame should be returned immediately without calling subprocess."""
        from unittest.mock import patch

        cached_path = str(tmp_path / "frame_10.jpg")
        Path(cached_path).write_text("fake image")
        trimming_mgr.current_video_url = "https://youtu.be/test"
        trimming_mgr._cache_preview_frame(10, cached_path)

        with patch("managers.trimming_manager.subprocess.run") as mock_run:
            result = trimming_mgr.extract_frame(10)

        assert result == cached_path
        mock_run.assert_not_called()

    def test_cache_miss_calls_subprocess(self, trimming_mgr, tmp_path):
        """Cache miss for a local file should call subprocess to extract frame."""
        import os
        from unittest.mock import MagicMock, patch

        local_video = str(tmp_path / "video.mp4")
        trimming_mgr.current_video_url = local_video

        expected_frame = os.path.join("/tmp", "frame_5.jpg")

        mock_result = MagicMock()
        mock_result.returncode = 0

        def fake_retry(fn, desc):
            return fn()

        def mock_run(cmd, **kwargs):
            # Create the output file so extract_frame sees it
            Path(expected_frame).parent.mkdir(parents=True, exist_ok=True)
            Path(expected_frame).write_text("fake frame")
            return mock_result

        with (
            patch("managers.trimming_manager.retry_network_operation", side_effect=fake_retry),
            patch("managers.trimming_manager.subprocess.run", side_effect=mock_run),
        ):
            result = trimming_mgr.extract_frame(5)

        assert result == expected_frame
        # Clean up
        if os.path.exists(expected_frame):
            os.unlink(expected_frame)

    def test_no_url_returns_none(self, trimming_mgr):
        """Should return None when no video URL is set."""
        trimming_mgr.current_video_url = None
        result = trimming_mgr.extract_frame(10)
        assert result is None


# ─── Gap 8: upload_to_catbox ──────────────────────────────────────────


class TestUploadToCatbox:
    """Test UploadManager.upload_to_catbox success and error paths."""

    @pytest.fixture
    def upload_mgr(self, qapp):
        from concurrent.futures import ThreadPoolExecutor

        from managers.upload_manager import UploadManager

        pool = ThreadPoolExecutor(max_workers=1)
        m = UploadManager(thread_pool=pool)
        yield m
        pool.shutdown(wait=False)

    def test_success_emits_signals(self, upload_mgr, tmp_path):
        """Successful upload should emit upload_complete signal."""
        from unittest.mock import MagicMock, patch

        test_file = tmp_path / "video.mp4"
        test_file.write_text("data")
        upload_mgr.last_output_file = str(test_file)

        complete_spy = MagicMock()
        upload_mgr.sig_upload_complete.connect(complete_spy)

        mock_client = MagicMock()
        mock_client.upload.return_value = "https://files.catbox.moe/abc123.mp4"
        upload_mgr.catbox_client = mock_client

        with patch.object(upload_mgr, "save_upload_link"):
            upload_mgr.upload_to_catbox()

        complete_spy.assert_called_once_with("https://files.catbox.moe/abc123.mp4", "video.mp4")
        assert upload_mgr.is_uploading is False

    def test_exception_emits_error(self, upload_mgr, tmp_path):
        """Upload exception should emit error messagebox signal."""
        from unittest.mock import MagicMock

        test_file = tmp_path / "video.mp4"
        test_file.write_text("data")
        upload_mgr.last_output_file = str(test_file)

        error_spy = MagicMock()
        upload_mgr.sig_show_messagebox.connect(error_spy)
        status_spy = MagicMock()
        upload_mgr.sig_upload_status.connect(status_spy)

        mock_client = MagicMock()
        mock_client.upload.side_effect = Exception("network timeout")
        upload_mgr.catbox_client = mock_client

        upload_mgr.upload_to_catbox()

        error_spy.assert_called_once()
        assert error_spy.call_args[0][0] == "error"
        assert "network timeout" in error_spy.call_args[0][2]
        status_spy.assert_called()
        assert upload_mgr.is_uploading is False

    def test_no_file_returns_early(self, upload_mgr):
        """No last_output_file should return without doing anything."""
        from unittest.mock import MagicMock

        upload_mgr.last_output_file = None
        complete_spy = MagicMock()
        upload_mgr.sig_upload_complete.connect(complete_spy)

        upload_mgr.upload_to_catbox()

        complete_spy.assert_not_called()


# ─── Gap 9: process_uploader_queue / start_queue_upload ────────────────


class TestUploaderQueue:
    """Test UploadManager queue processing flow."""

    @pytest.fixture
    def upload_mgr(self, qapp):
        from concurrent.futures import ThreadPoolExecutor

        from managers.upload_manager import UploadManager

        pool = ThreadPoolExecutor(max_workers=1)
        m = UploadManager(thread_pool=pool)
        yield m
        pool.shutdown(wait=False)

    def test_empty_queue_rejected(self, upload_mgr):
        """start_queue_upload should reject an empty queue."""
        upload_mgr.uploader_file_queue = []
        ok, msg = upload_mgr.start_queue_upload()
        assert ok is False
        assert "No files" in msg

    def test_processes_all_items(self, upload_mgr):
        """process_uploader_queue should iterate all queued items."""
        from unittest.mock import MagicMock, patch

        upload_mgr.add_to_queue("/tmp/a.mp4")
        upload_mgr.add_to_queue("/tmp/b.mp4")
        upload_mgr.uploader_is_uploading = True

        done_spy = MagicMock()
        upload_mgr.sig_uploader_queue_done.connect(done_spy)

        with patch.object(upload_mgr, "upload_single_file", return_value=True) as mock_upload:
            upload_mgr.process_uploader_queue()

        assert mock_upload.call_count == 2
        done_spy.assert_called_once_with(2)

    def test_stop_flag_stops_iteration(self, upload_mgr):
        """Setting uploader_is_uploading=False should stop queue processing."""
        from unittest.mock import MagicMock, patch

        upload_mgr.add_to_queue("/tmp/a.mp4")
        upload_mgr.add_to_queue("/tmp/b.mp4")
        upload_mgr.add_to_queue("/tmp/c.mp4")
        upload_mgr.uploader_is_uploading = True

        call_count = [0]

        def upload_and_stop(path):
            call_count[0] += 1
            if call_count[0] >= 1:
                upload_mgr.uploader_is_uploading = False
            return True

        done_spy = MagicMock()
        upload_mgr.sig_uploader_queue_done.connect(done_spy)

        with patch.object(upload_mgr, "upload_single_file", side_effect=upload_and_stop):
            upload_mgr.process_uploader_queue()

        # Should have processed only 1 item before the stop flag was checked
        assert call_count[0] == 1
        done_spy.assert_called_once_with(1)

    def test_start_queue_upload_marks_uploading(self, upload_mgr):
        """start_queue_upload should set uploader_is_uploading and return True."""
        upload_mgr.add_to_queue("/tmp/test.mp4")
        ok, msg = upload_mgr.start_queue_upload()
        assert ok is True
        assert msg == ""
        assert upload_mgr.uploader_is_uploading is True

    def test_start_queue_while_already_uploading(self, upload_mgr):
        """Starting upload while already uploading should return False."""
        upload_mgr.add_to_queue("/tmp/test.mp4")
        upload_mgr.uploader_is_uploading = True
        ok, msg = upload_mgr.start_queue_upload()
        assert ok is False


# ─── Gap 10: encode_single_pass / encode_two_pass ──────────────────────


class TestEncodeCommands:
    """Test encode_single_pass and encode_two_pass command construction."""

    def _make_cb(self):
        import threading
        from unittest.mock import MagicMock

        from managers.encoding import EncodeCallbacks

        return EncodeCallbacks(
            on_progress=MagicMock(),
            on_status=MagicMock(),
            is_cancelled=lambda: False,
            process_lock=threading.Lock(),
            set_process=MagicMock(),
            on_heartbeat=MagicMock(),
        )

    def test_single_pass_includes_target_bitrate(self):
        """encode_single_pass command should contain the target bitrate."""
        from unittest.mock import patch

        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder="h264_nvenc")
        cb = self._make_cb()
        captured_cmd = []

        def capture_run(cmd, duration, prefix, cb_arg):
            captured_cmd.extend(cmd)
            return True

        with patch.object(enc, "run_ffmpeg_with_progress", side_effect=capture_run):
            enc.encode_single_pass("input.mp4", "output.mp4", 2000000, 60.0, cb)

        assert "-b:v" in captured_cmd
        assert "2000000" in captured_cmd or str(2000000) in captured_cmd

    def test_two_pass_includes_passlog(self):
        """encode_two_pass should include -passlogfile in both passes."""
        from unittest.mock import patch

        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder=None)
        cb = self._make_cb()
        captured_cmds = []

        def capture_run(cmd, duration, prefix, cb_arg):
            captured_cmds.append(list(cmd))
            return True

        with patch.object(enc, "run_ffmpeg_with_progress", side_effect=capture_run):
            enc.encode_two_pass("input.mp4", "output.mp4", 1500000, 60.0, cb)

        assert len(captured_cmds) == 2
        # Both passes should have -passlogfile
        assert "-passlogfile" in captured_cmds[0]
        assert "-passlogfile" in captured_cmds[1]
        # Pass 1 should have -pass 1, pass 2 should have -pass 2
        assert "1" in captured_cmds[0][captured_cmds[0].index("-pass") + 1]
        assert "2" in captured_cmds[1][captured_cmds[1].index("-pass") + 1]

    def test_single_pass_trim_args(self):
        """Trim args (-ss, -to) should be included when start/end times are provided."""
        from unittest.mock import patch

        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder="h264_nvenc")
        cb = self._make_cb()
        captured_cmd = []

        def capture_run(cmd, duration, prefix, cb_arg):
            captured_cmd.extend(cmd)
            return True

        with patch.object(enc, "run_ffmpeg_with_progress", side_effect=capture_run):
            enc.encode_single_pass(
                "input.mp4",
                "output.mp4",
                2000000,
                60.0,
                cb,
                start_time=10.0,
                end_time=70.0,
            )

        assert "-ss" in captured_cmd
        assert "-to" in captured_cmd
        ss_idx = captured_cmd.index("-ss")
        assert captured_cmd[ss_idx + 1] == str(10.0)
        to_idx = captured_cmd.index("-to")
        assert captured_cmd[to_idx + 1] == str(70.0)

    def test_two_pass_trim_args(self):
        """encode_two_pass should include -ss/-to in both passes when provided."""
        from unittest.mock import patch

        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder=None)
        cb = self._make_cb()
        captured_cmds = []

        def capture_run(cmd, duration, prefix, cb_arg):
            captured_cmds.append(list(cmd))
            return True

        with patch.object(enc, "run_ffmpeg_with_progress", side_effect=capture_run):
            enc.encode_two_pass(
                "input.mp4",
                "output.mp4",
                1500000,
                60.0,
                cb,
                start_time=5.0,
                end_time=35.0,
            )

        for cmd in captured_cmds:
            assert "-ss" in cmd
            assert "-to" in cmd

    def test_single_pass_no_trim_without_times(self):
        """Without start/end times, -ss and -to should not appear."""
        from unittest.mock import patch

        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder="h264_nvenc")
        cb = self._make_cb()
        captured_cmd = []

        def capture_run(cmd, duration, prefix, cb_arg):
            captured_cmd.extend(cmd)
            return True

        with patch.object(enc, "run_ffmpeg_with_progress", side_effect=capture_run):
            enc.encode_single_pass(
                "input.mp4",
                "output.mp4",
                2000000,
                60.0,
                cb,
            )

        assert "-ss" not in captured_cmd
        assert "-to" not in captured_cmd

    def test_two_pass_volume_multiplier(self):
        """Volume multiplier should appear in pass 2 only (pass 1 has -an)."""
        from unittest.mock import patch

        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder=None)
        cb = self._make_cb()
        captured_cmds = []

        def capture_run(cmd, duration, prefix, cb_arg):
            captured_cmds.append(list(cmd))
            return True

        with patch.object(enc, "run_ffmpeg_with_progress", side_effect=capture_run):
            enc.encode_two_pass(
                "input.mp4",
                "output.mp4",
                1500000,
                60.0,
                cb,
                volume_multiplier=0.5,
            )

        # Pass 1 should have -an (no audio)
        assert "-an" in captured_cmds[0]
        # Pass 2 should have volume filter
        pass2_str = " ".join(captured_cmds[1])
        assert "volume=0.5" in pass2_str


# ─── Audit 4: _download_stream_segment_inner error paths ─────────────────


class TestDownloadStreamSegmentInnerErrors:
    """Error-path tests for _download_stream_segment_inner (TQ-1)."""

    def _make_url(self, clen=1000000, dur=60.0):
        return f"https://rr.google.com/videoplayback?clen={clen}&dur={dur}"

    def test_network_timeout_propagates(self, download_mgr, tmp_path):
        """urllib timeout during header fetch should propagate as-is."""
        from unittest.mock import patch
        from urllib.error import URLError

        download_mgr.is_downloading = True
        download_mgr.last_progress_time = 0
        url = self._make_url()

        with patch(
            "managers.download_manager.urllib.request.urlopen",
            side_effect=URLError("timed out"),
        ):
            with pytest.raises(URLError):
                download_mgr._download_stream_segment_inner(
                    url, 10.0, 20.0, str(tmp_path / "out.mp4"), "video"
                )

    @pytest.mark.xfail(reason="Mock urlopen context manager interaction flaky in CI")
    def test_cancellation_during_data_download(self, download_mgr, tmp_path):
        """Setting is_downloading=False mid-download should return early."""
        from unittest.mock import MagicMock, patch

        download_mgr.is_downloading = True
        download_mgr.last_progress_time = 0

        call_count = [0]

        def mock_urlopen(req, timeout=None):
            call_count[0] += 1
            resp = MagicMock()
            if call_count[0] == 1:
                resp.read = MagicMock(side_effect=[b"\x00" * 1024, b""])
            else:
                # Cancel during data download
                download_mgr.is_downloading = False
                resp.read = MagicMock(side_effect=[b"x" * 1024, b""])
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        url = self._make_url(clen=1000000, dur=60.0)
        out = str(tmp_path / "out.mp4")
        with patch("managers.download_manager.urllib.request.urlopen", side_effect=mock_urlopen):
            result = download_mgr._download_stream_segment_inner(url, 10.0, 20.0, out, "video")

        # Should return the actual_start value (cancellation returns early, not exception)
        assert isinstance(result, float)


# ─── Audit 4: _download_audio_trimmed error handling ─────────────────────


class TestDownloadAudioTrimmedErrors:
    """Error-path tests for _download_audio_trimmed (TQ-2)."""

    def test_stream_urls_failure_raises(self, download_mgr):
        """When _get_stream_urls fails, exception should propagate."""
        from unittest.mock import patch

        download_mgr.is_downloading = True

        with patch.object(download_mgr, "_get_stream_urls", side_effect=RuntimeError("no streams")):
            with pytest.raises(RuntimeError, match="no streams"):
                download_mgr._download_audio_trimmed(
                    "https://www.youtube.com/watch?v=test", 0, 10, "/tmp/out.mp3"
                )

    def test_cancellation_after_segment_download(self, download_mgr, tmp_path):
        """If cancelled after segment download, should return False."""
        from unittest.mock import patch

        download_mgr.is_downloading = True

        def fake_segment(*args, **kwargs):
            download_mgr.is_downloading = False
            return 0.0

        with (
            patch.object(
                download_mgr,
                "_get_stream_urls",
                return_value=("https://example.com/audio.m4a", None),
            ),
            patch.object(download_mgr, "_download_stream_segment", side_effect=fake_segment),
        ):
            result = download_mgr._download_audio_trimmed(
                "https://www.youtube.com/watch?v=test",
                0,
                10,
                str(tmp_path / "out.mp3"),
            )

        assert result is False

    def test_ffmpeg_failure_returns_false(self, download_mgr, tmp_path):
        """When ffmpeg encoding fails, should return False."""
        from unittest.mock import patch

        download_mgr.is_downloading = True

        with (
            patch.object(
                download_mgr,
                "_get_stream_urls",
                return_value=("https://example.com/audio.m4a", None),
            ),
            patch.object(download_mgr, "_download_stream_segment", return_value=0.0),
            patch.object(download_mgr.encoding, "run_ffmpeg_with_progress", return_value=False),
        ):
            result = download_mgr._download_audio_trimmed(
                "https://www.youtube.com/watch?v=test",
                0,
                10,
                str(tmp_path / "out.mp3"),
            )

        assert result is False


# ─── Audit 4: Strengthen weak test assertions (TQ-11) ───────────────────


class TestUploaderQueueAssertions:
    """Strengthened assertions for upload queue tests (TQ-11)."""

    @pytest.fixture
    def upload_mgr(self, qapp):
        from concurrent.futures import ThreadPoolExecutor

        from managers.upload_manager import UploadManager

        pool = ThreadPoolExecutor(max_workers=1)
        m = UploadManager(thread_pool=pool)
        yield m
        pool.shutdown(wait=False)

    def test_processes_items_with_correct_paths(self, upload_mgr):
        """process_uploader_queue should call upload_single_file with correct paths."""
        from unittest.mock import MagicMock, patch

        upload_mgr.add_to_queue("/tmp/a.mp4")
        upload_mgr.add_to_queue("/tmp/b.mp4")
        upload_mgr.uploader_is_uploading = True

        done_spy = MagicMock()
        upload_mgr.sig_uploader_queue_done.connect(done_spy)

        with patch.object(upload_mgr, "upload_single_file", return_value=True) as mock_upload:
            upload_mgr.process_uploader_queue()

        assert mock_upload.call_count == 2
        paths = [call[0][0] for call in mock_upload.call_args_list]
        assert "/tmp/a.mp4" in paths
        assert "/tmp/b.mp4" in paths
        done_spy.assert_called_once_with(2)

    def test_start_queue_upload_sets_flag_and_submits(self, upload_mgr):
        """start_queue_upload should set flag to True and submit to thread pool."""
        upload_mgr.add_to_queue("/tmp/test.mp4")
        ok, msg = upload_mgr.start_queue_upload()
        assert ok is True
        assert upload_mgr.uploader_is_uploading is True
        assert len(upload_mgr.uploader_file_queue) == 1


class TestProgressStallDetection:
    """Test _monitor_download_timeout progress stall (not just absolute timeout)."""

    def test_progress_stall_normal_mode(self, download_mgr):
        """Stall detection fires at DOWNLOAD_PROGRESS_TIMEOUT (600s) in normal mode."""
        from unittest.mock import patch

        download_mgr.is_downloading = True
        download_mgr._shutting_down = False
        download_mgr._download_has_progress = True
        download_mgr._trim_download_active = False
        download_mgr.download_start_time = 1000.0
        # Progress was 601 seconds ago (exceeds 600s threshold)
        download_mgr.last_progress_time = 1000.0

        def fake_time():
            return 1000.0 + 601

        with (
            patch("managers.download_manager.time.sleep"),
            patch("managers.download_manager.time.time", side_effect=fake_time),
            patch.object(download_mgr, "_timeout_download") as mock_timeout,
        ):
            download_mgr._monitor_download_timeout()

        mock_timeout.assert_called_once()
        assert "stall" in mock_timeout.call_args[0][0].lower()

    def test_progress_stall_trim_uses_longer_timeout(self, download_mgr):
        """Trim mode uses DOWNLOAD_PROGRESS_TIMEOUT_TRIM (1200s), not 600s."""
        from unittest.mock import patch

        download_mgr.is_downloading = True
        download_mgr._shutting_down = False
        download_mgr._download_has_progress = True
        download_mgr._trim_download_active = True
        download_mgr.download_start_time = 1000.0
        # 800s since progress — exceeds normal (600s) but NOT trim (1200s)
        download_mgr.last_progress_time = 1000.0

        call_count = 0

        def fake_time():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return 1000.0 + 800  # within trim timeout
            # On 3rd call, exceed absolute timeout to break loop
            return 1000.0 + 3601

        with (
            patch("managers.download_manager.time.sleep"),
            patch("managers.download_manager.time.time", side_effect=fake_time),
            patch.object(download_mgr, "_timeout_download") as mock_timeout,
        ):
            download_mgr._monitor_download_timeout()

        # Should have been called for absolute timeout, NOT stall
        mock_timeout.assert_called_once()
        assert "60 min" in mock_timeout.call_args[0][0].lower()


class TestDoTrimmedDownload:
    """Test _do_trimmed_download merge failure and cancellation paths."""

    def test_cancel_after_video_download(self, download_mgr):
        """Cancellation after video segment returns False without downloading audio."""
        from unittest.mock import patch

        download_mgr.is_downloading = False  # cancelled

        with (
            patch.object(download_mgr, "_get_stream_urls", return_value=("http://v", "http://a")),
            patch.object(download_mgr, "_download_stream_segment", return_value=0.0),
        ):
            result = download_mgr._do_trimmed_download(
                "http://yt", "best", 10.0, 20.0, "/tmp/out.mp4", 1.0, True, "/tmp/td"
            )

        assert result is False

    def test_cancel_after_audio_download(self, download_mgr):
        """Cancellation after audio segment returns False without merging."""
        from unittest.mock import patch

        call_count = 0

        def fake_download_segment(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                download_mgr.is_downloading = False
            return 0.0

        download_mgr.is_downloading = True

        with (
            patch.object(download_mgr, "_get_stream_urls", return_value=("http://v", "http://a")),
            patch.object(
                download_mgr, "_download_stream_segment", side_effect=fake_download_segment
            ),
            patch.object(download_mgr, "update_status"),
        ):
            result = download_mgr._do_trimmed_download(
                "http://yt", "best", 10.0, 20.0, "/tmp/out.mp4", 1.0, True, "/tmp/td"
            )

        assert result is False
        assert call_count == 2

    def test_merge_failure_returns_false(self, download_mgr):
        """Merge command returning non-zero should return False."""
        from unittest.mock import MagicMock, patch

        download_mgr.is_downloading = True
        mock_merge = MagicMock()
        mock_merge.returncode = 1
        mock_merge.stderr = "merge error"

        with (
            patch.object(download_mgr, "_get_stream_urls", return_value=("http://v", "http://a")),
            patch.object(download_mgr, "_download_stream_segment", return_value=5.0),
            patch.object(download_mgr, "update_status"),
            patch("managers.download_manager.subprocess.run", return_value=mock_merge),
        ):
            result = download_mgr._do_trimmed_download(
                "http://yt", "best", 10.0, 20.0, "/tmp/out.mp4", 1.0, True, "/tmp/td"
            )

        assert result is False

    def test_volume_changed_triggers_audio_reencode(self, download_mgr):
        """Volume multiplier != 1.0 with copy_codec=False should add volume filter."""
        from unittest.mock import patch

        download_mgr.is_downloading = True

        captured_cmd = []

        def fake_ffmpeg(cmd, *args, **kwargs):
            captured_cmd.extend(cmd)
            return True

        with (
            patch.object(download_mgr, "_get_stream_urls", return_value=("http://v", None)),
            patch.object(download_mgr, "_download_stream_segment", return_value=5.0),
            patch.object(download_mgr, "update_status"),
            patch.object(
                download_mgr.encoding, "run_ffmpeg_with_progress", side_effect=fake_ffmpeg
            ),
            patch.object(download_mgr, "_make_encode_callbacks", return_value={}),
        ):
            download_mgr._do_trimmed_download(
                "http://yt", "best", 10.0, 20.0, "/tmp/out.mp4", 2.0, False, "/tmp/td"
            )

        assert "-af" in captured_cmd
        assert "volume=2.0" in captured_cmd
        assert "-c:v" in captured_cmd
        assert "copy" in captured_cmd

    def test_copy_codec_path(self, download_mgr):
        """copy_codec=True should use -c copy without audio filter."""
        from unittest.mock import patch

        download_mgr.is_downloading = True

        captured_cmd = []

        def fake_ffmpeg(cmd, *args, **kwargs):
            captured_cmd.extend(cmd)
            return True

        with (
            patch.object(download_mgr, "_get_stream_urls", return_value=("http://v", None)),
            patch.object(download_mgr, "_download_stream_segment", return_value=5.0),
            patch.object(download_mgr, "update_status"),
            patch.object(
                download_mgr.encoding, "run_ffmpeg_with_progress", side_effect=fake_ffmpeg
            ),
            patch.object(download_mgr, "_make_encode_callbacks", return_value={}),
        ):
            download_mgr._do_trimmed_download(
                "http://yt", "best", 10.0, 20.0, "/tmp/out.mp4", 1.0, True, "/tmp/td"
            )

        assert "-c" in captured_cmd
        assert "-af" not in captured_cmd


class TestApplyUpdateSourceRollback:
    """Test _apply_update_source rollback on partial failure."""

    @pytest.fixture
    def update_mgr(self, qapp):
        from concurrent.futures import ThreadPoolExecutor

        from managers.update_manager import UpdateManager

        pool = ThreadPoolExecutor(max_workers=1)
        mgr = UpdateManager(ytdlp_path="yt-dlp", thread_pool=pool)
        yield mgr
        pool.shutdown(wait=False)

    def test_rollback_on_write_failure(self, update_mgr, tmp_path):
        """If a module write fails mid-update, all replaced modules are rolled back."""
        import hashlib
        import json
        from unittest.mock import MagicMock, patch

        # Create fake module files
        modules_dir = tmp_path
        managers_dir = modules_dir / "managers"
        managers_dir.mkdir()

        original_content = b"# original code\n"
        new_content = b"# updated code\n"
        git_sha = update_mgr._compute_git_blob_sha(new_content)
        sha256 = hashlib.sha256(new_content).hexdigest()

        # Create the first two files
        (modules_dir / "downloader_pyqt6.py").write_bytes(original_content)
        (modules_dir / "constants.py").write_bytes(original_content)
        (managers_dir / "__init__.py").write_bytes(original_content)

        # Mock __file__ to point to managers dir
        write_count = 0
        original_move = __import__("shutil").move

        def fail_on_third_move(src, dst):
            nonlocal write_count
            write_count += 1
            if write_count >= 3:
                raise OSError("disk full")
            return original_move(src, dst)

        sha_sums = "\n".join(
            f"{sha256}  {m}"
            for m in [
                "downloader_pyqt6.py",
                "constants.py",
                "managers/__init__.py",
            ]
        )

        api_resp = MagicMock()
        api_resp.read.return_value = json.dumps({"sha": git_sha}).encode()
        api_resp.__enter__ = MagicMock(return_value=api_resp)
        api_resp.__exit__ = MagicMock(return_value=False)

        sha_resp = MagicMock()
        sha_resp.read.return_value = sha_sums.encode()
        sha_resp.__enter__ = MagicMock(return_value=sha_resp)
        sha_resp.__exit__ = MagicMock(return_value=False)

        dl_resp = MagicMock()
        dl_resp.read.side_effect = [new_content, b""]
        dl_resp.headers = {"Content-Length": str(len(new_content))}
        dl_resp.__enter__ = MagicMock(return_value=dl_resp)
        dl_resp.__exit__ = MagicMock(return_value=False)

        def mock_urlopen(req, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "SHA256SUMS" in url:
                return sha_resp
            if "/contents/" in url:
                return api_resp
            # Reset read for each download call
            fresh = MagicMock()
            fresh.read.side_effect = [new_content, b""]
            fresh.headers = {"Content-Length": str(len(new_content))}
            fresh.__enter__ = MagicMock(return_value=fresh)
            fresh.__exit__ = MagicMock(return_value=False)
            return fresh

        release_data = {"tag_name": "v1.0"}

        import managers.update_manager as um_module

        fake_file = str(managers_dir / "update_manager.py")

        with (
            patch.object(um_module, "__file__", fake_file),
            patch.object(type(update_mgr), "sig_run_on_gui", create=True),
            patch.object(type(update_mgr), "sig_update_status", create=True),
            patch.object(type(update_mgr), "sig_show_messagebox", create=True),
            patch("urllib.request.urlopen", side_effect=mock_urlopen),
            patch("shutil.move", side_effect=fail_on_third_move),
        ):
            update_mgr._apply_update_source(release_data)

        # First two files should have been rolled back to original
        assert (modules_dir / "downloader_pyqt6.py").read_bytes() == original_content
        assert (modules_dir / "constants.py").read_bytes() == original_content


class TestFrozenLinuxSecurityGuards:
    """Test symlink and tar traversal defenses in _apply_update_frozen_linux."""

    @pytest.fixture
    def update_mgr(self, qapp):
        from concurrent.futures import ThreadPoolExecutor

        from managers.update_manager import UpdateManager

        pool = ThreadPoolExecutor(max_workers=1)
        mgr = UpdateManager(ytdlp_path="yt-dlp", thread_pool=pool)
        yield mgr
        pool.shutdown(wait=False)

    def test_symlink_exe_raises_error(self, update_mgr, tmp_path):
        """Should raise RuntimeError if exe_path is a symlink."""
        from unittest.mock import MagicMock, patch

        real_file = tmp_path / "real_binary"
        real_file.write_bytes(b"binary")
        symlink = tmp_path / "YTDownloader"
        symlink.symlink_to(real_file)

        headers = {"User-Agent": "test"}
        release_data = {"tag_name": "v1.0"}

        # We need to get past the download and SHA verification to reach the symlink check.
        # The symlink check is at line 731, after tar extraction.
        # Easiest: mock everything up to the symlink check.
        import hashlib
        import io
        import tarfile

        # Create a real tar with a YTDownloader binary (>1024 bytes to pass size check)
        binary_content = b"x" * 2048
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
            info = tarfile.TarInfo(name="YTDownloader")
            info.size = len(binary_content)
            tar.addfile(info, io.BytesIO(binary_content))
        tar_bytes = tar_buffer.getvalue()
        real_sha = hashlib.sha256(tar_bytes).hexdigest()

        dl_resp = MagicMock()
        dl_resp.read.side_effect = [tar_bytes, b""]
        dl_resp.headers = {"Content-Length": str(len(tar_bytes))}
        dl_resp.__enter__ = MagicMock(return_value=dl_resp)
        dl_resp.__exit__ = MagicMock(return_value=False)

        with (
            patch("urllib.request.urlopen", return_value=dl_resp),
            patch.object(update_mgr, "_get_expected_sha256", return_value=real_sha),
            patch.object(update_mgr, "_sha256_file", return_value=real_sha),
            patch.object(type(update_mgr), "sig_run_on_gui", create=True),
        ):
            with pytest.raises(RuntimeError, match="symlink"):
                update_mgr._apply_update_frozen_linux(
                    "http://example.com/update.tar.gz",
                    headers,
                    symlink,
                    release_data,
                )

    def test_tar_traversal_member_skipped(self, update_mgr, tmp_path):
        """Tar members with '..' or starting with '/' should be skipped."""
        import hashlib
        import io
        import tarfile
        from unittest.mock import MagicMock, patch

        # Create a tar with a malicious member AND a legit member (>1024 bytes total)
        binary_content = b"x" * 2048
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
            # Malicious member
            evil = tarfile.TarInfo(name="../../../etc/passwd")
            evil.size = 4
            tar.addfile(evil, io.BytesIO(b"evil"))
            # Legit member
            good = tarfile.TarInfo(name="YTDownloader")
            good.size = len(binary_content)
            tar.addfile(good, io.BytesIO(binary_content))
        tar_bytes = tar_buffer.getvalue()
        real_sha = hashlib.sha256(tar_bytes).hexdigest()

        exe_path = tmp_path / "YTDownloader"
        exe_path.write_bytes(b"old")

        dl_resp = MagicMock()
        dl_resp.read.side_effect = [tar_bytes, b""]
        dl_resp.headers = {"Content-Length": str(len(tar_bytes))}
        dl_resp.__enter__ = MagicMock(return_value=dl_resp)
        dl_resp.__exit__ = MagicMock(return_value=False)

        with (
            patch("urllib.request.urlopen", return_value=dl_resp),
            patch.object(update_mgr, "_get_expected_sha256", return_value=real_sha),
            patch.object(update_mgr, "_sha256_file", return_value=real_sha),
            patch.object(type(update_mgr), "sig_run_on_gui", create=True),
            patch.object(type(update_mgr), "sig_update_status", create=True),
            patch.object(type(update_mgr), "sig_request_close", create=True),
            patch("subprocess.Popen"),
        ):
            # Should succeed — the evil member is skipped, the good one is extracted
            update_mgr._apply_update_frozen_linux(
                "http://example.com/update.tar.gz",
                {"User-Agent": "test"},
                exe_path,
                {"tag_name": "v1.0"},
            )

        # The binary should have been replaced with the legit content
        assert exe_path.read_bytes() == binary_content


class TestDownloadStreamSegmentErrorWrapping:
    """Test _download_stream_segment wraps network errors into RuntimeError."""

    def test_url_error_wrapped(self, download_mgr):
        """URLError should be wrapped in RuntimeError with user-friendly message."""
        import urllib.error
        from unittest.mock import patch

        with patch.object(
            download_mgr,
            "_download_stream_segment_inner",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            with pytest.raises(RuntimeError, match="Network error"):
                download_mgr._download_stream_segment(
                    "http://example.com/stream", 0, 10, "/tmp/out", "video"
                )

    def test_socket_timeout_wrapped(self, download_mgr):
        """socket.timeout should be wrapped in RuntimeError."""
        import socket
        from unittest.mock import patch

        with patch.object(
            download_mgr,
            "_download_stream_segment_inner",
            side_effect=socket.timeout("timed out"),
        ):
            with pytest.raises(RuntimeError, match="Network error"):
                download_mgr._download_stream_segment(
                    "http://example.com/stream", 0, 10, "/tmp/out", "audio"
                )

    def test_os_error_wrapped(self, download_mgr):
        """OSError should be wrapped in RuntimeError with try again suggestion."""
        from unittest.mock import patch

        with patch.object(
            download_mgr,
            "_download_stream_segment_inner",
            side_effect=OSError("Connection reset"),
        ):
            with pytest.raises(RuntimeError, match="Try again"):
                download_mgr._download_stream_segment(
                    "http://example.com/stream", 0, 10, "/tmp/out", "video"
                )


class TestParseYtdlpOutputErrorLineCap:
    """Test _parse_ytdlp_output caps error lines at 100."""

    def test_error_line_cap(self, download_mgr):
        """Should collect at most 100 error lines."""
        from unittest.mock import MagicMock

        download_mgr.is_downloading = True
        download_mgr._download_has_progress = False
        download_mgr.last_progress_time = None

        # Create a mock process with 150 error lines
        lines = [f"ERROR: something went wrong #{i}\n" for i in range(150)]
        mock_proc = MagicMock()
        mock_proc.stdout = iter(lines)

        with (
            __import__("unittest.mock", fromlist=["patch"]).patch.object(
                download_mgr, "update_status"
            ),
            __import__("unittest.mock", fromlist=["patch"]).patch.object(
                download_mgr, "update_progress"
            ),
        ):
            errors = download_mgr._parse_ytdlp_output(mock_proc)

        assert len(errors) == 100


class TestClipboardManagerLifecycle:
    """Test ClipboardManager deque FIFO ordering and stop event lifecycle."""

    @pytest.fixture
    def mgr(self):
        from concurrent.futures import ThreadPoolExecutor

        from managers.clipboard_manager import ClipboardManager

        pool = ThreadPoolExecutor(max_workers=1)
        m = ClipboardManager(thread_pool=pool)
        yield m
        pool.shutdown(wait=False)

    def test_deque_fifo_ordering(self, mgr):
        """Items should be retrievable in FIFO order with popleft."""
        with mgr.clipboard_lock:
            mgr.clipboard_url_list.append({"url": "http://a", "status": "pending"})
            mgr.clipboard_url_list.append({"url": "http://b", "status": "pending"})
            mgr.clipboard_url_list.append({"url": "http://c", "status": "pending"})

        assert mgr.clipboard_url_list[0]["url"] == "http://a"
        first = mgr.clipboard_url_list.popleft()
        assert first["url"] == "http://a"
        assert mgr.clipboard_url_list[0]["url"] == "http://b"

    def test_stop_event_lifecycle(self, mgr):
        """clipboard_stop_event should toggle correctly."""
        assert mgr.clipboard_stop_event.is_set()
        mgr.clipboard_stop_event.clear()
        assert not mgr.clipboard_stop_event.is_set()
        mgr.clipboard_stop_event.set()
        assert mgr.clipboard_stop_event.is_set()

    def test_shutting_down_flag(self, mgr):
        """_shutting_down flag should default False and be settable."""
        assert mgr._shutting_down is False
        mgr._shutting_down = True
        assert mgr._shutting_down is True


class TestEncodingStderrThreadTimeout:
    """Test run_ffmpeg_with_progress handles stderr thread join timeout."""

    def test_stderr_thread_timeout_logs_warning(self):
        """When stderr thread doesn't exit in 5s, method should still return."""
        import threading
        from unittest.mock import MagicMock, patch

        enc = EncodingService(ffmpeg_path="ffmpeg", hw_encoder=None)

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = iter([])  # no output

        # Make stderr block forever so the thread won't finish
        block_event = threading.Event()

        def blocking_stderr():
            block_event.wait(10)  # block up to 10s
            yield "error line"

        mock_proc.stderr = blocking_stderr()

        callbacks = MagicMock()
        callbacks.on_progress = MagicMock()
        callbacks.on_status = MagicMock()
        callbacks.on_heartbeat = MagicMock()

        with (
            patch("managers.encoding.subprocess.Popen", return_value=mock_proc),
            patch("managers.encoding.safe_process_cleanup"),
        ):
            result = enc.run_ffmpeg_with_progress(
                ["ffmpeg", "-i", "in.mp4", "out.mp4"],
                60,
                "Test encoding",
                callbacks,
            )

        block_event.set()  # unblock the thread
        assert result is True


class TestDownloadLocalFileErrors:
    """Test download_local_file error paths."""

    def test_ffmpeg_not_found(self, download_mgr):
        """FileNotFoundError should report ffmpeg not found."""
        from unittest.mock import patch

        download_mgr.is_downloading = True

        with (
            patch.object(download_mgr, "update_status") as mock_status,
            patch.object(download_mgr, "update_progress"),
            patch(
                "managers.download_manager.subprocess.Popen",
                side_effect=FileNotFoundError("ffmpeg not found"),
            ),
        ):
            download_mgr.download_local_file("/tmp/input.mp4")

        # Should mention ffmpeg in the status
        status_calls = [str(c) for c in mock_status.call_args_list]
        assert any("ffmpeg" in s.lower() for s in status_calls)

    def test_generic_exception_handled(self, download_mgr):
        """Generic exceptions should be caught and reported."""
        from unittest.mock import patch

        download_mgr.is_downloading = True

        with (
            patch.object(download_mgr, "update_status") as mock_status,
            patch.object(download_mgr, "update_progress"),
            patch(
                "managers.download_manager.subprocess.Popen",
                side_effect=RuntimeError("unexpected"),
            ),
        ):
            download_mgr.download_local_file("/tmp/input.mp4")

        status_calls = [str(c) for c in mock_status.call_args_list]
        assert any("error" in s.lower() or "unexpected" in s.lower() for s in status_calls)


class TestTrimHistoryOnStartup:
    """Test UploadManager._trim_history_on_startup."""

    def test_trims_file_over_500_lines(self, tmp_path):
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch

        from managers.upload_manager import UploadManager

        history_file = tmp_path / "upload_history.txt"
        lines = [f"2026-01-01 | file{i}.mp4 | http://example.com/{i}\n" for i in range(600)]
        history_file.write_text("".join(lines))

        pool = ThreadPoolExecutor(max_workers=1)
        with patch("managers.upload_manager.UPLOAD_HISTORY_FILE", history_file):
            UploadManager(thread_pool=pool)

        result_lines = history_file.read_text().splitlines()
        assert len(result_lines) == 500
        pool.shutdown(wait=False)

    def test_no_op_under_500_lines(self, tmp_path):
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch

        from managers.upload_manager import UploadManager

        history_file = tmp_path / "upload_history.txt"
        lines = [f"2026-01-01 | file{i}.mp4 | http://example.com/{i}\n" for i in range(100)]
        history_file.write_text("".join(lines))

        pool = ThreadPoolExecutor(max_workers=1)
        with patch("managers.upload_manager.UPLOAD_HISTORY_FILE", history_file):
            UploadManager(thread_pool=pool)

        result_lines = history_file.read_text().splitlines()
        assert len(result_lines) == 100
        pool.shutdown(wait=False)


class TestSaveUploadLinkPeriodicTrim:
    """Test save_upload_link trims history every 100 saves."""

    def test_periodic_trim_at_100_saves(self, tmp_path):
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch

        from managers.upload_manager import UploadManager

        history_file = tmp_path / "upload_history.txt"
        # Pre-populate with exactly 500 lines (no startup trim needed)
        history_file.write_text("".join(f"old entry {i}\n" for i in range(500)))

        pool = ThreadPoolExecutor(max_workers=1)
        with patch("managers.upload_manager.UPLOAD_HISTORY_FILE", history_file):
            mgr = UploadManager(thread_pool=pool)  # no trim (<=500)
            # Write 600 entries: after 100th write, file has 600 lines (<= 1000, no trim)
            # After 200th write, file has 700 lines (<= 1000, no trim)
            # ... after 600th write, file has 1100 lines (> 1000), periodic trim to 500
            for i in range(600):
                mgr.save_upload_link(f"http://example.com/{i}", f"file{i}.mp4")

        # 500 initial + 600 writes = 1100 > 1000 → trimmed to 500
        result_lines = history_file.read_text().splitlines()
        assert len(result_lines) == 500
        pool.shutdown(wait=False)


class TestGetUpdateAssetUrl:
    """Test _get_update_asset_url finds correct platform binary."""

    @pytest.fixture
    def update_mgr(self, qapp):
        from concurrent.futures import ThreadPoolExecutor

        from managers.update_manager import UpdateManager

        pool = ThreadPoolExecutor(max_workers=1)
        mgr = UpdateManager(ytdlp_path="yt-dlp", thread_pool=pool)
        yield mgr
        pool.shutdown(wait=False)

    def test_finds_windows_asset(self, update_mgr):
        from unittest.mock import patch

        release = {
            "assets": [
                {"name": "YTDownloader.exe", "browser_download_url": "http://dl/win.exe"},
                {
                    "name": "YTDownloader-Linux.tar.gz",
                    "browser_download_url": "http://dl/linux.tar.gz",
                },
            ]
        }
        with patch("managers.update_manager.sys") as mock_sys:
            mock_sys.platform = "win32"
            result = update_mgr._get_update_asset_url(release)
        assert result == "http://dl/win.exe"

    def test_finds_linux_asset(self, update_mgr):
        from unittest.mock import patch

        release = {
            "assets": [
                {"name": "YTDownloader.exe", "browser_download_url": "http://dl/win.exe"},
                {
                    "name": "YTDownloader-Linux.tar.gz",
                    "browser_download_url": "http://dl/linux.tar.gz",
                },
            ]
        }
        with patch("managers.update_manager.sys") as mock_sys:
            mock_sys.platform = "linux"
            result = update_mgr._get_update_asset_url(release)
        assert result == "http://dl/linux.tar.gz"

    def test_missing_asset_returns_none(self, update_mgr):
        release = {"assets": [{"name": "README.md", "browser_download_url": "http://dl/readme"}]}
        result = update_mgr._get_update_asset_url(release)
        assert result is None


class TestIsOnedirFrozen:
    """Test _is_onedir_frozen detection."""

    @pytest.fixture
    def update_mgr(self, qapp):
        from concurrent.futures import ThreadPoolExecutor

        from managers.update_manager import UpdateManager

        pool = ThreadPoolExecutor(max_workers=1)
        mgr = UpdateManager(ytdlp_path="yt-dlp", thread_pool=pool)
        yield mgr
        pool.shutdown(wait=False)

    def test_source_mode_returns_false(self, update_mgr):
        """Non-frozen (source) mode should return False."""
        from unittest.mock import patch

        with patch("managers.update_manager.sys") as mock_sys:
            mock_sys.frozen = False
            del mock_sys.frozen  # getattr(sys, "frozen", False) returns False
            result = update_mgr._is_onedir_frozen()
        assert result is False

    def test_onefile_mode_returns_false(self, update_mgr, tmp_path):
        """Onefile mode (_MEIPASS != exe parent) should return False."""
        from unittest.mock import patch

        with patch("managers.update_manager.sys") as mock_sys:
            mock_sys.frozen = True
            mock_sys._MEIPASS = "/tmp/random_temp_dir"
            mock_sys.executable = str(tmp_path / "YTDownloader")
            result = update_mgr._is_onedir_frozen()
        assert result is False

    def test_onedir_mode_returns_true(self, update_mgr, tmp_path):
        """Onedir mode (_MEIPASS == exe parent) should return True."""
        from unittest.mock import patch

        app_dir = str(tmp_path / "myapp")
        with patch("managers.update_manager.sys") as mock_sys:
            mock_sys.frozen = True
            mock_sys._MEIPASS = app_dir
            mock_sys.executable = str(tmp_path / "myapp" / "YTDownloader")
            result = update_mgr._is_onedir_frozen()
        assert result is True


class TestSha256File:
    """Test _sha256_file chunked hashing with actual files."""

    def test_matches_hashlib(self, tmp_path):
        """Chunked file hash should match in-memory hash."""
        import hashlib

        from managers.update_manager import UpdateManager

        content = b"A" * 500_000 + b"B" * 500_000  # 1MB
        test_file = tmp_path / "testfile.bin"
        test_file.write_bytes(content)

        expected = hashlib.sha256(content).hexdigest().lower()
        result = UpdateManager._sha256_file(str(test_file))
        assert result == expected

    def test_empty_file(self, tmp_path):
        """Empty file should return SHA-256 of empty bytes."""
        import hashlib

        from managers.update_manager import UpdateManager

        test_file = tmp_path / "empty.bin"
        test_file.write_bytes(b"")

        expected = hashlib.sha256(b"").hexdigest().lower()
        result = UpdateManager._sha256_file(str(test_file))
        assert result == expected


class TestUpdatePreviewsEndTimeAdjustment:
    """Test update_previews_thread adjusts end_time near EOF."""

    def test_end_time_near_eof_adjusted(self):
        """End time within 1s of duration should be adjusted to duration - 3."""
        from unittest.mock import MagicMock, patch

        from managers.trimming_manager import TrimmingManager

        mgr = TrimmingManager.__new__(TrimmingManager)
        mgr.video_duration = 60
        mgr.preview_lock = __import__("threading").Lock()
        mgr.preview_thread_running = True

        captured_times = []

        def mock_extract_frame(t):
            captured_times.append(t)
            return "/tmp/frame.png"

        mock_image = MagicMock()

        with (
            patch.object(mgr, "extract_frame", side_effect=mock_extract_frame),
            patch.object(mgr, "_path_to_image", return_value=mock_image),
            patch.object(type(mgr), "sig_preview_ready", create=True),
        ):
            mgr.update_previews_thread(start_time=5, end_time=59)

        # Start frame at 5, end frame adjusted to 57 (60 - 3)
        assert captured_times[0] == 5
        assert captured_times[1] == 57

    def test_end_time_far_from_eof_not_adjusted(self):
        """End time far from duration should not be adjusted."""
        from unittest.mock import MagicMock, patch

        from managers.trimming_manager import TrimmingManager

        mgr = TrimmingManager.__new__(TrimmingManager)
        mgr.video_duration = 60
        mgr.preview_lock = __import__("threading").Lock()
        mgr.preview_thread_running = True

        captured_times = []

        def mock_extract_frame(t):
            captured_times.append(t)
            return "/tmp/frame.png"

        mock_image = MagicMock()

        with (
            patch.object(mgr, "extract_frame", side_effect=mock_extract_frame),
            patch.object(mgr, "_path_to_image", return_value=mock_image),
            patch.object(type(mgr), "sig_preview_ready", create=True),
        ):
            mgr.update_previews_thread(start_time=5, end_time=30)

        assert captured_times[1] == 30  # not adjusted


class TestFetchLocalFileDurationErrors:
    """Test _fetch_local_file_duration error handling paths."""

    @pytest.fixture
    def trim_mgr(self):
        from managers.trimming_manager import TrimmingManager

        mgr = TrimmingManager.__new__(TrimmingManager)
        mgr.ffprobe_path = "ffprobe"
        mgr.video_duration = 0
        mgr.is_fetching_duration = True
        mgr.fetch_lock = __import__("threading").Lock()
        return mgr

    def test_ffprobe_nonzero_exit(self, trim_mgr):
        """CalledProcessError should emit error messagebox."""
        import subprocess
        from unittest.mock import MagicMock, patch

        mock_show = MagicMock()
        mock_status = MagicMock()
        mock_fetch_done = MagicMock()

        with (
            patch.object(type(trim_mgr), "sig_show_messagebox", create=True, new=mock_show),
            patch.object(type(trim_mgr), "sig_update_status", create=True, new=mock_status),
            patch.object(type(trim_mgr), "sig_fetch_done", create=True, new=mock_fetch_done),
            patch(
                "managers.trimming_manager.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "ffprobe", stderr="bad file"),
            ),
        ):
            trim_mgr._fetch_local_file_duration("/tmp/bad.mp4")

        mock_show.emit.assert_called_once()
        assert "error" in str(mock_show.emit.call_args)
        assert trim_mgr.is_fetching_duration is False

    def test_non_numeric_duration(self, trim_mgr):
        """Non-numeric ffprobe output should trigger ValueError path."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.stdout = "not_a_number\n"
        mock_result.returncode = 0

        mock_show = MagicMock()
        mock_status = MagicMock()
        mock_fetch_done = MagicMock()

        with (
            patch.object(type(trim_mgr), "sig_show_messagebox", create=True, new=mock_show),
            patch.object(type(trim_mgr), "sig_update_status", create=True, new=mock_status),
            patch.object(type(trim_mgr), "sig_fetch_done", create=True, new=mock_fetch_done),
            patch("managers.trimming_manager.subprocess.run", return_value=mock_result),
        ):
            trim_mgr._fetch_local_file_duration("/tmp/weird.mp4")

        mock_show.emit.assert_called_once()
        assert "Invalid" in str(mock_show.emit.call_args) or "error" in str(
            mock_show.emit.call_args
        )
        assert trim_mgr.is_fetching_duration is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
