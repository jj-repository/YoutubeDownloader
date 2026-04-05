# Technical Debt

Last updated: 2026-04-05 (audit 7)

## Summary
**Audit 1**: 55 found, 53 fixed, 2 accepted
**Audit 2**: 48 found, 47 fixed, 1 remaining
**Audit 3**: 65 found, 62 fixed, 3 accepted
**Audit 4**: 38 raw → 21 validated (12 false positives removed), 20 fixed, 1 deferred
**Audit 5**: 39 raw (5 agents) → 18 unique after dedup, 17 fixed (incl. 2 formerly deferred), 0 remaining
**Audit 6**: 65 raw (5 agents) → 48 unique after dedup, 16 fixed, 12 deferred (refactors/medium effort), 20 test gap findings documented
**Audit 7**: 50 raw (5 agents) → 44 unique after dedup, 39 fixed (2 iterations), 5 deferred

## Remaining Issues

- **DO-5**: ffmpeg downloaded from rolling `latest` URL with no SHA gate. Accepted — BtbN rolling releases make pinning impractical. [medium]
- **M-17**: No HTTP connection reuse for byte-range downloads. Accepted — urllib3 is transitive dep only, overhead small, no new dependency warranted. [medium]
- **M-28**: No `pip --require-hashes` for supply chain integrity in release builds. Accepted — PyInstaller pinned, full hash pinning too complex for the benefit. [medium]
- **DO-8**: Release notes not structured (no CHANGELOG.md). Deferred — `generate_release_notes: true` sufficient for current scale. [low]

### Deferred (audit 7 — remaining)
- **CQ-M5**: Clipboard download subprocess creation duplicated in main window — should delegate to DownloadManager. [medium]
- **P-M1**: O(n) indexed deletion on deque in _remove_url_from_list — bounded at 500, acceptable for user-triggered action. [low]
- **CQ-L11**: check_dependencies and _detect_hw_encoder on main window, belong on DownloadManager. [low]
- **TQ-L7**: download_local_file 10MB cancellation path (is_downloading=False during encoding) untested. [low]
- **P-L3**: _http_range_read has no max_size guard (currently capped at 512KB by caller). [low]

### Deferred (audit 6 — refactors, medium effort)
- **CQ-3**: Duplicated UI state snapshot pattern across 6 call sites. Deferred — works correctly, refactor is cosmetic. [medium]
- **CQ-6**: Progress dialog code duplicated 3× in update_manager.py. Deferred — refactor, ~150 lines. [medium]
- **P-08**: Multiple setStyleSheet passes during theme toggle. Deferred — needs QSS object-name refactor. [medium]
- **P-12**: Nested locks in auto-download on GUI thread. Deferred — O(n) scan in `_finish_clipboard_downloads` fixed via counters in audit 7, but `_auto_download_single_url` still scans. [medium]
- **DO-6**: Test workflow runs only on ubuntu-latest, no Windows. Deferred — needs matrix + conditional steps. [medium]
- **DO-9**: Ruff select rules minimal (E, F, W, I only). Deferred — enable B, UP, S incrementally. [medium]

### Test coverage gaps (audit 6 — 20 findings, see GH#20)
- **TQ-1** [critical]: `_apply_update_frozen_windows` untested (rename-dance, bat trampoline, rollback)
- **TQ-2** [critical]: `_apply_ytdlp_update_binary` untested (SHA-256 verify, symlink guard)
- **TQ-3** [high]: `_apply_ytdlp_update_pip` untested (success/failure/timeout)
- **TQ-4** [high]: `download()` PermissionError/OSError handlers untested
- **TQ-5** [high]: `_post_ytdlp_10mb_encode` untested (empty temp dir, success, failure)
- **TQ-6** [high]: `validate_download_path` Windows branch untested
- **TQ-7** [high]: `_download_video_trimmed_10mb_path` full pipeline untested
- **TQ-8** [medium]: `test_cancellation_during_data_download` xfail masks real gap
- **TQ-9** [medium]: `test_10mb_path_taken` weak assertions (only checks is_downloading)
- **TQ-10–20** [medium/low]: Various smaller coverage gaps in update_manager, download_manager, upload_manager

### Accepted tradeoffs (from audit 1)
- **Widget reads from worker in `_fetch_file_size`** — Safe via closure. [informational]

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
