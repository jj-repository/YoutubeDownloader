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

## Quality Standards
Target: reliable downloads, good UX. UI strings: inline English.
Do not optimize: download speed (yt-dlp/network), UI responsiveness, thumbnail caching — all done.

## Review (2026-03-27 — Production Ready)
Security: URL validation, no shell=True, config schema, git blob SHA + SHA256 verification, no injection, network timeouts, config lock, tempfile names ✓
Thread safety: download/clipboard/config/uploader locks, signals for all worker→GUI, `_shutting_down` flag ✓
Code quality: constants.py, config validation, error handling, log rotation (1MB), history cap (1000), cache cleanup ✓
