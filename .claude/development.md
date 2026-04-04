# Development

## Run
```bash
python downloader_pyqt6.py  # or ./venv/bin/python downloader_pyqt6.py
pip install -r requirements.txt
```
`run.sh` launches tkinter legacy — do not use.

## Dependencies
- `PyQt6`, `yt-dlp`, `catboxpy`
- Optional: `pyperclip` (clipboard), `dbus` (Linux KDE)
- `requirements.txt` — ranges for development; `requirements.lock` — pinned for CI builds

## Common Tasks
**Download behavior:** quality → `_on_quality_change()`; progress → parses yt-dlp output → `sig_update_progress`

**New signal (worker → GUI):**
1. `sig_foo = pyqtSignal(...)` on `YouTubeDownloader`
2. `self.sig_foo.connect(self._do_foo)` in `__init__`
3. `_do_foo(self, ...)` runs on GUI thread
4. `self.sig_foo.emit(...)` from worker

## Versioning
Default bump: **+0.0.1** unless told otherwise. Each component 0–9; rollover on overflow (0.0.9 → 0.1.0).
