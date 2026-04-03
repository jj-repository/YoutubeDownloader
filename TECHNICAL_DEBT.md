# Technical Debt

Last updated: 2026-04-03

## Summary
**Total Issues**: 28 | Critical: 3 | High: 14 | Medium: 14 | Low: 11

## Critical Issues

- [ ] **Clipboard widget access from worker thread** — `update_clipboard_status`/`update_clipboard_progress` touch Qt widgets directly from background threads, causing crashes. (`downloader_pyqt6.py:2877`) [small]
- [ ] **Startup freeze** — `check_dependencies()` + `_detect_hw_encoder()` run synchronously in `__init__`, blocking up to 35s before the window appears. (`downloader_pyqt6.py:505`) [small]
- [ ] **`_parse_sidx` has zero tests** — Core trim byte-range logic is completely untested; root cause of long-video trim bugs. [small]

## High Issues

- [ ] **Self-update uses SHA1 only** — Source-mode self-update has no real cryptographic integrity check. (`downloader_pyqt6.py:6675`) [large]
- [ ] **Frozen binary update — no integrity check** — Windows/Linux exe update has no hash verification before replacing the running binary. (`downloader_pyqt6.py:6944`) [small]
- [ ] **`_get_speed_limit_args` reads widget from worker thread** — `self.speed_limit_entry.text()` called outside GUI thread. (`downloader_pyqt6.py:5999`) [small]
- [ ] **Dead `status_text` key lookup** — `_do_update_url_status` looks up a key that was never stored; URL status text never updates. (`downloader_pyqt6.py:1749`) [small]
- [ ] **`cmd` potentially unbound** — `cmd` referenced at log line but only defined in specific branches. (`downloader_pyqt6.py:6058`) [small]
- [ ] **`start_hms_file` potentially unbound** — Referenced in keep-below-10MB path but only set in trim-enabled guard. (`downloader_pyqt6.py:6134`) [small]
- [ ] **No timeout on ffmpeg merge** — `subprocess.run()` in trim merge step has no timeout; can hang forever. (`downloader_pyqt6.py:5137`) [small]
- [ ] **`download_local_file` stderr not drained** — No concurrent stderr read causes pipe deadlock on verbose ffmpeg output. (`downloader_pyqt6.py:6451`) [small]
- [ ] **HTTP range read has no cancellation** — `_http_range_read` stalls on slow CDN with no cancel hook; root cause of long-video trim hang. (`downloader_pyqt6.py:4939`) [medium]
- [ ] **Per-line `download_lock` in stdout loop** — Mutex acquired on every ffmpeg output line; expensive and unnecessary. (`downloader_pyqt6.py:5306`) [small]
- [ ] **Full EXE buffered in RAM during self-update** — 2x file size memory spike from accumulating chunks before writing. (`downloader_pyqt6.py:6947`) [small]
- [ ] **Tests test stubs, not real code** — All 59 unit tests reimplement logic locally instead of importing from production code. (`test_unit.py`) [medium]
- [ ] **`test_trimming.py`/`test_commands.py` not pytest** — Script-style tests with print(); collect 0 tests in pytest. [medium]
- [ ] **CI bundles unverified binaries** — ffmpeg/yt-dlp downloaded from `latest` with no checksum. (`build-release.yml:51`) [medium]

## Medium Issues

- [ ] **Unpinned GH Actions** — Third-party actions use mutable tags, not SHA pins. (all workflows) [small]
- [ ] **`dependabot-auto-merge` overly broad permissions** — `contents: write` + `pull-requests: write` on all PR events. (`dependabot-auto-merge.yml:4`) [small]
- [ ] **`validate_download_path` doesn't resolve symlinks** — Returns unresolved path; symlinks can point outside safe dirs. (`downloader_pyqt6.py:4372`) [small]
- [ ] **Volume value interpolated into ffmpeg args string** — Not exploitable currently but fragile pattern. (`downloader_pyqt6.py:4798`) [small]
- [ ] **God class** — `YouTubeDownloader` is 7100 lines with 130+ methods. (`downloader_pyqt6.py`) [large]
- [ ] **`download()` is 400 lines** — 8 nested paths with duplicated lookups and double-reset cleanup. (`downloader_pyqt6.py:5661`) [medium]
- [ ] **QTimer leaked on every URL keystroke** — New QTimer created per keystroke instead of reusing one. (`downloader_pyqt6.py:4082`) [small]
- [ ] **`_find_latest_file` uses ctime heuristic** — Can pick wrong file if other apps write to download dir. (`downloader_pyqt6.py:4703`) [medium]
- [ ] **Widget reads from worker thread in `_fetch_file_size`** — `quality_combo.currentText()` read outside GUI thread. (`downloader_pyqt6.py:3203`) [small]
- [ ] **Two sequential subprocess calls for duration+title** — Could be combined into one yt-dlp call. (`downloader_pyqt6.py:3046`) [small]
- [ ] **Upload history fully read+rewritten on every upload** — Unnecessary file I/O. (`downloader_pyqt6.py:4731`) [small]
- [ ] **O(n²) duplicate check in `_restore_clipboard_urls`** — List comprehension instead of dict lookup. (`downloader_pyqt6.py:1925`) [small]
- [ ] **CI `contents: write` too broad** — Build jobs only need read; only create-release needs write. (`build-release.yml:9`) [small]
- [ ] **Dependabot pip block is a no-op** — CI deps are inline, not in requirements.txt. (`dependabot.yml:2`) [small]

## Low Issues

- [ ] **`hms_to_seconds` returns 0 for invalid input** — Should return None for consistency. (`downloader_pyqt6.py:3457`) [small]
- [ ] **`"tmp_path" in locals()` antipattern** — Initialize `tmp_path = None` before try block. (`downloader_pyqt6.py:7368`) [small]
- [ ] **Duplicated slider enforcement** — `on_start/end_slider_change` duplicate logic already in `on_slider_change`. (`downloader_pyqt6.py:3409`) [small]
- [ ] **Unbounded `stderr_lines` list** — Use `deque(maxlen=200)` instead. (`downloader_pyqt6.py:5286`) [small]
- [ ] **Missing `sanitize_filename` on local file stems** — `input_path.stem` used directly without sanitizing. (`downloader_pyqt6.py:6321`) [small]
- [ ] **Audio format detection fragile** — `"mime=audio%2Fwebm" in url` check doesn't cover all formats. (`downloader_pyqt6.py:5203`) [small]
- [ ] **`current_process` race in `_run_ffmpeg_with_progress`** — Capture local ref before wait. (`downloader_pyqt6.py:5320`) [small]
- [ ] **Config read without lock at startup** — `CONFIG_FILE` read before `config_lock` initialized. (`downloader_pyqt6.py:431`) [small]
- [ ] **No pip caching in CI** — Missing `cache: 'pip'` on setup-python. (`build-release.yml:26`) [small]
- [ ] **No artifact retention period** — Default 90-day retention wastes storage. (`build-release.yml:100`) [small]
- [ ] **`constants.py` type inconsistency** — `Path(os.environ.get("LOCALAPPDATA", Path.home()))` mixes types. (`constants.py:86`) [small]

## Progress Tracking

Issues resolved will be checked off as fixes are committed.
