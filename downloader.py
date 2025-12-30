#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import sys
import subprocess
import threading
import re
import logging
from pathlib import Path
from PIL import Image, ImageTk, ImageDraw, ImageFont
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs
from catboxpy.catbox import CatboxClient

# Try to import dbus for KDE Klipper integration
try:
    import dbus
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False

# Try to import pyperclip for cross-platform clipboard support
try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False

# Configure logging
log_dir = Path.home() / ".youtubedownloader"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "youtubedownloader.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
PREVIEW_WIDTH = 240
PREVIEW_HEIGHT = 135
SLIDER_LENGTH = 400
PREVIEW_DEBOUNCE_MS = 500
PROCESS_TERMINATE_TIMEOUT = 3
TEMP_DIR_MAX_AGE = 3600  # 1 hour
DOWNLOAD_TIMEOUT = 3600  # 60 minutes max for any download
DOWNLOAD_PROGRESS_TIMEOUT = 600  # 10 minutes without progress = stalled
PREVIEW_CACHE_SIZE = 20  # Cache up to 20 preview frames
MAX_WORKER_THREADS = 3  # Thread pool size for background tasks
MAX_RETRY_ATTEMPTS = 3  # Retry network operations up to 3 times
RETRY_DELAY = 2  # Seconds between retry attempts

# Performance constants
CLIPBOARD_POLL_INTERVAL_MS = 500  # Poll clipboard every 500ms (was 100ms)
VIDEO_CRF = 23  # Video quality (lower = better, 18-28 range)
AUDIO_BITRATE = '128k'  # Audio bitrate for downloads
BUFFER_SIZE = '16K'  # Download buffer size
CHUNK_SIZE = '10M'  # HTTP chunk size
CONCURRENT_FRAGMENTS = '5'  # Parallel fragment downloads
UI_UPDATE_DELAY_MS = 100  # UI update delay in milliseconds
PROGRESS_COMPLETE = 100  # Progress bar completion value

# Timeout constants
CLIPBOARD_TIMEOUT = 0.5  # Clipboard operation timeout in seconds
METADATA_FETCH_TIMEOUT = 30  # Timeout for fetching video metadata
STREAM_FETCH_TIMEOUT = 15  # Timeout for stream/frame operations
FFPROBE_TIMEOUT = 10  # Timeout for ffprobe operations
DEPENDENCY_CHECK_TIMEOUT = 5  # Timeout for dependency checks
TIMEOUT_CHECK_INTERVAL = 10  # Download timeout check interval

# Security: Maximum values for validation
MAX_VOLUME = 2.0  # Maximum 200% volume
MIN_VOLUME = 0.0  # Minimum 0% volume (mute)
MAX_VIDEO_DURATION = 86400  # Max 24 hours
CATBOX_MAX_SIZE_MB = 200  # Catbox file size limit
MAX_FILENAME_LENGTH = 200  # Maximum filename length
DEFAULT_VIDEO_QUALITY = "480"  # Default video quality preset

# UI Constants
CLIPBOARD_URL_LIST_HEIGHT = 12  # Height for clipboard URL list (reduced from 200)

# File paths for persistence
UPLOAD_HISTORY_FILE = Path.home() / ".youtubedownloader" / "upload_history.txt"
CLIPBOARD_URLS_FILE = Path.home() / ".youtubedownloader" / "clipboard_urls.json"

# Theme colors
THEMES = {
    'light': {
        'bg': '#f0f0f0',
        'fg': '#000000',
        'select_bg': '#0078d7',
        'select_fg': '#ffffff',
        'button_bg': '#e1e1e1',
        'entry_bg': '#ffffff',
        'frame_bg': '#f0f0f0'
    },
    'dark': {
        'bg': '#2b2b2b',
        'fg': '#ffffff',
        'select_bg': '#0078d7',
        'select_fg': '#ffffff',
        'button_bg': '#3c3c3c',
        'entry_bg': '#1e1e1e',
        'frame_bg': '#2b2b2b'
    }
}

# Compiled regex patterns for performance
PROGRESS_REGEX = re.compile(r'(\d+\.?\d*)%')
SPEED_REGEX = re.compile(r'(\d+\.?\d*\s*[KMG]iB/s)')
ETA_REGEX = re.compile(r'ETA\s+(\d{2}:\d{2}(?::\d{2})?)')
FILESIZE_REGEX = re.compile(r'(\d+\.?\d*\s*[KMG]iB)')
TIME_REGEX = re.compile(r'^(\d{1,2}):(\d{2}):(\d{2})$')

class YouTubeDownloader:
    def __init__(self, root):
        logger.info("Initializing YoutubeDownloader")
        self.root = root
        self.root.title("YoutubeDownloader")
        self.root.geometry("900x1140")
        self.root.resizable(True, True)
        self.root.minsize(750, 600)

        self.download_path = str(Path.home() / "Downloads")
        self.current_process = None
        self.is_downloading = False
        self.video_duration = 0
        self.is_fetching_duration = False
        self.last_progress_time = None
        self.download_start_time = None
        self.timeout_monitor_thread = None

        # Detect bundled executables (when packaged with PyInstaller)
        self.ffmpeg_path = self._get_bundled_executable('ffmpeg')
        self.ffprobe_path = self._get_bundled_executable('ffprobe')
        self.ytdlp_path = self._get_bundled_executable('yt-dlp')

        # Frame preview variables
        self.start_preview_image = None
        self.end_preview_image = None
        self.temp_dir = None
        self.current_video_url = None
        self.preview_update_timer = None
        self.last_preview_update = 0
        self.preview_thread_running = False  # Track if preview thread is active
        self.preview_cache = {}  # Cache for preview frames {timestamp: file_path}
        self.cache_access_order = []  # Track access order for LRU eviction

        # Volume control
        self.volume_var = tk.DoubleVar(value=1.0)  # 1.0 = 100%

        # Local file support
        self.local_file_path = None

        # Upload to Catbox.moe
        self.last_output_file = None  # Track last downloaded/processed file
        self.is_uploading = False
        self.catbox_client = CatboxClient()  # Anonymous upload client

        # Custom filename
        self.custom_filename = None  # User-specified output filename

        # Playlist support
        self.is_playlist = False  # Track if current URL is a playlist
        self.estimated_filesize = None  # Estimated file size for current video

        # Initialize temp directory with cleanup on exit
        self._init_temp_directory()

        # Check dependencies once at startup
        self.dependencies_ok = self.check_dependencies()
        if not self.dependencies_ok:
            logger.warning("Dependencies check failed at startup")

        # Thread pool for background tasks
        self.thread_pool = ThreadPoolExecutor(max_workers=MAX_WORKER_THREADS, thread_name_prefix="ytdl_worker")

        # Thread safety locks
        self.preview_lock = threading.Lock()  # Protect preview thread state
        self.clipboard_lock = threading.Lock()  # Protect clipboard URL list
        self.auto_download_lock = threading.Lock()  # Protect auto-download state

        # Clipboard Mode variables
        self.clipboard_monitoring = False
        self.clipboard_monitor_thread = None
        self.clipboard_last_content = ""
        self.clipboard_url_list = []  # List of dict: {'url': str, 'status': str, 'widget': Frame}
        self.clipboard_download_path = str(Path.home() / "Downloads" / "ClipboardMode")
        self.clipboard_downloading = False
        self.clipboard_auto_downloading = False  # Separate flag for auto-downloads
        self.clipboard_current_download_index = 0
        self.clipboard_url_widgets = {}
        self.klipper_interface = None  # KDE Klipper D-Bus interface

        # Theme mode
        self.current_theme = 'light'  # Default to light theme

        # Auto-upload feature
        self.auto_upload_var = tk.BooleanVar(value=False)  # Auto-upload after download/trim

        # Uploader tab variables
        self.uploader_file_queue = []  # List of file paths to upload
        self.uploader_is_uploading = False
        self.uploader_current_index = 0

        # Load persisted clipboard URLs
        self._load_clipboard_urls()

        # Try to connect to KDE Klipper
        if DBUS_AVAILABLE:
            try:
                bus = dbus.SessionBus()
                klipper = bus.get_object('org.kde.klipper', '/klipper')
                self.klipper_interface = dbus.Interface(klipper, 'org.kde.klipper.klipper')
                logger.info("Connected to KDE Klipper clipboard manager")
            except Exception as e:
                logger.info(f"KDE Klipper not available: {e}")
                self.klipper_interface = None

        # Create clipboard download directory
        Path(self.clipboard_download_path).mkdir(parents=True, exist_ok=True)

        self.setup_ui()

        # Bind cleanup on window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    # Persistence methods

    def _load_clipboard_urls(self):
        """Load persisted clipboard URLs from previous session"""
        try:
            if CLIPBOARD_URLS_FILE.exists():
                with open(CLIPBOARD_URLS_FILE, 'r') as f:
                    import json
                    data = json.load(f)
                    # Store URLs, will be restored to UI after setup_ui() completes
                    self.persisted_clipboard_urls = data.get('urls', [])
                    logger.info(f"Loaded {len(self.persisted_clipboard_urls)} persisted clipboard URLs")
            else:
                self.persisted_clipboard_urls = []
        except Exception as e:
            logger.error(f"Error loading clipboard URLs: {e}")
            self.persisted_clipboard_urls = []

    def _save_clipboard_urls(self):
        """Save clipboard URLs to file for persistence between sessions"""
        try:
            CLIPBOARD_URLS_FILE.parent.mkdir(parents=True, exist_ok=True)
            import json
            # Save only pending and failed URLs (not completed ones)
            urls_to_save = [
                {'url': item['url'], 'status': item['status']}
                for item in self.clipboard_url_list
                if item['status'] in ['pending', 'failed']
            ]
            with open(CLIPBOARD_URLS_FILE, 'w') as f:
                json.dump({'urls': urls_to_save}, f, indent=2)
            logger.info(f"Saved {len(urls_to_save)} clipboard URLs")
        except Exception as e:
            logger.error(f"Error saving clipboard URLs: {e}")

    def _restore_clipboard_urls(self):
        """Restore persisted URLs to the UI (called after setup_ui)"""
        if hasattr(self, 'persisted_clipboard_urls') and self.persisted_clipboard_urls:
            for url_data in self.persisted_clipboard_urls:
                url = url_data.get('url', '')
                status = url_data.get('status', 'pending')
                if url and url not in [item['url'] for item in self.clipboard_url_list]:
                    self._add_url_to_clipboard_list(url)
                    if status == 'failed':
                        self._update_url_status(url, 'failed')
            logger.info(f"Restored {len(self.persisted_clipboard_urls)} URLs to clipboard list")

    def save_upload_link(self, link, filename=""):
        """Save uploaded video link to history file"""
        try:
            UPLOAD_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(UPLOAD_HISTORY_FILE, 'a') as f:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{timestamp} | {filename} | {link}\n")
            logger.info(f"Saved upload link to history: {link}")
        except Exception as e:
            logger.error(f"Error saving upload link: {e}")

    def view_upload_history(self):
        """View upload link history in a new window"""
        history_window = tk.Toplevel(self.root)
        history_window.title("Upload Link History")
        history_window.geometry("800x500")

        # Create text widget with scrollbar
        frame = ttk.Frame(history_window, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        text_widget = tk.Text(frame, wrap=tk.WORD, yscrollcommand=scrollbar.set, font=('Consolas', 9))
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)

        # Load and display history
        try:
            if UPLOAD_HISTORY_FILE.exists():
                with open(UPLOAD_HISTORY_FILE, 'r') as f:
                    content = f.read()
                    if content:
                        text_widget.insert('1.0', content)
                    else:
                        text_widget.insert('1.0', "No upload history yet.")
            else:
                text_widget.insert('1.0', "No upload history yet.")
        except Exception as e:
            text_widget.insert('1.0', f"Error loading history: {e}")

        text_widget.config(state='disabled')  # Make read-only

        # Add copy and clear buttons
        button_frame = ttk.Frame(history_window, padding="10")
        button_frame.pack(fill=tk.X)

        def copy_all():
            self.root.clipboard_clear()
            self.root.clipboard_append(text_widget.get('1.0', tk.END))
            messagebox.showinfo("Copied", "History copied to clipboard!")

        def clear_history():
            if messagebox.askyesno("Clear History", "Are you sure you want to clear all upload history?"):
                try:
                    if UPLOAD_HISTORY_FILE.exists():
                        UPLOAD_HISTORY_FILE.unlink()
                    text_widget.config(state='normal')
                    text_widget.delete('1.0', tk.END)
                    text_widget.insert('1.0', "No upload history yet.")
                    text_widget.config(state='disabled')
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to clear history: {e}")

        ttk.Button(button_frame, text="Copy All", command=copy_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear History", command=clear_history).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Close", command=history_window.destroy).pack(side=tk.RIGHT, padx=5)

    def retry_network_operation(self, operation, operation_name, *args, **kwargs):
        """Retry a network operation with exponential backoff"""
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                return operation(*args, **kwargs)
            except subprocess.TimeoutExpired as e:
                if attempt == MAX_RETRY_ATTEMPTS:
                    logger.error(f"{operation_name} failed after {MAX_RETRY_ATTEMPTS} attempts: timeout")
                    raise
                logger.warning(f"{operation_name} timeout (attempt {attempt}/{MAX_RETRY_ATTEMPTS}), retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY * attempt)  # Exponential backoff
            except subprocess.CalledProcessError as e:
                if attempt == MAX_RETRY_ATTEMPTS:
                    logger.error(f"{operation_name} failed after {MAX_RETRY_ATTEMPTS} attempts: {e}")
                    raise
                logger.warning(f"{operation_name} failed (attempt {attempt}/{MAX_RETRY_ATTEMPTS}), retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY * attempt)
            except Exception as e:
                # Don't retry on unexpected errors
                logger.error(f"{operation_name} failed with unexpected error: {e}")
                raise

    # Security and validation methods

    @staticmethod
    def sanitize_filename(filename):
        """Sanitize filename to prevent path traversal and command injection.

        Removes:
        - Path separators (/, \\)
        - Parent directory references (..)
        - Shell metacharacters
        - Control characters
        - Leading/trailing dots and spaces
        """
        if not filename:
            return ""

        # Remove path separators and parent directory references
        dangerous_chars = ['/', '\\', '..', '\x00']
        for char in dangerous_chars:
            filename = filename.replace(char, '')

        # Remove shell metacharacters that could be dangerous
        shell_chars = ['$', '`', '|', ';', '&', '<', '>', '(', ')', '{', '}', '[', ']', '!', '*', '?', '~', '^']
        for char in shell_chars:
            filename = filename.replace(char, '')

        # Remove control characters (ASCII 0-31 and 127)
        filename = ''.join(char for char in filename if ord(char) >= 32 and ord(char) != 127)

        # Remove leading/trailing dots and spaces
        filename = filename.strip('. ')

        # Limit length to filesystem limits
        if len(filename) > MAX_FILENAME_LENGTH:
            filename = filename[:MAX_FILENAME_LENGTH]

        return filename

    @staticmethod
    def validate_volume(volume):
        """Validate and clamp volume value to safe range."""
        try:
            vol = float(volume)
            return max(MIN_VOLUME, min(MAX_VOLUME, vol))
        except (ValueError, TypeError):
            return 1.0  # Default to 100%

    @staticmethod
    def validate_time(time_str):
        """Validate time format HH:MM:SS and return seconds, or None if invalid."""
        if not time_str:
            return None

        match = TIME_REGEX.match(time_str.strip())
        if not match:
            return None

        hours, minutes, seconds = map(int, match.groups())
        if minutes >= 60 or seconds >= 60:
            return None

        total_seconds = hours * 3600 + minutes * 60 + seconds
        if total_seconds > MAX_VIDEO_DURATION:
            return None

        return total_seconds

    @staticmethod
    def validate_time_range(start_seconds, end_seconds, duration):
        """Validate that time range is logical and within bounds."""
        if start_seconds is None or end_seconds is None or duration is None:
            return False

        if start_seconds < 0 or end_seconds < 0:
            return False

        if start_seconds >= end_seconds:
            return False

        if end_seconds > duration:
            return False

        return True

    @staticmethod
    def safe_process_cleanup(process, timeout=PROCESS_TERMINATE_TIMEOUT):
        """Safely terminate and cleanup a subprocess.

        Args:
            process: subprocess.Popen instance
            timeout: Seconds to wait for graceful termination

        Returns:
            bool: True if process was cleaned up successfully
        """
        if process is None:
            return True

        try:
            if process.poll() is None:  # Process still running
                process.terminate()
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    logger.warning(f"Process {process.pid} did not terminate, forcing kill")
                    process.kill()
                    process.wait()

            # Close pipes to prevent resource leaks
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
            if process.stdin:
                process.stdin.close()

            return True
        except Exception as e:
            logger.error(f"Error cleaning up process: {e}")
            return False

    # Command building helper methods

    def build_base_ytdlp_command(self, url):
        """Build base yt-dlp command with common options.

        Args:
            url: YouTube URL to download

        Returns:
            list: Base command with common flags
        """
        return [
            self.ytdlp_path,
            '--concurrent-fragments', CONCURRENT_FRAGMENTS,
            '--buffer-size', BUFFER_SIZE,
            '--http-chunk-size', CHUNK_SIZE,
            '--newline',
            '--progress',
        ]

    def build_audio_ytdlp_command(self, url, output_path, volume=1.0):
        """Build yt-dlp command for audio-only download.

        Args:
            url: YouTube URL
            output_path: Full output path with filename template
            volume: Volume multiplier (default 1.0)

        Returns:
            list: Complete command for audio download
        """
        cmd = self.build_base_ytdlp_command(url)
        cmd.extend([
            '-f', 'bestaudio',
            '--extract-audio',
            '--audio-format', 'm4a',
            '--audio-quality', AUDIO_BITRATE,
        ])

        # Add volume filter if needed
        if volume != 1.0:
            cmd.extend(['--postprocessor-args', f'ffmpeg:-af volume={volume}'])

        cmd.extend(['-o', output_path, url])
        return cmd

    def build_video_ytdlp_command(self, url, output_path, quality, volume=1.0,
                                    trim_start=None, trim_end=None):
        """Build yt-dlp command for video download with optional trimming.

        Args:
            url: YouTube URL
            output_path: Full output path with filename template
            quality: Video height (e.g., '1080', '720')
            volume: Volume multiplier (default 1.0)
            trim_start: Start time in seconds (optional)
            trim_end: End time in seconds (optional)

        Returns:
            list: Complete command for video download
        """
        cmd = self.build_base_ytdlp_command(url)
        cmd.extend([
            '-f', f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]',
            '--merge-output-format', 'mp4',
        ])

        # Add trimming if specified
        trim_enabled = trim_start is not None and trim_end is not None
        if trim_enabled:
            start_hms = self.seconds_to_hms(trim_start)
            end_hms = self.seconds_to_hms(trim_end)
            cmd.extend([
                '--download-sections', f'*{start_hms}-{end_hms}',
                '--force-keyframes-at-cuts',
            ])

        # Build ffmpeg postprocessor args if needed
        needs_processing = trim_enabled or volume != 1.0
        if needs_processing:
            ffmpeg_args = [
                '-c:v', 'libx264', '-crf', str(VIDEO_CRF),
                '-preset', 'faster', '-c:a', 'aac', '-b:a', AUDIO_BITRATE
            ]
            if volume != 1.0:
                ffmpeg_args.extend(['-af', f'volume={volume}'])

            cmd.extend(['--postprocessor-args', 'ffmpeg:' + ' '.join(ffmpeg_args)])

        cmd.extend(['-o', output_path, url])
        return cmd

    def validate_youtube_url(self, url):
        """Validate if URL is a valid YouTube URL"""
        if not url:
            return False, "URL is empty"

        try:
            parsed = urlparse(url)

            # Check for valid YouTube domains
            valid_domains = [
                'youtube.com', 'www.youtube.com', 'm.youtube.com',
                'youtu.be', 'www.youtu.be'
            ]

            if parsed.netloc not in valid_domains:
                return False, "Not a YouTube URL. Please enter a valid YouTube link."

            # For youtu.be short links
            if 'youtu.be' in parsed.netloc:
                if not parsed.path or parsed.path == '/':
                    return False, "Invalid YouTube short URL"
                return True, "Valid YouTube URL"

            # For youtube.com links
            if 'youtube.com' in parsed.netloc:
                # Check for /watch?v= format
                if '/watch' in parsed.path:
                    query_params = parse_qs(parsed.query)
                    if 'v' not in query_params:
                        return False, "Missing video ID in URL"
                    return True, "Valid YouTube URL"

                # Check for /shorts/ format
                elif '/shorts/' in parsed.path:
                    return True, "Valid YouTube Shorts URL"

                # Check for /embed/ format
                elif '/embed/' in parsed.path:
                    return True, "Valid YouTube embed URL"

                # Check for /v/ format (old style)
                elif '/v/' in parsed.path:
                    return True, "Valid YouTube URL"

                # Check for playlist
                elif '/playlist' in parsed.path or 'list=' in parsed.query:
                    return True, "Valid YouTube Playlist URL"

                else:
                    return False, "Unrecognized YouTube URL format"

            return False, "Invalid URL format"

        except Exception as e:
            logger.error(f"URL validation error: {e}")
            return False, f"Invalid URL format: {str(e)}"

    def is_playlist_url(self, url):
        """Check if URL is a YouTube playlist"""
        try:
            parsed = urlparse(url)
            # Check for playlist in path or list parameter in query
            if '/playlist' in parsed.path:
                return True
            query_params = parse_qs(parsed.query)
            if 'list=' in parsed.query and query_params.get('list'):
                return True
            return False
        except Exception:
            return False

    def _init_temp_directory(self):
        """Initialize temp directory and clean up orphaned ones from previous crashes"""
        import shutil
        import glob

        # Clean up old orphaned temp directories
        temp_base = tempfile.gettempdir()
        old_dirs = glob.glob(os.path.join(temp_base, "ytdl_preview_*"))
        for old_dir in old_dirs:
            try:
                # Only remove if older than TEMP_DIR_MAX_AGE (to avoid conflicts with other instances)
                dir_age = time.time() - os.path.getmtime(old_dir)
                if dir_age > TEMP_DIR_MAX_AGE:
                    shutil.rmtree(old_dir, ignore_errors=True)
            except Exception:
                pass

        # Create new temp directory
        self.temp_dir = tempfile.mkdtemp(prefix="ytdl_preview_")

    def setup_ui(self):
        # Configure root grid to expand
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Create canvas with scrollbar for scrollable content
        canvas = tk.Canvas(self.root)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # Enable mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        def _on_mousewheel_linux(event):
            # Linux uses Button-4 (scroll up) and Button-5 (scroll down)
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")

        # Bind mousewheel to canvas and scrollable frame for better UX
        canvas.bind("<MouseWheel>", _on_mousewheel)  # Windows/MacOS
        canvas.bind("<Button-4>", _on_mousewheel_linux)  # Linux scroll up
        canvas.bind("<Button-5>", _on_mousewheel_linux)  # Linux scroll down

        scrollable_frame.bind("<MouseWheel>", _on_mousewheel)
        scrollable_frame.bind("<Button-4>", _on_mousewheel_linux)
        scrollable_frame.bind("<Button-5>", _on_mousewheel_linux)

        # Recursively bind mousewheel to all children widgets
        def bind_to_mousewheel(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            widget.bind("<Button-4>", _on_mousewheel_linux)
            widget.bind("<Button-5>", _on_mousewheel_linux)
            for child in widget.winfo_children():
                bind_to_mousewheel(child)

        # This will be called after all widgets are created
        self.root.after(100, lambda: bind_to_mousewheel(scrollable_frame))

        # Store canvas reference for cleanup
        self.canvas = canvas

        # Create notebook for tabs
        self.notebook = ttk.Notebook(scrollable_frame)
        self.notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        # Clipboard Mode tab (first tab)
        clipboard_tab_frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(clipboard_tab_frame, text="Clipboard Mode")
        # Setup will be called after Trimmer tab is created

        # Trimmer tab (second tab)
        main_tab_frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(main_tab_frame, text="Trimmer")

        # Uploader tab (third tab)
        uploader_tab_frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(uploader_tab_frame, text="Uploader")

        ttk.Label(main_tab_frame, text="YouTube URL or Local File:", font=('Arial', 12)).grid(row=0, column=0, sticky=tk.W, pady=(0, 10))

        # URL/File input frame
        url_input_frame = ttk.Frame(main_tab_frame)
        url_input_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        self.url_entry = ttk.Entry(url_input_frame, width=50)
        self.url_entry.pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True)
        self.url_entry.bind('<KeyRelease>', self.on_url_change)

        ttk.Button(url_input_frame, text="Browse Local File", command=self.browse_local_file).pack(side=tk.LEFT)

        # Mode indicator label
        self.mode_label = ttk.Label(main_tab_frame, text="", foreground="blue", font=('Arial', 9))
        self.mode_label.grid(row=2, column=0, sticky=tk.W, pady=(0, 10))

        # Video Quality section - dropdown
        quality_frame = ttk.Frame(main_tab_frame)
        quality_frame.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(10, 5))

        ttk.Label(quality_frame, text="Video Quality:", font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=(0, 10))

        self.quality_var = tk.StringVar(value="480")
        self.quality_var.trace_add('write', self.on_quality_change)

        quality_options = ["1440", "1080", "720", "480", "360", "240", "none (Audio only)"]
        self.quality_combo = ttk.Combobox(quality_frame, textvariable=self.quality_var,
            values=quality_options, state='readonly', width=20)
        self.quality_combo.pack(side=tk.LEFT)

        ttk.Separator(main_tab_frame, orient='horizontal').grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)

        # Trimming section with Volume Control on the right
        trim_and_volume_row = ttk.Frame(main_tab_frame)
        trim_and_volume_row.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 3))

        # Left side: Trim Video
        ttk.Label(trim_and_volume_row, text="Trim Video:", font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=(0, 30))

        # Right side: Volume Adjustment
        ttk.Label(trim_and_volume_row, text="Volume:", font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=(20, 5))

        self.volume_slider = ttk.Scale(trim_and_volume_row, from_=0, to=2.0, variable=self.volume_var,
                                        orient='horizontal', length=150, command=self.on_volume_change)
        self.volume_slider.pack(side=tk.LEFT, padx=(0, 5))

        # Volume entry field
        self.volume_entry = ttk.Entry(trim_and_volume_row, width=6)
        self.volume_entry.pack(side=tk.LEFT, padx=(0, 3))
        self.volume_entry.insert(0, "100")
        self.volume_entry.bind('<Return>', self.on_volume_entry_change)
        self.volume_entry.bind('<FocusOut>', self.on_volume_entry_change)

        self.volume_label = ttk.Label(trim_and_volume_row, text="%", font=('Arial', 9))
        self.volume_label.pack(side=tk.LEFT, padx=(0, 5))

        # Reset to 100% button
        ttk.Button(trim_and_volume_row, text="Reset to 100%", command=self.reset_volume, width=12).pack(side=tk.LEFT)

        # Trim checkbox row with fetch button
        trim_checkbox_frame = ttk.Frame(main_tab_frame)
        trim_checkbox_frame.grid(row=6, column=0, sticky=tk.W, padx=(20, 0), pady=(3, 5))

        self.trim_enabled_var = tk.BooleanVar()
        ttk.Checkbutton(trim_checkbox_frame, text="Enable video trimming", variable=self.trim_enabled_var,
                       command=self.toggle_trim).pack(side=tk.LEFT)

        self.fetch_duration_btn = ttk.Button(trim_checkbox_frame, text="Fetch Video Duration", command=self.fetch_duration_clicked, state='disabled')
        self.fetch_duration_btn.pack(side=tk.LEFT, padx=(10, 0))

        # Video info label
        self.video_info_label = ttk.Label(main_tab_frame, text="", foreground="blue", wraplength=500, justify=tk.LEFT)
        self.video_info_label.grid(row=7, column=0, sticky=tk.W, padx=(20, 0), pady=(2, 0))

        # File size estimation label
        self.filesize_label = ttk.Label(main_tab_frame, text="", foreground="green", font=('Arial', 9))
        self.filesize_label.grid(row=8, column=0, sticky=tk.W, padx=(20, 0), pady=(2, 0))

        # Preview frame to hold both previews side by side
        preview_container = ttk.Frame(main_tab_frame)
        preview_container.grid(row=9, column=0, sticky=tk.W, padx=(40, 0), pady=(10, 5))

        # Start time preview
        start_preview_frame = ttk.Frame(preview_container)
        start_preview_frame.grid(row=0, column=0, padx=(0, 20))

        ttk.Label(start_preview_frame, text="Start Time:", font=('Arial', 9)).pack()
        self.start_preview_label = tk.Label(start_preview_frame, bg='gray20', fg='white', relief='sunken')
        self.start_preview_label.pack(pady=(5, 0))

        # Create placeholder images
        self.placeholder_image = self.create_placeholder_image(PREVIEW_WIDTH, PREVIEW_HEIGHT, "Preview")
        self.loading_image = self.create_placeholder_image(PREVIEW_WIDTH, PREVIEW_HEIGHT, "Loading...")
        self.start_preview_label.config(image=self.placeholder_image)

        # End time preview
        end_preview_frame = ttk.Frame(preview_container)
        end_preview_frame.grid(row=0, column=1)

        ttk.Label(end_preview_frame, text="End Time:", font=('Arial', 9)).pack()
        self.end_preview_label = tk.Label(end_preview_frame, bg='gray20', fg='white', relief='sunken')
        self.end_preview_label.pack(pady=(5, 0))
        self.end_preview_label.config(image=self.placeholder_image)

        # Start time slider and entry
        start_control_frame = ttk.Frame(main_tab_frame)
        start_control_frame.grid(row=10, column=0, sticky=tk.W, padx=(40, 0), pady=(2, 2))

        self.start_time_var = tk.DoubleVar(value=0)
        self.start_slider = ttk.Scale(start_control_frame, from_=0, to=100, variable=self.start_time_var,
                                      orient='horizontal', length=SLIDER_LENGTH, command=self.on_slider_change, state='disabled')
        self.start_slider.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(start_control_frame, text="Start:", font=('Arial', 9)).pack(side=tk.LEFT, padx=(0, 5))
        self.start_time_entry = ttk.Entry(start_control_frame, width=10, state='disabled')
        self.start_time_entry.pack(side=tk.LEFT)
        self.start_time_entry.insert(0, "00:00:00")
        self.start_time_entry.bind('<Return>', self.on_start_entry_change)
        self.start_time_entry.bind('<FocusOut>', self.on_start_entry_change)

        # End time slider and entry
        end_control_frame = ttk.Frame(main_tab_frame)
        end_control_frame.grid(row=11, column=0, sticky=tk.W, padx=(40, 0), pady=(2, 2))

        self.end_time_var = tk.DoubleVar(value=100)
        self.end_slider = ttk.Scale(end_control_frame, from_=0, to=100, variable=self.end_time_var,
                                    orient='horizontal', length=SLIDER_LENGTH, command=self.on_slider_change, state='disabled')
        self.end_slider.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(end_control_frame, text="End:", font=('Arial', 9)).pack(side=tk.LEFT, padx=(0, 5))
        self.end_time_entry = ttk.Entry(end_control_frame, width=10, state='disabled')
        self.end_time_entry.pack(side=tk.LEFT)
        self.end_time_entry.insert(0, "00:00:00")
        self.end_time_entry.bind('<Return>', self.on_end_entry_change)
        self.end_time_entry.bind('<FocusOut>', self.on_end_entry_change)

        # Trim duration display
        self.trim_duration_label = ttk.Label(main_tab_frame, text="Selected Duration: 00:00:00", foreground="green", font=('Arial', 9, 'bold'))
        self.trim_duration_label.grid(row=12, column=0, sticky=tk.W, padx=(40, 0), pady=(3, 0))

        ttk.Separator(main_tab_frame, orient='horizontal').grid(row=13, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)

        path_frame = ttk.Frame(main_tab_frame)
        path_frame.grid(row=14, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(path_frame, text="Save to:").pack(side=tk.LEFT)
        self.path_label = ttk.Label(path_frame, text=self.download_path, foreground="blue")
        self.path_label.pack(side=tk.LEFT, padx=(10, 10))
        ttk.Button(path_frame, text="Change", command=self.change_path).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(path_frame, text="Open Folder", command=self.open_download_folder).pack(side=tk.LEFT)

        # Filename customization
        filename_frame = ttk.Frame(main_tab_frame)
        filename_frame.grid(row=15, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(filename_frame, text="Output filename:", font=('Arial', 9)).pack(side=tk.LEFT, padx=(0, 5))
        self.filename_entry = ttk.Entry(filename_frame, width=40)
        self.filename_entry.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(filename_frame, text="(Optional - leave empty for auto-generated name)", foreground="gray", font=('Arial', 8)).pack(side=tk.LEFT)

        button_frame = ttk.Frame(main_tab_frame)
        button_frame.grid(row=16, column=0, columnspan=2, pady=(0, 10))

        self.download_btn = ttk.Button(button_frame, text="Download", command=self.start_download)
        self.download_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_btn = ttk.Button(button_frame, text="Stop", command=self.stop_download, state='disabled')
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 15))

        # Speed limit controls
        self.speed_limit_var = tk.StringVar(value="")
        self.speed_limit_entry = ttk.Entry(button_frame, textvariable=self.speed_limit_var, width=6)
        self.speed_limit_entry.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Label(button_frame, text="MB/s", font=('Arial', 9)).pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(main_tab_frame, mode='determinate', length=560, maximum=100)
        self.progress.grid(row=17, column=0, columnspan=2)

        self.progress_label = ttk.Label(main_tab_frame, text="0%", foreground="blue")
        self.progress_label.grid(row=18, column=0, columnspan=2, pady=(5, 0))

        self.status_label = ttk.Label(main_tab_frame, text="Ready", foreground="green")
        self.status_label.grid(row=19, column=0, columnspan=2, pady=(10, 0))

        # Upload to Catbox.moe Section
        ttk.Separator(main_tab_frame, orient='horizontal').grid(row=20, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)

        ttk.Label(main_tab_frame, text="Upload to Streaming Site:", font=('Arial', 11, 'bold')).grid(row=21, column=0, sticky=tk.W, pady=(0, 3))

        upload_frame = ttk.Frame(main_tab_frame)
        upload_frame.grid(row=22, column=0, columnspan=2, sticky=tk.W, pady=(5, 5))

        self.upload_btn = ttk.Button(upload_frame, text="Upload to Catbox.moe", command=self.start_upload, state='disabled')
        self.upload_btn.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(upload_frame, text="View Upload History", command=self.view_upload_history).pack(side=tk.LEFT, padx=(0, 10))

        self.upload_status_label = ttk.Label(upload_frame, text="", foreground="blue", font=('Arial', 9))
        self.upload_status_label.pack(side=tk.LEFT)

        # Auto-upload checkbox
        auto_upload_frame = ttk.Frame(main_tab_frame)
        auto_upload_frame.grid(row=23, column=0, columnspan=2, sticky=tk.W, padx=(20, 0), pady=(5, 0))

        ttk.Checkbutton(auto_upload_frame, text="Auto-upload after download/trim completes",
                       variable=self.auto_upload_var).pack(side=tk.LEFT)

        # Upload URL display (initially hidden)
        self.upload_url_frame = ttk.Frame(main_tab_frame)
        self.upload_url_frame.grid(row=24, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))

        ttk.Label(self.upload_url_frame, text="Upload URL:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 5))

        self.upload_url_entry = ttk.Entry(self.upload_url_frame, width=60, state='readonly')
        self.upload_url_entry.pack(side=tk.LEFT, padx=(0, 10))

        self.copy_url_btn = ttk.Button(self.upload_url_frame, text="Copy URL", command=self.copy_upload_url)
        self.copy_url_btn.pack(side=tk.LEFT)

        # Hide upload URL frame initially
        self.upload_url_frame.grid_remove()

        # Setup Clipboard Mode UI (tab was created at the beginning)
        self.setup_clipboard_mode_ui(clipboard_tab_frame)

        # Setup Uploader UI
        self.setup_uploader_ui(uploader_tab_frame)

        # Restore persisted clipboard URLs
        self._restore_clipboard_urls()

        # Bind tab change event
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    def setup_clipboard_mode_ui(self, parent):
        """Setup Clipboard Mode tab UI"""

        # Header
        ttk.Label(parent, text="Clipboard Mode", font=('Arial', 14, 'bold')).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        ttk.Label(parent, text="Copy YouTube URLs (Ctrl+C) to automatically detect and download them.",
                  foreground="gray", font=('Arial', 9)).grid(
            row=1, column=0, columnspan=2, sticky=tk.W, pady=(0, 15))

        # Mode Toggle
        mode_frame = ttk.Frame(parent)
        mode_frame.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        ttk.Label(mode_frame, text="Download Mode:", font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=(0, 10))
        self.clipboard_auto_download_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(mode_frame, text="Auto-download (starts immediately)",
                       variable=self.clipboard_auto_download_var).pack(side=tk.LEFT)

        # Settings
        ttk.Separator(parent, orient='horizontal').grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)
        ttk.Label(parent, text="Settings", font=('Arial', 11, 'bold')).grid(row=4, column=0, sticky=tk.W, pady=(0, 5))

        settings_frame = ttk.Frame(parent)
        settings_frame.grid(row=5, column=0, columnspan=2, sticky=tk.W, padx=(20, 0), pady=(0, 10))

        # Quality dropdown
        ttk.Label(settings_frame, text="Quality:", font=('Arial', 9)).grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.clipboard_quality_var = tk.StringVar(value="1080")
        quality_options = ["1440", "1080", "720", "480", "360", "240", "none (Audio only)"]
        self.clipboard_quality_combo = ttk.Combobox(settings_frame, textvariable=self.clipboard_quality_var,
            values=quality_options, state='readonly', width=20)
        self.clipboard_quality_combo.grid(row=0, column=1, sticky=tk.W)

        # Output Folder
        ttk.Separator(parent, orient='horizontal').grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        folder_frame = ttk.Frame(parent)
        folder_frame.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(folder_frame, text="Save to:", font=('Arial', 9)).pack(side=tk.LEFT)
        self.clipboard_path_label = ttk.Label(folder_frame, text=self.clipboard_download_path, foreground="blue")
        self.clipboard_path_label.pack(side=tk.LEFT, padx=(10, 10))
        ttk.Button(folder_frame, text="Change", command=self.change_clipboard_path).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(folder_frame, text="Open Folder", command=self.open_clipboard_folder).pack(side=tk.LEFT)

        # URL List
        ttk.Separator(parent, orient='horizontal').grid(row=8, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        url_header_frame = ttk.Frame(parent)
        url_header_frame.grid(row=9, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))

        ttk.Label(url_header_frame, text="Detected URLs", font=('Arial', 11, 'bold')).pack(side=tk.LEFT)
        self.clipboard_url_count_label = ttk.Label(url_header_frame, text="(0 URLs)", foreground="gray", font=('Arial', 9))
        self.clipboard_url_count_label.pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(url_header_frame, text="Clear All", command=self.clear_all_clipboard_urls).pack(side=tk.RIGHT)

        # Scrollable URL list
        url_list_container = ttk.Frame(parent)
        url_list_container.grid(row=10, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        self.clipboard_url_canvas = tk.Canvas(url_list_container, height=CLIPBOARD_URL_LIST_HEIGHT, bg='white',
                                             highlightthickness=1, highlightbackground='gray')
        url_scrollbar = ttk.Scrollbar(url_list_container, orient="vertical",
                                      command=self.clipboard_url_canvas.yview)
        self.clipboard_url_list_frame = ttk.Frame(self.clipboard_url_canvas)

        self.clipboard_url_list_frame.bind("<Configure>",
            lambda e: self.clipboard_url_canvas.configure(scrollregion=self.clipboard_url_canvas.bbox("all")))

        self.clipboard_url_canvas.create_window((0, 0), window=self.clipboard_url_list_frame, anchor="nw")
        self.clipboard_url_canvas.configure(yscrollcommand=url_scrollbar.set)

        self.clipboard_url_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        url_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Progress & Controls
        ttk.Separator(parent, orient='horizontal').grid(row=11, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        button_frame = ttk.Frame(parent)
        button_frame.grid(row=12, column=0, columnspan=2, pady=(0, 10))

        self.clipboard_download_btn = ttk.Button(button_frame, text="Download All",
            command=self.start_clipboard_downloads, state='disabled')
        self.clipboard_download_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.clipboard_stop_btn = ttk.Button(button_frame, text="Stop",
            command=self.stop_clipboard_downloads, state='disabled')
        self.clipboard_stop_btn.pack(side=tk.LEFT)

        # Individual progress
        ttk.Label(parent, text="Current Download:", font=('Arial', 9, 'bold')).grid(row=13, column=0, sticky=tk.W, pady=(0, 3))

        self.clipboard_progress = ttk.Progressbar(parent, mode='determinate', length=560, maximum=100)
        self.clipboard_progress.grid(row=14, column=0, columnspan=2)

        self.clipboard_progress_label = ttk.Label(parent, text="0%", foreground="blue")
        self.clipboard_progress_label.grid(row=15, column=0, columnspan=2, pady=(5, 0))

        # Total progress
        self.clipboard_total_label = ttk.Label(parent, text="Completed: 0/0 videos",
            foreground="green", font=('Arial', 9, 'bold'))
        self.clipboard_total_label.grid(row=16, column=0, columnspan=2, pady=(5, 0))

        # Status
        self.clipboard_status_label = ttk.Label(parent, text="Ready", foreground="green")
        self.clipboard_status_label.grid(row=17, column=0, columnspan=2, pady=(10, 0))

    def setup_uploader_ui(self, parent):
        """Setup Uploader tab UI"""

        # Header
        ttk.Label(parent, text="Upload Local File", font=('Arial', 14, 'bold')).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        ttk.Label(parent, text="Upload local video files to Catbox.moe streaming service.",
                  foreground="gray", font=('Arial', 9)).grid(
            row=1, column=0, columnspan=2, sticky=tk.W, pady=(0, 15))

        # File selection
        ttk.Separator(parent, orient='horizontal').grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        file_header_frame = ttk.Frame(parent)
        file_header_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))

        ttk.Label(file_header_frame, text="File Queue:", font=('Arial', 11, 'bold')).pack(side=tk.LEFT)
        self.uploader_queue_count_label = ttk.Label(file_header_frame, text="(0 files)", foreground="gray", font=('Arial', 9))
        self.uploader_queue_count_label.pack(side=tk.LEFT, padx=(10, 0))

        file_select_frame = ttk.Frame(parent)
        file_select_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Button(file_select_frame, text="Add Files", command=self.browse_uploader_files).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(file_select_frame, text="Clear All", command=self.clear_uploader_queue).pack(side=tk.LEFT)

        # Scrollable file list
        file_list_container = ttk.Frame(parent)
        file_list_container.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        self.uploader_file_canvas = tk.Canvas(file_list_container, height=75, bg='white',
                                             highlightthickness=1, highlightbackground='gray')
        file_scrollbar = ttk.Scrollbar(file_list_container, orient="vertical",
                                      command=self.uploader_file_canvas.yview)
        self.uploader_file_list_frame = ttk.Frame(self.uploader_file_canvas)

        self.uploader_file_list_frame.bind("<Configure>",
            lambda e: self.uploader_file_canvas.configure(scrollregion=self.uploader_file_canvas.bbox("all")))

        self.uploader_file_canvas.create_window((0, 0), window=self.uploader_file_list_frame, anchor="nw")
        self.uploader_file_canvas.configure(yscrollcommand=file_scrollbar.set)

        self.uploader_file_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        file_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Upload controls
        ttk.Separator(parent, orient='horizontal').grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        upload_controls_frame = ttk.Frame(parent)
        upload_controls_frame.grid(row=7, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        self.uploader_upload_btn = ttk.Button(upload_controls_frame, text="Upload to Catbox.moe",
                                              command=self.start_uploader_upload, state='disabled')
        self.uploader_upload_btn.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(upload_controls_frame, text="View Upload History", command=self.view_upload_history).pack(side=tk.LEFT)

        self.uploader_status_label = ttk.Label(parent, text="", foreground="blue", font=('Arial', 9))
        self.uploader_status_label.grid(row=8, column=0, columnspan=2, sticky=tk.W, pady=(5, 10))

        # Upload URL display (initially hidden)
        self.uploader_url_frame = ttk.Frame(parent)
        self.uploader_url_frame.grid(row=9, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))

        ttk.Label(self.uploader_url_frame, text="Upload URL:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 5))

        self.uploader_url_entry = ttk.Entry(self.uploader_url_frame, width=60, state='readonly')
        self.uploader_url_entry.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(self.uploader_url_frame, text="Copy URL", command=self.copy_uploader_url).pack(side=tk.LEFT)

        # Hide URL frame initially
        self.uploader_url_frame.grid_remove()

    # Phase 4: Tab Management & Clipboard Monitoring

    def on_tab_changed(self, event=None):
        """Handle notebook tab changes"""
        current_tab = self.notebook.index(self.notebook.select())
        if current_tab == 0:  # Clipboard Mode tab (first tab)
            self.start_clipboard_monitoring()
        else:  # Trimmer tab (second tab)
            self.stop_clipboard_monitoring()

    def start_clipboard_monitoring(self):
        """Start clipboard monitoring using tkinter polling"""
        if not self.clipboard_monitoring:
            self.clipboard_monitoring = True
            logger.info("Clipboard monitoring started (tkinter polling)")
            # Initialize last content from current clipboard
            try:
                self.clipboard_last_content = self.root.clipboard_get()
            except tk.TclError:
                self.clipboard_last_content = ""
            # Start polling loop
            self._poll_clipboard()

    def stop_clipboard_monitoring(self):
        """Stop clipboard monitoring"""
        if self.clipboard_monitoring:
            self.clipboard_monitoring = False
            logger.info("Clipboard monitoring stopped")

    def _poll_clipboard(self):
        """Poll clipboard using best available method for each platform"""
        if not self.clipboard_monitoring:
            return

        clipboard_content = None

        try:
            # Try KDE Klipper first (most reliable on KDE Plasma Linux)
            if self.klipper_interface:
                try:
                    clipboard_content = str(self.klipper_interface.getClipboardContents())
                except Exception as e:
                    logger.debug(f"Klipper read failed: {e}")
                    clipboard_content = None

            # Try pyperclip (works on Windows even when Firefox has focus)
            if not clipboard_content and PYPERCLIP_AVAILABLE:
                try:
                    clipboard_content = pyperclip.paste()
                except Exception as e:
                    logger.debug(f"Pyperclip read failed: {e}")
                    clipboard_content = None

            # Fallback to tkinter if other methods unavailable or failed
            if not clipboard_content:
                self.root.update_idletasks()
                clipboard_content = self.root.clipboard_get()

            if clipboard_content and clipboard_content != self.clipboard_last_content:
                logger.info(f"Clipboard changed: {clipboard_content[:80]}")
                self.clipboard_last_content = clipboard_content

                is_valid, message = self.validate_youtube_url(clipboard_content)

                if is_valid:
                    url_exists = any(item['url'] == clipboard_content for item in self.clipboard_url_list)

                    if not url_exists:
                        self._add_url_to_clipboard_list(clipboard_content)
                        logger.info(f"New YouTube URL detected and added: {clipboard_content}")

                        if self.clipboard_auto_download_var.get():
                            logger.info(f"Auto-download enabled, starting download: {clipboard_content}")
                            self._auto_download_single_url(clipboard_content)
                else:
                    logger.debug(f"Clipboard content not a valid YouTube URL: {message}")

        except tk.TclError:
            # This is normal when clipboard is empty or selection owner doesn't respond
            pass
        except Exception as e:
            logger.error(f"Error polling clipboard: {e}")

        # Schedule next poll
        if self.clipboard_monitoring:
            self.root.after(CLIPBOARD_POLL_INTERVAL_MS, self._poll_clipboard)

    def _get_clipboard_content(self):
        """Get clipboard content using platform-specific method"""
        try:
            # On Linux, try using xclip or xsel for reliable clipboard access without window focus
            if sys.platform.startswith('linux'):
                # Ensure DISPLAY is set (required for xclip/xsel to work)
                env = os.environ.copy()
                if 'DISPLAY' not in env:
                    env['DISPLAY'] = ':0'  # Default X display

                try:
                    # Try CLIPBOARD selection first (Ctrl+C in most apps)
                    result = subprocess.run(['xclip', '-selection', 'clipboard', '-t', 'UTF8_STRING', '-o'],
                                          capture_output=True, text=True, timeout=0.5, env=env)
                    if result.returncode == 0 and result.stdout:
                        content = result.stdout.strip()
                        if content:
                            return content

                    # Try CLIPBOARD without target type
                    result = subprocess.run(['xclip', '-selection', 'clipboard', '-o'],
                                          capture_output=True, text=True, timeout=0.5, env=env)
                    if result.returncode == 0 and result.stdout:
                        content = result.stdout.strip()
                        if content:
                            return content

                    # Try PRIMARY selection (selected text, middle-click paste)
                    result = subprocess.run(['xclip', '-selection', 'primary', '-o'],
                                          capture_output=True, text=True, timeout=0.5, env=env)
                    if result.returncode == 0 and result.stdout:
                        content = result.stdout.strip()
                        if content:
                            return content

                    # All xclip attempts returned empty
                    return ""

                except FileNotFoundError:
                    logger.info("xclip not found, falling back to tkinter")
                except subprocess.TimeoutExpired:
                    logger.debug("xclip timeout")
                except subprocess.SubprocessError as e:
                    logger.debug(f"xclip subprocess error: {e}")

                try:
                    # Try xsel as fallback
                    result = subprocess.run(['xsel', '--clipboard', '--output'],
                                          capture_output=True, text=True, timeout=0.5, env=env)
                    if result.returncode == 0:
                        # Success! Use xsel even if clipboard is empty
                        content = result.stdout.strip()
                        return content
                except FileNotFoundError:
                    logger.debug("xsel not found, falling back to tkinter")
                except subprocess.SubprocessError as e:
                    logger.debug(f"xsel subprocess error: {e}")

            # Fallback to tkinter clipboard (works on all platforms when window has focus)
            try:
                content = self.root.clipboard_get()
                logger.debug(f"tkinter read clipboard: {len(content)} chars")
                return content
            except tk.TclError:
                return ""  # Clipboard empty

        except Exception as e:
            logger.debug(f"Error getting clipboard: {e}")
            return ""

    # Phase 5: URL List Management

    def _add_url_to_clipboard_list(self, url):
        """Add URL to clipboard list with UI widget"""
        url_frame = ttk.Frame(self.clipboard_url_list_frame, relief='solid', borderwidth=1)
        url_frame.pack(fill=tk.X, padx=5, pady=2)

        status_canvas = tk.Canvas(url_frame, width=12, height=12, bg='white', highlightthickness=0)
        status_canvas.pack(side=tk.LEFT, padx=(5, 5))
        status_circle = status_canvas.create_oval(2, 2, 10, 10, fill='gray', outline='')

        url_display = url if len(url) <= 60 else url[:57] + "..."
        url_label = ttk.Label(url_frame, text=url_display, font=('Arial', 9))
        url_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        remove_btn = ttk.Button(url_frame, text="X", width=3, command=lambda: self._remove_url_from_list(url))
        remove_btn.pack(side=tk.RIGHT, padx=5)

        url_data = {
            'url': url,
            'status': 'pending',
            'widget': url_frame,
            'status_canvas': status_canvas,
            'status_circle': status_circle
        }

        self.clipboard_url_list.append(url_data)
        self.clipboard_url_widgets[url] = url_data

        self._update_clipboard_url_count()
        if len(self.clipboard_url_list) > 0 and not self.clipboard_downloading:
            self.clipboard_download_btn.config(state='normal')

        # Save URLs to persistence file
        self._save_clipboard_urls()

    def _remove_url_from_list(self, url):
        """Remove URL from clipboard list"""
        for i, item in enumerate(self.clipboard_url_list):
            if item['url'] == url:
                if item['widget']:
                    item['widget'].destroy()
                self.clipboard_url_list.pop(i)
                if url in self.clipboard_url_widgets:
                    del self.clipboard_url_widgets[url]
                self._update_clipboard_url_count()
                if len(self.clipboard_url_list) == 0:
                    self.clipboard_download_btn.config(state='disabled')
                logger.info(f"Removed URL: {url}")

                # Save URLs to persistence file
                self._save_clipboard_urls()
                break

    def clear_all_clipboard_urls(self):
        """Clear all URLs from clipboard list"""
        if self.clipboard_downloading:
            messagebox.showwarning("Cannot Clear", "Cannot clear URLs while downloads are in progress.")
            return

        for item in self.clipboard_url_list:
            if item['widget']:
                item['widget'].destroy()

        self.clipboard_url_list.clear()
        self.clipboard_url_widgets.clear()
        self._update_clipboard_url_count()
        self.clipboard_download_btn.config(state='disabled')
        logger.info("Cleared all clipboard URLs")

        # Save URLs to persistence file
        self._save_clipboard_urls()

    def _update_clipboard_url_count(self):
        """Update URL count label"""
        count = len(self.clipboard_url_list)
        self.clipboard_url_count_label.config(text=f"({count} URL{'s' if count != 1 else ''})")

    def _update_url_status(self, url, status):
        """Update visual status of URL: pending (gray), downloading (blue), completed (green), failed (red)"""
        if url in self.clipboard_url_widgets:
            item = self.clipboard_url_widgets[url]
            status_canvas = item['status_canvas']
            status_circle = item['status_circle']

            color_map = {'pending': 'gray', 'downloading': 'blue', 'completed': 'green', 'failed': 'red'}
            color = color_map.get(status, 'gray')
            status_canvas.itemconfig(status_circle, fill=color)

            for item_data in self.clipboard_url_list:
                if item_data['url'] == url:
                    item_data['status'] = status
                    break

    # Phase 6: Download Queue (Sequential Processing)

    def start_clipboard_downloads(self):
        """Start downloading all pending URLs sequentially"""
        if self.clipboard_downloading:
            return

        pending_urls = [item for item in self.clipboard_url_list if item['status'] == 'pending']

        if not pending_urls:
            messagebox.showinfo("No URLs", "No pending URLs to download.")
            return

        self.clipboard_downloading = True
        self.clipboard_download_btn.config(state='disabled')
        self.clipboard_stop_btn.config(state='normal')

        total_count = len(pending_urls)
        self.clipboard_total_label.config(text=f"Completed: 0/{total_count} videos")

        logger.info(f"Starting clipboard batch download: {total_count} URLs")
        self.thread_pool.submit(self._process_clipboard_queue)

    def _process_clipboard_queue(self):
        """Process clipboard download queue sequentially"""
        pending_urls = [item for item in self.clipboard_url_list if item['status'] == 'pending']
        total_count = len(pending_urls)

        for index, item in enumerate(pending_urls):
            if not self.clipboard_downloading:
                logger.info("Clipboard downloads stopped by user")
                break

            url = item['url']

            self.root.after(0, lambda u=url: self._update_url_status(u, 'downloading'))
            self.root.after(0, lambda i=index, t=total_count:
                self.clipboard_total_label.config(text=f"Completed: {i}/{t} videos"))
            self.root.after(0, lambda u=url:
                self.update_clipboard_status(f"Downloading: {u[:50]}...", "blue"))

            success = self._download_clipboard_url(url, check_stop=True)

            if success:
                self.root.after(0, lambda u=url: self._update_url_status(u, 'completed'))
            else:
                self.root.after(0, lambda u=url: self._update_url_status(u, 'failed'))

            completed = index + 1
            self.root.after(0, lambda c=completed, t=total_count:
                self.clipboard_total_label.config(text=f"Completed: {c}/{t} videos"))

        self.root.after(0, self._finish_clipboard_downloads)

    def _download_clipboard_url(self, url, check_stop=False, check_stop_auto=False):
        """Download single URL from clipboard mode (blocking, runs in thread). Returns True if successful."""
        process = None
        try:
            quality = self.clipboard_quality_var.get()
            if "none" in quality.lower():
                quality = "none"

            audio_only = (quality == "none")

            self.root.after(0, lambda: self.clipboard_progress.config(value=0))
            self.root.after(0, lambda: self.clipboard_progress_label.config(text="0%"))

            output_path = os.path.join(self.clipboard_download_path, '%(title)s.%(ext)s')

            # Use helper methods for command construction
            if audio_only:
                cmd = self.build_audio_ytdlp_command(url, output_path, volume=1.0)
            else:
                cmd = self.build_video_ytdlp_command(url, output_path, quality, volume=1.0)

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       universal_newlines=True, bufsize=1)

            for line in process.stdout:
                # Check stop flags
                if check_stop and not self.clipboard_downloading:
                    self.safe_process_cleanup(process)
                    return False
                if check_stop_auto and not self.clipboard_auto_downloading:
                    self.safe_process_cleanup(process)
                    return False

                if '[download]' in line or 'Downloading' in line:
                    progress_match = PROGRESS_REGEX.search(line)
                    if progress_match:
                        progress = float(progress_match.group(1))
                        self.root.after(0, lambda p=progress: self.update_clipboard_progress(p))

            process.wait()

            if process.returncode == 0:
                self.root.after(0, lambda: self.update_clipboard_progress(PROGRESS_COMPLETE))
                logger.info(f"Clipboard download completed: {url}")
                success = True
            else:
                logger.error(f"Clipboard download failed: {url}, returncode={process.returncode}")
                success = False

            # Clean up process resources
            self.safe_process_cleanup(process)
            return success

        except Exception as e:
            logger.exception(f"Error downloading clipboard URL {url}: {e}")
            if process:
                self.safe_process_cleanup(process)
            return False

    def _finish_clipboard_downloads(self):
        """Clean up after batch downloads complete"""
        self.clipboard_downloading = False
        self.clipboard_download_btn.config(state='normal' if len(self.clipboard_url_list) > 0 else 'disabled')
        self.clipboard_stop_btn.config(state='disabled')

        completed = sum(1 for item in self.clipboard_url_list if item['status'] == 'completed')
        failed = sum(1 for item in self.clipboard_url_list if item['status'] == 'failed')

        if failed > 0:
            self.update_clipboard_status(f"Completed: {completed} | Failed: {failed}", "orange")
        else:
            self.update_clipboard_status(f"All downloads complete! ({completed} videos)", "green")

        logger.info(f"Clipboard batch download finished: {completed} completed, {failed} failed")

    def stop_clipboard_downloads(self):
        """Stop clipboard batch downloads and auto-downloads"""
        stopped = False
        if self.clipboard_downloading:
            self.clipboard_downloading = False
            stopped = True
            logger.info("Clipboard batch downloads stopped by user")
        if self.clipboard_auto_downloading:
            self.clipboard_auto_downloading = False
            stopped = True
            logger.info("Clipboard auto-downloads stopped by user")
        if stopped:
            self.update_clipboard_status("Downloads stopped by user", "orange")
            self.clipboard_stop_btn.config(state='disabled')

    def _auto_download_single_url(self, url):
        """Auto-download single URL when detected (if auto-download enabled)"""
        # Check if another auto-download is already in progress (thread-safe)
        with self.auto_download_lock:
            downloading_count = sum(1 for item in self.clipboard_url_list if item['status'] == 'downloading')
            if downloading_count > 0:
                # Another download is in progress, keep this one pending
                logger.info(f"URL queued (another download in progress): {url}")
                return

            self.clipboard_auto_downloading = True
            self._update_url_status(url, 'downloading')

        # Update UI outside the lock
        self.clipboard_stop_btn.config(state='normal')  # Enable stop button
        self._update_auto_download_total()
        self.thread_pool.submit(self._auto_download_worker, url)

    def _auto_download_worker(self, url):
        """Worker thread for auto-downloading single URL"""
        # Check if stopped before starting
        if not self.clipboard_auto_downloading:
            self.root.after(0, lambda: self._update_url_status(url, 'pending'))
            return

        self.root.after(0, lambda: self.update_clipboard_status(f"Auto-downloading: {url[:50]}...", "blue"))

        success = self._download_clipboard_url(url, check_stop_auto=True)

        # Check if stopped during download
        if not self.clipboard_auto_downloading:
            self.root.after(0, lambda: self._update_url_status(url, 'pending'))
            self.root.after(0, lambda: self.update_clipboard_status("Auto-download stopped", "orange"))
            return

        # Schedule all UI updates and next download in a single callback to ensure order
        self.root.after(0, lambda: self._handle_auto_download_complete(url, success))

    def _handle_auto_download_complete(self, url, success):
        """Handle auto-download completion - runs on main thread"""
        if success:
            self._update_url_status(url, 'completed')
            self._update_auto_download_total()
            self.update_clipboard_status(f"Auto-download complete: {url[:50]}...", "green")
            # Auto-remove successfully completed URLs from list
            self._remove_url_from_list(url)
            logger.info(f"Auto-download completed and removed: {url}")
        else:
            self._update_url_status(url, 'failed')
            self._update_auto_download_total()
            self.update_clipboard_status(f"Auto-download failed: {url[:50]}...", "red")
            logger.info(f"Auto-download failed: {url}")

        # Now check for next pending download (all state is consistent now)
        self._check_pending_auto_downloads()

    def _disable_stop_if_idle(self):
        """Disable stop button if no downloads in progress"""
        if not self.clipboard_downloading and not self.clipboard_auto_downloading:
            self.clipboard_stop_btn.config(state='disabled')

    def _check_pending_auto_downloads(self):
        """Check if there are pending URLs that need to be auto-downloaded"""
        # Reset auto-downloading flag if no more downloads
        self.clipboard_auto_downloading = False

        if self.clipboard_auto_download_var.get():
            # Find first pending URL
            for item in self.clipboard_url_list:
                if item['status'] == 'pending':
                    self._auto_download_single_url(item['url'])
                    break  # Only start one at a time
        else:
            # Disable stop button if idle
            self._disable_stop_if_idle()

    def _update_auto_download_total(self):
        """Update total progress for auto-downloads"""
        total = len(self.clipboard_url_list)
        completed = sum(1 for item in self.clipboard_url_list if item['status'] in ['completed', 'failed'])
        self.clipboard_total_label.config(text=f"Completed: {completed}/{total} videos")

    # Phase 7: Helper Methods

    def update_clipboard_progress(self, value):
        """Update clipboard mode progress bar"""
        self.clipboard_progress['value'] = value
        self.clipboard_progress_label.config(text=f"{value:.1f}%")

    def update_clipboard_status(self, message, color):
        """Update clipboard mode status label"""
        self.clipboard_status_label.config(text=message, foreground=color)

    def change_clipboard_path(self):
        """Change clipboard mode download path"""
        path = filedialog.askdirectory(initialdir=self.clipboard_download_path)
        if path:
            if not os.path.exists(path):
                messagebox.showerror("Error", f"Path does not exist: {path}")
                return

            if not os.path.isdir(path):
                messagebox.showerror("Error", f"Path is not a directory: {path}")
                return

            test_file = os.path.join(path, ".ytdl_write_test")
            try:
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
            except (IOError, OSError) as e:
                messagebox.showerror("Error", f"Path is not writable:\n{path}\n\n{str(e)}")
                return

            self.clipboard_download_path = path
            self.clipboard_path_label.config(text=path)
            logger.info(f"Clipboard download path changed to: {path}")

    def open_clipboard_folder(self):
        """Open clipboard mode download folder"""
        try:
            if sys.platform == 'win32':
                os.startfile(self.clipboard_download_path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', self.clipboard_download_path])
            else:
                subprocess.Popen(['xdg-open', self.clipboard_download_path])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open folder:\n{str(e)}")

    def create_placeholder_image(self, width, height, text):
        """Create a placeholder image with text"""
        img = Image.new('RGB', (width, height), color='#2d2d2d')
        draw = ImageDraw.Draw(img)

        # Draw text in center - use default font for cross-platform compatibility
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        # Get text bounding box to center it
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        position = ((width - text_width) // 2, (height - text_height) // 2)
        draw.text(position, text, fill='white', font=font)

        return ImageTk.PhotoImage(img)

    def seconds_to_hms(self, seconds):
        """Convert seconds to HH:MM:SS format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def toggle_trim(self):
        """Enable or disable trimming controls"""
        enabled = self.trim_enabled_var.get()
        if enabled:
            self.fetch_duration_btn.config(state='normal')
            if self.video_duration > 0:
                self.start_slider.config(state='normal')
                self.end_slider.config(state='normal')
                self.start_time_entry.config(state='normal')
                self.end_time_entry.config(state='normal')
        else:
            self.fetch_duration_btn.config(state='disabled')
            self.start_slider.config(state='disabled')
            self.end_slider.config(state='disabled')
            self.start_time_entry.config(state='disabled')
            self.end_time_entry.config(state='disabled')

        # Update file size display when trimming is toggled
        self._update_trimmed_filesize()

    def fetch_duration_clicked(self):
        """Handler for fetch duration button"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a YouTube URL or select a local file first")
            return

        # Check if it's a local file or YouTube URL
        if self.is_local_file(url):
            # Validate local file exists
            if not os.path.isfile(url):
                messagebox.showerror("Error", f"File not found:\n{url}")
                return
            self.local_file_path = url
        else:
            # Validate YouTube URL
            is_valid, message = self.validate_youtube_url(url)
            if not is_valid:
                messagebox.showerror("Invalid URL", message)
                logger.warning(f"Invalid URL rejected: {url}")
                return
            self.local_file_path = None

            # Check if it's a playlist
            self.is_playlist = self.is_playlist_url(url)
            if self.is_playlist:
                # Disable trimming and upload for playlists
                self.trim_enabled_var.set(False)
                self.toggle_trim()  # Disable trim controls
                self.video_info_label.config(text="Playlist detected - Trimming and upload disabled for playlists", foreground="orange")
                self.filesize_label.config(text="")
                logger.info("Playlist URL detected - trimming disabled")
                # Don't fetch duration for playlists
                return

        if self.is_fetching_duration or self.is_downloading:
            return

        # Save the URL for preview extraction and clear cache
        if self.current_video_url != url:
            self.current_video_url = url
            self._clear_preview_cache()
        else:
            self.current_video_url = url

        self.is_fetching_duration = True
        self.fetch_duration_btn.config(state='disabled')
        self.update_status("Fetching video duration...", "blue")

        # Submit to thread pool
        self.thread_pool.submit(self.fetch_video_duration, url)

    def fetch_video_duration(self, url):
        """Fetch video duration and info from URL or local file"""
        try:
            # Check if local file
            if self.is_local_file(url):
                return self._fetch_local_file_duration(url)

            # Fetch duration
            def _fetch_duration():
                cmd = [self.ytdlp_path, '--get-duration', url]
                return subprocess.run(cmd, capture_output=True, text=True, timeout=METADATA_FETCH_TIMEOUT)

            result = self.retry_network_operation(_fetch_duration, "Fetch duration")

            # Fetch title in parallel
            def _fetch_title():
                cmd = [self.ytdlp_path, '--get-title', url]
                return subprocess.run(cmd, capture_output=True, text=True, timeout=METADATA_FETCH_TIMEOUT)

            title_result = self.retry_network_operation(_fetch_title, "Fetch title")

            if result.returncode == 0:
                duration_str = result.stdout.strip()
                # Parse duration (format can be SS, MM:SS, or HH:MM:SS)
                parts = duration_str.split(':')
                if len(parts) == 1:  # Just seconds (e.g., "59")
                    self.video_duration = int(parts[0])
                elif len(parts) == 2:  # MM:SS
                    self.video_duration = int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 3:  # HH:MM:SS
                    self.video_duration = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                else:
                    raise ValueError(f"Invalid duration format: {duration_str}")

                # Update sliders
                self.start_slider.config(from_=0, to=self.video_duration, state='normal')
                self.end_slider.config(from_=0, to=self.video_duration, state='normal')
                self.start_time_var.set(0)
                self.end_time_var.set(self.video_duration)

                # Update entry fields
                self.start_time_entry.config(state='normal')
                self.end_time_entry.config(state='normal')
                self.start_time_entry.delete(0, tk.END)
                self.start_time_entry.insert(0, self.seconds_to_hms(0))
                self.end_time_entry.delete(0, tk.END)
                self.end_time_entry.insert(0, self.seconds_to_hms(self.video_duration))

                # Update duration label
                self.trim_duration_label.config(text=f"Selected Duration: {self.seconds_to_hms(self.video_duration)}")

                # Display video title if available
                if title_result and title_result.returncode == 0:
                    video_title = title_result.stdout.strip()
                    self.video_info_label.config(text=f"Title: {video_title}")
                    logger.info(f"Video title: {video_title}")

                # Fetch estimated file size
                self._fetch_file_size(url)

                self.update_status("Duration fetched successfully", "green")

                # Trigger initial preview update
                self.root.after(100, self.update_previews)
                logger.info(f"Successfully fetched video duration: {self.video_duration}s")
            else:
                raise Exception(f"yt-dlp returned error: {result.stderr}")

        except subprocess.TimeoutExpired:
            error_msg = "Request timed out. Please check your internet connection."
            messagebox.showerror("Error", error_msg)
            self.update_status("Duration fetch timed out", "red")
            logger.error("Timeout fetching video duration")
        except ValueError as e:
            error_msg = f"Invalid duration format received: {str(e)}"
            messagebox.showerror("Error", error_msg)
            self.update_status("Invalid duration format", "red")
            logger.error(f"Duration parsing error: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch video duration:\n{str(e)}")
            self.update_status("Failed to fetch duration", "red")
            logger.exception(f"Unexpected error fetching duration: {e}")

        finally:
            self.is_fetching_duration = False
            if self.trim_enabled_var.get():
                self.fetch_duration_btn.config(state='normal')

    def _fetch_file_size(self, url):
        """Fetch estimated file size for the video (runs in background thread)"""
        def _fetch():
            try:
                import json
                quality = self.quality_var.get()

                # Build format selector based on quality
                if quality == "none":
                    format_selector = "bestaudio"
                else:
                    format_selector = f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]'

                cmd = [self.ytdlp_path, '--dump-json', '-f', format_selector, url]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=STREAM_FETCH_TIMEOUT)

                if result.returncode == 0:
                    info = json.loads(result.stdout)
                    filesize = info.get('filesize') or info.get('filesize_approx')

                    if filesize:
                        # Convert to MB and update UI on main thread
                        filesize_mb = filesize / (1024 * 1024)
                        self.root.after(0, lambda: self._update_filesize_display(filesize, filesize_mb))
                    else:
                        self.root.after(0, lambda: self._update_filesize_display(None, None))
                else:
                    self.root.after(0, lambda: self._update_filesize_display(None, None))
            except Exception as e:
                logger.debug(f"Could not fetch file size: {e}")
                self.root.after(0, lambda: self._update_filesize_display(None, None))

        # Run in background thread
        self.thread_pool.submit(_fetch)

    def _update_filesize_display(self, filesize_bytes, filesize_mb):
        """Update file size display on main thread"""
        if filesize_bytes and filesize_mb:
            self.filesize_label.config(text=f"Estimated size: {filesize_mb:.1f} MB")
            self.estimated_filesize = filesize_bytes
        elif filesize_mb is None and filesize_bytes is None:
            self.filesize_label.config(text="Estimated size: Unknown")
            self.estimated_filesize = None

        # Update trimmed size if trimming is enabled
        self._update_trimmed_filesize()

    def on_quality_change(self, *args):
        """Handle quality selection changes - re-fetch file size with new quality"""
        # Only re-fetch if we have a valid URL and have already fetched duration
        if self.current_video_url and self.video_duration > 0 and not self.is_playlist:
            # Show loading indicator
            self.filesize_label.config(text="Calculating size...")
            # Re-fetch file size with new quality setting (in background)
            self._fetch_file_size(self.current_video_url)

    def _update_trimmed_filesize(self):
        """Update file size estimate based on trim selection using linear calculation"""
        if not self.estimated_filesize or not self.trim_enabled_var.get():
            # If no size estimate or trimming disabled, show original size
            if self.estimated_filesize:
                filesize_mb = self.estimated_filesize / (1024 * 1024)
                self.filesize_label.config(text=f"Estimated size: {filesize_mb:.1f} MB")
            return

        # Calculate trimmed size using linear approach
        start_time = int(self.start_time_var.get())
        end_time = int(self.end_time_var.get())
        selected_duration = end_time - start_time

        if self.video_duration > 0:
            duration_percentage = selected_duration / self.video_duration
            trimmed_size = self.estimated_filesize * duration_percentage
            trimmed_size_mb = trimmed_size / (1024 * 1024)
            self.filesize_label.config(text=f"Estimated size (trimmed): {trimmed_size_mb:.1f} MB")

    def _fetch_local_file_duration(self, filepath):
        """Fetch duration from local file using ffprobe"""
        try:
            cmd = [
                self.ffprobe_path,
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                filepath
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=True)
            duration_seconds = float(result.stdout.strip())
            self.video_duration = int(duration_seconds)

            video_title = Path(filepath).stem

            # Update sliders
            self.start_slider.config(from_=0, to=self.video_duration, state='normal')
            self.end_slider.config(from_=0, to=self.video_duration, state='normal')
            self.start_time_var.set(0)
            self.end_time_var.set(self.video_duration)

            # Update entry fields
            self.start_time_entry.config(state='normal')
            self.end_time_entry.config(state='normal')
            self.start_time_entry.delete(0, tk.END)
            self.start_time_entry.insert(0, self.seconds_to_hms(0))
            self.end_time_entry.delete(0, tk.END)
            self.end_time_entry.insert(0, self.seconds_to_hms(self.video_duration))

            # Update duration label
            self.trim_duration_label.config(text=f"Selected Duration: {self.seconds_to_hms(self.video_duration)}")

            # Display filename
            self.video_info_label.config(text=f"File: {video_title}")
            logger.info(f"Local file duration: {self.video_duration}s")

            self.update_status("Duration fetched successfully", "green")

            # Trigger initial preview update
            self.root.after(100, self.update_previews)

        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to read video file:\n{e.stderr if e.stderr else str(e)}"
            messagebox.showerror("Error", error_msg)
            self.update_status("Failed to read file", "red")
            logger.error(f"ffprobe error: {e}")
        except ValueError as e:
            error_msg = "Invalid video file format"
            messagebox.showerror("Error", error_msg)
            self.update_status("Invalid file format", "red")
            logger.error(f"Duration parsing error: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read file:\n{str(e)}")
            self.update_status("Failed to read file", "red")
            logger.exception(f"Unexpected error reading local file: {e}")
        finally:
            self.is_fetching_duration = False
            if self.trim_enabled_var.get():
                self.fetch_duration_btn.config(state='normal')

    def on_slider_change(self, event=None):
        """Handle slider changes"""
        start_time = int(self.start_time_var.get())
        end_time = int(self.end_time_var.get())

        # Ensure start is before end
        if start_time >= end_time:
            if event:  # Only adjust if this was a user interaction
                # Determine which slider was moved and adjust the other
                if abs(self.start_slider.get() - start_time) < 0.1:  # Start slider was moved
                    end_time = min(start_time + 1, self.video_duration)
                    self.end_time_var.set(end_time)
                else:  # End slider was moved
                    start_time = max(end_time - 1, 0)
                    self.start_time_var.set(start_time)

        # Update entry fields
        self.start_time_entry.delete(0, tk.END)
        self.start_time_entry.insert(0, self.seconds_to_hms(start_time))
        self.end_time_entry.delete(0, tk.END)
        self.end_time_entry.insert(0, self.seconds_to_hms(end_time))

        # Update selected duration
        selected_duration = end_time - start_time
        self.trim_duration_label.config(text=f"Selected Duration: {self.seconds_to_hms(selected_duration)}")

        # Update file size based on trim selection
        self._update_trimmed_filesize()

        # Schedule preview update with debouncing
        self.schedule_preview_update()

    def hms_to_seconds(self, hms_str):
        """Convert HH:MM:SS format to seconds"""
        try:
            parts = hms_str.strip().split(':')
            if len(parts) != 3:
                return None
            hours, minutes, seconds = map(int, parts)
            return hours * 3600 + minutes * 60 + seconds
        except (ValueError, AttributeError):
            return None

    def on_start_entry_change(self, event=None):
        """Handle changes to start time entry field"""
        value_str = self.start_time_entry.get()
        seconds = self.hms_to_seconds(value_str)

        if seconds is not None and 0 <= seconds <= self.video_duration:
            # Valid input, update the slider
            self.start_time_var.set(seconds)
            # on_slider_change will be called automatically via the variable trace
            # But we need to trigger it manually since we're setting the variable directly
            self.on_slider_change()
        else:
            # Invalid input, restore the current value
            current_time = int(self.start_time_var.get())
            self.start_time_entry.delete(0, tk.END)
            self.start_time_entry.insert(0, self.seconds_to_hms(current_time))

    def on_end_entry_change(self, event=None):
        """Handle changes to end time entry field"""
        value_str = self.end_time_entry.get()
        seconds = self.hms_to_seconds(value_str)

        if seconds is not None and 0 <= seconds <= self.video_duration:
            # Valid input, update the slider
            self.end_time_var.set(seconds)
            # Trigger slider change handler
            self.on_slider_change()
        else:
            # Invalid input, restore the current value
            current_time = int(self.end_time_var.get())
            self.end_time_entry.delete(0, tk.END)
            self.end_time_entry.insert(0, self.seconds_to_hms(current_time))

    def on_volume_change(self, event=None):
        """Handle volume slider changes"""
        volume_percent = int(self.volume_var.get() * 100)
        self.volume_entry.delete(0, tk.END)
        self.volume_entry.insert(0, str(volume_percent))

    def on_volume_entry_change(self, event=None):
        """Handle volume entry field changes"""
        try:
            volume_percent = int(self.volume_entry.get())
            # Clamp to 0-200 range
            volume_percent = max(0, min(200, volume_percent))
            self.volume_var.set(volume_percent / 100.0)
            # Update entry with clamped value
            self.volume_entry.delete(0, tk.END)
            self.volume_entry.insert(0, str(volume_percent))
        except ValueError:
            # If invalid input, reset to current slider value
            volume_percent = int(self.volume_var.get() * 100)
            self.volume_entry.delete(0, tk.END)
            self.volume_entry.insert(0, str(volume_percent))

    def reset_volume(self):
        """Reset volume to 100%"""
        self.volume_var.set(1.0)
        self.volume_entry.delete(0, tk.END)
        self.volume_entry.insert(0, "100")

    def start_upload(self):
        """Start upload to Catbox.moe in a background thread"""
        if not self.last_output_file or not os.path.isfile(self.last_output_file):
            messagebox.showerror("Error", "No file available to upload. Please download/process a video first.")
            return

        # Check file size (200MB limit for Catbox.moe)
        file_size_mb = os.path.getsize(self.last_output_file) / (1024 * 1024)
        if file_size_mb > 200:
            messagebox.showerror("File Too Large",
                               f"File size ({file_size_mb:.1f} MB) exceeds Catbox.moe's 200MB limit.\n"
                               "Please trim the video or use a lower quality setting.")
            return

        # Disable upload button during upload
        self.upload_btn.config(state='disabled')
        self.upload_status_label.config(text="Uploading...", foreground="blue")
        self.upload_url_frame.grid_remove()

        # Start upload in background thread
        upload_thread = threading.Thread(target=self.upload_to_catbox, daemon=True)
        upload_thread.start()

    def upload_to_catbox(self):
        """Upload file to Catbox.moe and display the URL"""
        try:
            self.is_uploading = True
            logger.info(f"Starting upload to Catbox.moe: {self.last_output_file}")

            # Upload file using catboxpy
            file_url = self.catbox_client.upload(self.last_output_file)

            # Update UI on success
            self.root.after(0, lambda: self._upload_success(file_url))
            logger.info(f"Upload successful: {file_url}")

        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda: self._upload_failed(error_msg))
            logger.exception(f"Upload failed: {e}")

        finally:
            self.is_uploading = False

    def _upload_success(self, file_url):
        """Handle successful upload (called on main thread)"""
        self.upload_status_label.config(text="Upload complete!", foreground="green")

        # Show URL in entry field
        self.upload_url_entry.config(state='normal')
        self.upload_url_entry.delete(0, tk.END)
        self.upload_url_entry.insert(0, file_url)
        self.upload_url_entry.config(state='readonly')
        self.upload_url_frame.grid()

        # Re-enable upload button for re-uploading if needed
        self.upload_btn.config(state='normal')

        # Save upload link to history
        filename = os.path.basename(self.last_output_file) if self.last_output_file else "unknown"
        self.save_upload_link(file_url, filename)

        messagebox.showinfo("Upload Complete",
                          f"File uploaded successfully!\n\nURL: {file_url}\n\n"
                          "The URL has been copied to your clipboard.")

        # Auto-copy to clipboard
        self.root.clipboard_clear()
        self.root.clipboard_append(file_url)

    def _upload_failed(self, error_msg):
        """Handle failed upload (called on main thread)"""
        self.upload_status_label.config(text="Upload failed", foreground="red")
        self.upload_btn.config(state='normal')
        messagebox.showerror("Upload Failed", f"Failed to upload file:\n\n{error_msg}")

    def copy_upload_url(self):
        """Copy upload URL to clipboard"""
        url = self.upload_url_entry.get()
        if url:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self.upload_status_label.config(text="URL copied to clipboard!", foreground="green")
            logger.info("Upload URL copied to clipboard")

    # Uploader tab methods

    def browse_uploader_files(self):
        """Browse and select multiple files for upload in Uploader tab"""
        file_paths = filedialog.askopenfilenames(
            title="Select Video Files",
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mkv *.mov *.flv *.wmv *.webm *.m4v"),
                ("Audio files", "*.mp3 *.m4a *.wav *.flac *.aac *.ogg"),
                ("All files", "*.*")
            ]
        )

        if file_paths:
            for file_path in file_paths:
                # Check file size
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                if file_size_mb > 200:
                    messagebox.showwarning("File Too Large",
                                         f"Skipped: {os.path.basename(file_path)}\nFile size ({file_size_mb:.1f} MB) exceeds 200MB limit.")
                    continue

                # Add to queue if not already there
                if not any(item['path'] == file_path for item in self.uploader_file_queue):
                    self._add_file_to_uploader_queue(file_path)
                    logger.info(f"Added file to upload queue: {file_path}")

    def _add_file_to_uploader_queue(self, file_path):
        """Add a file to the upload queue with UI widget"""
        file_frame = ttk.Frame(self.uploader_file_list_frame, relief='solid', borderwidth=1)
        file_frame.pack(fill=tk.X, padx=5, pady=2)

        filename = os.path.basename(file_path)
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

        file_label = ttk.Label(file_frame, text=f"{filename} ({file_size_mb:.1f} MB)", font=('Arial', 9))
        file_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 10))

        remove_btn = ttk.Button(file_frame, text="X", width=3,
                              command=lambda: self._remove_file_from_queue(file_path))
        remove_btn.pack(side=tk.RIGHT, padx=5)

        self.uploader_file_queue.append({'path': file_path, 'widget': file_frame})
        self._update_uploader_queue_count()

        if len(self.uploader_file_queue) > 0 and not self.uploader_is_uploading:
            self.uploader_upload_btn.config(state='normal')

    def _remove_file_from_queue(self, file_path):
        """Remove a file from the upload queue"""
        for i, item in enumerate(self.uploader_file_queue):
            if item['path'] == file_path:
                if item['widget']:
                    item['widget'].destroy()
                self.uploader_file_queue.pop(i)
                self._update_uploader_queue_count()
                if len(self.uploader_file_queue) == 0:
                    self.uploader_upload_btn.config(state='disabled')
                logger.info(f"Removed file from queue: {file_path}")
                break

    def clear_uploader_queue(self):
        """Clear all files from upload queue"""
        if self.uploader_is_uploading:
            messagebox.showwarning("Cannot Clear", "Cannot clear queue while uploads are in progress.")
            return

        for item in self.uploader_file_queue:
            if item['widget']:
                item['widget'].destroy()

        self.uploader_file_queue.clear()
        self._update_uploader_queue_count()
        self.uploader_upload_btn.config(state='disabled')
        logger.info("Cleared all files from upload queue")

    def _update_uploader_queue_count(self):
        """Update file queue count label"""
        count = len(self.uploader_file_queue)
        self.uploader_queue_count_label.config(text=f"({count} file{'s' if count != 1 else ''})")

    def start_uploader_upload(self):
        """Start uploading all files in queue sequentially"""
        if len(self.uploader_file_queue) == 0:
            messagebox.showinfo("No Files", "No files in queue. Please add files first.")
            return

        if self.uploader_is_uploading:
            return

        self.uploader_is_uploading = True
        self.uploader_current_index = 0
        self.uploader_upload_btn.config(state='disabled')
        self.uploader_url_frame.grid_remove()

        # Start upload queue processing in background thread
        upload_thread = threading.Thread(target=self._process_uploader_queue, daemon=True)
        upload_thread.start()

    def _process_uploader_queue(self):
        """Process upload queue sequentially"""
        total_count = len(self.uploader_file_queue)

        for index, item in enumerate(self.uploader_file_queue):
            if not self.uploader_is_uploading:
                logger.info("Uploader queue processing stopped by user")
                break

            file_path = item['path']
            filename = os.path.basename(file_path)

            self.root.after(0, lambda i=index, t=total_count, fn=filename:
                self.uploader_status_label.config(
                    text=f"Uploading {i+1}/{t}: {fn}...",
                    foreground="blue"))

            success = self._upload_single_file(file_path)

            if not success:
                # Continue with next file even if one fails
                continue

        self.root.after(0, self._finish_uploader_queue)

    def _upload_single_file(self, file_path):
        """Upload a single file from the queue. Returns True if successful."""
        try:
            logger.info(f"Uploading file from queue: {file_path}")

            # Upload file using catboxpy
            file_url = self.catbox_client.upload(file_path)

            # Save upload link to history
            filename = os.path.basename(file_path)
            self.save_upload_link(file_url, filename)

            # Show latest URL in entry field
            self.root.after(0, lambda url=file_url: self._show_upload_url(url))

            logger.info(f"Upload successful: {file_url}")
            return True

        except Exception as e:
            logger.exception(f"Upload failed for {file_path}: {e}")
            error_msg = str(e)
            self.root.after(0, lambda msg=error_msg, path=file_path:
                messagebox.showerror("Upload Failed",
                    f"Failed to upload {os.path.basename(path)}:\n\n{msg}"))
            return False

    def _show_upload_url(self, file_url):
        """Display the most recent upload URL"""
        self.uploader_url_entry.config(state='normal')
        self.uploader_url_entry.delete(0, tk.END)
        self.uploader_url_entry.insert(0, file_url)
        self.uploader_url_entry.config(state='readonly')
        self.uploader_url_frame.grid()

        # Auto-copy to clipboard
        self.root.clipboard_clear()
        self.root.clipboard_append(file_url)

    def _finish_uploader_queue(self):
        """Clean up after queue upload completes"""
        self.uploader_is_uploading = False

        # Clear the queue
        for item in self.uploader_file_queue:
            if item['widget']:
                item['widget'].destroy()

        count = len(self.uploader_file_queue)
        self.uploader_file_queue.clear()
        self._update_uploader_queue_count()

        self.uploader_status_label.config(text=f"All uploads complete! ({count} files)", foreground="green")
        self.uploader_upload_btn.config(state='disabled')

        logger.info(f"Uploader queue finished: {count} files uploaded")

    def copy_uploader_url(self):
        """Copy upload URL to clipboard from Uploader tab"""
        url = self.uploader_url_entry.get()
        if url:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self.uploader_status_label.config(text="URL copied to clipboard!", foreground="green")
            logger.info("Upload URL copied to clipboard from Uploader tab")

    def _find_latest_file(self):
        """Find the most recently created file in the download directory"""
        try:
            download_dir = Path(self.download_path)
            if not download_dir.exists():
                return None

            # Get all files (not directories) in download directory
            files = [f for f in download_dir.iterdir() if f.is_file()]
            if not files:
                return None

            # Find most recently created file
            latest_file = max(files, key=lambda f: f.stat().st_ctime)
            return str(latest_file)

        except Exception as e:
            logger.error(f"Error finding latest file: {e}")
            return None

    def _enable_upload_button(self, filepath):
        """Enable upload button after successful download"""
        if filepath and os.path.isfile(filepath):
            self.last_output_file = filepath
            self.upload_btn.config(state='normal')
            logger.info(f"Upload enabled for: {filepath}")

            # Auto-upload if enabled (but not for playlists)
            if self.auto_upload_var.get():
                url = self.url_entry.get().strip()
                if url and self.is_playlist_url(url):
                    logger.info("Auto-upload skipped for playlist URL")
                else:
                    logger.info("Auto-upload enabled, starting upload...")
                    self.root.after(500, self.start_upload)  # Small delay to ensure UI updates

    def schedule_preview_update(self):
        """Schedule preview update with debouncing to avoid excessive calls"""
        # Cancel any pending update
        if self.preview_update_timer:
            self.root.after_cancel(self.preview_update_timer)

        # Schedule new update after debounce delay
        self.preview_update_timer = self.root.after(PREVIEW_DEBOUNCE_MS, self.update_previews)

    def _clear_preview_cache(self):
        """Clear the preview frame cache"""
        logger.info("Clearing preview cache")
        self.preview_cache.clear()
        self.cache_access_order.clear()

    def _cache_preview_frame(self, timestamp, file_path):
        """Add a frame to the cache with LRU eviction"""
        # Remove oldest if cache is full
        if len(self.preview_cache) >= PREVIEW_CACHE_SIZE:
            if self.cache_access_order:
                oldest = self.cache_access_order.pop(0)
                if oldest in self.preview_cache:
                    old_path = self.preview_cache.pop(oldest)
                    # Optionally delete the old cached file
                    try:
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    except Exception:
                        pass

        # Add to cache
        self.preview_cache[timestamp] = file_path
        if timestamp in self.cache_access_order:
            self.cache_access_order.remove(timestamp)
        self.cache_access_order.append(timestamp)

    def _get_cached_frame(self, timestamp):
        """Get a cached frame if available"""
        if timestamp in self.preview_cache:
            # Update access order (move to end as most recently used)
            if timestamp in self.cache_access_order:
                self.cache_access_order.remove(timestamp)
            self.cache_access_order.append(timestamp)
            return self.preview_cache[timestamp]
        return None

    def extract_frame(self, timestamp):
        """Extract a single frame at the given timestamp"""
        if not self.current_video_url:
            return None

        # Check cache first
        cached = self._get_cached_frame(timestamp)
        if cached and os.path.exists(cached):
            logger.debug(f"Using cached frame for timestamp {timestamp}s")
            return cached

        try:
            # Create unique temp file for this frame
            temp_file = os.path.join(self.temp_dir, f"frame_{timestamp}.jpg")

            # Handle local files differently
            if self.is_local_file(self.current_video_url):
                # For local files, use the file path directly
                video_url = self.current_video_url
            else:
                # Get the actual video stream URL using yt-dlp with retry
                def _get_stream_url():
                    get_url_cmd = [
                        self.ytdlp_path,
                        '-f', 'bestvideo[height<=480]/best[height<=480]',
                        '-g',
                        self.current_video_url
                    ]
                    return subprocess.run(get_url_cmd, capture_output=True, text=True, timeout=15, check=True)

                result = self.retry_network_operation(_get_stream_url, f"Get stream URL for frame at {timestamp}s")
                video_url = result.stdout.strip().split('\n')[0]

            # Now extract frame from the actual stream with retry
            def _extract_frame():
                cmd = [
                    self.ffmpeg_path,
                    '-ss', str(timestamp),
                    '-i', video_url,
                    '-vframes', '1',
                    '-q:v', '2',
                    '-y',
                    temp_file
                ]
                return subprocess.run(cmd, capture_output=True, timeout=15, check=True)

            self.retry_network_operation(_extract_frame, f"Extract frame at {timestamp}s")

            if os.path.exists(temp_file):
                # Cache the extracted frame
                self._cache_preview_frame(timestamp, temp_file)
                return temp_file

        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout while extracting frame at {timestamp}s")
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error extracting frame at {timestamp}s: {e}")
        except Exception as e:
            logger.error(f"Unexpected error extracting frame at {timestamp}s: {e}")

        return None

    def update_previews(self):
        """Update both preview images"""
        if not self.current_video_url or self.video_duration == 0:
            return

        # Prevent spawning multiple preview threads (thread-safe)
        with self.preview_lock:
            if self.preview_thread_running:
                return
            self.preview_thread_running = True

        start_time = int(self.start_time_var.get())
        end_time = int(self.end_time_var.get())

        # Show loading indicators
        self.start_preview_label.config(image=self.loading_image)
        self.end_preview_label.config(image=self.loading_image)

        # Submit to thread pool instead of creating new thread
        self.thread_pool.submit(self._update_previews_thread, start_time, end_time)

    def _update_previews_thread(self, start_time, end_time):
        """Background thread to extract and update preview frames"""
        try:
            logger.info(f"Extracting preview frames at {start_time}s and {end_time}s")

            # Extract start frame
            start_frame_path = self.extract_frame(start_time)
            if start_frame_path:
                self._update_preview_image(start_frame_path, 'start')
            else:
                # Show error placeholder if extraction failed
                error_img = self.create_placeholder_image(PREVIEW_WIDTH, PREVIEW_HEIGHT, "Error")
                self.root.after(0, lambda img=error_img: self._set_start_preview(img))

            # Extract end frame
            end_frame_path = self.extract_frame(end_time)
            if end_frame_path:
                self._update_preview_image(end_frame_path, 'end')
            else:
                # Show error placeholder if extraction failed
                error_img = self.create_placeholder_image(PREVIEW_WIDTH, PREVIEW_HEIGHT, "Error")
                self.root.after(0, lambda img=error_img: self._set_end_preview(img))
        finally:
            self.preview_thread_running = False

    def _update_preview_image(self, image_path, position):
        """Update preview image in UI (must be called from main thread or scheduled)"""
        try:
            # Load and resize image
            img = Image.open(image_path)
            img.thumbnail((PREVIEW_WIDTH, PREVIEW_HEIGHT), Image.Resampling.LANCZOS)

            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(img)

            # Schedule UI update on main thread
            if position == 'start':
                self.root.after(0, lambda: self._set_start_preview(photo))
            else:
                self.root.after(0, lambda: self._set_end_preview(photo))

        except Exception as e:
            logger.error(f"Error updating preview image for {position}: {e}")

    def _set_start_preview(self, photo):
        """Set start preview image (called on main thread)"""
        self.start_preview_image = photo  # Keep reference to avoid garbage collection
        self.start_preview_label.config(image=photo, text='')

    def _set_end_preview(self, photo):
        """Set end preview image (called on main thread)"""
        self.end_preview_image = photo  # Keep reference to avoid garbage collection
        self.end_preview_label.config(image=photo, text='')

    def change_path(self):
        """Change download path with validation"""
        path = filedialog.askdirectory(initialdir=self.download_path)
        if path:
            # Validate that path exists and is writable
            if not os.path.exists(path):
                messagebox.showerror("Error", f"Path does not exist: {path}")
                return

            if not os.path.isdir(path):
                messagebox.showerror("Error", f"Path is not a directory: {path}")
                return

            # Test write permissions
            test_file = os.path.join(path, ".ytdl_write_test")
            try:
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
            except (IOError, OSError) as e:
                messagebox.showerror("Error", f"Path is not writable:\n{path}\n\n{str(e)}")
                return

            self.download_path = path
            self.path_label.config(text=path)

    def open_download_folder(self):
        """Open the download folder in the system file manager"""
        try:
            if sys.platform == 'win32':
                os.startfile(self.download_path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', self.download_path])
            else:
                subprocess.Popen(['xdg-open', self.download_path])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open folder:\n{str(e)}")

    def browse_local_file(self):
        """Open file dialog to select a local video file"""
        filetypes = [
            ('Video Files', '*.mp4 *.mkv *.avi *.mov *.flv *.webm *.wmv *.m4v'),
            ('All Files', '*.*')
        ]

        filepath = filedialog.askopenfilename(
            title="Select a video file",
            filetypes=filetypes,
            initialdir=str(Path.home())
        )

        if filepath:
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, filepath)
            self.local_file_path = filepath
            self.mode_label.config(
                text=f"Mode: Local File | {Path(filepath).name}",
                foreground="green"
            )
            # Clear filename field for new file
            self.filename_entry.delete(0, tk.END)
            logger.info(f"Local file selected: {filepath}")

    def on_url_change(self, event=None):
        """Detect if input is URL or file path"""
        input_text = self.url_entry.get().strip()

        if not input_text:
            self.mode_label.config(text="")
            self.local_file_path = None
            return

        # Clear filename field when URL/file changes
        self.filename_entry.delete(0, tk.END)

        if self.is_local_file(input_text):
            self.local_file_path = input_text
            self.mode_label.config(
                text=f"Mode: Local File | {Path(input_text).name}",
                foreground="green"
            )
        else:
            self.local_file_path = None
            self.mode_label.config(
                text="Mode: YouTube Download",
                foreground="blue"
            )

    def is_local_file(self, input_text):
        """Check if input is a local file path"""
        if os.path.isfile(input_text):
            return True

        path = Path(input_text)
        video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm', '.wmv', '.m4v', '.ts', '.mpg', '.mpeg'}
        if path.suffix.lower() in video_extensions:
            return True

        return False

    def _get_bundled_executable(self, name):
        """Get path to bundled executable (ffmpeg/ffprobe/yt-dlp) if available"""
        # When packaged with PyInstaller, bundled files are in sys._MEIPASS
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            if sys.platform == 'win32':
                exe_name = f"{name}.exe"
            else:
                exe_name = name

            bundled_path = os.path.join(bundle_dir, exe_name)
            if os.path.exists(bundled_path):
                logger.info(f"Using bundled {name}: {bundled_path}")
                return bundled_path

        # When running from source, check local venv first
        else:
            # Check venv in script directory
            script_dir = Path(__file__).parent
            venv_path = script_dir / 'venv' / 'bin' / name
            if venv_path.exists():
                logger.info(f"Using venv {name}: {venv_path}")
                return str(venv_path)

            # Check current Python's bin directory (if venv is activated)
            python_bin_path = Path(sys.executable).parent / name
            if python_bin_path.exists():
                logger.info(f"Using Python bin {name}: {python_bin_path}")
                return str(python_bin_path)

        # Fall back to system PATH
        return name

    def check_dependencies(self):
        """Check if yt-dlp, ffmpeg, and ffprobe are available"""
        try:
            # Check yt-dlp
            result = subprocess.run([self.ytdlp_path, '--version'],
                                  capture_output=True, check=True, timeout=DEPENDENCY_CHECK_TIMEOUT)
            logger.info(f"yt-dlp version: {result.stdout.decode().strip()}")

            # Check ffmpeg (use bundled or system)
            result = subprocess.run([self.ffmpeg_path, '-version'],
                                  capture_output=True, check=True, timeout=DEPENDENCY_CHECK_TIMEOUT)
            logger.info(f"ffmpeg is available at: {self.ffmpeg_path}")

            # Check ffprobe (use bundled or system)
            result = subprocess.run([self.ffprobe_path, '-version'],
                                  capture_output=True, check=True, timeout=DEPENDENCY_CHECK_TIMEOUT)
            logger.info(f"ffprobe is available at: {self.ffprobe_path}")

            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.error(f"Dependency check failed: {e}")
            return False

    def start_download(self):
        url = self.url_entry.get().strip()

        if not url:
            messagebox.showerror("Error", "Please enter a YouTube URL or select a local file")
            return

        # Check if local file or YouTube URL
        is_local = self.is_local_file(url)

        if is_local:
            # Validate local file exists
            if not os.path.isfile(url):
                messagebox.showerror("Error", f"File not found:\n{url}")
                return
        else:
            # Validate YouTube URL
            is_valid, message = self.validate_youtube_url(url)
            if not is_valid:
                messagebox.showerror("Invalid URL", message)
                logger.warning(f"Invalid URL rejected for download: {url}")
                return

            # Check if it's a playlist and update flag
            self.is_playlist = self.is_playlist_url(url)

        if not self.dependencies_ok:
            messagebox.showerror("Error", "yt-dlp or ffmpeg is not installed.\n\nInstall with:\npip install yt-dlp\n\nand install ffmpeg from your package manager")
            return

        logger.info(f"Starting download for URL: {url}")

        self.is_downloading = True
        self.download_start_time = time.time()
        self.last_progress_time = time.time()
        self.download_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.progress['value'] = 0
        self.progress_label.config(text="0%")

        # Submit download and timeout monitor to thread pool
        self.thread_pool.submit(self.download, url)
        self.thread_pool.submit(self._monitor_download_timeout)

    def _monitor_download_timeout(self):
        """Monitor download for timeouts (absolute and progress-based)"""
        while self.is_downloading:
            time.sleep(10)  # Check every 10 seconds

            if not self.is_downloading:
                break

            current_time = time.time()

            # Check absolute timeout
            if self.download_start_time:
                elapsed = current_time - self.download_start_time
                if elapsed > DOWNLOAD_TIMEOUT:
                    logger.error(f"Download exceeded absolute timeout ({DOWNLOAD_TIMEOUT}s)")
                    self.root.after(0, lambda: self._timeout_download("Download timeout (60 min limit exceeded)"))
                    break

            # Check progress timeout (stalled download)
            if self.last_progress_time:
                time_since_progress = current_time - self.last_progress_time
                if time_since_progress > DOWNLOAD_PROGRESS_TIMEOUT:
                    logger.error(f"Download stalled (no progress for {DOWNLOAD_PROGRESS_TIMEOUT}s)")
                    self.root.after(0, lambda: self._timeout_download("Download stalled (no progress for 10 minutes)"))
                    break

    def _timeout_download(self, reason):
        """Handle download timeout"""
        if self.is_downloading:
            logger.warning(f"Timing out download: {reason}")
            self.update_status(reason, "red")
            self.stop_download()

    def _get_speed_limit_args(self):
        """Get yt-dlp speed limit arguments if speed limit is set"""
        speed_limit_str = self.speed_limit_var.get().strip()
        if speed_limit_str:
            try:
                speed_limit = float(speed_limit_str)
                if speed_limit > 0:
                    # yt-dlp expects rate in bytes/second, user enters MB/s
                    # 1 MB = 1024 * 1024 bytes
                    rate_bytes = int(speed_limit * 1024 * 1024)
                    return ['--limit-rate', f'{rate_bytes}']
            except ValueError:
                # Invalid input, ignore
                pass
        return []

    def stop_download(self):
        """Stop download gracefully, with forced termination as fallback"""
        if self.current_process and self.is_downloading:
            self.safe_process_cleanup(self.current_process)

            self.is_downloading = False
            self.update_status("Download stopped", "orange")
            self.download_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            self.progress['value'] = 0
            self.progress_label.config(text="0%")

    def download(self, url):
        try:
            # Route to local file handler if needed
            if self.is_local_file(url):
                return self.download_local_file(url)

            # Handle playlist downloads
            if self.is_playlist:
                return self.download_playlist(url)

            quality = self.quality_var.get()
            trim_enabled = self.trim_enabled_var.get()
            audio_only = (quality == "none")

            self.update_status("Starting download...", "blue")

            # Check if trimming is enabled and validate
            if trim_enabled:
                if self.video_duration <= 0:
                    self.update_status("Please fetch video duration first", "red")
                    self.download_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    self.is_downloading = False
                    return

                start_time = int(self.start_time_var.get())
                end_time = int(self.end_time_var.get())

                if start_time >= end_time:
                    self.update_status("Invalid time range", "red")
                    self.download_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    self.is_downloading = False
                    return

            if audio_only:
                # Check for custom filename
                custom_name = self.sanitize_filename(self.filename_entry.get().strip())
                if custom_name:
                    # Use custom filename
                    base_name = custom_name
                else:
                    # Use video title from yt-dlp
                    base_name = '%(title)s'

                # Generate filename with trim times if trimming is enabled
                if trim_enabled:
                    start_hms = self.seconds_to_hms(start_time).replace(':', '-')
                    end_hms = self.seconds_to_hms(end_time).replace(':', '-')
                    output_template = f'{base_name}_[{start_hms}_to_{end_hms}].%(ext)s'
                else:
                    output_template = f'{base_name}.%(ext)s'

                cmd = [
                    self.ytdlp_path,
                    '--concurrent-fragments', '5',  # Download fragments in parallel
                    '--buffer-size', BUFFER_SIZE,  # Better buffering
                    '--http-chunk-size', CHUNK_SIZE,  # Larger chunks = fewer requests
                    '-f', 'bestaudio',
                    '--extract-audio',
                    '--audio-format', 'm4a',
                    '--audio-quality', '128K',
                    '--newline',
                    '--progress',
                    '-o', os.path.join(self.download_path, output_template),
                ]

                # Build ffmpeg postprocessor args for audio
                ffmpeg_args = []

                if trim_enabled:
                    ffmpeg_args.extend(['-ss', str(start_time), '-to', str(end_time)])

                # Add volume filter (validated)
                volume_multiplier = self.validate_volume(self.volume_var.get())
                if volume_multiplier != 1.0:
                    ffmpeg_args.extend(['-af', f'volume={volume_multiplier}'])

                # Add to command if there are any ffmpeg args
                if ffmpeg_args:
                    cmd.extend(['--postprocessor-args', 'ffmpeg:' + ' '.join(ffmpeg_args)])

                # Add speed limit if set
                cmd.extend(self._get_speed_limit_args())

                cmd.append(url)
            else:
                if quality == "none":
                    self.update_status("Please select a video quality", "red")
                    self.download_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    self.is_downloading = False
                    return

                height = quality

                # Check for custom filename
                custom_name = self.sanitize_filename(self.filename_entry.get().strip())
                if custom_name:
                    # Use custom filename
                    base_name = custom_name
                else:
                    # Use video title from yt-dlp
                    base_name = '%(title)s'

                # Generate filename with trim times if trimming is enabled
                if trim_enabled:
                    start_hms_file = self.seconds_to_hms(start_time).replace(':', '-')
                    end_hms_file = self.seconds_to_hms(end_time).replace(':', '-')
                    output_template = f'{base_name}_[{start_hms_file}_to_{end_hms_file}].%(ext)s'
                else:
                    output_template = f'{base_name}.%(ext)s'

                cmd = [
                    self.ytdlp_path,
                    '--concurrent-fragments', '5',  # Download fragments in parallel
                    '--buffer-size', BUFFER_SIZE,  # Better buffering
                    '--http-chunk-size', CHUNK_SIZE,  # Larger chunks = fewer requests
                    '-f', f'bestvideo[height<={height}]+bestaudio/best[height<={height}]',
                    '--merge-output-format', 'mp4',
                ]

                # Add trimming parameters
                if trim_enabled:
                    # Use download-sections for efficient trimming
                    start_hms = self.seconds_to_hms(start_time)
                    end_hms = self.seconds_to_hms(end_time)
                    cmd.extend([
                        '--download-sections', f'*{start_hms}-{end_hms}',
                        '--force-keyframes-at-cuts',
                    ])

                # Build ffmpeg postprocessor args for video (only if needed)
                volume_multiplier = self.validate_volume(self.volume_var.get())
                needs_processing = trim_enabled or volume_multiplier != 1.0

                if needs_processing:
                    # Need to re-encode due to trimming or volume change
                    ffmpeg_video_args = ['-c:v', 'libx264', '-crf', str(VIDEO_CRF), '-preset', 'faster', '-c:a', 'aac', '-b:a', AUDIO_BITRATE]

                    # Add volume filter if needed
                    if volume_multiplier != 1.0:
                        ffmpeg_video_args.extend(['-af', f'volume={volume_multiplier}'])

                    cmd.extend(['--postprocessor-args', 'ffmpeg:' + ' '.join(ffmpeg_video_args)])

                # Add speed limit if set
                cmd.extend(self._get_speed_limit_args())

                cmd.extend([
                    '--newline',
                    '--progress',
                    '-o', os.path.join(self.download_path, output_template),
                    url
                ])

            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            # Parse output for progress
            for line in self.current_process.stdout:
                if not self.is_downloading:
                    break

                # Look for download progress - multiple patterns for reliability
                if '[download]' in line or 'Downloading' in line:
                    # Parse progress percentage
                    progress_match = PROGRESS_REGEX.search(line)
                    if progress_match:
                        progress = float(progress_match.group(1))
                        self.update_progress(progress)

                        # Try to extract speed and ETA from the line
                        status_msg = f"Downloading... {progress:.1f}%"

                        # Look for speed (e.g., "1.23MiB/s" or "500.00KiB/s")
                        speed_match = SPEED_REGEX.search(line)
                        if speed_match:
                            speed = speed_match.group(1)
                            status_msg += f" at {speed}"

                        # Look for ETA (e.g., "00:05" or "01:23:45")
                        eta_match = ETA_REGEX.search(line)
                        if eta_match:
                            eta = eta_match.group(1)
                            status_msg += f" | ETA: {eta}"

                        self.update_status(status_msg, "blue")
                        self.last_progress_time = time.time()  # Update progress timestamp
                    elif 'Destination' in line:
                        # yt-dlp is starting download
                        self.update_status("Starting download...", "blue")
                        self.last_progress_time = time.time()

                # Look for different download phases
                elif '[info]' in line and 'Downloading' in line:
                    self.update_status("Preparing download...", "blue")
                    self.last_progress_time = time.time()
                elif '[ExtractAudio]' in line:
                    self.update_status("Extracting audio...", "blue")
                    self.last_progress_time = time.time()
                elif '[Merger]' in line or 'Merging' in line:
                    self.update_status("Merging video and audio...", "blue")
                    self.last_progress_time = time.time()
                elif '[ffmpeg]' in line:
                    self.update_status("Processing with ffmpeg...", "blue")
                    self.last_progress_time = time.time()
                elif 'Post-processing' in line or 'Postprocessing' in line:
                    self.update_status("Post-processing...", "blue")
                    self.last_progress_time = time.time()
                elif 'has already been downloaded' in line:
                    self.update_status("File already exists, skipping...", "orange")
                    self.last_progress_time = time.time()

            self.current_process.wait()

            if self.current_process.returncode == 0 and self.is_downloading:
                self.update_progress(100)
                self.update_status("Download complete!", "green")
                logger.info(f"Download completed successfully: {url}")

                # Enable upload button with the most recent file
                latest_file = self._find_latest_file()
                self._enable_upload_button(latest_file)

            elif self.is_downloading:
                self.update_status("Download failed", "red")
                logger.error(f"Download failed with return code {self.current_process.returncode}")

        except FileNotFoundError as e:
            if self.is_downloading:
                error_msg = "yt-dlp or ffmpeg not found. Please ensure they are installed."
                self.update_status(error_msg, "red")
                logger.error(f"Dependency not found: {e}")
        except PermissionError as e:
            if self.is_downloading:
                error_msg = "Permission denied. Check write permissions for download folder."
                self.update_status(error_msg, "red")
                logger.error(f"Permission error: {e}")
        except OSError as e:
            if self.is_downloading:
                error_msg = f"OS error: {str(e)}"
                self.update_status(error_msg, "red")
                logger.error(f"OS error during download: {e}")
        except Exception as e:
            if self.is_downloading:
                self.update_status(f"Error: {str(e)}", "red")
                logger.exception(f"Unexpected error during download: {e}")

        finally:
            self.is_downloading = False
            self.download_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            self.current_process = None

    def download_local_file(self, filepath):
        """Process local video file with trimming, quality adjustment, and volume control"""
        try:
            quality = self.quality_var.get()
            trim_enabled = self.trim_enabled_var.get()
            audio_only = (quality == "none")

            self.update_status("Processing local file...", "blue")

            # Validate trimming
            if trim_enabled:
                if self.video_duration <= 0:
                    self.update_status("Please fetch video duration first", "red")
                    self.download_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    self.is_downloading = False
                    return

                start_time = int(self.start_time_var.get())
                end_time = int(self.end_time_var.get())

                if start_time >= end_time:
                    self.update_status("Invalid time range", "red")
                    self.download_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    self.is_downloading = False
                    return

            # Generate output filename
            custom_name = self.sanitize_filename(self.filename_entry.get().strip())
            if custom_name:
                # Use custom filename
                base_name = custom_name
            else:
                # Use original file stem
                input_path = Path(filepath)
                base_name = input_path.stem

            if trim_enabled:
                start_hms = self.seconds_to_hms(start_time).replace(':', '-')
                end_hms = self.seconds_to_hms(end_time).replace(':', '-')
                output_name = f"{base_name}_[{start_hms}_to_{end_hms}]"
            else:
                # Only add "_processed" if using original filename, not custom
                if custom_name:
                    output_name = base_name
                else:
                    output_name = f"{base_name}_processed"

            volume_multiplier = self.validate_volume(self.volume_var.get())

            if audio_only:
                # Extract audio only
                output_file = os.path.join(self.download_path, f"{output_name}.m4a")
                cmd = [self.ffmpeg_path, '-i', filepath]

                if trim_enabled:
                    cmd.extend(['-ss', str(start_time), '-to', str(end_time)])

                cmd.extend(['-vn', '-c:a', 'aac', '-b:a', '128k'])

                if volume_multiplier != 1.0:
                    cmd.extend(['-af', f'volume={volume_multiplier}'])

                cmd.extend(['-progress', 'pipe:1', '-y', output_file])
            else:
                # Video processing
                if quality == "none":
                    self.update_status("Please select a video quality", "red")
                    self.download_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    self.is_downloading = False
                    return

                height = quality
                output_file = os.path.join(self.download_path, f"{output_name}.mp4")

                cmd = [self.ffmpeg_path, '-i', filepath]

                if trim_enabled:
                    cmd.extend(['-ss', str(start_time), '-to', str(end_time)])

                cmd.extend(['-vf', f'scale=-2:{height}', '-c:v', 'libx264', '-crf', str(VIDEO_CRF),
                           '-preset', 'faster', '-c:a', 'aac', '-b:a', AUDIO_BITRATE])

                if volume_multiplier != 1.0:
                    cmd.extend(['-af', f'volume={volume_multiplier}'])

                cmd.extend(['-progress', 'pipe:1', '-y', output_file])

            logger.info(f"Processing local file: {' '.join(cmd)}")

            # Execute ffmpeg
            self.current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                                     universal_newlines=True, bufsize=1)

            # Parse ffmpeg progress
            total_duration = self.video_duration if not trim_enabled else (end_time - start_time)

            for line in self.current_process.stdout:
                if not self.is_downloading:
                    break

                if 'out_time_ms=' in line:
                    try:
                        time_ms = int(line.split('=')[1].strip())
                        current_time = time_ms / 1000000

                        if total_duration > 0:
                            progress = min(100, (current_time / total_duration) * 100)
                            self.update_progress(progress)
                            self.update_status(f"Processing... {progress:.1f}%", "blue")
                            self.last_progress_time = time.time()
                    except (ValueError, IndexError):
                        pass

            self.current_process.wait()

            if self.current_process.returncode == 0 and self.is_downloading:
                self.update_progress(100)
                self.update_status("Processing complete!", "green")
                logger.info(f"Local file processed: {output_file}")

                # Enable upload button
                self._enable_upload_button(output_file)

            elif self.is_downloading:
                stderr = self.current_process.stderr.read() if self.current_process.stderr else ""
                self.update_status("Processing failed", "red")
                logger.error(f"ffmpeg failed: {stderr}")

        except FileNotFoundError as e:
            if self.is_downloading:
                self.update_status("ffmpeg not found. Please ensure it is installed.", "red")
                logger.error(f"ffmpeg not found: {e}")
        except Exception as e:
            if self.is_downloading:
                self.update_status(f"Error: {str(e)}", "red")
                logger.exception(f"Error processing local file: {e}")
        finally:
            self.is_downloading = False
            self.download_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            self.current_process = None

    def download_playlist(self, url):
        """Download entire YouTube playlist with quality and volume settings"""
        try:
            quality = self.quality_var.get()
            audio_only = (quality == "none")
            volume_multiplier = self.validate_volume(self.volume_var.get())

            # Check for custom filename
            custom_name = self.sanitize_filename(self.filename_entry.get().strip())
            if custom_name:
                # Use custom name with playlist index: MyVideo-1, MyVideo-2, etc.
                output_template = f'{custom_name}-%(playlist_index)s.%(ext)s'
            else:
                # Use default: index-title format
                output_template = '%(playlist_index)s-%(title)s.%(ext)s'

            self.update_status("Downloading playlist...", "blue")
            logger.info(f"Starting playlist download: {url}")

            if audio_only:
                # Audio-only playlist
                cmd = [
                    self.ytdlp_path,
                    '--concurrent-fragments', '5',  # Download fragments in parallel
                    '--buffer-size', BUFFER_SIZE,  # Better buffering
                    '--http-chunk-size', CHUNK_SIZE,  # Larger chunks = fewer requests
                    '-f', 'bestaudio',
                    '--extract-audio',
                    '--audio-format', 'm4a',
                    '--audio-quality', '128K',
                    '--newline',
                    '--progress',
                    '-o', os.path.join(self.download_path, output_template),
                ]

                # Add volume filter
                if volume_multiplier != 1.0:
                    cmd.extend(['--postprocessor-args', f'ffmpeg:-af volume={volume_multiplier}'])

                # Add speed limit if set
                cmd.extend(self._get_speed_limit_args())

                cmd.append(url)

            else:
                # Video playlist
                if quality == "none":
                    self.update_status("Please select a video quality", "red")
                    self.download_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    self.is_downloading = False
                    return

                height = quality
                cmd = [
                    self.ytdlp_path,
                    '--concurrent-fragments', '5',  # Download fragments in parallel
                    '--buffer-size', BUFFER_SIZE,  # Better buffering
                    '--http-chunk-size', CHUNK_SIZE,  # Larger chunks = fewer requests
                    '-f', f'bestvideo[height<={height}]+bestaudio/best[height<={height}]',
                    '--merge-output-format', 'mp4',
                ]

                # Build ffmpeg postprocessor args for video (only if volume changed)
                if volume_multiplier != 1.0:
                    # Need to re-encode for volume adjustment
                    ffmpeg_video_args = ['-c:v', 'libx264', '-crf', str(VIDEO_CRF), '-preset', 'faster', '-c:a', 'aac', '-b:a', AUDIO_BITRATE]
                    ffmpeg_video_args.extend(['-af', f'volume={volume_multiplier}'])
                    cmd.extend(['--postprocessor-args', 'ffmpeg:' + ' '.join(ffmpeg_video_args)])

                # Add speed limit if set
                cmd.extend(self._get_speed_limit_args())

                cmd.extend([
                    '--newline',
                    '--progress',
                    '-o', os.path.join(self.download_path, output_template),
                    url
                ])

            logger.info(f"Playlist download command: {' '.join(cmd)}")

            # Execute yt-dlp
            self.current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                     universal_newlines=True, bufsize=1)

            # Parse yt-dlp output
            for line in self.current_process.stdout:
                if not self.is_downloading:
                    break

                logger.debug(f"yt-dlp output: {line.strip()}")

                # Parse progress
                if '[download]' in line and '%' in line:
                    try:
                        # Extract percentage
                        match = PROGRESS_REGEX.search(line)
                        if match:
                            progress = float(match.group(1))
                            self.update_progress(progress)
                            self.last_progress_time = time.time()

                            # Extract current file info
                            if 'Downloading item' in line:
                                self.update_status(line.strip(), "blue")
                            else:
                                self.update_status(f"Downloading playlist... {progress:.1f}%", "blue")
                    except (ValueError, AttributeError):
                        pass

            self.current_process.wait()

            if self.current_process.returncode == 0 and self.is_downloading:
                self.update_progress(100)
                self.update_status("Playlist download complete!", "green")
                logger.info(f"Playlist downloaded successfully: {url}")
                # Note: Upload is disabled for playlists
            elif self.is_downloading:
                self.update_status("Playlist download failed", "red")
                logger.error(f"Playlist download failed with return code {self.current_process.returncode}")

        except FileNotFoundError as e:
            if self.is_downloading:
                self.update_status("yt-dlp not found. Please ensure it is installed.", "red")
                logger.error(f"yt-dlp not found: {e}")
        except Exception as e:
            if self.is_downloading:
                self.update_status(f"Error: {str(e)}", "red")
                logger.exception(f"Error downloading playlist: {e}")
        finally:
            self.is_downloading = False
            self.download_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            self.current_process = None

    def update_progress(self, value):
        self.progress['value'] = value
        self.progress_label.config(text=f"{value:.1f}%")

    def update_status(self, message, color):
        self.status_label.config(text=message, foreground=color)

    def cleanup_temp_files(self):
        """Clean up temporary preview files"""
        try:
            import shutil
            # Clear cache references
            self._clear_preview_cache()
            # Remove temp directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temp directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {e}")

    def on_closing(self):
        """Handle window close event with proper resource cleanup"""
        logger.info("Application shutdown initiated...")

        # Stop clipboard monitoring
        self.stop_clipboard_monitoring()

        # Stop clipboard downloads
        if self.clipboard_downloading:
            self.clipboard_downloading = False
            time.sleep(0.5)

        # Stop any ongoing downloads gracefully
        if self.is_downloading and self.current_process:
            logger.info("Terminating active download process...")
            self.safe_process_cleanup(self.current_process)

        # Clean up temp files
        try:
            self.cleanup_temp_files()
        except Exception as e:
            logger.error(f"Error cleaning temp files: {e}")

        # Shutdown thread pool gracefully with timeout
        logger.info("Shutting down thread pool...")
        try:
            self.thread_pool.shutdown(wait=True, cancel_futures=False)
        except Exception as e:
            logger.error(f"Error shutting down thread pool: {e}")

        logger.info("Application shutdown complete")

        # Close the window
        self.root.destroy()

def main():
    root = tk.Tk()
    app = YouTubeDownloader(root)
    root.mainloop()

if __name__ == "__main__":
    main()
