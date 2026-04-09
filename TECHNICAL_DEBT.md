# Technical Debt

Last updated: 2026-04-09 (final review)

## Summary
**Audit 1**: 55 found, 53 fixed, 2 accepted
**Audit 2**: 48 found, 47 fixed, 1 remaining
**Audit 3**: 65 found, 62 fixed, 3 accepted
**Audit 4**: 38 raw → 21 validated (12 false positives removed), 20 fixed, 1 deferred
**Audit 5**: 39 raw (5 agents) → 18 unique after dedup, 17 fixed (incl. 2 formerly deferred), 0 remaining
**Audit 6**: 65 raw (5 agents) → 48 unique after dedup, 16 fixed, 12 deferred (refactors/medium effort), 20 test gap findings documented
**Audit 7**: 50 raw (5 agents) → 44 unique after dedup, 39 fixed (2 iterations), 5 deferred
**Post-audit cleanup**: 17 deferred items fixed (6 refactors, 3 performance, 2 DevOps, 9 test gaps + dependency tests), 28 new tests (340 total)
**Audit 8**: 15 raw (5 agents) → 15 unique (1 dup removed), 15 fixed (1 iteration), 0 deferred (339 tests, was 340 — net -1 from merged tests)
**Audit 9**: 30 raw (5 agents) → 30 unique, 24 fixed (1 iteration), 6 deferred (353 tests, was 339 — net +14 from strengthened tests)
**Audit 10**: 35 raw (5 agents) → 35 unique after dedup, 28 fixed (1 iteration), 7 deferred (364 tests, was 353 — net +11 from new tests)
**Audit 11**: 59 raw (5 agents) → 56 unique after dedup, 28 fixed (1 iteration), 28 deferred/accepted (376 tests, was 363 — net +13 from new tests)
**Final review**: 18 found (6 agents), 18 fixed + 4 regression fixes from verification round (376 tests)

## Remaining Issues

- **DO-5**: ffmpeg downloaded from rolling `latest` URL with no SHA gate. Accepted — BtbN rolling releases make pinning impractical. [medium]
- **M-17**: No HTTP connection reuse for byte-range downloads. Accepted — urllib3 is transitive dep only, overhead small, no new dependency warranted. [medium]
- **M-28**: No `pip --require-hashes` for supply chain integrity in release builds. Accepted — PyInstaller pinned, full hash pinning too complex for the benefit. [medium]
- **DO-8**: Release notes not structured (no CHANGELOG.md). Deferred — `generate_release_notes: true` sufficient for current scale. [low]

### Deferred (audit 7 — remaining)
- **CQ-M5**: Clipboard download subprocess creation duplicated in main window — should delegate to DownloadManager. [medium]
- **P-M1**: O(n) indexed deletion on deque in _remove_url_from_list — bounded at 500, acceptable for user-triggered action. [low]

### Deferred (audit 9)
- **SEC-L3**: Upload history file written non-atomically — append-only path, cosmetic data, low risk. [low]
- **SEC-L4**: SIDX parser missing bounds check before fixed-offset reads — caught by `struct.error` exception handler. [low]
- **SEC-L5**: Log file created with default umask — directory is 0o700, defense-in-depth only. [low]
- **P-L4**: `view_upload_history` reads entire file into QTextEdit — one-time cost per dialog open, 500 lines max. [low]
- **P-L5**: `on_slider_change` fires per-pixel without debounce for text updates — preview already debounced 500ms. [low]
- **P-L6**: `_restore_clipboard_urls` re-validates persisted URLs at startup — acceptable at 500 max. [low]
### Deferred (audit 10)
- **P-M3**: `last_progress_time` / `_download_has_progress` / `_trim_download_active` read across threads without lock — GIL-safe in CPython, formally undefined. [medium]
- **DO-L1**: Action version comments in workflow YAML may not match actual tag — Dependabot-managed. [low]
- **DO-L2**: No coverage report artifact or external upload (only printed to job log). [low]
- **DO-L3**: `QT_QPA_PLATFORM: offscreen` applied to Windows runner without OS guard. [low]
- **DO-L5**: No type checking (mypy/pyright) in CI. [low]
- **SEC-L6**: yt-dlp error lines with signed URLs logged verbatim to rotating log file. [low]

### Deferred (audit 11)
- **DO-H1**: Dependabot blind to `.lock` files (requirements.lock, requirements-ci.lock) — Dependabot watches `requirements.txt` (ranges) which is sufficient; lock files are intentionally manually bumped. Accepted. [low]
- **CQ-M2**: Volume threshold differs between trimmed (±0.15 threshold) and non-trimmed (exact `!= 1.0`) paths — intentional by design. Accepted. [medium]
- **SEC-M3**: yt-dlp SHA2-256SUMS not verified against signing key — HTTPS + GitHub release integrity sufficient. Accepted. [medium]
- **P-M3**: `_find_latest_file` scans entire Downloads directory — one-time `scandir` per download, milliseconds even with thousands of files. Accepted. [medium]
- ~~**DO-M3**: Build yt-dlp binary version not checked against requirements.lock~~ — Fixed: added `--version` check on both Linux and Windows. [medium]
- **SEC-L2**: Window geometry restore without size validation. [low]
- **SEC-L3-b**: `_open_folder` defensive path validation. [low]
- **SEC-L4-b**: Error messages may leak paths (desktop app, minimal risk). [low]
- **SEC-L6-b**: `download_local_file` doesn't validate input file path (user-typed). [low]
- **SEC-L7**: `webbrowser.open()` with env-controlled path. [low]
- **P-L2**: Checkbox temp dir leaks on crash (belt-and-suspenders). [low]
- **P-L3**: `_http_range_read` double memory with chunks+join (bounded 512KB). [low]
- **P-L4-b**: `_download_stream_segment` 120s connect timeout. [low]
- **P-L6-b**: `save_upload_link` trim blocks under lock (rare, small file). [low]
- **DO-L1-b**: Cosign version pinned inline, not Dependabot-tracked. [low]
- **DO-L3-b**: dbus-python version not tracked centrally. [low]
- **DO-L4-b**: Dependabot auto-merge no concurrency group. [low]
- **DO-L5-b**: ruff S rule ignores broadly scoped — should use per-file-ignores. [low]
- **CQ-L9**: `_download_timeout_timer` extra fires after download completion (benign). [low]

### Test coverage gaps (remaining)
- **TQ-8** [medium]: `test_cancellation_during_data_download` xfail masks real gap (mock urlopen interaction flaky)
- **TQ-10–20** [medium/low]: Various smaller coverage gaps in update_manager, download_manager, upload_manager
- **TQ-L1**: `_PLAYLIST_ITEM_RE` regex untested. [low]
- **TQ-L2**: `enable_upload_button` untested. [low]
- **TQ-L3**: `queue_count`, `stop_queue_upload`, `set_widget_for_queue_item` untested. [low]
- **TQ-L4**: `cleanup_old_updates` untested. [low]
- **TQ-L5**: `_get_pip_path` untested. [low]
- **TQ-L6**: `init_dependencies_async` untested. [low]
- **TQ-L9**: `_parse_ytdlp_output` status branches (ExtractAudio/ffmpeg) not fully tested. [low]
- **TQ-L10**: Shared QApplication fixture fragility. [low]
- **TQ-M1**: ClipboardManager backend detection untested. [medium]

### Accepted tradeoffs (from audit 1)
- **Widget reads from worker in `_fetch_file_size`** — Safe via closure. [informational]

## Fixed Issues (audit 11 — 27 fixed, 376 tests)

<details>
<summary>Click to expand</summary>

### Medium (7)
- [x] CQ-M1: `_on_local_duration_fetched` did not set `self.video_title` — local file trims used generic "video" name. Added `self.video_title = video_title or None`.
- [x] SEC-M1: Batch file URL sanitization incomplete — tabs/whitespace not stripped, no comment/option line rejection. Added `.strip()` and `#`/`-` prefix skip.
- [x] SEC-M2: `tarfile.open` member iteration without total count or symlink check. Added 100-member cap and `issym()`/`islnk()` skip.
- [x] P-M1: `_parse_ytdlp_output` emitted status on every progress line (~10Hz). Added 0.25s throttle gate.
- [x] P-M2: `download_local_file` stdout progress loop unthrottled (~20Hz). Added 0.25s throttle gate.
- [x] P-M4: `on_url_change` slider reset triggered 4+ signal cascades per keystroke. Added `blockSignals` around `setValue(0)`.
- [x] DO-M1: PyInstaller version pinned inline in workflow, not in any lock file. Added to `requirements.lock`.
- [x] DO-M2: CodeQL scheduled run cancellable by push to main. Added `github.event_name` to concurrency group.

### Low (20)
- [x] CQ-L1: Dead method `_finish_download` in DownloadManager — never called. Removed.
- [x] CQ-L2: Dead attribute `self.custom_filename` on main window. Removed.
- [x] CQ-L3: Dead `_shutting_down` on three managers — set by main window but never read by any manager. Removed.
- [x] CQ-L4: Unused constants `UI_UPDATE_DELAY_MS`, `CLIPBOARD_TIMEOUT`. Removed.
- [x] CQ-L5: Hardcoded `MAX_DURATION = 24 * 3600` duplicated `MAX_VIDEO_DURATION`. Replaced with constant import.
- [x] CQ-L6: `_fetch_local_file_duration` missing negative duration validation. Added check matching URL path.
- [x] CQ-L7: `_fetch_local_file_duration` did not set `self.video_title` on trimming manager. Added.
- [x] CQ-L8: `save_upload_link` double-locking TOCTOU on trim. Merged trim into single lock scope.
- [x] SEC-L1: Config JSON loaded without type validation. Added `isinstance(loaded, dict)` check.
- [x] SEC-L5: `_do_update_status` CSS injection via color param. Added `_VALID_STATUS_COLORS` whitelist.
- [x] P-L1: `_build_dark_style()` regenerated full QSS string on every call. Added module-level cache.
- [x] P-L5: Repeated `import urllib.request`/`urllib.error` inside 7 methods in update_manager. Moved to module-level.
- [x] DO-L2: `inputs.version` shell interpolation in `gh release create`. Changed to env var `$VERSION`.
- [x] TQ-M7: `_fetch_local_file_duration` success path not tested. Added 3 tests (success, negative, capped).
- [x] TQ-M6: `speed_limit` insertion order not tested. Added test verifying `--limit-rate` before `--`.
- [x] TQ-M5: `_download_audio_trimmed_path` not tested. Added success + failure tests.
- [x] TQ-M4: `_download_video_trimmed_path` not tested. Added success + custom filename tests.
- [x] TQ-M3: `_make_encode_callbacks` type masking. Added type assertion test.
- [x] TQ-M2: `cleanup_old_temp_dirs` untested. Added test with real tmp_path dirs.
- [x] TQ-L7-b: `test_trimmed_path_taken` weak assertions. Added format_spec + volume_multiplier test.
- [x] TQ-L8: `validate_youtube_url` `/v/` path not tested. Added 2 tests.

</details>

## Fixed Issues (audit 10 — 28 fixed, 364 tests)

<details>
<summary>Click to expand</summary>

### High (1)
- [x] TQ-H1: `stop_download()` with `current_process=None` left `is_downloading=True` — stuck state. Fixed to reset `is_downloading` even without a process.

### Medium (7)
- [x] SEC-M1: QSS path injection via unquoted temp dir in checkbox image `url()`. Added double-quote wrapping.
- [x] SEC-M2: Stream URLs from yt-dlp not validated before HTTP fetch (SSRF). Added `https://` scheme check.
- [x] P-M1: Sequential clipboard progress unthrottled (~100 events/sec). Added 0.25s throttle gate.
- [x] P-M2: `_clipboard_batch_process` written from worker, read from GUI without lock. Added `_clipboard_batch_lock`.
- [x] P-M4: `encoding.run_ffmpeg_with_progress` status emitted at ~25 Hz without throttle. Added 0.25s throttle gate.
- [x] DO-M1: pytest/ruff/pytest-cov pinned in workflow YAML invisible to Dependabot. Created `requirements-ci.lock`.
- [x] DO-M2: `dependabot-auto-merge` uses `pull_request_target` without fork origin check. Added `head.repo.full_name` guard.
- [x] DO-M3: pytest hardcoded to `test_unit.py` — new test files silently skipped. Changed to `pytest` discovery.

### Low (20)
- [x] CQ-L1: `progress_state` unused across all `_make_progress_helpers()` call sites. Replaced with `_`.
- [x] CQ-L2: Rollback in `_apply_update_source` leaks `.py.backup` files. Added cleanup on success path.
- [x] CQ-L3: Local variable `is_playlist_url` shadows imported function. Renamed to `url_is_playlist`.
- [x] CQ-L4: Dead `"question"` branch in `_do_show_messagebox` — never emitted. Removed.
- [x] CQ-L5: Duplicate assignments in `fetch_duration_clicked`. Hoisted above if/else.
- [x] CQ-L6: Dead alias `widget_data = item` and always-true guard in `_update_url_status`. Removed.
- [x] CQ-L7: `_init_temp_directory` referenced `self.trimming_mgr` before assignment. Moved cleanup scheduling.
- [x] SEC-L1: `validate_volume` passes `nan`/`inf` through clamp. Added `math.isfinite()` guard.
- [x] SEC-L5-b: Persisted clipboard URL list count unbounded before validation loop. Added `[:MAX_CLIPBOARD_URLS]` cap.
- [x] P-L1: `UploadManager.add_to_queue` O(n) linear scan for duplicate detection. Added parallel `_queued_paths` set.
- [x] P-L2: `_fetch_file_size` stale results overwrite fresh. Added `_filesize_fetch_seq` counter.
- [x] P-L4-b: `_do_run_on_gui` no exception safety. Added try/except with logging.
- [x] P-L6: `save_upload_link` TOCTOU on `_upload_save_count`. Protected with `upload_lock`.
- [x] DO-L4: No `all-checks` aggregator job for branch protection. Added `all-checks` job.
- [x] TQ-M1: Missing test for `download()` trim with `video_duration=0`.
- [x] TQ-M2: Missing test for `download()` with `start_time >= end_time`.
- [x] TQ-M3: Missing test for `_parse_sidx` with `timescale=0`.
- [x] TQ-M4: Missing test for `upload_to_catbox` non-HTTPS response.
- [x] TQ-M6: Missing assertion for `uploader_is_uploading` reset after queue done.
- [x] TQ-L2: `retry_network_operation` hardcodes delay constant. Test now uses `RETRY_DELAY`.

</details>

## Fixed Issues (audit 9 — 23 fixed, 353 tests)

<details>
<summary>Click to expand</summary>

### Critical (1)
- [x] DO-C1: SHA256SUMS `sed 's|.*/||'` stripped hashes from binary artifact entries — all frozen-mode self-updates silently broken. Fixed with `cd` + `sha256sum` per directory.

### High (2)
- [x] CQ-H1: `_on_uploader_queue_done` "completed normally" branch unreachable — `finally` block reset `uploader_is_uploading` before signal. Added `completed_normally` bool parameter to `sig_uploader_queue_done`.
- [x] TQ-H1: `TestApplyUpdateSourceRollback` patched `shutil.move` but production uses `os.replace` — failure injection was dead code. Fixed to patch `os.replace`.

### Medium (6)
- [x] CQ-M1: `downloading_count` not reset in `clear_all_clipboard_urls` — stale counter could block future auto-downloads. Added reset.
- [x] SEC-M1: Missing `--` sentinel before filepath in ffprobe command — file paths starting with `-` interpreted as flags. Added `--` separator.
- [x] SEC-M2: Catbox upload URL not validated — could return malicious URL. Added `https://` prefix check.
- [x] P-M1: `_do_update_status` (and 3 other status slots) called `setStyleSheet` on every invocation. Added last-color cache to skip redundant QSS parsing.
- [x] P-M2: Batch clipboard progress emitted unthrottled lambdas flooding GUI event queue (~1500+ events per batch). Added 250ms throttle gate.
- [x] TQ-M1: `stop_download` with `current_process=None` test missing state assertion. Strengthened with `current_process is None` check.

### Low (14)
- [x] CQ-L1: Dead signals `sig_update_url_status`, `sig_downloads_finished` in ClipboardManager — never emitted. Removed.
- [x] CQ-L2: Dead signals `sig_set_upload_url`, `sig_set_uploader_url` in UploadManager — never emitted. Removed with connections and slots.
- [x] CQ-L3: Dead signals `sig_set_mode_label`, `sig_set_video_info`, `sig_set_filesize_label` on YouTubeDownloader — never emitted. Removed with connections and slots.
- [x] CQ-L4: 7 dead widget builder methods (`_group`, `_int_row`, `_float_row`, `_pct_row`, `_bool_row`, `_combo_row`, `_label_row`), `self.widgets` dict, and unused imports (`QSpinBox`, `QDoubleSpinBox`, `QGroupBox`). Removed.
- [x] CQ-L5: Double `shutil.rmtree` on same `temp_dir` in 10MB path — `_post_ytdlp_10mb_encode` and `download()` finally block both cleaned it. Removed from `_post_ytdlp_10mb_encode`.
- [x] CQ-L6: `height` passed as `str` to `build_vf_args(scale_height: int | None)` — cast to `int(quality)`. Also fixed default `quality` from `""` to `"720"` in `download_local_file`.
- [x] SEC-L1: SIDX parser division by zero on crafted `timescale=0`. Added early return.
- [x] SEC-L2: SHA256SUMS hash value not validated as 64-char hex string. Added `re.fullmatch` validation (both app and yt-dlp update paths).
- [x] SEC-L6: `_open_folder` passes path to `os.startfile`/`xdg-open` without validation. Added `os.path.isdir` check.
- [x] P-L1: `_update_url_status` performed triple dict lookup. Reduced to single `.get()` call.
- [x] P-L2: `_poll_clipboard` acquired lock unnecessarily for GUI-thread-only boolean check. Removed lock.
- [x] TQ-L1: Redundant type-only assertions on `calculate_optimal_quality`. Replaced with value-checking test.
- [x] TQ-L2: NVENC/AMF CRF tests only checked encoder name. Added `-qp`/`-qp_i` and `23` assertions.
- [x] TQ-L3: Thread pool leak on assertion failure in `TestTrimHistoryOnStartup` and `TestSaveUploadLinkPeriodicTrim`. Converted to pytest fixture with yield+shutdown.
- [x] TQ-L4: `TestTrimmingManagerCache` fixture missing `_stream_url_cache`. Added with assertion on `clear_preview_cache`.
- [x] DO-L1: Inconsistent platform conditions (`matrix.os == 'ubuntu-latest'` vs `runner.os == 'Linux'`). Standardized to `runner.os`.

</details>

## Fixed Issues (audit 8 — 15 fixed)

<details>
<summary>Click to expand</summary>

### High (2)
- [x] CQ-H1: `uploader_is_uploading` never reset after `process_uploader_queue` completes — next queue upload silently blocked. Added `finally` block.
- [x] TQ-H1: `test_windows_system_dir_blocked` and `test_windows_normal_path_allowed` had tautological assertions (`isinstance(valid, bool)`). Now assert `valid is False`/`True` and check error messages.

### Medium (6)
- [x] CQ-M1: Batch clipboard counters never updated — in-lock `item["status"]` mutations raced with `_update_url_status`, causing "Completed: 0" after batch downloads. Removed in-lock mutations; `_update_url_status` is sole source of truth.
- [x] CQ-M2: `closeEvent` checked `self._updating` (always False on main window) instead of `self.update_mgr._updating` — window could close during active self-update.
- [x] TQ-M1: `TestExtractingUrlRegex` tested a locally duplicated regex, not the production `_EXTRACTING_URL_RE`. Now imports from `downloader_pyqt6`.
- [x] DO-M1: `test.yml` concurrency group `test-${{ github.ref }}` could cancel release's test phase on concurrent push. Added `${{ github.workflow }}` to disambiguate.
- [x] P-M1: Upload history file read blocked GUI thread in `view_upload_history`. Offloaded to thread pool with callback.
- [x] P-M2: O(n) linear scans of `clipboard_url_list` in batch download hot path (7× per URL transition under lock). Eliminated by removing in-lock mutations (covered by CQ-M1 fix).

### Low (7)
- [x] SEC-L1: Missing `_validate_tag_name` in `_apply_update_frozen` — source update validated it, frozen didn't.
- [x] CQ-L1: 6 dead state variables on `YouTubeDownloader` (`start_preview_image`, `end_preview_image`, `preview_update_timer`, `last_preview_update`, `local_file_path`, `uploader_current_index`) + dead assignments removed.
- [x] CQ-L2: `TIMEOUT_CHECK_INTERVAL` imported inside `__init__` instead of top-level — moved to top-level import block.
- [x] CQ-L3: Dead method `_monitor_download_timeout` (blocking loop) replaced by `_monitor_download_timeout_tick` — removed method, rewrote 5 tests to use tick API (net -1 test from merged early-exit tests).
- [x] P-L1: `_sha256sums_cache` grew unbounded across update checks — cleared at start of `_check_for_updates`.
- [x] TQ-L1: `TestTrimmingManagerErrorImage` mutated class singleton without cleanup guarantee — switched to `monkeypatch.setattr`.
- [x] TQ-L2: `TestParseYtdlpOutputErrorLineCap` used non-standard `__import__("unittest.mock")` — replaced with standard `from unittest.mock import patch`.

</details>

## Fixed Issues (post-audit cleanup — 17 fixed, 28 new tests)

<details>
<summary>Click to expand</summary>

### Code quality refactors (6)
- [x] CQ-3: Duplicated UI state snapshot pattern — extracted `_snapshot_clipboard_state()` helper.
- [x] CQ-6: Progress dialog code duplicated 3× in update_manager — extracted `_make_progress_helpers()`.
- [x] CQ-L11: `check_dependencies` and `_detect_hw_encoder` moved from main window to DownloadManager.
- [x] DO-9: Ruff rules expanded from E,F,W,I to include B (bugbear), UP (pyupgrade), S (bandit). Fixed all violations.
- [x] DO-6: Test workflow extended with Windows CI matrix (`ubuntu-latest` + `windows-latest`).
- [x] UP024/UP041/UP035/B904: Modernized exception aliases, import paths, `raise from` chains.

### Performance (3)
- [x] P-08: 7 `setStyleSheet()` calls during theme toggle batched into 1 via QSS object names.
- [x] P-12: O(n) scans in `_auto_download_single_url` and `_update_auto_download_total` replaced with `downloading_count` counter (O(1)).
- [x] P-L3: `_http_range_read` max_size guard added (512KB cap with ValueError on exceed).

### Tests (28 new — 340 total, was 312)
- [x] TQ-1: `_apply_update_frozen_windows` — SHA-256 verification, download too small, hash mismatch (3 tests)
- [x] TQ-2: `_apply_ytdlp_update_binary` — SHA-256 mismatch aborts, missing binary in SHA256SUMS (2 tests)
- [x] TQ-3: `_apply_ytdlp_update_pip` — success, failure with stderr, timeout (3 tests)
- [x] TQ-4: `download()` — PermissionError and OSError handlers (2 tests)
- [x] TQ-5: `_post_ytdlp_10mb_encode` — empty temp dir, custom name, cleanup (3 tests)
- [x] TQ-6: `validate_download_path` — Windows blocked dirs, normal path, traversal (3 tests)
- [x] TQ-7: `_download_video_trimmed_10mb_path` — trim+encode pipeline, failure skips encode, cleanup (3 tests)
- [x] TQ-9: `test_10mb_path_taken` — strengthened with `_post_ytdlp_10mb_encode` assertion and temp dir check (2 tests)
- [x] TQ-L7: `download_local_file` 10MB path — calls `size_constrained_encode` (1 test)
- [x] P-L3: `_http_range_read` max_size guard — exceeds raises, within OK (2 tests)
- [x] CQ-L11: `check_dependencies` and `detect_hw_encoder` — all ok, ytdlp missing, no encoder, deps_not_ok (4 tests)

</details>

## Fixed Issues (audit 7 — 32 total)

<details>
<summary>Click to expand</summary>

### High (1 — functional bug)
- [x] CQ-H1: `closeEvent` saves window geometry after `thread_pool.shutdown()` — geometry lost on every close. Moved geometry save before pool shutdown with synchronous write.

### Medium (13)
- [x] CQ-M1: Duplicate/inconsistent URL status methods (`_do_update_url_status` dead code with different colors). Removed dead method.
- [x] CQ-M2: Batch clipboard status race — worker deferred status via `_safe_after` while persist could fire in between. Now updates data model immediately under lock.
- [x] CQ-M3: Nested lock acquisition (auto_download_lock → clipboard_lock) without documented ordering. Added ordering comment.
- [x] SEC-M1: Unsanitized `tag_name` from GitHub API interpolated into download URLs. Added regex validation.
- [x] SEC-M2: `browser_download_url` from GitHub API used without domain pinning. Added `startswith(github.com/REPO)` check.
- [x] P-M2: Per-chunk signal emission floods Qt event queue (~3200 events for 200MB download). Added 250ms throttle.
- [x] TQ-M1: Cache eviction test used wrong `PREVIEW_CACHE_SIZE` (comment said 50, constant is 20). Now imports constant.
- [x] TQ-M2: `TestEncodingStderrThreadTimeout` used bare MagicMock instead of proper `EncodeCallbacks`.
- [x] TQ-M4: `_get_ytdlp_version` zero tests — added 3 tests (success, failure, exception).
- [x] TQ-M5: `_download_audio_trimmed` success path untested — added test verifying correct ffmpeg args.
- [x] TQ-M3: `_download_trimmed_via_ffmpeg` wrapper temp cleanup untested — added 2 tests (success+failure).
- [x] CQ-M4: Clipboard backend methods on main window — moved `_detect_clipboard_backend`, `read_clipboard_content` to ClipboardManager.
- [x] DO-M1: `create-release` job missing `timeout-minutes` — added 15min.
- [x] DO-M2: External binary downloads (ffmpeg, yt-dlp) had no retry logic — added retry for wget and PowerShell.
- [x] DO-M3: Test coverage not measured for `downloader_pyqt6.py` — added `--cov=downloader_pyqt6`.

### Low (18)
- [x] CQ-L1: Dead method `_add_tab` (template artifact) — removed.
- [x] CQ-L2: Empty `_load` method (no-op template hook) — removed method and call.
- [x] CQ-L3: Split PyQt6 imports (QImage, QDialog, QTextEdit separate from main block) — consolidated.
- [x] CQ-L4: Unnecessary `getattr(self, ..., default)` for guaranteed attributes — replaced with direct access.
- [x] CQ-L5: `_config_save_timer` lazily created via `hasattr` — initialized in `__init__`.
- [x] CQ-L6: Magic number 500 for clipboard URL cap — added `MAX_CLIPBOARD_URLS` constant.
- [x] CQ-L9: `on_start/end_slider_change` ignored `value` parameter — renamed to `_value`.
- [x] CQ-L10: Redundant `_finish_download()` calls in trimmed download sub-paths (already handled by `download()` finally block).
- [x] SEC-L1: Source update used non-atomic `shutil.move` — replaced with `os.replace`.
- [x] SEC-L2: Persisted clipboard URLs restored without re-validation — added `validate_youtube_url()` check.
- [x] SEC-L3: Linux frozen update `os.chmod` after `shutil.move` — chmod before move for atomic permission.
- [x] P-L1: `sanitize_filename` performed 21 sequential `str.replace()` calls — replaced with single `str.translate()`.
- [x] P-L2: `_save_clipboard_urls` synchronous file I/O on GUI thread — offloaded to thread pool.
- [x] DO-L1: `generate_release_notes: true` silently overridden by `body:` — removed misleading config.
- [x] DO-L2: CodeQL workflow missing concurrency group — added.
- [x] DO-L3: `dependabot-auto-merge` job missing job-level timeout — added 45min.
- [x] DO-L4: `requirements.lock` missing `dbus-python` platform marker — added with `sys_platform == 'linux'`.
- [x] TQ-L6: `_check_for_updates` silent=False paths untested — added test for non-silent up-to-date.
- [x] CQ-L7: `_cleanup_old_updates` on main window — moved to `UpdateManager.cleanup_old_updates()` static method.
- [x] CQ-L8: `_cleanup_old_temp_dirs` on main window — moved to `TrimmingManager.cleanup_old_temp_dirs()`.
- [x] P-L4: `_finish_clipboard_downloads` O(n) scans — added `completed_count`/`failed_count` counters to ClipboardManager.
- [x] P-L5: Per-download daemon thread for timeout — replaced with persistent `_download_timeout_timer` QTimer.
- [x] TQ-L5: `upload_to_catbox` didn't verify `is_uploading=True` during upload — added test.

### Tests (19 new — 312 total, was 293)
- [x] `is_local_file` URL scheme guard regression tests (3): http+mp4, ftp+mkv, http+mp3
- [x] `validate_youtube_url` unrecognized YouTube paths (3): /channel, /feed, /about
- [x] `_validate_tag_name` and `_validate_download_url` (4): valid/invalid tags and URLs
- [x] `_get_ytdlp_version` (3): success, nonzero returncode, exception
- [x] `_check_for_updates` silent=False (1): non-silent shows "up to date" messagebox
- [x] `_download_audio_trimmed` success path (1): verifies correct ffmpeg args including `-vn`
- [x] `_apply_update_source` rollback (1): verifies error messagebox emitted
- [x] `_get_update_asset_url` external URL rejection (1): verifies None for non-GitHub URLs
- [x] `_download_trimmed_via_ffmpeg` wrapper (2): temp dir cleaned on success and failure
- [x] `upload_to_catbox` (1): verifies is_uploading=True during upload

</details>

## Fixed Issues (audit 6 — 16 total)

<details>
<summary>Click to expand</summary>

### Critical (1 — functional bug)
- [x] BUG-1: 3 broken signal connections lost during manager extraction — `_show_update_dialog`, `_show_ytdlp_update_dialog` (methods missing), `stop_download` (connected to self instead of download_mgr)

### High (3)
- [x] DO-3: GH Actions script injection via `${{ inputs.version }}` in shell `run:` blocks — replaced with `env:` variable indirection
- [x] CQ-14: `is_local_file` matched URLs with media extensions (e.g. `https://…/video.mp4`) — added scheme guard
- [x] SEC-7: TOCTOU in yt-dlp binary update between symlink check and remove+rename — replaced with `os.replace()` atomic rename

### Medium (8)
- [x] SEC-3: Non-atomic config/clipboard writes risk corruption on crash — write-to-tmp + `os.replace()`
- [x] SEC-5: Source-mode restart propagated unsanitized `sys.argv` — now uses known script path
- [x] SEC-1: Volume value passed via f-string to ffmpeg args without validation in builders — added `float()` coercion
- [x] CQ-2: `stderr_lines` in `download_local_file` was unbounded plain list — replaced with `deque(maxlen=200)`
- [x] CQ-4: `_sha256sums_cache` created lazily via `getattr` — initialized in `__init__`
- [x] CQ-13: yt-dlp error detection matched any line containing "error" substring — tightened to `ERROR:` prefix or `[error]` tag
- [x] CQ-16: Linux frozen update had no post-extraction integrity check — added size guard (< 1024 bytes = corrupt)
- [x] DO-1: `validate` job in build-release.yml missing `timeout-minutes` — added 5min

### Low (4)
- [x] CQ-5: `_compute_git_blob_sha` was instance method but didn't use `self` — added `@staticmethod`
- [x] CQ-11: `_version_newer` had no documented invariant for X.XX format — added docstring clarification
- [x] SEC-4: `APP_DATA_DIR.mkdir()` used default permissions (world-readable on Linux) — added `mode=0o700`
- [x] DO-4: `dbus-python` unpinned in build and test CI — pinned to 1.3.2

</details>

## Fixed Issues (audit 5 — 15 total)

<details>
<summary>Click to expand</summary>

### Critical (1)
- [x] C-1: `UnboundLocalError` in `stop_clipboard_downloads` — `stopped` used before assignment when auto-downloading inactive

### High (1)
- [x] H-1: Race condition in `_drain_stderr` — closure captured `self.current_process` which could become None; captured to local

### Medium (5)
- [x] M-1: Missing `--` sentinel before URLs in 4 yt-dlp commands (trimming_manager:96, :264, downloader_pyqt6:3222, download_manager:1210)
- [x] M-3: Missing symlink check before yt-dlp binary replacement in `_update_ytdlp`
- [x] M-4: `_cleanup_old_temp_dirs` ran on GUI thread via QTimer — moved to thread pool
- [x] M-6: Test CI used `requirements.txt` (ranges) while build used `requirements.lock` (pinned) — aligned to `.lock`
- [x] M-7: `dependabot-auto-merge.yml` used `synchronize` event — removed (redundant with `--auto`)

### Medium (2, formerly deferred)
- [x] M-2: Inline yt-dlp command duplication — refactored audio/10MB/normal paths to use builders
- [x] M-5: `_fetch_file_size` used expensive `--dump-json` — replaced with `--print filesize,filesize_approx`

### Tests (51 new — 293 total, was 242)
- [x] `_monitor_download_timeout` progress stall: normal 600s and trim 1200s thresholds (2)
- [x] `_do_trimmed_download`: cancel after video/audio, merge failure, volume reencode, copy codec (5)
- [x] `_apply_update_source` rollback on partial write failure (1)
- [x] `_apply_update_frozen_linux` symlink guard and tar traversal defense (2)
- [x] `_download_stream_segment` error wrapping: URLError, socket.timeout, OSError (3)
- [x] `_parse_ytdlp_output` error line cap at 100 (1)
- [x] `ClipboardManager` deque FIFO, stop_event lifecycle, _shutting_down flag (3)
- [x] `EncodingService.run_ffmpeg_with_progress` stderr thread join timeout (1)
- [x] `download_local_file` FileNotFoundError and generic exception paths (2)
- [x] `UploadManager._trim_history_on_startup` over/under 500 lines (2)
- [x] `save_upload_link` periodic trimming at 100 saves (1)
- [x] `_get_update_asset_url` Windows/Linux/missing asset (3)
- [x] `_is_onedir_frozen` source/onefile/onedir modes (3)
- [x] `_sha256_file` chunked hashing with actual file + empty file (2)
- [x] `update_previews_thread` end-time adjustment near/far from EOF (2)
- [x] `_fetch_local_file_duration` ffprobe error and non-numeric duration (2)

### Low (8)
- [x] L-1: Redundant `import tempfile` inside `_apply_update_frozen_windows`
- [x] L-2: Clipboard status update scanned deque O(n) — now uses `clipboard_url_widgets` dict O(1)
- [x] L-3: `check_dependencies` ran yt-dlp `--version` twice — consolidated
- [x] L-4: `_cleanup_old_updates` ran synchronous I/O on GUI thread during `__init__` — offloaded to thread pool
- [x] L-5: Coverage threshold documented as 70% but enforced at 55% — fixed documentation
- [x] L-6: Lint job missing `cache-dependency-path` — added
- [x] L-7: Two separate `pip install` commands in build job — combined
- [x] L-8: cosign `sign-blob` step missing `name:` label — added

</details>

## Fixed Issues (audit 4 — 20 total)

<details>
<summary>Click to expand</summary>

### Security (3)
- [x] SEC-1: BAT trampoline path injection — added batch-special char validation before writing .bat
- [x] SEC-2: Clipboard URLs written to batch file without newline/null stripping — sanitized
- [x] SEC-6: Symlink race in Linux binary update — added `is_symlink()` check before `shutil.move`

### Performance (3)
- [x] PERF-1: O(n) `list.pop(0)` on clipboard URL eviction — replaced with `collections.deque.popleft()`
- [x] PERF-3: Config flush synchronous on GUI thread — offloaded to worker thread via `thread_pool.submit()`
- [x] PERF-7: Silent thread join timeout in encoding — added `is_alive()` check with warning log

### DevOps (10)
- [x] DO-1: Lint job missing pip cache — added `cache: 'pip'` to lint job
- [x] DO-2: Build job upgrades pip without pinning — removed unnecessary `pip install --upgrade pip`
- [x] DO-4: Cosign binary version not pinned — pinned to v2.4.1
- [x] DO-6: Dependabot auto-merge CI wait no timeout — added `timeout-minutes: 30`
- [x] DO-7: Missing `workflow_dispatch` on test.yml and codeql.yml — added
- [x] DO-9: Dependabot groups GH Actions together — split into major vs minor/patch groups
- [x] DO-10: No post-build artifact validation — added Linux/Windows validation steps
- [x] DO-12: Release concurrency allows parallel builds — changed to global `release` group
- [x] DO-13: No dependency lock file — created `requirements.lock` with pinned versions for CI builds
- [x] DO-14: Artifact download has no integrity check — added existence/size verification step

### Test Quality (4)
- [x] TQ-1: `_download_stream_segment_inner` missing error path tests — added network timeout + cancellation tests
- [x] TQ-2: `_download_audio_trimmed` missing error handling tests — added 3 tests (stream fail, cancel, ffmpeg fail)
- [x] TQ-11: Weak test assertions (call count only) — added path verification and flag assertion tests

### False Positives Removed (12)
CQ-3 (pipe cleanup exists), CQ-4 (TOCTOU already fixed), CQ-7 (guard exists), CQ-8 (standard pattern),
SEC-3/DO-3 (accepted DO-5), SEC-7 (cert pinning overkill), SEC-8 (resolve handles symlinks),
PERF-2 (256KB buffered), PERF-5 (deque capped), PERF-6 (accepted M-17), DO-11 (auto-masked)

</details>

## Fixed Issues (audit 3, pass 2 — 12 additional)

<details>
<summary>Click to expand</summary>

### Medium (6)
- [x] M-8: Progress dialog ordering — verified correct (non-issue)
- [x] M-10: `_on_uploader_queue_done` now only clears queue if completed normally
- [x] M-20: Clipboard batch downloads use single `--batch-file` process (playlist URLs fall back to per-URL)
- [x] M-22: `test.yml` callable via `workflow_call`; `build-release.yml` reuses it
- [x] M-23: `workflow_dispatch` gains `dry_run` input; skips build when true

### Low (7)
- [x] L-4: Dead `encode_args` parameter removed from trimmed download methods
- [x] L-6: `validate_download_path` allows any absolute path on Windows except system dirs
- [x] L-8: `_fetch_file_size` captures `ytdlp_path` as local before closure
- [x] L-10: `UploadManager.__init__` trims history to 500 lines at startup
- [x] L-13: `_init_temp_directory` defers old-dir cleanup via `QTimer.singleShot`
- [x] L-14: Clipboard backend detected once at startup, cached in `_clipboard_backend`
- [x] L-15: `clipboard_downloading` replaced with `clipboard_stop_event` (threading.Event)
- [x] L-29: pytest==8.3.4 and pytest-cov==6.0.0 pinned in test.yml

### Test coverage (39 new tests — GH#20)
- [x] `_http_range_read` (3 tests)
- [x] `_get_stream_urls` (3 tests)
- [x] `download_local_file` (3 tests)
- [x] `_get_expected_sha256` (4 tests)
- [x] `_check_for_updates` (3 tests)
- [x] `fetch_video_duration` (6 tests)
- [x] `extract_frame` (3 tests)
- [x] `upload_to_catbox` (3 tests)
- [x] `process_uploader_queue` / `start_queue_upload` (5 tests)
- [x] `encode_single_pass` / `encode_two_pass` (6 tests)

</details>

## Fixed Issues (audit 3, pass 1 — 50 total)

<details>
<summary>Click to expand</summary>

### High (7)
- [x] `_init_dependencies_async` race with download start — apply mutations on GUI thread via signal
- [x] `_apply_update_source` no rollback on partial failure — added backup restore loop
- [x] Thread pool exhaustion (5 workers, 8+ consumers) — increased to 8 workers
- [x] Dependabot auto-merge no CI gate — added `gh pr checks --watch` step
- [x] `_parse_ytdlp_output` zero tests — 6 tests covering progress, errors, merger, stop
- [x] `_download_stream_segment_inner` zero tests — 4 tests covering params, estimation, byte range
- [x] `_verify_file_against_github` zero tests — 4 tests covering hash match/mismatch, SHA-256 mandatory

### Medium (22)
- [x] `--` missing before URL in `_get_stream_urls` — added `--` separator
- [x] `--` missing before URL in download 10MB path and normal path — added `--` separator
- [x] 30s timeout too short for large byte-range downloads — increased to 120s
- [x] `_error_image` classmethod not thread-safe — double-checked locking with `threading.Lock`
- [x] `process_uploader_queue` reports wrong upload count — track successful uploads explicitly
- [x] Speed limit args appended after `--` in clipboard download — insert before separator
- [x] `on_url_change` doesn't reset `trimming_mgr.video_duration` — added reset
- [x] `stop_download` doesn't set `current_process = None` — set after cleanup
- [x] `encoding.get_video_encoder_args` crashes on `target_bitrate=None` — added validation guard
- [x] `run_ffmpeg_with_progress` pipe leak on success — added `safe_process_cleanup` on success path
- [x] `upload_to_catbox` TOCTOU on `last_output_file` — captured to local variable
- [x] `_download_clipboard_url` process pipe leak — moved cleanup to `finally` block
- [x] SHA-256 reads entire binary into memory (3 sites) — created chunked `_sha256_file` helper
- [x] `_save_config_key` synchronous disk write on GUI thread — debounced with 500ms QTimer
- [x] Redundant SHA256SUMS fetches during source update — cached per tag
- [x] No `permissions: {}` top-level on 4 workflow files — added least-privilege default
- [x] No concurrency control on workflows — added concurrency groups
- [x] `ruff` version not pinned in CI — pinned to 0.9.7
- [x] No coverage threshold enforcement — added `--cov-fail-under=55` (managers-only scope)
- [x] No `timeout-minutes` on jobs — added to all workflows
- [x] `_find_latest_file` uses 2N stat calls — replaced with `os.scandir`
- [x] `check_dependencies` parallel opportunity — documented (kept sequential for simplicity)

### Low (21)
- [x] `_http_range_read` hardcoded 60s timeout — use constant from `DOWNLOAD_PROGRESS_TIMEOUT_TRIM`
- [x] Duplicate `clip_duration` calculation in `download_local_file` — removed duplicate
- [x] `seconds_to_hms` garbage output on negative input — added `max(0, seconds)` guard
- [x] Checkbox temp dir never cleaned up — registered cleanup in `closeEvent`
- [x] Fallback `clip_state` quality `"best"` invalid — changed to `"1080"`
- [x] Uncompiled regex in clipboard download loop — pre-compiled `_PLAYLIST_ITEM_RE`
- [x] `dbus` imported at module level on Windows — guarded behind `sys.platform` check
- [x] Binary tar extraction loads entire file into memory — stream via `shutil.copyfileobj`
- [x] Segment download file write not buffered — added `buffering=256 * 1024`
- [x] Flaky `test_finds_latest` (50ms sleep) — removed timing dependency
- [x] `run.sh` has no error handling — added `set -euo pipefail`
- [x] `update_progress` clamping not tested — 4 tests for boundary values
- [x] `seconds_to_hms` negative not tested — 2 tests added
- [x] URL length validation not tested — test for >2048 chars
- [x] `get_video_encoder_args` bitrate=None not tested — ValueError test added
- [x] `calculate_optimal_quality` return typing not tested — tuple typing test added
- [x] ruff E402 from conditional imports — added per-file-ignore in ruff.toml
- [x] Test assertion for `MAX_WORKER_THREADS` updated (5 → 8)
- [x] 242 tests total (was 154)

</details>

## Fixed Issues (audit 2 — 47 total)

<details>
<summary>Click to expand</summary>

### Key fixes
- Critical: clipboard download crash, missing clipboard signals
- Security: source-mode self-update SHA-256, tar traversal, `--` before URLs, memory bounds
- Performance: removed PIL, daemon timeout, cached pixmaps, in-memory config
- DevOps: test gate, Python 3.11, dependabot scope, pinned PyInstaller, pytest-cov
- Tests: 154 total (was 130)
- Cleanup: ~15 dead imports, dead test class, PROGRESS_REGEX dedup

</details>

## Fixed Issues (audit 1 — 53 total)

<details>
<summary>Click to expand — Critical (5), High (12), Medium (18), Low (15)</summary>

See git history for full details.

</details>
