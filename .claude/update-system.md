# Update System

Fully implemented with integrity verification and UI toggle.

## Functions
- `_load/save_auto_check_updates_setting()` — config preference
- `_check_for_updates()` — GitHub API fetch
- `_version_newer()` — semantic version compare
- `_show_update_dialog()` — modal: Update Now / Open Releases / Later
- `_apply_update()` — download, verify, backup, apply

## GitHub
Repo: `jj-repository/YoutubeDownloader`
API: `https://api.github.com/repos/jj-repository/YoutubeDownloader/releases/latest`

## Integrity
- App files: verified against GitHub git tree SHA (blob hash)
- yt-dlp binary: verified against SHA2-256SUMS
- Syntax check via `compile()`
- `.py.backup` created before replacing each module
- All files verified before any replaced (atomic)
- All network ops have timeouts
- BAT trampoline rejects paths with batch-special characters (`"&|^<>%`)
- Linux update rejects symlink targets before overwriting binary
