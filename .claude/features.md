# Features

## Clipboard Monitoring (Clipboard Mode tab)
Detection priority: `dbus` (KDE Klipper, Linux) → `pyperclip` → Qt clipboard
- QTimer-based polling
- Auto-detects YouTube/supported URLs, maintains session list

## Catbox Upload (Uploader tab)
- `catboxpy` library, max 200MB
- History: `~/.youtubedownloader/upload_history.txt` (max 1000 lines)
- Queue protected by `uploader_lock` (RLock)
- No timeout/cancel — library limitation (accepted, see decisions.md)
- File input: "Add Files" dialog **or** drag & drop onto the tab (`_UploaderPage` subclass; both paths share `_add_files_to_uploader_queue`)
- Build bundles `requests` explicitly (transitive dep of `catboxpy`); `requirements.lock` pins `requests` and the PyInstaller command lists it as `--hidden-import` so the upload code path can run from the frozen exe
