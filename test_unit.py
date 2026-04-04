#!/usr/bin/env python3
"""
Unit tests for YoutubeDownloader

Run with: pytest test_unit.py -v
Run with coverage: pytest test_unit.py -v --cov=constants --cov=managers
"""

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
        assert constants.MAX_WORKER_THREADS == 5
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
