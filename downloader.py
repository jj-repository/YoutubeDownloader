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
UI_INITIAL_DELAY_MS = 100  # Delay for initial UI setup callbacks (milliseconds)
AUTO_UPLOAD_DELAY_MS = 500  # Delay before auto-upload starts (milliseconds)
SHUTDOWN_GRACE_PERIOD_SEC = 0.5  # Wait time during graceful shutdown (seconds)

# File paths for persistence
UPLOAD_HISTORY_FILE = Path.home() / ".youtubedownloader" / "upload_history.txt"
CLIPBOARD_URLS_FILE = Path.home() / ".youtubedownloader" / "clipboard_urls.json"
CONFIG_FILE = Path.home() / ".youtubedownloader" / "config.json"

# Internationalization (i18n) - Multi-language support
CURRENT_LANGUAGE = 'en'  # Default language

# Translation strings for English, German, and Polish
TRANSLATIONS = {
    'en': {
        # Window & Language
        'window_title': 'YoutubeDownloader',
        'language': 'Language',
        'info_language_changed_title': 'Language Changed',
        'info_language_changed_msg': 'Language has been changed. Please restart the application for changes to take effect.',

        # Tabs
        'tab_trimmer': 'Trimmer',
        'tab_clipboard': 'Clipboard Mode',
        'tab_uploader': 'Uploader',

        # Common buttons
        'btn_download': 'Download',
        'btn_stop': 'Stop',
        'btn_browse': 'Browse',
        'btn_change': 'Change',
        'btn_open_folder': 'Open Folder',
        'btn_upload': 'Upload to Catbox.moe',
        'btn_copy_url': 'Copy URL',
        'btn_clear_all': 'Clear All',
        'btn_add_files': 'Add Files',
        'btn_close': 'Close',
        'btn_copy_all': 'Copy All',

        # Trimmer tab
        'label_youtube_url': 'YouTube URL or Local File:',
        'btn_browse_local': 'Browse Local File',
        'label_video_quality': 'Video Quality:',
        'quality_audio_only': 'none (Audio only)',
        'label_trim_video': 'Trim Video:',
        'label_volume': 'Volume:',
        'btn_reset_volume': 'Reset to 100%',
        'checkbox_enable_trimming': 'Enable video trimming',
        'btn_fetch_duration': 'Fetch Video Duration',
        'label_start_time': 'Start Time:',
        'label_end_time': 'End Time:',
        'label_preview': 'Preview',
        'label_loading': 'Loading...',
        'label_error': 'Error',
        'label_selected_duration': 'Selected Duration: 00:00:00',
        'label_save_to': 'Save to:',
        'label_output_filename': 'Output filename:',
        'hint_filename': '(Optional - leave empty for auto-generated name)',
        'label_upload_section': 'Upload to Streaming Site:',
        'btn_view_history': 'View Upload History',
        'checkbox_auto_upload': 'Auto-upload after download/trim completes',
        'label_upload_url': 'Upload URL:',
        'label_mode_local': 'Mode: Local File | {filename}',
        'label_mode_youtube': 'Mode: YouTube Download',

        # Clipboard Mode tab
        'header_clipboard_mode': 'Clipboard Mode',
        'desc_clipboard_mode': 'Copy YouTube URLs (Ctrl+C) to automatically detect and download them.',
        'label_download_mode': 'Download Mode:',
        'checkbox_auto_download': 'Auto-download (starts immediately)',
        'header_settings': 'Settings',
        'label_quality': 'Quality:',
        'label_detected_urls': 'Detected URLs',
        'label_url_count': '({count} URL{s})',
        'btn_download_all': 'Download All',
        'label_current_download': 'Current Download:',
        'label_completed_total': 'Completed: {done}/{total} videos',

        # Uploader tab
        'header_upload_file': 'Upload Local File',
        'desc_upload_file': 'Upload local video files to Catbox.moe streaming service.',
        'label_file_queue': 'File Queue:',
        'label_file_count': '({count} file{s})',

        # Status messages
        'status_ready': 'Ready',
        'status_fetching_duration': 'Fetching video duration...',
        'status_duration_fetched': 'Duration fetched successfully',
        'status_starting_download': 'Starting download...',
        'status_downloading': 'Downloading... {progress}%',
        'status_download_complete': 'Download complete!',
        'status_download_stopped': 'Download stopped',
        'status_download_failed': 'Download failed',
        'status_processing': 'Processing... {progress}%',
        'status_uploading': 'Uploading...',
        'status_upload_complete': 'Upload complete!',
        'status_upload_failed': 'Upload failed',
        'status_url_copied': 'URL copied to clipboard!',
        'status_all_downloads_complete': 'All downloads complete! ({count} videos)',
        'status_completed_failed': 'Completed: {completed} | Failed: {failed}',
        'status_downloads_stopped': 'Downloads stopped by user',
        'status_all_uploads_complete': 'All uploads complete! ({count} files)',
        'status_preparing_download': 'Preparing download...',
        'status_extracting_audio': 'Extracting audio...',
        'status_merging': 'Merging video and audio...',
        'status_processing_ffmpeg': 'Processing with ffmpeg...',
        'status_post_processing': 'Post-processing...',
        'status_file_exists': 'File already exists, skipping...',
        'status_downloading_playlist': 'Downloading playlist... {progress}%',
        'status_processing_local': 'Processing local file...',
        'status_auto_downloading': 'Auto-downloading: {url}...',
        'status_auto_download_complete': 'Auto-download complete: {url}...',
        'status_auto_download_failed': 'Auto-download failed: {url}...',
        'status_uploading_file': 'Uploading {current}/{total}: {filename}...',

        # Error messages
        'error_title': 'Error',
        'error_enter_url': 'Please enter a YouTube URL or select a local file',
        'error_file_not_found': 'File not found:\n{path}',
        'error_invalid_url': 'Invalid URL',
        'error_not_youtube_url': 'Not a YouTube URL. Please enter a valid YouTube link.',
        'error_invalid_youtube_short': 'Invalid YouTube short URL',
        'error_valid_youtube_url': 'Valid YouTube URL',
        'error_valid_youtube_shorts': 'Valid YouTube Shorts URL',
        'error_valid_youtube_embed': 'Valid YouTube embed URL',
        'error_valid_youtube_playlist': 'Valid YouTube Playlist URL',
        'error_unrecognized_youtube': 'Unrecognized YouTube URL format',
        'error_missing_video_id': 'Missing video ID in URL',
        'error_invalid_url_format': 'Invalid URL format',
        'error_url_empty': 'URL is empty',
        'error_missing_dependencies': 'yt-dlp or ffmpeg is not installed.\n\nInstall with:\npip install yt-dlp\n\nand install ffmpeg from your package manager',
        'error_no_file_to_upload': 'No file available to upload. Please download/process a video first.',
        'error_file_too_large_title': 'File Too Large',
        'error_file_too_large': 'File size ({size} MB) exceeds Catbox.moe\'s 200MB limit.\nPlease trim the video or use a lower quality setting.',
        'error_request_timeout': 'Request timed out. Please check your internet connection.',
        'error_invalid_duration': 'Invalid duration format received: {error}',
        'error_fetch_duration_failed': 'Failed to fetch video duration:\n{error}',
        'error_read_video_failed': 'Failed to read video file:\n{error}',
        'error_invalid_video_format': 'Invalid video file format',
        'error_read_file_failed': 'Failed to read file:\n{error}',
        'error_path_not_exist': 'Path does not exist: {path}',
        'error_path_not_directory': 'Path is not a directory: {path}',
        'error_path_not_writable': 'Path is not writable:\n{path}\n\n{error}',
        'error_failed_open_folder': 'Failed to open folder:\n{error}',
        'error_select_quality': 'Please select a video quality',
        'error_fetch_duration_first': 'Please fetch video duration first',
        'error_invalid_time_range': 'Invalid time range',

        # Info messages
        'info_copied': 'Copied',
        'info_history_copied': 'History copied to clipboard!',
        'info_upload_complete_title': 'Upload Complete',
        'info_upload_complete': 'File uploaded successfully!\n\nURL: {url}\n\nThe URL has been copied to your clipboard.',
        'info_upload_failed_title': 'Upload Failed',
        'info_upload_failed': 'Failed to upload file:\n\n{error}',
        'info_skipped_file': 'Skipped: {filename}\nFile size ({size} MB) exceeds 200MB limit.',

        # Warning messages
        'warning_clear_history_title': 'Clear History',
        'warning_clear_history': 'Are you sure you want to clear all upload history?',
        'warning_cannot_clear_title': 'Cannot Clear',
        'warning_cannot_clear_downloading': 'Cannot clear URLs while downloads are in progress.',
        'warning_cannot_clear_uploading': 'Cannot clear queue while uploads are in progress.',
        'warning_no_urls_title': 'No URLs',
        'warning_no_urls': 'No pending URLs to download.',
        'warning_no_files_title': 'No Files',
        'warning_no_files': 'No files in queue. Please add files first.',
        'warning_playlist_detected': 'Playlist detected - Trimming and upload disabled for playlists',

        # History window
        'window_history_title': 'Upload Link History',
        'history_empty': 'No upload history yet.',
        'history_load_error': 'Error loading history: {error}',

        # File dialogs
        'dialog_select_video_files': 'Select Video Files',
        'dialog_video_files': 'Video files',
        'dialog_audio_files': 'Audio files',
        'dialog_all_files': 'All files',
        'dialog_select_video': 'Select a video file',

        # Download timeout messages
        'timeout_download_absolute': 'Download timeout (60 min limit exceeded)',
        'timeout_download_stalled': 'Download stalled (no progress for 10 minutes)',

        # Additional status messages
        'status_duration_timeout': 'Duration fetch timed out',
        'status_invalid_duration_format': 'Invalid duration format',
        'status_duration_fetch_failed': 'Failed to fetch duration',
        'status_processing_complete': 'Processing complete!',
        'status_processing_failed': 'Processing failed',
        'status_processing_local': 'Processing local file...',
        'status_preparing_download': 'Preparing download...',
        'status_extracting_audio': 'Extracting audio...',
        'status_merging': 'Merging video and audio...',
        'status_processing_ffmpeg': 'Processing with ffmpeg...',
        'status_post_processing': 'Post-processing...',
        'status_file_exists': 'File already exists, skipping...',
        'status_playlist_downloading': 'Downloading playlist...',
        'status_playlist_complete': 'Playlist download complete!',
        'status_playlist_failed': 'Playlist download failed',
        'error_ffmpeg_not_found': 'ffmpeg not found. Please ensure it is installed.',
        'error_ytdlp_not_found': 'yt-dlp not found. Please ensure it is installed.',
        'error_failed_clear_history': 'Failed to clear history: {error}',
        'status_auto_download_stopped': 'Auto-download stopped',

        # Additional UI labels
        'label_selected_duration_value': 'Selected Duration: {duration}',
        'label_video_title': 'Title: {title}',
        'label_file': 'File: {filename}',
        'label_estimated_size': 'Estimated size: {size} MB',
        'label_estimated_size_trimmed': 'Estimated size (trimmed): {size} MB',
        'label_estimated_size_unknown': 'Estimated size: Unknown',
        'label_calculating_size': 'Calculating size...',
        'label_file_size': '{filename} ({size} MB)',

        # Additional status messages
        'status_clipboard_downloading': 'Downloading: {url}...',
        'status_clipboard_completed_total': 'Completed: {completed}/{total} videos',
        'status_downloading_detailed': 'Downloading... {progress}%',
        'status_downloading_with_speed': 'Downloading... {progress}% at {speed}',
        'status_downloading_full': 'Downloading... {progress}% at {speed} | ETA: {eta}',

        # Additional error messages
        'error_url_empty': 'URL is empty',
        'error_permission_denied': 'Permission denied. Check write permissions for download folder.',
        'error_os_error': 'OS error: {error}',
        'error_generic': 'Error: {error}',
    },

    'de': {
        # Window & Language
        'window_title': 'YoutubeDownloader',
        'language': 'Sprache',
        'info_language_changed_title': 'Sprache geändert',
        'info_language_changed_msg': 'Die Sprache wurde geändert. Bitte starten Sie die Anwendung neu, damit die Änderungen wirksam werden.',

        # Tabs
        'tab_trimmer': 'Trimmer',
        'tab_clipboard': 'Zwischenablage-Modus',
        'tab_uploader': 'Uploader',

        # Common buttons
        'btn_download': 'Herunterladen',
        'btn_stop': 'Stopp',
        'btn_browse': 'Durchsuchen',
        'btn_change': 'Ändern',
        'btn_open_folder': 'Ordner öffnen',
        'btn_upload': 'Auf Catbox.moe hochladen',
        'btn_copy_url': 'URL kopieren',
        'btn_clear_all': 'Alles löschen',
        'btn_add_files': 'Dateien hinzufügen',
        'btn_close': 'Schließen',
        'btn_copy_all': 'Alles kopieren',

        # Trimmer tab
        'label_youtube_url': 'YouTube URL oder lokale Datei:',
        'btn_browse_local': 'Lokale Datei durchsuchen',
        'label_video_quality': 'Videoqualität:',
        'quality_audio_only': 'keine (Nur Audio)',
        'label_trim_video': 'Video zuschneiden:',
        'label_volume': 'Lautstärke:',
        'btn_reset_volume': 'Auf 100% zurücksetzen',
        'checkbox_enable_trimming': 'Videozuschnitt aktivieren',
        'btn_fetch_duration': 'Videodauer abrufen',
        'label_start_time': 'Startzeit:',
        'label_end_time': 'Endzeit:',
        'label_preview': 'Vorschau',
        'label_loading': 'Laden...',
        'label_error': 'Fehler',
        'label_selected_duration': 'Ausgewählte Dauer: 00:00:00',
        'label_save_to': 'Speichern unter:',
        'label_output_filename': 'Ausgabedateiname:',
        'hint_filename': '(Optional - leer lassen für automatisch generierten Namen)',
        'label_upload_section': 'Auf Streaming-Seite hochladen:',
        'btn_view_history': 'Upload-Verlauf anzeigen',
        'checkbox_auto_upload': 'Automatischer Upload nach Download/Zuschnitt',
        'label_upload_url': 'Upload URL:',
        'label_mode_local': 'Modus: Lokale Datei | {filename}',
        'label_mode_youtube': 'Modus: YouTube Download',

        # Clipboard Mode tab
        'header_clipboard_mode': 'Zwischenablage-Modus',
        'desc_clipboard_mode': 'YouTube URLs kopieren (Strg+C), um sie automatisch zu erkennen und herunterzuladen.',
        'label_download_mode': 'Download-Modus:',
        'checkbox_auto_download': 'Automatischer Download (startet sofort)',
        'header_settings': 'Einstellungen',
        'label_quality': 'Qualität:',
        'label_detected_urls': 'Erkannte URLs',
        'label_url_count': '({count} URL{s})',
        'btn_download_all': 'Alle herunterladen',
        'label_current_download': 'Aktueller Download:',
        'label_completed_total': 'Abgeschlossen: {done}/{total} Videos',

        # Uploader tab
        'header_upload_file': 'Lokale Datei hochladen',
        'desc_upload_file': 'Lokale Videodateien auf Catbox.moe-Streaming-Dienst hochladen.',
        'label_file_queue': 'Dateiwarteschlange:',
        'label_file_count': '({count} Datei{s})',

        # Status messages
        'status_ready': 'Bereit',
        'status_fetching_duration': 'Videodauer wird abgerufen...',
        'status_duration_fetched': 'Dauer erfolgreich abgerufen',
        'status_starting_download': 'Download wird gestartet...',
        'status_downloading': 'Herunterladen... {progress}%',
        'status_download_complete': 'Download abgeschlossen!',
        'status_download_stopped': 'Download gestoppt',
        'status_download_failed': 'Download fehlgeschlagen',
        'status_processing': 'Verarbeitung... {progress}%',
        'status_uploading': 'Hochladen...',
        'status_upload_complete': 'Upload abgeschlossen!',
        'status_upload_failed': 'Upload fehlgeschlagen',
        'status_url_copied': 'URL in Zwischenablage kopiert!',
        'status_all_downloads_complete': 'Alle Downloads abgeschlossen! ({count} Videos)',
        'status_completed_failed': 'Abgeschlossen: {completed} | Fehlgeschlagen: {failed}',
        'status_downloads_stopped': 'Downloads vom Benutzer gestoppt',
        'status_all_uploads_complete': 'Alle Uploads abgeschlossen! ({count} Dateien)',
        'status_preparing_download': 'Download wird vorbereitet...',
        'status_extracting_audio': 'Audio wird extrahiert...',
        'status_merging': 'Video und Audio werden zusammengeführt...',
        'status_processing_ffmpeg': 'Verarbeitung mit ffmpeg...',
        'status_post_processing': 'Nachbearbeitung...',
        'status_file_exists': 'Datei existiert bereits, überspringe...',
        'status_downloading_playlist': 'Playlist wird heruntergeladen... {progress}%',
        'status_processing_local': 'Lokale Datei wird verarbeitet...',
        'status_auto_downloading': 'Automatischer Download: {url}...',
        'status_auto_download_complete': 'Automatischer Download abgeschlossen: {url}...',
        'status_auto_download_failed': 'Automatischer Download fehlgeschlagen: {url}...',
        'status_uploading_file': 'Hochladen {current}/{total}: {filename}...',

        # Error messages
        'error_title': 'Fehler',
        'error_enter_url': 'Bitte geben Sie eine YouTube URL ein oder wählen Sie eine lokale Datei',
        'error_file_not_found': 'Datei nicht gefunden:\n{path}',
        'error_invalid_url': 'Ungültige URL',
        'error_not_youtube_url': 'Keine YouTube URL. Bitte geben Sie einen gültigen YouTube-Link ein.',
        'error_invalid_youtube_short': 'Ungültige YouTube Kurz-URL',
        'error_valid_youtube_url': 'Gültige YouTube URL',
        'error_valid_youtube_shorts': 'Gültige YouTube Shorts URL',
        'error_valid_youtube_embed': 'Gültige YouTube Einbettungs-URL',
        'error_valid_youtube_playlist': 'Gültige YouTube Playlist URL',
        'error_unrecognized_youtube': 'Nicht erkanntes YouTube URL-Format',
        'error_missing_video_id': 'Fehlende Video-ID in URL',
        'error_invalid_url_format': 'Ungültiges URL-Format',
        'error_url_empty': 'URL ist leer',
        'error_missing_dependencies': 'yt-dlp oder ffmpeg ist nicht installiert.\n\nInstallieren mit:\npip install yt-dlp\n\nund ffmpeg über Ihren Paketmanager installieren',
        'error_no_file_to_upload': 'Keine Datei zum Hochladen verfügbar. Bitte zuerst ein Video herunterladen/verarbeiten.',
        'error_file_too_large_title': 'Datei zu groß',
        'error_file_too_large': 'Dateigröße ({size} MB) überschreitet Catbox.moe\'s 200MB-Limit.\nBitte schneiden Sie das Video zu oder verwenden Sie eine niedrigere Qualitätseinstellung.',
        'error_request_timeout': 'Zeitüberschreitung der Anfrage. Bitte überprüfen Sie Ihre Internetverbindung.',
        'error_invalid_duration': 'Ungültiges Dauerformat erhalten: {error}',
        'error_fetch_duration_failed': 'Fehler beim Abrufen der Videodauer:\n{error}',
        'error_read_video_failed': 'Fehler beim Lesen der Videodatei:\n{error}',
        'error_invalid_video_format': 'Ungültiges Videodateiformat',
        'error_read_file_failed': 'Fehler beim Lesen der Datei:\n{error}',
        'error_path_not_exist': 'Pfad existiert nicht: {path}',
        'error_path_not_directory': 'Pfad ist kein Verzeichnis: {path}',
        'error_path_not_writable': 'Pfad ist nicht beschreibbar:\n{path}\n\n{error}',
        'error_failed_open_folder': 'Ordner konnte nicht geöffnet werden:\n{error}',
        'error_select_quality': 'Bitte wählen Sie eine Videoqualität',
        'error_fetch_duration_first': 'Bitte rufen Sie zuerst die Videodauer ab',
        'error_invalid_time_range': 'Ungültiger Zeitbereich',

        # Info messages
        'info_copied': 'Kopiert',
        'info_history_copied': 'Verlauf in Zwischenablage kopiert!',
        'info_upload_complete_title': 'Upload abgeschlossen',
        'info_upload_complete': 'Datei erfolgreich hochgeladen!\n\nURL: {url}\n\nDie URL wurde in Ihre Zwischenablage kopiert.',
        'info_upload_failed_title': 'Upload fehlgeschlagen',
        'info_upload_failed': 'Fehler beim Hochladen der Datei:\n\n{error}',
        'info_skipped_file': 'Übersprungen: {filename}\nDateigröße ({size} MB) überschreitet 200MB-Limit.',

        # Warning messages
        'warning_clear_history_title': 'Verlauf löschen',
        'warning_clear_history': 'Möchten Sie wirklich den gesamten Upload-Verlauf löschen?',
        'warning_cannot_clear_title': 'Kann nicht löschen',
        'warning_cannot_clear_downloading': 'URLs können während laufender Downloads nicht gelöscht werden.',
        'warning_cannot_clear_uploading': 'Warteschlange kann während laufender Uploads nicht gelöscht werden.',
        'warning_no_urls_title': 'Keine URLs',
        'warning_no_urls': 'Keine ausstehenden URLs zum Herunterladen.',
        'warning_no_files_title': 'Keine Dateien',
        'warning_no_files': 'Keine Dateien in der Warteschlange. Bitte fügen Sie zuerst Dateien hinzu.',
        'warning_playlist_detected': 'Playlist erkannt - Zuschneiden und Upload für Playlists deaktiviert',

        # History window
        'window_history_title': 'Upload-Link-Verlauf',
        'history_empty': 'Noch kein Upload-Verlauf vorhanden.',
        'history_load_error': 'Fehler beim Laden des Verlaufs: {error}',

        # File dialogs
        'dialog_select_video_files': 'Videodateien auswählen',
        'dialog_video_files': 'Videodateien',
        'dialog_audio_files': 'Audiodateien',
        'dialog_all_files': 'Alle Dateien',
        'dialog_select_video': 'Wählen Sie eine Videodatei',

        # Download timeout messages
        'timeout_download_absolute': 'Download-Zeitüberschreitung (60 Min. Limit überschritten)',
        'timeout_download_stalled': 'Download ins Stocken geraten (10 Minuten kein Fortschritt)',

        # Additional status messages
        'status_duration_timeout': 'Zeitüberschreitung beim Abrufen der Dauer',
        'status_invalid_duration_format': 'Ungültiges Dauerformat',
        'status_duration_fetch_failed': 'Dauer konnte nicht abgerufen werden',
        'status_processing_complete': 'Verarbeitung abgeschlossen!',
        'status_processing_failed': 'Verarbeitung fehlgeschlagen',
        'status_processing_local': 'Lokale Datei wird verarbeitet...',
        'status_preparing_download': 'Download wird vorbereitet...',
        'status_extracting_audio': 'Audio wird extrahiert...',
        'status_merging': 'Video und Audio werden zusammengeführt...',
        'status_processing_ffmpeg': 'Verarbeitung mit ffmpeg...',
        'status_post_processing': 'Nachbearbeitung...',
        'status_file_exists': 'Datei existiert bereits, überspringe...',
        'status_playlist_downloading': 'Playlist wird heruntergeladen...',
        'status_playlist_complete': 'Playlist-Download abgeschlossen!',
        'status_playlist_failed': 'Playlist-Download fehlgeschlagen',
        'error_ffmpeg_not_found': 'ffmpeg nicht gefunden. Bitte stellen Sie sicher, dass es installiert ist.',
        'error_ytdlp_not_found': 'yt-dlp nicht gefunden. Bitte stellen Sie sicher, dass es installiert ist.',
        'error_failed_clear_history': 'Verlauf konnte nicht gelöscht werden: {error}',
        'status_auto_download_stopped': 'Automatischer Download gestoppt',

        # Additional UI labels
        'label_selected_duration_value': 'Ausgewählte Dauer: {duration}',
        'label_video_title': 'Titel: {title}',
        'label_file': 'Datei: {filename}',
        'label_estimated_size': 'Geschätzte Größe: {size} MB',
        'label_estimated_size_trimmed': 'Geschätzte Größe (zugeschnitten): {size} MB',
        'label_estimated_size_unknown': 'Geschätzte Größe: Unbekannt',
        'label_calculating_size': 'Größe wird berechnet...',
        'label_file_size': '{filename} ({size} MB)',

        # Additional status messages
        'status_clipboard_downloading': 'Herunterladen: {url}...',
        'status_clipboard_completed_total': 'Abgeschlossen: {completed}/{total} Videos',
        'status_downloading_detailed': 'Herunterladen... {progress}%',
        'status_downloading_with_speed': 'Herunterladen... {progress}% bei {speed}',
        'status_downloading_full': 'Herunterladen... {progress}% bei {speed} | ETA: {eta}',

        # Additional error messages
        'error_url_empty': 'URL ist leer',
        'error_permission_denied': 'Zugriff verweigert. Überprüfen Sie die Schreibrechte für den Download-Ordner.',
        'error_os_error': 'OS-Fehler: {error}',
        'error_generic': 'Fehler: {error}',
    },

    'pl': {
        # Window & Language
        'window_title': 'YoutubeDownloader',
        'language': 'Język',
        'info_language_changed_title': 'Język zmieniony',
        'info_language_changed_msg': 'Język został zmieniony. Uruchom ponownie aplikację, aby zmiany zaczęły obowiązywać.',

        # Tabs
        'tab_trimmer': 'Przycinanie',
        'tab_clipboard': 'Tryb schowka',
        'tab_uploader': 'Przesyłanie',

        # Common buttons
        'btn_download': 'Pobierz',
        'btn_stop': 'Zatrzymaj',
        'btn_browse': 'Przeglądaj',
        'btn_change': 'Zmień',
        'btn_open_folder': 'Otwórz folder',
        'btn_upload': 'Prześlij do Catbox.moe',
        'btn_copy_url': 'Kopiuj URL',
        'btn_clear_all': 'Wyczyść wszystko',
        'btn_add_files': 'Dodaj pliki',
        'btn_close': 'Zamknij',
        'btn_copy_all': 'Kopiuj wszystko',

        # Trimmer tab
        'label_youtube_url': 'URL YouTube lub plik lokalny:',
        'btn_browse_local': 'Przeglądaj plik lokalny',
        'label_video_quality': 'Jakość wideo:',
        'quality_audio_only': 'brak (Tylko audio)',
        'label_trim_video': 'Przytnij wideo:',
        'label_volume': 'Głośność:',
        'btn_reset_volume': 'Resetuj do 100%',
        'checkbox_enable_trimming': 'Włącz przycinanie wideo',
        'btn_fetch_duration': 'Pobierz czas trwania wideo',
        'label_start_time': 'Czas rozpoczęcia:',
        'label_end_time': 'Czas zakończenia:',
        'label_preview': 'Podgląd',
        'label_loading': 'Ładowanie...',
        'label_error': 'Błąd',
        'label_selected_duration': 'Wybrany czas trwania: 00:00:00',
        'label_save_to': 'Zapisz do:',
        'label_output_filename': 'Nazwa pliku wyjściowego:',
        'hint_filename': '(Opcjonalne - pozostaw puste dla automatycznej nazwy)',
        'label_upload_section': 'Prześlij na stronę streamingową:',
        'btn_view_history': 'Zobacz historię przesyłania',
        'checkbox_auto_upload': 'Automatyczne przesyłanie po pobraniu/przycięciu',
        'label_upload_url': 'URL przesyłania:',
        'label_mode_local': 'Tryb: Plik lokalny | {filename}',
        'label_mode_youtube': 'Tryb: Pobieranie YouTube',

        # Clipboard Mode tab
        'header_clipboard_mode': 'Tryb schowka',
        'desc_clipboard_mode': 'Kopiuj URL YouTube (Ctrl+C), aby automatycznie wykrywać i pobierać je.',
        'label_download_mode': 'Tryb pobierania:',
        'checkbox_auto_download': 'Automatyczne pobieranie (rozpoczyna natychmiast)',
        'header_settings': 'Ustawienia',
        'label_quality': 'Jakość:',
        'label_detected_urls': 'Wykryte URL',
        'label_url_count': '({count} URL{s})',
        'btn_download_all': 'Pobierz wszystkie',
        'label_current_download': 'Bieżące pobieranie:',
        'label_completed_total': 'Ukończono: {done}/{total} filmów',

        # Uploader tab
        'header_upload_file': 'Prześlij plik lokalny',
        'desc_upload_file': 'Przesyłaj lokalne pliki wideo do usługi streamingowej Catbox.moe.',
        'label_file_queue': 'Kolejka plików:',
        'label_file_count': '({count} plik{s})',

        # Status messages
        'status_ready': 'Gotowy',
        'status_fetching_duration': 'Pobieranie czasu trwania wideo...',
        'status_duration_fetched': 'Czas trwania pobrany pomyślnie',
        'status_starting_download': 'Rozpoczynanie pobierania...',
        'status_downloading': 'Pobieranie... {progress}%',
        'status_download_complete': 'Pobieranie zakończone!',
        'status_download_stopped': 'Pobieranie zatrzymane',
        'status_download_failed': 'Pobieranie nie powiodło się',
        'status_processing': 'Przetwarzanie... {progress}%',
        'status_uploading': 'Przesyłanie...',
        'status_upload_complete': 'Przesyłanie zakończone!',
        'status_upload_failed': 'Przesyłanie nie powiodło się',
        'status_url_copied': 'URL skopiowany do schowka!',
        'status_all_downloads_complete': 'Wszystkie pobierania zakończone! ({count} filmów)',
        'status_completed_failed': 'Ukończono: {completed} | Niepowodzenie: {failed}',
        'status_downloads_stopped': 'Pobierania zatrzymane przez użytkownika',
        'status_all_uploads_complete': 'Wszystkie przesyłania zakończone! ({count} plików)',
        'status_preparing_download': 'Przygotowywanie pobierania...',
        'status_extracting_audio': 'Wyodrębnianie audio...',
        'status_merging': 'Łączenie wideo i audio...',
        'status_processing_ffmpeg': 'Przetwarzanie za pomocą ffmpeg...',
        'status_post_processing': 'Przetwarzanie końcowe...',
        'status_file_exists': 'Plik już istnieje, pomijanie...',
        'status_downloading_playlist': 'Pobieranie playlisty... {progress}%',
        'status_processing_local': 'Przetwarzanie pliku lokalnego...',
        'status_auto_downloading': 'Automatyczne pobieranie: {url}...',
        'status_auto_download_complete': 'Automatyczne pobieranie zakończone: {url}...',
        'status_auto_download_failed': 'Automatyczne pobieranie nie powiodło się: {url}...',
        'status_uploading_file': 'Przesyłanie {current}/{total}: {filename}...',

        # Error messages
        'error_title': 'Błąd',
        'error_enter_url': 'Wprowadź URL YouTube lub wybierz plik lokalny',
        'error_file_not_found': 'Nie znaleziono pliku:\n{path}',
        'error_invalid_url': 'Nieprawidłowy URL',
        'error_not_youtube_url': 'To nie jest URL YouTube. Wprowadź prawidłowy link YouTube.',
        'error_invalid_youtube_short': 'Nieprawidłowy krótki URL YouTube',
        'error_valid_youtube_url': 'Prawidłowy URL YouTube',
        'error_valid_youtube_shorts': 'Prawidłowy URL YouTube Shorts',
        'error_valid_youtube_embed': 'Prawidłowy URL osadzony YouTube',
        'error_valid_youtube_playlist': 'Prawidłowy URL playlisty YouTube',
        'error_unrecognized_youtube': 'Nierozpoznany format URL YouTube',
        'error_missing_video_id': 'Brak ID wideo w URL',
        'error_invalid_url_format': 'Nieprawidłowy format URL',
        'error_url_empty': 'URL jest pusty',
        'error_missing_dependencies': 'yt-dlp lub ffmpeg nie jest zainstalowane.\n\nZainstaluj za pomocą:\npip install yt-dlp\n\ni zainstaluj ffmpeg z menedżera pakietów',
        'error_no_file_to_upload': 'Brak pliku do przesłania. Najpierw pobierz/przetwórz wideo.',
        'error_file_too_large_title': 'Plik za duży',
        'error_file_too_large': 'Rozmiar pliku ({size} MB) przekracza limit 200MB Catbox.moe.\nPrzytnij wideo lub użyj niższej jakości.',
        'error_request_timeout': 'Przekroczono limit czasu żądania. Sprawdź połączenie internetowe.',
        'error_invalid_duration': 'Otrzymano nieprawidłowy format czasu trwania: {error}',
        'error_fetch_duration_failed': 'Nie udało się pobrać czasu trwania wideo:\n{error}',
        'error_read_video_failed': 'Nie udało się odczytać pliku wideo:\n{error}',
        'error_invalid_video_format': 'Nieprawidłowy format pliku wideo',
        'error_read_file_failed': 'Nie udało się odczytać pliku:\n{error}',
        'error_path_not_exist': 'Ścieżka nie istnieje: {path}',
        'error_path_not_directory': 'Ścieżka nie jest katalogiem: {path}',
        'error_path_not_writable': 'Ścieżka nie jest zapisywalna:\n{path}\n\n{error}',
        'error_failed_open_folder': 'Nie udało się otworzyć folderu:\n{error}',
        'error_select_quality': 'Wybierz jakość wideo',
        'error_fetch_duration_first': 'Najpierw pobierz czas trwania wideo',
        'error_invalid_time_range': 'Nieprawidłowy zakres czasu',

        # Info messages
        'info_copied': 'Skopiowano',
        'info_history_copied': 'Historia skopiowana do schowka!',
        'info_upload_complete_title': 'Przesyłanie zakończone',
        'info_upload_complete': 'Plik przesłany pomyślnie!\n\nURL: {url}\n\nURL został skopiowany do schowka.',
        'info_upload_failed_title': 'Przesyłanie nie powiodło się',
        'info_upload_failed': 'Nie udało się przesłać pliku:\n\n{error}',
        'info_skipped_file': 'Pominięto: {filename}\nRozmiar pliku ({size} MB) przekracza limit 200MB.',

        # Warning messages
        'warning_clear_history_title': 'Wyczyść historię',
        'warning_clear_history': 'Czy na pewno chcesz wyczyścić całą historię przesyłania?',
        'warning_cannot_clear_title': 'Nie można wyczyścić',
        'warning_cannot_clear_downloading': 'Nie można wyczyścić URL podczas trwających pobierań.',
        'warning_cannot_clear_uploading': 'Nie można wyczyścić kolejki podczas trwających przesyłań.',
        'warning_no_urls_title': 'Brak URL',
        'warning_no_urls': 'Brak oczekujących URL do pobrania.',
        'warning_no_files_title': 'Brak plików',
        'warning_no_files': 'Brak plików w kolejce. Najpierw dodaj pliki.',
        'warning_playlist_detected': 'Wykryto playlistę - Przycinanie i przesyłanie wyłączone dla playlist',

        # History window
        'window_history_title': 'Historia linków przesyłania',
        'history_empty': 'Brak historii przesyłania.',
        'history_load_error': 'Błąd ładowania historii: {error}',

        # File dialogs
        'dialog_select_video_files': 'Wybierz pliki wideo',
        'dialog_video_files': 'Pliki wideo',
        'dialog_audio_files': 'Pliki audio',
        'dialog_all_files': 'Wszystkie pliki',
        'dialog_select_video': 'Wybierz plik wideo',

        # Download timeout messages
        'timeout_download_absolute': 'Limit czasu pobierania (przekroczono limit 60 min)',
        'timeout_download_stalled': 'Pobieranie wstrzymane (brak postępu przez 10 minut)',

        # Additional status messages
        'status_duration_timeout': 'Limit czasu pobierania czasu trwania',
        'status_invalid_duration_format': 'Nieprawidłowy format czasu trwania',
        'status_duration_fetch_failed': 'Nie udało się pobrać czasu trwania',
        'status_processing_complete': 'Przetwarzanie zakończone!',
        'status_processing_failed': 'Przetwarzanie nie powiodło się',
        'status_processing_local': 'Przetwarzanie pliku lokalnego...',
        'status_preparing_download': 'Przygotowywanie pobierania...',
        'status_extracting_audio': 'Wyodrębnianie audio...',
        'status_merging': 'Łączenie wideo i audio...',
        'status_processing_ffmpeg': 'Przetwarzanie za pomocą ffmpeg...',
        'status_post_processing': 'Przetwarzanie końcowe...',
        'status_file_exists': 'Plik już istnieje, pomijanie...',
        'status_playlist_downloading': 'Pobieranie playlisty...',
        'status_playlist_complete': 'Pobieranie playlisty zakończone!',
        'status_playlist_failed': 'Pobieranie playlisty nie powiodło się',
        'error_ffmpeg_not_found': 'ffmpeg nie został znaleziony. Upewnij się, że jest zainstalowany.',
        'error_ytdlp_not_found': 'yt-dlp nie został znaleziony. Upewnij się, że jest zainstalowany.',
        'error_failed_clear_history': 'Nie udało się wyczyścić historii: {error}',
        'status_auto_download_stopped': 'Automatyczne pobieranie zatrzymane',

        # Additional UI labels
        'label_selected_duration_value': 'Wybrany czas trwania: {duration}',
        'label_video_title': 'Tytuł: {title}',
        'label_file': 'Plik: {filename}',
        'label_estimated_size': 'Szacowany rozmiar: {size} MB',
        'label_estimated_size_trimmed': 'Szacowany rozmiar (przycięty): {size} MB',
        'label_estimated_size_unknown': 'Szacowany rozmiar: Nieznany',
        'label_calculating_size': 'Obliczanie rozmiaru...',
        'label_file_size': '{filename} ({size} MB)',

        # Additional status messages
        'status_clipboard_downloading': 'Pobieranie: {url}...',
        'status_clipboard_completed_total': 'Ukończono: {completed}/{total} filmów',
        'status_downloading_detailed': 'Pobieranie... {progress}%',
        'status_downloading_with_speed': 'Pobieranie... {progress}% przy {speed}',
        'status_downloading_full': 'Pobieranie... {progress}% przy {speed} | ETA: {eta}',

        # Additional error messages
        'error_url_empty': 'URL jest pusty',
        'error_permission_denied': 'Dostęp zabroniony. Sprawdź uprawnienia zapisu dla folderu pobierania.',
        'error_os_error': 'Błąd systemu: {error}',
        'error_generic': 'Błąd: {error}',
    }
}

def tr(key, **kwargs):
    """Get translated string for current language with optional formatting.

    Args:
        key: Translation key (e.g., 'btn_download')
        **kwargs: Optional format arguments (e.g., progress=50)

    Returns:
        Translated and formatted string
    """
    text = TRANSLATIONS.get(CURRENT_LANGUAGE, {}).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text

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
        self.root.title(tr('window_title'))
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
        self.download_lock = threading.Lock()  # Protect download state
        self.upload_lock = threading.Lock()  # Protect upload state
        self.uploader_lock = threading.Lock()  # Protect uploader queue state
        self.fetch_lock = threading.Lock()  # Protect duration fetch state

        # Clipboard Mode variables
        self.clipboard_monitoring = False
        self.clipboard_monitor_thread = None
        self.clipboard_last_content = ""
        self.clipboard_url_list = []  # List of dict: {'url': str, 'status': str, 'widget': Frame}
        self.clipboard_download_path = str(Path.home() / "Downloads")
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

        # Load language preference before UI setup
        self._load_language_preference()

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

                    # Validate JSON structure
                    if not isinstance(data, dict):
                        raise ValueError("Invalid clipboard URLs file format: expected dict")
                    if 'urls' not in data:
                        raise ValueError("Invalid clipboard URLs file format: missing 'urls' key")
                    if not isinstance(data['urls'], list):
                        raise ValueError("Invalid clipboard URLs file format: 'urls' must be a list")

                    # Store URLs, will be restored to UI after setup_ui() completes
                    self.persisted_clipboard_urls = data['urls']
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
            with self.clipboard_lock:
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
                with self.clipboard_lock:
                    url_exists = url and url not in [item['url'] for item in self.clipboard_url_list]
                if url_exists:
                    self._add_url_to_clipboard_list(url)
                    if status == 'failed':
                        self._update_url_status(url, 'failed')
            logger.info(f"Restored {len(self.persisted_clipboard_urls)} URLs to clipboard list")

    def _load_language_preference(self):
        """Load saved language preference"""
        global CURRENT_LANGUAGE
        try:
            if CONFIG_FILE.exists():
                import json
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    lang_code = config.get('language', 'en')
                    CURRENT_LANGUAGE = lang_code
                    logger.info(f"Loaded language preference: {lang_code}")
        except Exception as e:
            logger.error(f"Error loading language preference: {e}")
            CURRENT_LANGUAGE = 'en'

    def _save_language_preference(self):
        """Save language preference to config file"""
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            import json

            # Load existing config if any
            config = {}
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)

            # Update language
            config['language'] = CURRENT_LANGUAGE

            # Save config
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)

            logger.info(f"Saved language preference: {CURRENT_LANGUAGE}")
        except Exception as e:
            logger.error(f"Error saving language preference: {e}")

    def on_language_change(self, event=None):
        """Handle language selection change"""
        global CURRENT_LANGUAGE

        selected = self.language_var.get()
        lang_map = {
            "🇬🇧 English": 'en',
            "🇩🇪 Deutsch": 'de',
            "🇵🇱 Polski": 'pl'
        }

        new_lang = lang_map.get(selected, 'en')

        if new_lang != CURRENT_LANGUAGE:
            CURRENT_LANGUAGE = new_lang
            self._save_language_preference()

            # Show restart message
            messagebox.showinfo(
                tr('info_language_changed_title'),
                tr('info_language_changed_msg')
            )

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
        history_window.title(tr('window_history_title'))
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
                        text_widget.insert('1.0', tr('history_empty'))
            else:
                text_widget.insert('1.0', tr('history_empty'))
        except Exception as e:
            text_widget.insert('1.0', tr('history_load_error', error=str(e)))

        text_widget.config(state='disabled')  # Make read-only

        # Add copy and clear buttons
        button_frame = ttk.Frame(history_window, padding="10")
        button_frame.pack(fill=tk.X)

        def copy_all():
            self.root.clipboard_clear()
            self.root.clipboard_append(text_widget.get('1.0', tk.END))
            messagebox.showinfo(tr('info_copied'), tr('info_history_copied'))

        def clear_history():
            if messagebox.askyesno(tr('warning_clear_history_title'), tr('warning_clear_history')):
                try:
                    if UPLOAD_HISTORY_FILE.exists():
                        UPLOAD_HISTORY_FILE.unlink()
                    text_widget.config(state='normal')
                    text_widget.delete('1.0', tk.END)
                    text_widget.insert('1.0', tr('history_empty'))
                    text_widget.config(state='disabled')
                except Exception as e:
                    messagebox.showerror(tr('error_title'), tr('error_failed_clear_history', error=str(e)))

        ttk.Button(button_frame, text=tr('btn_copy_all'), command=copy_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text=tr('warning_clear_history_title'), command=clear_history).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text=tr('btn_close'), command=history_window.destroy).pack(side=tk.RIGHT, padx=5)

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
        - Path separators (/, \\\\)
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
            return False, tr('error_url_empty')

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
        """Setup the complete user interface with all tabs and widgets.

        Creates a tabbed interface with three main tabs:
        - Trimmer: Video download, trimming, and preview
        - Clipboard Mode: Automatic URL detection and batch downloading
        - Uploader: File upload to Catbox.moe

        Features:
        - Language selector dropdown at the top
        - Scrollable canvas for all content
        - Mouse wheel scrolling support
        - Responsive layout with proper grid configuration
        """
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
        self.root.after(UI_INITIAL_DELAY_MS, lambda: bind_to_mousewheel(scrollable_frame))

        # Store canvas reference for cleanup
        self.canvas = canvas

        # Language selector at top
        language_frame = ttk.Frame(scrollable_frame)
        language_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=(5, 0))

        ttk.Label(language_frame, text=tr('language') + ":", font=('Arial', 9)).pack(side=tk.LEFT, padx=(0, 5))

        # Language options with flag emojis
        language_options = [
            "🇬🇧 English",
            "🇩🇪 Deutsch",
            "🇵🇱 Polski"
        ]

        # Set initial language based on loaded preference
        lang_map_reverse = {'en': 0, 'de': 1, 'pl': 2}
        initial_index = lang_map_reverse.get(CURRENT_LANGUAGE, 0)

        self.language_var = tk.StringVar(value=language_options[initial_index])
        self.language_combo = ttk.Combobox(language_frame, textvariable=self.language_var,
            values=language_options, state='readonly', width=15)
        self.language_combo.pack(side=tk.LEFT)
        self.language_combo.bind('<<ComboboxSelected>>', self.on_language_change)

        # Create notebook for tabs
        self.notebook = ttk.Notebook(scrollable_frame)
        self.notebook.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        # Clipboard Mode tab (first tab)
        clipboard_tab_frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(clipboard_tab_frame, text=tr('tab_clipboard'))
        # Setup will be called after Trimmer tab is created

        # Trimmer tab (second tab)
        main_tab_frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(main_tab_frame, text=tr('tab_trimmer'))

        # Uploader tab (third tab)
        uploader_tab_frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(uploader_tab_frame, text=tr('tab_uploader'))

        ttk.Label(main_tab_frame, text=tr('label_youtube_url'), font=('Arial', 12)).grid(row=0, column=0, sticky=tk.W, pady=(0, 10))

        # URL/File input frame
        url_input_frame = ttk.Frame(main_tab_frame)
        url_input_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        self.url_entry = ttk.Entry(url_input_frame, width=50)
        self.url_entry.pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True)
        self.url_entry.bind('<KeyRelease>', self.on_url_change)

        ttk.Button(url_input_frame, text=tr('btn_browse_local'), command=self.browse_local_file).pack(side=tk.LEFT)

        # Mode indicator label
        self.mode_label = ttk.Label(main_tab_frame, text="", foreground="blue", font=('Arial', 9))
        self.mode_label.grid(row=2, column=0, sticky=tk.W, pady=(0, 10))

        # Video Quality section - dropdown
        quality_frame = ttk.Frame(main_tab_frame)
        quality_frame.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(10, 5))

        ttk.Label(quality_frame, text=tr('label_video_quality'), font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=(0, 10))

        self.quality_var = tk.StringVar(value="480")
        self.quality_var.trace_add('write', self.on_quality_change)

        quality_options = ["1440", "1080", "720", "480", "360", "240", tr('quality_audio_only')]
        self.quality_combo = ttk.Combobox(quality_frame, textvariable=self.quality_var,
            values=quality_options, state='readonly', width=20)
        self.quality_combo.pack(side=tk.LEFT)

        ttk.Separator(main_tab_frame, orient='horizontal').grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)

        # Trimming section with Volume Control on the right
        trim_and_volume_row = ttk.Frame(main_tab_frame)
        trim_and_volume_row.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 3))

        # Left side: Trim Video
        ttk.Label(trim_and_volume_row, text=tr('label_trim_video'), font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=(0, 30))

        # Right side: Volume Adjustment
        ttk.Label(trim_and_volume_row, text=tr('label_volume'), font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=(20, 5))

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
        ttk.Button(trim_and_volume_row, text=tr('btn_reset_volume'), command=self.reset_volume, width=12).pack(side=tk.LEFT)

        # Trim checkbox row with fetch button
        trim_checkbox_frame = ttk.Frame(main_tab_frame)
        trim_checkbox_frame.grid(row=6, column=0, sticky=tk.W, padx=(20, 0), pady=(3, 5))

        self.trim_enabled_var = tk.BooleanVar()
        ttk.Checkbutton(trim_checkbox_frame, text=tr('checkbox_enable_trimming'), variable=self.trim_enabled_var,
                       command=self.toggle_trim).pack(side=tk.LEFT)

        self.fetch_duration_btn = ttk.Button(trim_checkbox_frame, text=tr('btn_fetch_duration'), command=self.fetch_duration_clicked, state='disabled')
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

        ttk.Label(start_preview_frame, text=tr('label_start_time'), font=('Arial', 9)).pack()
        self.start_preview_label = tk.Label(start_preview_frame, bg='gray20', fg='white', relief='sunken')
        self.start_preview_label.pack(pady=(5, 0))

        # Create placeholder images
        self.placeholder_image = self.create_placeholder_image(PREVIEW_WIDTH, PREVIEW_HEIGHT, tr('label_preview'))
        self.loading_image = self.create_placeholder_image(PREVIEW_WIDTH, PREVIEW_HEIGHT, tr('label_loading'))
        self.start_preview_label.config(image=self.placeholder_image)

        # End time preview
        end_preview_frame = ttk.Frame(preview_container)
        end_preview_frame.grid(row=0, column=1)

        ttk.Label(end_preview_frame, text=tr('label_end_time'), font=('Arial', 9)).pack()
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

        ttk.Label(start_control_frame, text=tr('label_start_time') + ":", font=('Arial', 9)).pack(side=tk.LEFT, padx=(0, 5))
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

        ttk.Label(end_control_frame, text=tr('label_end_time') + ":", font=('Arial', 9)).pack(side=tk.LEFT, padx=(0, 5))
        self.end_time_entry = ttk.Entry(end_control_frame, width=10, state='disabled')
        self.end_time_entry.pack(side=tk.LEFT)
        self.end_time_entry.insert(0, "00:00:00")
        self.end_time_entry.bind('<Return>', self.on_end_entry_change)
        self.end_time_entry.bind('<FocusOut>', self.on_end_entry_change)

        # Trim duration display
        self.trim_duration_label = ttk.Label(main_tab_frame, text=tr('label_selected_duration'), foreground="green", font=('Arial', 9, 'bold'))
        self.trim_duration_label.grid(row=12, column=0, sticky=tk.W, padx=(40, 0), pady=(3, 0))

        ttk.Separator(main_tab_frame, orient='horizontal').grid(row=13, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)

        path_frame = ttk.Frame(main_tab_frame)
        path_frame.grid(row=14, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(path_frame, text=tr('label_save_to')).pack(side=tk.LEFT)
        self.path_label = ttk.Label(path_frame, text=self.download_path, foreground="blue")
        self.path_label.pack(side=tk.LEFT, padx=(10, 10))
        ttk.Button(path_frame, text=tr('btn_change'), command=self.change_path).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(path_frame, text=tr('btn_open_folder'), command=self.open_download_folder).pack(side=tk.LEFT)

        # Filename customization
        filename_frame = ttk.Frame(main_tab_frame)
        filename_frame.grid(row=15, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(filename_frame, text=tr('label_output_filename'), font=('Arial', 9)).pack(side=tk.LEFT, padx=(0, 5))
        self.filename_entry = ttk.Entry(filename_frame, width=40)
        self.filename_entry.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(filename_frame, text=tr('hint_filename'), foreground="gray", font=('Arial', 8)).pack(side=tk.LEFT)

        button_frame = ttk.Frame(main_tab_frame)
        button_frame.grid(row=16, column=0, columnspan=2, pady=(0, 10))

        self.download_btn = ttk.Button(button_frame, text=tr('btn_download'), command=self.start_download)
        self.download_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_btn = ttk.Button(button_frame, text=tr('btn_stop'), command=self.stop_download, state='disabled')
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

        self.status_label = ttk.Label(main_tab_frame, text=tr('status_ready'), foreground="green")
        self.status_label.grid(row=19, column=0, columnspan=2, pady=(10, 0))

        # Upload to Catbox.moe Section
        ttk.Separator(main_tab_frame, orient='horizontal').grid(row=20, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)

        ttk.Label(main_tab_frame, text=tr('label_upload_section'), font=('Arial', 11, 'bold')).grid(row=21, column=0, sticky=tk.W, pady=(0, 3))

        upload_frame = ttk.Frame(main_tab_frame)
        upload_frame.grid(row=22, column=0, columnspan=2, sticky=tk.W, pady=(5, 5))

        self.upload_btn = ttk.Button(upload_frame, text=tr('btn_upload'), command=self.start_upload, state='disabled')
        self.upload_btn.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(upload_frame, text=tr('btn_view_history'), command=self.view_upload_history).pack(side=tk.LEFT, padx=(0, 10))

        self.upload_status_label = ttk.Label(upload_frame, text="", foreground="blue", font=('Arial', 9))
        self.upload_status_label.pack(side=tk.LEFT)

        # Auto-upload checkbox
        auto_upload_frame = ttk.Frame(main_tab_frame)
        auto_upload_frame.grid(row=23, column=0, columnspan=2, sticky=tk.W, padx=(20, 0), pady=(5, 0))

        ttk.Checkbutton(auto_upload_frame, text=tr('checkbox_auto_upload'),
                       variable=self.auto_upload_var).pack(side=tk.LEFT)

        # Upload URL display (initially hidden)
        self.upload_url_frame = ttk.Frame(main_tab_frame)
        self.upload_url_frame.grid(row=24, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))

        ttk.Label(self.upload_url_frame, text=tr('label_upload_url'), font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 5))

        self.upload_url_entry = ttk.Entry(self.upload_url_frame, width=60, state='readonly')
        self.upload_url_entry.pack(side=tk.LEFT, padx=(0, 10))

        self.copy_url_btn = ttk.Button(self.upload_url_frame, text=tr('btn_copy_url'), command=self.copy_upload_url)
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
        ttk.Label(parent, text=tr('header_clipboard_mode'), font=('Arial', 14, 'bold')).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        ttk.Label(parent, text=tr('desc_clipboard_mode'),
                  foreground="gray", font=('Arial', 9)).grid(
            row=1, column=0, columnspan=2, sticky=tk.W, pady=(0, 15))

        # Mode Toggle
        mode_frame = ttk.Frame(parent)
        mode_frame.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        ttk.Label(mode_frame, text=tr('label_download_mode'), font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=(0, 10))
        self.clipboard_auto_download_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(mode_frame, text=tr('checkbox_auto_download'),
                       variable=self.clipboard_auto_download_var).pack(side=tk.LEFT)

        # Settings
        ttk.Separator(parent, orient='horizontal').grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)
        ttk.Label(parent, text=tr('header_settings'), font=('Arial', 11, 'bold')).grid(row=4, column=0, sticky=tk.W, pady=(0, 5))

        settings_frame = ttk.Frame(parent)
        settings_frame.grid(row=5, column=0, columnspan=2, sticky=tk.W, padx=(20, 0), pady=(0, 10))

        # Quality dropdown
        ttk.Label(settings_frame, text=tr('label_quality'), font=('Arial', 9)).grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.clipboard_quality_var = tk.StringVar(value="1080")
        quality_options = ["1440", "1080", "720", "480", "360", "240", tr('quality_audio_only')]
        self.clipboard_quality_combo = ttk.Combobox(settings_frame, textvariable=self.clipboard_quality_var,
            values=quality_options, state='readonly', width=20)
        self.clipboard_quality_combo.grid(row=0, column=1, sticky=tk.W)

        # Speed limit
        ttk.Label(settings_frame, text="Speed limit:", font=('Arial', 9)).grid(row=0, column=2, sticky=tk.W, padx=(20, 5))
        self.clipboard_speed_limit_var = tk.StringVar(value="")
        self.clipboard_speed_limit_entry = ttk.Entry(settings_frame, textvariable=self.clipboard_speed_limit_var, width=6)
        self.clipboard_speed_limit_entry.grid(row=0, column=3, sticky=tk.W)
        ttk.Label(settings_frame, text="MB/s", font=('Arial', 9)).grid(row=0, column=4, sticky=tk.W, padx=(5, 0))

        # Output Folder
        ttk.Separator(parent, orient='horizontal').grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        folder_frame = ttk.Frame(parent)
        folder_frame.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(folder_frame, text=tr('label_save_to'), font=('Arial', 9)).pack(side=tk.LEFT)
        self.clipboard_path_label = ttk.Label(folder_frame, text=self.clipboard_download_path, foreground="blue")
        self.clipboard_path_label.pack(side=tk.LEFT, padx=(10, 10))
        ttk.Button(folder_frame, text=tr('btn_change'), command=self.change_clipboard_path).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(folder_frame, text=tr('btn_open_folder'), command=self.open_clipboard_folder).pack(side=tk.LEFT)

        # URL List
        ttk.Separator(parent, orient='horizontal').grid(row=8, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        url_header_frame = ttk.Frame(parent)
        url_header_frame.grid(row=9, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))

        ttk.Label(url_header_frame, text=tr('label_detected_urls'), font=('Arial', 11, 'bold')).pack(side=tk.LEFT)
        self.clipboard_url_count_label = ttk.Label(url_header_frame, text=tr('label_url_count', count=0, s='s'), foreground="gray", font=('Arial', 9))
        self.clipboard_url_count_label.pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(url_header_frame, text=tr('btn_clear_all'), command=self.clear_all_clipboard_urls).pack(side=tk.RIGHT)

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

        self.clipboard_download_btn = ttk.Button(button_frame, text=tr('btn_download_all'),
            command=self.start_clipboard_downloads, state='disabled')
        self.clipboard_download_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.clipboard_stop_btn = ttk.Button(button_frame, text=tr('btn_stop'),
            command=self.stop_clipboard_downloads, state='disabled')
        self.clipboard_stop_btn.pack(side=tk.LEFT)

        # Individual progress
        ttk.Label(parent, text=tr('label_current_download'), font=('Arial', 9, 'bold')).grid(row=13, column=0, sticky=tk.W, pady=(0, 3))

        self.clipboard_progress = ttk.Progressbar(parent, mode='determinate', length=560, maximum=100)
        self.clipboard_progress.grid(row=14, column=0, columnspan=2)

        self.clipboard_progress_label = ttk.Label(parent, text="0%", foreground="blue")
        self.clipboard_progress_label.grid(row=15, column=0, columnspan=2, pady=(5, 0))

        # Total progress
        self.clipboard_total_label = ttk.Label(parent, text=tr('label_completed_total', done=0, total=0),
            foreground="green", font=('Arial', 9, 'bold'))
        self.clipboard_total_label.grid(row=16, column=0, columnspan=2, pady=(5, 0))

        # Status
        self.clipboard_status_label = ttk.Label(parent, text=tr('status_ready'), foreground="green")
        self.clipboard_status_label.grid(row=17, column=0, columnspan=2, pady=(10, 0))

    def setup_uploader_ui(self, parent):
        """Setup Uploader tab UI"""

        # Header
        ttk.Label(parent, text=tr('header_upload_file'), font=('Arial', 14, 'bold')).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        ttk.Label(parent, text=tr('desc_upload_file'),
                  foreground="gray", font=('Arial', 9)).grid(
            row=1, column=0, columnspan=2, sticky=tk.W, pady=(0, 15))

        # File selection
        ttk.Separator(parent, orient='horizontal').grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        file_header_frame = ttk.Frame(parent)
        file_header_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))

        ttk.Label(file_header_frame, text=tr('label_file_queue'), font=('Arial', 11, 'bold')).pack(side=tk.LEFT)
        self.uploader_queue_count_label = ttk.Label(file_header_frame, text=tr('label_file_count', count=0, s='s'), foreground="gray", font=('Arial', 9))
        self.uploader_queue_count_label.pack(side=tk.LEFT, padx=(10, 0))

        file_select_frame = ttk.Frame(parent)
        file_select_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Button(file_select_frame, text=tr('btn_add_files'), command=self.browse_uploader_files).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(file_select_frame, text=tr('btn_clear_all'), command=self.clear_uploader_queue).pack(side=tk.LEFT)

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

        self.uploader_upload_btn = ttk.Button(upload_controls_frame, text=tr('btn_upload'),
                                              command=self.start_uploader_upload, state='disabled')
        self.uploader_upload_btn.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(upload_controls_frame, text=tr('btn_view_history'), command=self.view_upload_history).pack(side=tk.LEFT)

        self.uploader_status_label = ttk.Label(parent, text="", foreground="blue", font=('Arial', 9))
        self.uploader_status_label.grid(row=8, column=0, columnspan=2, sticky=tk.W, pady=(5, 10))

        # Upload URL display (initially hidden)
        self.uploader_url_frame = ttk.Frame(parent)
        self.uploader_url_frame.grid(row=9, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))

        ttk.Label(self.uploader_url_frame, text=tr('label_upload_url'), font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 5))

        self.uploader_url_entry = ttk.Entry(self.uploader_url_frame, width=60, state='readonly')
        self.uploader_url_entry.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(self.uploader_url_frame, text=tr('btn_copy_url'), command=self.copy_uploader_url).pack(side=tk.LEFT)

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
                    with self.clipboard_lock:
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

        with self.clipboard_lock:
            self.clipboard_url_list.append(url_data)
            self.clipboard_url_widgets[url] = url_data
            has_urls = len(self.clipboard_url_list) > 0

        self._update_clipboard_url_count()
        with self.clipboard_lock:
            is_downloading = self.clipboard_downloading
        if has_urls and not is_downloading:
            self.clipboard_download_btn.config(state='normal')

        # Save URLs to persistence file
        self._save_clipboard_urls()

    def _remove_url_from_list(self, url):
        """Remove URL from clipboard list"""
        widget_to_destroy = None
        list_is_empty = False

        with self.clipboard_lock:
            for i, item in enumerate(self.clipboard_url_list):
                if item['url'] == url:
                    widget_to_destroy = item['widget']
                    self.clipboard_url_list.pop(i)
                    if url in self.clipboard_url_widgets:
                        del self.clipboard_url_widgets[url]
                    list_is_empty = len(self.clipboard_url_list) == 0
                    break

        # UI operations outside the lock
        if widget_to_destroy:
            widget_to_destroy.destroy()
            self._update_clipboard_url_count()
            if list_is_empty:
                self.clipboard_download_btn.config(state='disabled')
            logger.info(f"Removed URL: {url}")

            # Save URLs to persistence file
            self._save_clipboard_urls()

    def clear_all_clipboard_urls(self):
        """Clear all URLs from clipboard list"""
        with self.clipboard_lock:
            is_downloading = self.clipboard_downloading
        if is_downloading:
            messagebox.showwarning(tr('warning_cannot_clear_title'), tr('warning_cannot_clear_downloading'))
            return

        # Take snapshot of widgets to destroy
        with self.clipboard_lock:
            widgets_to_destroy = [item['widget'] for item in self.clipboard_url_list if item['widget']]
            self.clipboard_url_list.clear()
            self.clipboard_url_widgets.clear()

        # UI operations outside the lock
        for widget in widgets_to_destroy:
            widget.destroy()

        self._update_clipboard_url_count()
        self.clipboard_download_btn.config(state='disabled')
        logger.info("Cleared all clipboard URLs")

        # Save URLs to persistence file
        self._save_clipboard_urls()

    def _update_clipboard_url_count(self):
        """Update URL count label"""
        with self.clipboard_lock:
            count = len(self.clipboard_url_list)
        s = 's' if count != 1 else ''
        self.clipboard_url_count_label.config(text=tr('label_url_count', count=count, s=s))

    def _update_url_status(self, url, status):
        """Update visual status of URL: pending (gray), downloading (blue), completed (green), failed (red)"""
        if url in self.clipboard_url_widgets:
            item = self.clipboard_url_widgets[url]
            status_canvas = item['status_canvas']
            status_circle = item['status_circle']

            color_map = {'pending': 'gray', 'downloading': 'blue', 'completed': 'green', 'failed': 'red'}
            color = color_map.get(status, 'gray')
            status_canvas.itemconfig(status_circle, fill=color)

            with self.clipboard_lock:
                for item_data in self.clipboard_url_list:
                    if item_data['url'] == url:
                        item_data['status'] = status
                        break

    # Phase 6: Download Queue (Sequential Processing)

    def start_clipboard_downloads(self):
        """Start downloading all pending URLs sequentially"""
        with self.clipboard_lock:
            is_downloading = self.clipboard_downloading
        if is_downloading:
            return

        with self.clipboard_lock:
            pending_urls = [item for item in self.clipboard_url_list if item['status'] == 'pending']

        if not pending_urls:
            messagebox.showinfo(tr('warning_no_urls_title'), tr('warning_no_urls'))
            return

        with self.clipboard_lock:
            self.clipboard_downloading = True
        self.clipboard_download_btn.config(state='disabled')
        self.clipboard_stop_btn.config(state='normal')

        total_count = len(pending_urls)
        self.clipboard_total_label.config(text=tr('label_completed_total', done=0, total=total_count))

        logger.info(f"Starting clipboard batch download: {total_count} URLs")
        self.thread_pool.submit(self._process_clipboard_queue)

    def _process_clipboard_queue(self):
        """Process clipboard download queue sequentially"""
        with self.clipboard_lock:
            pending_urls = [item for item in self.clipboard_url_list if item['status'] == 'pending']
        total_count = len(pending_urls)

        for index, item in enumerate(pending_urls):
            with self.clipboard_lock:
                is_downloading = self.clipboard_downloading
            if not is_downloading:
                logger.info("Clipboard downloads stopped by user")
                break

            url = item['url']

            self.root.after(0, lambda u=url: self._update_url_status(u, 'downloading'))
            self.root.after(0, lambda i=index, t=total_count:
                self.clipboard_total_label.config(text=tr('label_completed_total', done=i, total=t)))
            self.root.after(0, lambda u=url:
                self.update_clipboard_status(f"Downloading: {u[:50]}...", "blue"))

            success = self._download_clipboard_url(url, check_stop=True)

            if success:
                self.root.after(0, lambda u=url: self._update_url_status(u, 'completed'))
            else:
                self.root.after(0, lambda u=url: self._update_url_status(u, 'failed'))

            completed = index + 1
            self.root.after(0, lambda c=completed, t=total_count:
                self.clipboard_total_label.config(text=tr('label_completed_total', done=c, total=t)))

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

            # Add speed limit if set
            cmd.extend(self._get_speed_limit_args(self.clipboard_speed_limit_var))

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       universal_newlines=True, bufsize=1)

            for line in process.stdout:
                # Check stop flags
                if check_stop:
                    with self.clipboard_lock:
                        is_downloading = self.clipboard_downloading
                    if not is_downloading:
                        self.safe_process_cleanup(process)
                        return False
                if check_stop_auto:
                    with self.auto_download_lock:
                        is_auto_downloading = self.clipboard_auto_downloading
                    if not is_auto_downloading:
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
        with self.clipboard_lock:
            self.clipboard_downloading = False
            has_urls = len(self.clipboard_url_list) > 0
            completed = sum(1 for item in self.clipboard_url_list if item['status'] == 'completed')
            failed = sum(1 for item in self.clipboard_url_list if item['status'] == 'failed')

        self.clipboard_download_btn.config(state='normal' if has_urls else 'disabled')
        self.clipboard_stop_btn.config(state='disabled')

        if failed > 0:
            self.update_clipboard_status(tr('status_completed_failed', completed=completed, failed=failed), "orange")
        else:
            self.update_clipboard_status(tr('status_all_downloads_complete', count=completed), "green")

        logger.info(f"Clipboard batch download finished: {completed} completed, {failed} failed")

    def stop_clipboard_downloads(self):
        """Stop clipboard batch downloads and auto-downloads"""
        stopped = False
        with self.clipboard_lock:
            if self.clipboard_downloading:
                self.clipboard_downloading = False
                stopped = True
        if stopped:
            logger.info("Clipboard batch downloads stopped by user")
        with self.auto_download_lock:
            if self.clipboard_auto_downloading:
                self.clipboard_auto_downloading = False
                stopped = True
        if stopped:
            logger.info("Clipboard auto-downloads stopped by user")
            self.update_clipboard_status(tr('status_downloads_stopped'), "orange")
            self.clipboard_stop_btn.config(state='disabled')

    def _auto_download_single_url(self, url):
        """Auto-download single URL when detected (if auto-download enabled)"""
        # Check if another auto-download is already in progress (thread-safe)
        with self.auto_download_lock:
            with self.clipboard_lock:
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
        with self.auto_download_lock:
            is_auto_downloading = self.clipboard_auto_downloading
        if not is_auto_downloading:
            self.root.after(0, lambda: self._update_url_status(url, 'pending'))
            return

        self.root.after(0, lambda: self.update_clipboard_status(tr('status_auto_downloading', url=url[:50]), "blue"))

        success = self._download_clipboard_url(url, check_stop_auto=True)

        # Check if stopped during download
        with self.auto_download_lock:
            is_auto_downloading = self.clipboard_auto_downloading
        if not is_auto_downloading:
            self.root.after(0, lambda: self._update_url_status(url, 'pending'))
            self.root.after(0, lambda: self.update_clipboard_status(tr('status_auto_download_stopped'), "orange"))
            return

        # Schedule all UI updates and next download in a single callback to ensure order
        self.root.after(0, lambda: self._handle_auto_download_complete(url, success))

    def _handle_auto_download_complete(self, url, success):
        """Handle auto-download completion - runs on main thread"""
        if success:
            self._update_url_status(url, 'completed')
            self._update_auto_download_total()
            self.update_clipboard_status(tr('status_auto_download_complete', url=url[:50]), "green")
            # Auto-remove successfully completed URLs from list
            self._remove_url_from_list(url)
            logger.info(f"Auto-download completed and removed: {url}")
        else:
            self._update_url_status(url, 'failed')
            self._update_auto_download_total()
            self.update_clipboard_status(tr('status_auto_download_failed', url=url[:50]), "red")
            logger.info(f"Auto-download failed: {url}")

        # Now check for next pending download (all state is consistent now)
        self._check_pending_auto_downloads()

    def _disable_stop_if_idle(self):
        """Disable stop button if no downloads in progress"""
        with self.clipboard_lock:
            is_downloading = self.clipboard_downloading
        with self.auto_download_lock:
            is_auto_downloading = self.clipboard_auto_downloading
        if not is_downloading and not is_auto_downloading:
            self.clipboard_stop_btn.config(state='disabled')

    def _check_pending_auto_downloads(self):
        """Check if there are pending URLs that need to be auto-downloaded"""
        # Reset auto-downloading flag if no more downloads
        with self.auto_download_lock:
            self.clipboard_auto_downloading = False

        if self.clipboard_auto_download_var.get():
            # Find first pending URL
            with self.clipboard_lock:
                next_pending_url = None
                for item in self.clipboard_url_list:
                    if item['status'] == 'pending':
                        next_pending_url = item['url']
                        break  # Only start one at a time

            if next_pending_url:
                self._auto_download_single_url(next_pending_url)
        else:
            # Disable stop button if idle
            self._disable_stop_if_idle()

    def _update_auto_download_total(self):
        """Update total progress for auto-downloads"""
        with self.clipboard_lock:
            total = len(self.clipboard_url_list)
            completed = sum(1 for item in self.clipboard_url_list if item['status'] in ['completed', 'failed'])
        self.clipboard_total_label.config(text=tr('status_clipboard_completed_total', completed=completed, total=total))

    # Phase 7: Helper Methods

    def update_clipboard_progress(self, value):
        """Update clipboard mode progress bar"""
        try:
            value = float(value)
            value = max(0, min(100, value))  # Clamp to 0-100
            self.clipboard_progress['value'] = value
            self.clipboard_progress_label.config(text=f"{value:.1f}%")
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid progress value: {value} - {e}")

    def update_clipboard_status(self, message, color):
        """Update clipboard mode status label"""
        self.clipboard_status_label.config(text=message, foreground=color)

    def change_clipboard_path(self):
        """Change clipboard mode download path"""
        path = filedialog.askdirectory(initialdir=self.clipboard_download_path)
        if path:
            if not os.path.exists(path):
                messagebox.showerror(tr('error_title'), tr('error_path_not_exist', path=path))
                return

            if not os.path.isdir(path):
                messagebox.showerror(tr('error_title'), tr('error_path_not_directory', path=path))
                return

            test_file = os.path.join(path, ".ytdl_write_test")
            try:
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
            except (IOError, OSError) as e:
                messagebox.showerror(tr('error_title'), tr('error_path_not_writable', path=path, error=str(e)))
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
                subprocess.Popen(['open', self.clipboard_download_path], close_fds=True, start_new_session=True)
            else:
                subprocess.Popen(['xdg-open', self.clipboard_download_path], close_fds=True, start_new_session=True)
        except Exception as e:
            messagebox.showerror(tr('error_title'), tr('error_failed_open_folder', error=str(e)))

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
            messagebox.showerror(tr('error_title'), tr('error_enter_url'))
            return

        # Check if it's a local file or YouTube URL
        if self.is_local_file(url):
            # Validate local file exists
            if not os.path.isfile(url):
                messagebox.showerror(tr('error_title'), tr('error_file_not_found', path=url))
                return
            self.local_file_path = url
        else:
            # Validate YouTube URL
            is_valid, message = self.validate_youtube_url(url)
            if not is_valid:
                messagebox.showerror(tr('error_invalid_url'), message)
                logger.warning(f"Invalid URL rejected: {url}")
                return
            self.local_file_path = None

            # Check if it's a playlist
            self.is_playlist = self.is_playlist_url(url)
            if self.is_playlist:
                # Disable trimming and upload for playlists
                self.trim_enabled_var.set(False)
                self.toggle_trim()  # Disable trim controls
                self.video_info_label.config(text=tr('warning_playlist_detected'), foreground="orange")
                self.filesize_label.config(text="")
                logger.info("Playlist URL detected - trimming disabled")
                # Don't fetch duration for playlists
                return

        with self.fetch_lock:
            is_fetching = self.is_fetching_duration
        if is_fetching or self.is_downloading:
            return

        # Save the URL for preview extraction and clear cache
        if self.current_video_url != url:
            self.current_video_url = url
            self._clear_preview_cache()
        else:
            self.current_video_url = url

        with self.fetch_lock:
            self.is_fetching_duration = True
        self.fetch_duration_btn.config(state='disabled')
        self.update_status(tr('status_fetching_duration'), "blue")

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
                self.trim_duration_label.config(text=tr('label_selected_duration_value', duration=self.seconds_to_hms(self.video_duration)))

                # Display video title if available
                if title_result and title_result.returncode == 0:
                    video_title = title_result.stdout.strip()
                    self.video_info_label.config(text=tr('label_video_title', title=video_title))
                    logger.info(f"Video title: {video_title}")

                # Fetch estimated file size
                self._fetch_file_size(url)

                self.update_status(tr('status_duration_fetched'), "green")

                # Trigger initial preview update
                self.root.after(UI_INITIAL_DELAY_MS, self.update_previews)
                logger.info(f"Successfully fetched video duration: {self.video_duration}s")
            else:
                raise Exception(f"yt-dlp returned error: {result.stderr}")

        except subprocess.TimeoutExpired:
            error_msg = tr('error_request_timeout')
            messagebox.showerror(tr('error_title'), error_msg)
            self.update_status(tr('status_duration_timeout'), "red")
            logger.error("Timeout fetching video duration")
        except ValueError as e:
            error_msg = tr('error_invalid_duration', error=str(e))
            messagebox.showerror(tr('error_title'), error_msg)
            self.update_status(tr('status_invalid_duration_format'), "red")
            logger.error(f"Duration parsing error: {e}")
        except Exception as e:
            messagebox.showerror(tr('error_title'), tr('error_fetch_duration_failed', error=str(e)))
            self.update_status(tr('status_duration_fetch_failed'), "red")
            logger.exception(f"Unexpected error fetching duration: {e}")

        finally:
            with self.fetch_lock:
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
            self.filesize_label.config(text=tr('label_estimated_size', size=f"{filesize_mb:.1f}"))
            self.estimated_filesize = filesize_bytes
        elif filesize_mb is None and filesize_bytes is None:
            self.filesize_label.config(text=tr('label_estimated_size_unknown'))
            self.estimated_filesize = None

        # Update trimmed size if trimming is enabled
        self._update_trimmed_filesize()

    def on_quality_change(self, *args):
        """Handle quality selection changes - re-fetch file size with new quality"""
        # Only re-fetch if we have a valid URL and have already fetched duration
        if self.current_video_url and self.video_duration > 0 and not self.is_playlist:
            # Show loading indicator
            self.filesize_label.config(text=tr('label_calculating_size'))
            # Re-fetch file size with new quality setting (in background)
            self._fetch_file_size(self.current_video_url)

    def _update_trimmed_filesize(self):
        """Update file size estimate based on trim selection using linear calculation"""
        if not self.estimated_filesize or not self.trim_enabled_var.get():
            # If no size estimate or trimming disabled, show original size
            if self.estimated_filesize:
                filesize_mb = self.estimated_filesize / (1024 * 1024)
                self.filesize_label.config(text=tr('label_estimated_size', size=f"{filesize_mb:.1f}"))
            return

        # Calculate trimmed size using linear approach
        start_time = int(self.start_time_var.get())
        end_time = int(self.end_time_var.get())
        selected_duration = end_time - start_time

        if self.video_duration > 0:
            duration_percentage = selected_duration / self.video_duration
            trimmed_size = self.estimated_filesize * duration_percentage
            trimmed_size_mb = trimmed_size / (1024 * 1024)
            self.filesize_label.config(text=tr('label_estimated_size_trimmed', size=f"{trimmed_size_mb:.1f}"))

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

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=FFPROBE_TIMEOUT, check=True)
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
            self.trim_duration_label.config(text=tr('label_selected_duration_value', duration=self.seconds_to_hms(self.video_duration)))

            # Display filename
            self.video_info_label.config(text=tr('label_file', filename=video_title))
            logger.info(f"Local file duration: {self.video_duration}s")

            self.update_status(tr('status_duration_fetched'), "green")

            # Trigger initial preview update
            self.root.after(100, self.update_previews)

        except subprocess.CalledProcessError as e:
            error_msg = tr('error_read_video_failed', error=(e.stderr if e.stderr else str(e)))
            messagebox.showerror(tr('error_title'), error_msg)
            self.update_status(tr('error_read_file_failed', error=''), "red")
            logger.error(f"ffprobe error: {e}")
        except ValueError as e:
            error_msg = tr('error_invalid_video_format')
            messagebox.showerror(tr('error_title'), error_msg)
            self.update_status(tr('error_invalid_video_format'), "red")
            logger.error(f"Duration parsing error: {e}")
        except Exception as e:
            messagebox.showerror(tr('error_title'), tr('error_read_file_failed', error=str(e)))
            self.update_status(tr('error_read_file_failed', error=''), "red")
            logger.exception(f"Unexpected error reading local file: {e}")
        finally:
            with self.fetch_lock:
                self.is_fetching_duration = False
            if self.trim_enabled_var.get():
                self.fetch_duration_btn.config(state='normal')

    def on_slider_change(self, event=None):
        """Handle slider changes and enforce valid time ranges.

        Called when start/end time sliders are moved by the user or programmatically.
        Ensures start time is always before end time by automatically adjusting
        the other slider when needed.

        Args:
            event: Optional event object. If None, no automatic adjustment occurs
                   (used for programmatic updates to prevent adjustment loops)

        Behavior:
            - If start >= end and event exists, adjusts the non-moved slider
            - Updates HH:MM:SS entry fields to match slider values
            - Recalculates selected duration label
            - Updates estimated file size for trimmed segment
            - Schedules debounced preview frame update
        """
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
        self.trim_duration_label.config(text=tr('label_selected_duration_value', duration=self.seconds_to_hms(selected_duration)))

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
            messagebox.showerror(tr('error_title'), tr('error_no_file_to_upload'))
            return

        # Check file size (200MB limit for Catbox.moe)
        file_size_mb = os.path.getsize(self.last_output_file) / (1024 * 1024)
        if file_size_mb > 200:
            messagebox.showerror(tr('error_file_too_large_title'),
                               tr('error_file_too_large', size=f"{file_size_mb:.1f}"))
            return

        # Disable upload button during upload
        self.upload_btn.config(state='disabled')
        self.upload_status_label.config(text=tr('status_uploading'), foreground="blue")
        self.upload_url_frame.grid_remove()

        # Start upload in background thread
        self.thread_pool.submit(self.upload_to_catbox)

    def upload_to_catbox(self):
        """Upload file to Catbox.moe and display the URL"""
        try:
            with self.upload_lock:
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
            with self.upload_lock:
                self.is_uploading = False

    def _upload_success(self, file_url):
        """Handle successful upload (called on main thread)"""
        self.upload_status_label.config(text=tr('status_upload_complete'), foreground="green")

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

        messagebox.showinfo(tr('info_upload_complete_title'),
                          tr('info_upload_complete', url=file_url))

        # Auto-copy to clipboard
        self.root.clipboard_clear()
        self.root.clipboard_append(file_url)

    def _upload_failed(self, error_msg):
        """Handle failed upload (called on main thread)"""
        self.upload_status_label.config(text=tr('status_upload_failed'), foreground="red")
        self.upload_btn.config(state='normal')
        messagebox.showerror(tr('info_upload_failed_title'), tr('info_upload_failed', error=error_msg))

    def copy_upload_url(self):
        """Copy upload URL to clipboard"""
        url = self.upload_url_entry.get()
        if url:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self.upload_status_label.config(text=tr('status_url_copied'), foreground="green")
            logger.info("Upload URL copied to clipboard")

    # Uploader tab methods

    def browse_uploader_files(self):
        """Browse and select multiple files for upload in Uploader tab"""
        file_paths = filedialog.askopenfilenames(
            title=tr('dialog_select_video_files'),
            filetypes=[
                (tr('dialog_video_files'), "*.mp4 *.avi *.mkv *.mov *.flv *.wmv *.webm *.m4v"),
                (tr('dialog_audio_files'), "*.mp3 *.m4a *.wav *.flac *.aac *.ogg"),
                (tr('dialog_all_files'), "*.*")
            ]
        )

        if file_paths:
            for file_path in file_paths:
                # Check file size
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                if file_size_mb > 200:
                    messagebox.showwarning(tr('error_file_too_large_title'),
                                         tr('info_skipped_file', filename=os.path.basename(file_path), size=f"{file_size_mb:.1f}"))
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

        file_label = ttk.Label(file_frame, text=tr('label_file_size', filename=filename, size=f"{file_size_mb:.1f}"), font=('Arial', 9))
        file_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 10))

        remove_btn = ttk.Button(file_frame, text="X", width=3,
                              command=lambda: self._remove_file_from_queue(file_path))
        remove_btn.pack(side=tk.RIGHT, padx=5)

        self.uploader_file_queue.append({'path': file_path, 'widget': file_frame})
        self._update_uploader_queue_count()

        with self.uploader_lock:
            is_uploading = self.uploader_is_uploading
        if len(self.uploader_file_queue) > 0 and not is_uploading:
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
        with self.uploader_lock:
            is_uploading = self.uploader_is_uploading
        if is_uploading:
            messagebox.showwarning(tr('warning_cannot_clear_title'), tr('warning_cannot_clear_uploading'))
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
        s = 's' if count != 1 else ''
        self.uploader_queue_count_label.config(text=tr('label_file_count', count=count, s=s))

    def start_uploader_upload(self):
        """Start uploading all files in queue sequentially"""
        if len(self.uploader_file_queue) == 0:
            messagebox.showinfo(tr('warning_no_files_title'), tr('warning_no_files'))
            return

        with self.uploader_lock:
            is_uploading = self.uploader_is_uploading
        if is_uploading:
            return

        with self.uploader_lock:
            self.uploader_is_uploading = True
        self.uploader_current_index = 0
        self.uploader_upload_btn.config(state='disabled')
        self.uploader_url_frame.grid_remove()

        # Start upload queue processing in background thread
        self.thread_pool.submit(self._process_uploader_queue)

    def _process_uploader_queue(self):
        """Process upload queue sequentially"""
        total_count = len(self.uploader_file_queue)

        for index, item in enumerate(self.uploader_file_queue):
            with self.uploader_lock:
                is_uploading = self.uploader_is_uploading
            if not is_uploading:
                logger.info("Uploader queue processing stopped by user")
                break

            file_path = item['path']
            filename = os.path.basename(file_path)

            self.root.after(0, lambda i=index, t=total_count, fn=filename:
                self.uploader_status_label.config(
                    text=tr('status_uploading_file', current=i+1, total=t, filename=fn),
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
            filename = os.path.basename(file_path)
            full_error = f"Failed to upload {filename}:\n\n{error_msg}"
            self.root.after(0, lambda msg=full_error:
                messagebox.showerror(tr('info_upload_failed_title'), msg))
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
        with self.uploader_lock:
            self.uploader_is_uploading = False

        # Clear the queue
        for item in self.uploader_file_queue:
            if item['widget']:
                item['widget'].destroy()

        count = len(self.uploader_file_queue)
        self.uploader_file_queue.clear()
        self._update_uploader_queue_count()

        self.uploader_status_label.config(text=tr('status_all_uploads_complete', count=count), foreground="green")
        self.uploader_upload_btn.config(state='disabled')

        logger.info(f"Uploader queue finished: {count} files uploaded")

    def copy_uploader_url(self):
        """Copy upload URL to clipboard from Uploader tab"""
        url = self.uploader_url_entry.get()
        if url:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self.uploader_status_label.config(text=tr('status_url_copied'), foreground="green")
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
                    self.root.after(AUTO_UPLOAD_DELAY_MS, self.start_upload)  # Small delay to ensure UI updates

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
                # Use a format that includes video+audio to avoid segmented streams
                def _get_stream_url():
                    get_url_cmd = [
                        self.ytdlp_path,
                        '-f', 'best[height<=480]/best',  # Combined format is more reliable for frame extraction
                        '--no-playlist',
                        '-g',
                        self.current_video_url
                    ]
                    return subprocess.run(get_url_cmd, capture_output=True, text=True, timeout=STREAM_FETCH_TIMEOUT, check=True)

                result = self.retry_network_operation(_get_stream_url, f"Get stream URL for frame at {timestamp}s")
                video_url = result.stdout.strip().split('\n')[0]

                if not video_url:
                    logger.error("Failed to get stream URL - empty response")
                    return None

            # Now extract frame from the actual stream with retry
            def _extract_frame():
                cmd = [
                    self.ffmpeg_path,
                    '-nostdin',
                ]
                # Add HTTP streaming options for YouTube URLs
                if video_url.startswith('http'):
                    cmd.extend([
                        '-reconnect', '1',
                        '-reconnect_streamed', '1',
                        '-reconnect_delay_max', '5',
                        '-timeout', '10000000',  # 10 second timeout in microseconds
                    ])
                cmd.extend([
                    '-ss', str(timestamp),
                    '-i', video_url,
                    '-vframes', '1',
                    '-q:v', '2',
                    '-y',
                    temp_file
                ])
                return subprocess.run(cmd, capture_output=True, timeout=STREAM_FETCH_TIMEOUT, check=True)

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
            # Adjust end_time if it's at or near the video end (ffmpeg struggles with exact EOF)
            adjusted_end_time = end_time
            if self.video_duration > 0 and end_time >= self.video_duration - 1:
                adjusted_end_time = max(0, self.video_duration - 3)  # 3 seconds before end
                logger.debug(f"Adjusted end preview time from {end_time}s to {adjusted_end_time}s (near EOF)")

            logger.info(f"Extracting preview frames at {start_time}s and {adjusted_end_time}s")

            # Extract start frame
            start_frame_path = self.extract_frame(start_time)
            if start_frame_path:
                self._update_preview_image(start_frame_path, 'start')
            else:
                # Show error placeholder if extraction failed
                error_img = self.create_placeholder_image(PREVIEW_WIDTH, PREVIEW_HEIGHT, "Error")
                self.root.after(0, lambda img=error_img: self._set_start_preview(img))

            # Extract end frame (using adjusted time to avoid EOF issues)
            end_frame_path = self.extract_frame(adjusted_end_time)
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
            # Load and resize image (using context manager for proper cleanup)
            with Image.open(image_path) as img:
                img.thumbnail((PREVIEW_WIDTH, PREVIEW_HEIGHT), Image.Resampling.LANCZOS)
                # Convert to PhotoImage (must be done before context exits)
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
                messagebox.showerror(tr('error_title'), tr('error_path_not_exist', path=path))
                return

            if not os.path.isdir(path):
                messagebox.showerror(tr('error_title'), tr('error_path_not_directory', path=path))
                return

            # Test write permissions
            test_file = os.path.join(path, ".ytdl_write_test")
            try:
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
            except (IOError, OSError) as e:
                messagebox.showerror(tr('error_title'), tr('error_path_not_writable', path=path, error=str(e)))
                return

            self.download_path = path
            self.path_label.config(text=path)

    def open_download_folder(self):
        """Open the download folder in the system file manager"""
        try:
            if sys.platform == 'win32':
                os.startfile(self.download_path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', self.download_path], close_fds=True, start_new_session=True)
            else:
                subprocess.Popen(['xdg-open', self.download_path], close_fds=True, start_new_session=True)
        except Exception as e:
            messagebox.showerror(tr('error_title'), tr('error_failed_open_folder', error=str(e)))

    def browse_local_file(self):
        """Open file dialog to select a local video file"""
        filetypes = [
            (tr('dialog_video_files'), '*.mp4 *.mkv *.avi *.mov *.flv *.webm *.wmv *.m4v'),
            (tr('dialog_all_files'), '*.*')
        ]

        filepath = filedialog.askopenfilename(
            title=tr('dialog_select_video'),
            filetypes=filetypes,
            initialdir=str(Path.home())
        )

        if filepath:
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, filepath)
            self.local_file_path = filepath
            self.mode_label.config(
                text=tr('label_mode_local', filename=Path(filepath).name),
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
                text=tr('label_mode_local', filename=Path(input_text).name),
                foreground="green"
            )
        else:
            self.local_file_path = None
            self.mode_label.config(
                text=tr('label_mode_youtube'),
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
            # Check yt-dlp (don't use check=True as warnings may cause non-zero exit)
            result = subprocess.run([self.ytdlp_path, '--version'],
                                  capture_output=True, timeout=DEPENDENCY_CHECK_TIMEOUT)
            version = result.stdout.decode().strip()
            if version:
                logger.info(f"yt-dlp version: {version}")
            else:
                logger.error("yt-dlp check failed: no version output")
                return False

            # Check ffmpeg (use bundled or system)
            result = subprocess.run([self.ffmpeg_path, '-version'],
                                  capture_output=True, timeout=DEPENDENCY_CHECK_TIMEOUT)
            if result.returncode == 0:
                logger.info(f"ffmpeg is available at: {self.ffmpeg_path}")
            else:
                logger.error("ffmpeg check failed")
                return False

            # Check ffprobe (use bundled or system)
            result = subprocess.run([self.ffprobe_path, '-version'],
                                  capture_output=True, timeout=DEPENDENCY_CHECK_TIMEOUT)
            if result.returncode == 0:
                logger.info(f"ffprobe is available at: {self.ffprobe_path}")
            else:
                logger.error("ffprobe check failed")
                return False

            return True
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.error(f"Dependency check failed: {e}")
            return False

    def start_download(self):
        url = self.url_entry.get().strip()

        if not url:
            messagebox.showerror(tr('error_title'), tr('error_enter_url'))
            return

        # Check if local file or YouTube URL
        is_local = self.is_local_file(url)

        if is_local:
            # Validate local file exists
            if not os.path.isfile(url):
                messagebox.showerror(tr('error_title'), tr('error_file_not_found', path=url))
                return
        else:
            # Validate YouTube URL
            is_valid, message = self.validate_youtube_url(url)
            if not is_valid:
                messagebox.showerror(tr('error_invalid_url'), message)
                logger.warning(f"Invalid URL rejected for download: {url}")
                return

            # Check if it's a playlist and update flag
            self.is_playlist = self.is_playlist_url(url)

        if not self.dependencies_ok:
            messagebox.showerror(tr('error_title'), tr('error_missing_dependencies'))
            return

        logger.info(f"Starting download for URL: {url}")

        with self.download_lock:
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
        while True:
            time.sleep(TIMEOUT_CHECK_INTERVAL)  # Check at configured interval

            with self.download_lock:
                is_still_downloading = self.is_downloading

            if not is_still_downloading:
                break

            current_time = time.time()

            # Check absolute timeout
            if self.download_start_time:
                elapsed = current_time - self.download_start_time
                if elapsed > DOWNLOAD_TIMEOUT:
                    logger.error(f"Download exceeded absolute timeout ({DOWNLOAD_TIMEOUT}s)")
                    self.root.after(0, lambda: self._timeout_download(tr('timeout_download_absolute')))
                    break

            # Check progress timeout (stalled download)
            if self.last_progress_time:
                time_since_progress = current_time - self.last_progress_time
                if time_since_progress > DOWNLOAD_PROGRESS_TIMEOUT:
                    logger.error(f"Download stalled (no progress for {DOWNLOAD_PROGRESS_TIMEOUT}s)")
                    self.root.after(0, lambda: self._timeout_download(tr('timeout_download_stalled')))
                    break

    def _timeout_download(self, reason):
        """Handle download timeout"""
        if self.is_downloading:
            logger.warning(f"Timing out download: {reason}")
            self.update_status(reason, "red")
            self.stop_download()

    def _get_speed_limit_args(self, speed_limit_var=None):
        """Get yt-dlp speed limit arguments if speed limit is set

        Args:
            speed_limit_var: Optional StringVar to use. Defaults to self.speed_limit_var
        """
        if speed_limit_var is None:
            speed_limit_var = self.speed_limit_var
        speed_limit_str = speed_limit_var.get().strip()
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
        with self.download_lock:
            process_to_cleanup = self.current_process
            is_active = self.is_downloading

        if process_to_cleanup and is_active:
            self.safe_process_cleanup(process_to_cleanup)

            with self.download_lock:
                self.is_downloading = False
            self.update_status(tr('status_download_stopped'), "orange")
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

            self.update_status(tr('status_starting_download'), "blue")

            # Check if trimming is enabled and validate
            if trim_enabled:
                if self.video_duration <= 0:
                    self.update_status(tr('error_fetch_duration_first'), "red")
                    self.download_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    with self.download_lock:
                        self.is_downloading = False
                    return

                start_time = int(self.start_time_var.get())
                end_time = int(self.end_time_var.get())

                if start_time >= end_time:
                    self.update_status(tr('error_invalid_time_range'), "red")
                    self.download_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    with self.download_lock:
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
                    self.update_status(tr('error_select_quality'), "red")
                    self.download_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    with self.download_lock:
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
            try:
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
                            self.update_status(tr('status_starting_download'), "blue")
                            self.last_progress_time = time.time()

                    # Look for different download phases
                    elif '[info]' in line and 'Downloading' in line:
                        self.update_status(tr('status_preparing_download'), "blue")
                        self.last_progress_time = time.time()
                    elif '[ExtractAudio]' in line:
                        self.update_status(tr('status_extracting_audio'), "blue")
                        self.last_progress_time = time.time()
                    elif '[Merger]' in line or 'Merging' in line:
                        self.update_status(tr('status_merging'), "blue")
                        self.last_progress_time = time.time()
                    elif '[ffmpeg]' in line:
                        self.update_status(tr('status_processing_ffmpeg'), "blue")
                        self.last_progress_time = time.time()
                    elif 'Post-processing' in line or 'Postprocessing' in line:
                        self.update_status(tr('status_post_processing'), "blue")
                        self.last_progress_time = time.time()
                    elif 'has already been downloaded' in line:
                        self.update_status(tr('status_file_exists'), "orange")
                        self.last_progress_time = time.time()
            except (BrokenPipeError, IOError) as e:
                if self.is_downloading:
                    logger.warning(f"Pipe error while reading process output: {e}")
                    # Process may have terminated, continue to wait()

            self.current_process.wait()

            if self.current_process.returncode == 0 and self.is_downloading:
                self.update_progress(100)
                self.update_status(tr('status_download_complete'), "green")
                logger.info(f"Download completed successfully: {url}")

                # Enable upload button with the most recent file
                latest_file = self._find_latest_file()
                self._enable_upload_button(latest_file)

            elif self.is_downloading:
                self.update_status(tr('status_download_failed'), "red")
                logger.error(f"Download failed with return code {self.current_process.returncode}")

        except FileNotFoundError as e:
            if self.is_downloading:
                error_msg = tr('error_missing_dependencies')
                self.update_status(error_msg, "red")
                logger.error(f"Dependency not found: {e}")
        except PermissionError as e:
            if self.is_downloading:
                error_msg = tr('error_permission_denied')
                self.update_status(error_msg, "red")
                logger.error(f"Permission error: {e}")
        except OSError as e:
            if self.is_downloading:
                error_msg = tr('error_os_error', error=str(e))
                self.update_status(error_msg, "red")
                logger.error(f"OS error during download: {e}")
        except Exception as e:
            if self.is_downloading:
                self.update_status(tr('error_generic', error=str(e)), "red")
                logger.exception(f"Unexpected error during download: {e}")

        finally:
            with self.download_lock:
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

            self.update_status(tr('status_processing_local'), "blue")

            # Validate trimming
            if trim_enabled:
                if self.video_duration <= 0:
                    self.update_status(tr('error_fetch_duration_first'), "red")
                    self.download_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    with self.download_lock:
                        self.is_downloading = False
                    return

                start_time = int(self.start_time_var.get())
                end_time = int(self.end_time_var.get())

                if start_time >= end_time:
                    self.update_status(tr('error_invalid_time_range'), "red")
                    self.download_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    with self.download_lock:
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
                    self.update_status(tr('error_select_quality'), "red")
                    self.download_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    with self.download_lock:
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
                            self.update_status(tr('status_processing', progress=f"{progress:.1f}"), "blue")
                            self.last_progress_time = time.time()
                    except (ValueError, IndexError):
                        pass

            self.current_process.wait()

            if self.current_process.returncode == 0 and self.is_downloading:
                self.update_progress(100)
                self.update_status(tr('status_processing_complete'), "green")
                logger.info(f"Local file processed: {output_file}")

                # Enable upload button
                self._enable_upload_button(output_file)

            elif self.is_downloading:
                stderr = self.current_process.stderr.read() if self.current_process.stderr else ""
                self.update_status(tr('status_processing_failed'), "red")
                logger.error(f"ffmpeg failed: {stderr}")

        except FileNotFoundError as e:
            if self.is_downloading:
                self.update_status(tr('error_ffmpeg_not_found'), "red")
                logger.error(f"ffmpeg not found: {e}")
        except Exception as e:
            if self.is_downloading:
                self.update_status(tr('error_generic', error=str(e)), "red")
                logger.exception(f"Error processing local file: {e}")
        finally:
            with self.download_lock:
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

            self.update_status(tr('status_playlist_downloading'), "blue")
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
                    self.update_status(tr('error_select_quality'), "red")
                    self.download_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    with self.download_lock:
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
                                self.update_status(tr('status_downloading_playlist', progress=f"{progress:.1f}"), "blue")
                    except (ValueError, AttributeError):
                        pass

            self.current_process.wait()

            if self.current_process.returncode == 0 and self.is_downloading:
                self.update_progress(100)
                self.update_status(tr('status_playlist_complete'), "green")
                logger.info(f"Playlist downloaded successfully: {url}")
                # Note: Upload is disabled for playlists
            elif self.is_downloading:
                self.update_status(tr('status_playlist_failed'), "red")
                logger.error(f"Playlist download failed with return code {self.current_process.returncode}")

        except FileNotFoundError as e:
            if self.is_downloading:
                self.update_status(tr('error_ytdlp_not_found'), "red")
                logger.error(f"yt-dlp not found: {e}")
        except Exception as e:
            if self.is_downloading:
                self.update_status(tr('error_generic', error=str(e)), "red")
                logger.exception(f"Error downloading playlist: {e}")
        finally:
            with self.download_lock:
                self.is_downloading = False
            self.download_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            self.current_process = None

    def update_progress(self, value):
        """Update main progress bar with validation"""
        try:
            value = float(value)
            value = max(0, min(100, value))  # Clamp to 0-100
            self.progress['value'] = value
            self.progress_label.config(text=f"{value:.1f}%")
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid progress value: {value} - {e}")

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

        # Save clipboard URLs before shutdown
        try:
            self._save_clipboard_urls()
        except Exception as e:
            logger.error(f"Error saving clipboard URLs: {e}")

        # Stop clipboard monitoring
        self.stop_clipboard_monitoring()

        # Stop clipboard downloads
        with self.clipboard_lock:
            if self.clipboard_downloading:
                self.clipboard_downloading = False
        time.sleep(SHUTDOWN_GRACE_PERIOD_SEC)

        # Stop any ongoing downloads gracefully
        with self.download_lock:
            process_to_cleanup = self.current_process
            is_active = self.is_downloading

        if is_active and process_to_cleanup:
            logger.info("Terminating active download process...")
            self.safe_process_cleanup(process_to_cleanup)

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
