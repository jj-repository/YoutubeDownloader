# Decisions & Standards

## Design Decisions
| Decision | Rationale |
|----------|-----------|
| PyQt6 | Replaced tkinter; better appearance, signals/slots |
| yt-dlp | Best-maintained downloader |
| constants.py | Clean separation of limits/timeouts |
| Catbox | Convenient sharing |
| Clipboard monitoring | Copy URL → app detects |
| `.py.backup` before update | Safety before module replace |
| Signals for thread→GUI | Qt built-in; safe by design |

## Won't Fix
| Issue | Reason |
|-------|--------|
| ~~6000-line downloader_pyqt6.py~~ | Resolved: split into 7 manager modules (2026-04-04) |
| Hardcoded site patterns | yt-dlp handles detection; patterns are hints |
| `_find_latest_file` heuristic | Rare edge case, acceptable |
| No Catbox timeout/cancel | Library limitation |
| `run.sh` launches tkinter | Legacy; use `python downloader_pyqt6.py` |

## Known Issues
1. Hardcoded site patterns — not easily extensible
2. `run.sh` outdated

## Intentional Silent Except Patterns (Do Not Fix)
Audited 2026-04-05. All `except ...: pass` blocks are intentional — do not add logging or refactor.

| Pattern | Where | Why silent |
|---------|-------|------------|
| Best-effort file/temp cleanup | pyqt6:1601,2067,2121,2134,2678 / trim_mgr:412 / encoding:318 / update_mgr:979 | OS delete fails are non-critical |
| Feature/backend probing | pyqt6:2200,2207,2213 | Tries klipper→pyperclip→Qt, expected failures |
| Subprocess stream drain | download_mgr:1551 / encoding:178 | `(ValueError, OSError)` when process dies — normal |
| ffmpeg progress parsing | download_mgr:1571 / encoding:197 | `(ValueError, IndexError)` on malformed lines — skip |
| Optional import | pyqt6:98 | `except ImportError` for optional `dbus` |
| Corrupt config fallback | pyqt6:381,389 | Bad config/geometry → use defaults |
| Win32 API best-effort | pyqt6:316 | Dark titlebar; outer handler already logs |
| Input validation | utils:407 | Invalid speed limit → no limit args |

## Quality Standards
Target: reliable downloads, good UX. UI strings: inline English.
Do not optimize: download speed (yt-dlp/network), UI responsiveness, thumbnail caching — all done.

## Review (2026-04-05 — Audit 4 Complete)
Security: URL validation, no shell=True, config schema, git blob SHA + SHA256 verification, no injection, network timeouts, config lock, tempfile names, BAT trampoline path validation, symlink check on update, clipboard URL sanitization ✓
Thread safety: download/clipboard/config/uploader locks, signals for all worker→GUI, `_shutting_down` flag (main window only), config flush offloaded to worker thread ✓
Code quality: constants.py, config validation, error handling, log rotation (1MB), history cap (1000), cache cleanup, deque for clipboard URLs ✓
CI: reproducible builds via requirements.lock, cosign pinned, post-build validation, artifact integrity checks, dependabot major/minor split ✓
