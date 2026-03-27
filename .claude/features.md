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
