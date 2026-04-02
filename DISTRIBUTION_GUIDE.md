# How to Share YoutubeDownloader with Your Friend

## Quick Answer

Send your friend the file: **`YoutubeDownloader-Linux.tar.gz`** (~35 MB)

That's it! They just need to extract it and run - **no additional software needed!**

---

## Instructions for Your Friend

### Step 1: Extract the Archive
```bash
tar -xzf YoutubeDownloader-Linux.tar.gz
cd YoutubeDownloader-Linux/
```

Or just right-click the file and select "Extract Here" in your file manager.

### Step 2: Run the App
```bash
./YoutubeDownloader
```

Or just double-click the `YoutubeDownloader` file.

**That's it!** All dependencies (ffmpeg, ffprobe, yt-dlp) are bundled inside the executable.

---

## What Your Friend Needs

### System Requirements:
- Linux (any distribution, 64-bit)
- About 100 MB of disk space
- Internet connection

### Dependencies:
**None!** All dependencies are bundled inside the executable:
- **ffmpeg/ffprobe** - bundled for video/audio processing
- **yt-dlp** - bundled for downloading videos
- **Python libraries** - bundled via PyInstaller

Your friend doesn't need to install Python, ffmpeg, yt-dlp, or anything else.

---

## Quick Start Example

```bash
# Extract
tar -xzf YoutubeDownloader-Linux.tar.gz
cd YoutubeDownloader-Linux/

# Run the app - that's it!
./YoutubeDownloader
```

---

## What's Inside the Archive

- **YoutubeDownloader** - The main executable (~35 MB, fully self-contained)
- **README.txt** - User documentation

---

## Sharing the File

You can share `YoutubeDownloader-Linux.tar.gz` via:
- Email attachment (if your provider allows ~35 MB)
- File sharing services (Google Drive, Dropbox, WeTransfer, etc.)
- USB drive
- Cloud storage

---

## Note

The app will:
- Save downloads to `~/Downloads` by default
- Let users choose video quality (240p to 1440p)
- Extract audio-only if needed
- Trim videos with visual frame previews
- Show real-time download progress
- Use space-efficient encoding (H.264/AAC)

Your friend doesn't need to know Python, set up virtual environments, install ffmpeg, or deal with any technical setup!

---

## For Windows Users

Send them **`YTDownloader.exe`** instead. Just download and run it directly. All dependencies are bundled.
