# Technical Debt

Last updated: 2026-04-04

## Summary
**Audit 1**: 55 found, 53 fixed, 2 accepted
**Audit 2**: 48 found, 47 fixed, 1 remaining
**Audit 3**: 65 found, 62 fixed, 3 accepted

## Remaining Issues

- **DO-5**: ffmpeg downloaded from rolling `latest` URL with no SHA gate. Accepted — BtbN rolling releases make pinning impractical. [medium]
- **M-17**: No HTTP connection reuse for byte-range downloads. Accepted — urllib3 is transitive dep only, overhead small, no new dependency warranted. [medium]
- **M-28**: No `pip --require-hashes` for supply chain integrity in release builds. Accepted — PyInstaller pinned, full hash pinning too complex for the benefit. [medium]

### Accepted tradeoffs (from audit 1)
- **Widget reads from worker in `_fetch_file_size`** — Safe via closure. [informational]

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
- [x] No coverage threshold enforcement — added `--cov-fail-under=70`
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
