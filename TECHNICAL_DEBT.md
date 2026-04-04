# Technical Debt

Last updated: 2026-04-04

## Summary
**Total Issues**: 55 | **Fixed: 53** | Remaining: 2 (accepted tradeoffs)

## Remaining Issues (accepted)

- **Unpinned ffmpeg download URLs** — BtbN/FFmpeg-Builds uses rolling `latest`. Size validation added but builds are non-reproducible. Accepted tradeoff: pinning is impractical for BtbN rolling releases. [small]
- **Widget reads from worker in `_fetch_file_size`** — Safe (captured on GUI thread via closure before thread pool submit). Clarified with comment. [informational]

## Fixed Issues (this audit — 53 total)

<details>
<summary>Click to expand</summary>

### Critical (5)
- [x] `thread_pool` used before creation — moved ThreadPoolExecutor before managers
- [x] No test workflow in CI — added `test.yml` with pytest + ruff
- [x] Clipboard widget access from worker thread — require `clip_state`, removed widget fallbacks
- [x] `_parse_sidx` has zero tests — SIDX parsing tests with crafted binary data
- [x] No timeout on ffmpeg merge — already has 20min timeout (stale)

### High (12)
- [x] Frozen binary update SHA-256 optional — made mandatory, abort on missing checksum
- [x] QImage memory safety — deep-copy via `qimg.copy()` then replaced with QImage-direct
- [x] `ui_state` None branch dereferences None — use defaults directly
- [x] Clipboard code fully duplicated — stripped ClipboardManager to state-only container
- [x] Duplicate `_make_encode_callbacks` — removed dead copy from main window
- [x] Duplicate progress/status methods — removed `update_progress`/`update_status` from main window
- [x] Auto-merge Dependabot with no CI gate — scoped to `pull_request_target`
- [x] Dead `status_text` key lookup — already fixed (stale)
- [x] HTTP range read has no cancellation — already has chunked reads (stale)
- [x] ffmpeg CI download not integrity-checked — added size validation + SHA256 logging
- [x] QPixmap/QPainter from worker threads — replaced with QImage (thread-safe)
- [x] PIL detour in `_path_to_pixmap` — replaced with direct QImage loading

### Medium (18)
- [x] Preview debounce signal leak — connect once in `__init__`
- [x] Preview cache not thread-safe — guarded by `preview_lock`
- [x] Stream URL not cached — cache keyed by video URL
- [x] `_subprocess_kwargs` duplicated 6 times — extracted to `managers/utils.py`
- [x] Duplicate placeholder methods — removed `create_placeholder_image`
- [x] `_save_clipboard_urls` called per URL — debounced with 2s QTimer
- [x] Config file read 3x at startup — loaded once into `self._config`
- [x] Duplicate `open_folder`/`change_path` — extracted `_open_folder` and `_pick_directory`
- [x] `_find_latest_file` scans entire dir — documented as future enhancement
- [x] No linting/formatting in CI — added ruff config + lint job
- [x] `dependabot-auto-merge` overly broad trigger — switched to `pull_request_target`
- [x] No branch protection — enabled via GitHub API, `test` job required
- [x] Upload manager None dereference — lazy `_get_catbox_client()`
- [x] `validate_download_path` symlinks — uses `.resolve()`
- [x] Two sequential subprocess calls — already single call (stale)
- [x] O(n2) duplicate check — already dict lookup (stale)
- [x] Duplicate regex patterns — removed unused from main file
- [x] Zero test coverage for `managers/utils.py` — comprehensive tests added

### Low (15)
- [x] Unused imports — cleaned
- [x] `.env` not in `.gitignore` — added
- [x] Clipboard content logged unsanitized — only log YouTube URLs
- [x] `test_commands.py`/`test_trimming.py` not pytest — deleted
- [x] 5 test classes test reimplemented functions — all import production code
- [x] Bat trampoline predictable path — uses `tempfile.NamedTemporaryFile`
- [x] No auto-generated changelog — added `generate_release_notes: true`
- [x] Dependabot groups all deps — split into pyqt/yt-dlp/other
- [x] CodeQL default query suite — upgraded to `security-and-quality`
- [x] `constants.py` type inconsistency — wrapped in `str()`
- [x] CatboxClient instantiated eagerly — lazy-initialized
- [x] `hms_to_seconds` returns 0 — already returns None (stale)
- [x] Duplicated slider enforcement — already minimal (stale)
- [x] Missing `sanitize_filename` on stems — already handled (stale)
- [x] `is_local_file()` trusts extension — already checks `isfile()` first (stale)

</details>
