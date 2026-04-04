#!/usr/bin/env python3
"""
Unit tests for YoutubeDownloader

Run with: pytest test_unit.py -v
Run with coverage: pytest test_unit.py -v --cov=constants --cov=managers
"""

import os
import re
import struct
import sys
from pathlib import Path

import pytest

import constants
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
from managers.encoding import EncodingService
from managers.download_manager import DownloadManager


# ─── Constants ────────────────────────────────────────────────────────────


class TestConstantsModule:
    """Test suite for constants.py"""

    def test_preview_dimensions_positive(self):
        assert constants.PREVIEW_WIDTH > 0
        assert constants.PREVIEW_HEIGHT > 0

    def test_timing_constants_positive(self):
        assert constants.PREVIEW_DEBOUNCE_MS > 0
        assert constants.CLIPBOARD_POLL_INTERVAL_MS > 0

    def test_timeout_constants_reasonable(self):
        assert 60 <= constants.DOWNLOAD_TIMEOUT <= 7200
        assert constants.DOWNLOAD_PROGRESS_TIMEOUT >= 60
        assert constants.METADATA_FETCH_TIMEOUT >= 10
        assert constants.FFPROBE_TIMEOUT >= 5

    def test_cache_and_thread_constants(self):
        assert 0 < constants.MAX_WORKER_THREADS <= 10
        assert 0 < constants.MAX_RETRY_ATTEMPTS <= 5

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
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], (int, float))


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


class TestBuildCommands:
    """Test DownloadManager command builders (need mock DownloadManager)."""

    @pytest.fixture
    def dm(self):
        """Create a minimal DownloadManager for command building."""
        # DownloadManager inherits QObject, needs QApplication
        # We test the static/simple methods only
        return None

    def test_build_base_uses_constants(self):
        """Verify base command uses expected constant values."""
        assert constants.CONCURRENT_FRAGMENTS == "8"
        assert constants.BUFFER_SIZE == "128K"
        assert constants.CHUNK_SIZE == "10M"


class TestFindLatestFile:
    """Test DownloadManager._find_latest_file."""

    def test_empty_directory(self, tmp_path):
        assert DownloadManager._find_latest_file(str(tmp_path)) is None

    def test_nonexistent_directory(self):
        assert DownloadManager._find_latest_file("/nonexistent/path/xyz") is None

    def test_finds_latest(self, tmp_path):
        import time

        f1 = tmp_path / "old.mp4"
        f1.write_text("old")
        time.sleep(0.05)
        f2 = tmp_path / "new.mp4"
        f2.write_text("new")
        result = DownloadManager._find_latest_file(str(tmp_path))
        assert result is not None
        assert "new.mp4" in result

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

        mgr = UpdateManager.__new__(UpdateManager)
        return mgr._version_newer

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
        assert cmd[-2] == "/tmp/out.mp3"
        assert cmd[-3] == "-o"

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
        assert mgr.clipboard_downloading is False
        assert mgr.clipboard_url_list == []
        assert mgr.clipboard_last_content == ""

    def test_lock_acquisition(self, mgr):
        """Locks should be acquirable without deadlock."""
        with mgr.clipboard_lock:
            pass
        with mgr.auto_download_lock:
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
