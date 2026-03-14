"""YoutubeDownloader Translations Module

Contains all internationalization (i18n) strings for supported languages:
- English (en)
- German (de)
- Polish (pl)
"""

# Current language setting
CURRENT_LANGUAGE = 'en'

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
        'checkbox_keep_below_10mb': 'Keep video below 10MB',
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
        'label_full_playlist': 'Full Playlist Download (download all videos when given a playlist link)',

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
        'status_two_pass_1': 'Encoding pass 1/2 (analysing)...',
        'status_two_pass_1_progress': 'Encoding pass 1/2... {progress}%',
        'status_two_pass_2': 'Encoding pass 2/2...',
        'status_two_pass_2_progress': 'Encoding pass 2/2... {progress}%',
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
        'info_playlist_params_stripped': 'Playlist parameters removed - downloading single video',

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

        # Clipboard and download status messages
        'status_clipboard_downloading': 'Downloading: {url}...',
        'status_clipboard_completed_total': 'Completed: {completed}/{total} videos',
        'status_downloading_detailed': 'Downloading... {progress}%',
        'status_downloading_with_speed': 'Downloading... {progress}% at {speed}',
        'status_downloading_full': 'Downloading... {progress}% at {speed} | ETA: {eta}',

        # Additional error messages
        'error_permission_denied': 'Permission denied. Check write permissions for download folder.',
        'error_os_error': 'OS error: {error}',
        'error_generic': 'Error: {error}',

        # Update feature
        'update_check_btn': 'Check for Updates',
        'update_auto_check': 'Check for updates on startup',
        'update_checking': 'Checking for updates...',
        'update_available_title': 'Update Available',
        'update_available_msg': 'A new version is available!\n\nCurrent: v{current}\nLatest: v{latest}\n\nWould you like to update?',
        'update_now_btn': 'Update Now',
        'update_open_releases': 'Open Releases Page',
        'update_later_btn': 'Later',
        'update_up_to_date_title': 'Up to Date',
        'update_up_to_date_msg': 'You are running the latest version (v{version}).',
        'update_error_title': 'Update Error',
        'update_error_msg': 'Failed to check for updates:\n{error}',
        'update_downloading': 'Downloading update...',
        'update_complete_title': 'Update Complete',
        'update_complete_msg': 'Update downloaded successfully!\n\nPlease restart the application to apply the update.',
        'update_failed_title': 'Update Failed',
        'update_failed_msg': 'Failed to download update:\n{error}',

        # yt-dlp updates
        'ytdlp_update_btn': 'Update yt-dlp',
        'ytdlp_checking': 'Checking yt-dlp version...',
        'ytdlp_current_version': 'Current yt-dlp: {version}',
        'ytdlp_update_available_title': 'yt-dlp Update Available',
        'ytdlp_update_available_msg': 'A new version of yt-dlp is available!\n\nCurrent: {current}\nLatest: {latest}\n\nThis may fix download issues.\nUpdate now?',
        'ytdlp_up_to_date_title': 'yt-dlp Up to Date',
        'ytdlp_up_to_date_msg': 'yt-dlp is already at the latest version ({version}).',
        'ytdlp_updating': 'Updating yt-dlp...',
        'ytdlp_update_success_title': 'yt-dlp Updated',
        'ytdlp_update_success_msg': 'yt-dlp has been updated to version {version}.',
        'ytdlp_update_failed_title': 'yt-dlp Update Failed',
        'ytdlp_update_failed_msg': 'Failed to update yt-dlp:\n{error}',
        'ytdlp_update_not_supported_title': 'Update Not Supported',
        'ytdlp_update_not_supported_msg': 'Cannot auto-update yt-dlp in this mode.\n\nPlease update yt-dlp manually or download the latest app release.',
        'ytdlp_check_failed_title': 'Check Failed',
        'ytdlp_check_failed_msg': 'Failed to check yt-dlp version:\n{error}',
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
        'checkbox_keep_below_10mb': 'Video unter 10MB halten',
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
        'label_full_playlist': 'Vollständige Playlist herunterladen (alle Videos bei Playlist-Link)',

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
        'status_two_pass_1': 'Kodierung Durchgang 1/2 (Analyse)...',
        'status_two_pass_1_progress': 'Kodierung Durchgang 1/2... {progress}%',
        'status_two_pass_2': 'Kodierung Durchgang 2/2...',
        'status_two_pass_2_progress': 'Kodierung Durchgang 2/2... {progress}%',
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
        'info_playlist_params_stripped': 'Playlist-Parameter entfernt - Einzelvideo wird heruntergeladen',

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

        # Clipboard and download status messages
        'status_clipboard_downloading': 'Herunterladen: {url}...',
        'status_clipboard_completed_total': 'Abgeschlossen: {completed}/{total} Videos',
        'status_downloading_detailed': 'Herunterladen... {progress}%',
        'status_downloading_with_speed': 'Herunterladen... {progress}% bei {speed}',
        'status_downloading_full': 'Herunterladen... {progress}% bei {speed} | ETA: {eta}',

        # Additional error messages
        'error_permission_denied': 'Zugriff verweigert. Überprüfen Sie die Schreibrechte für den Download-Ordner.',
        'error_os_error': 'OS-Fehler: {error}',
        'error_generic': 'Fehler: {error}',

        # Update feature
        'update_check_btn': 'Nach Updates suchen',
        'update_auto_check': 'Beim Start nach Updates suchen',
        'update_checking': 'Suche nach Updates...',
        'update_available_title': 'Update verfügbar',
        'update_available_msg': 'Eine neue Version ist verfügbar!\n\nAktuell: v{current}\nNeueste: v{latest}\n\nMöchten Sie aktualisieren?',
        'update_now_btn': 'Jetzt aktualisieren',
        'update_open_releases': 'Releases-Seite öffnen',
        'update_later_btn': 'Später',
        'update_up_to_date_title': 'Aktuell',
        'update_up_to_date_msg': 'Sie verwenden die neueste Version (v{version}).',
        'update_error_title': 'Update-Fehler',
        'update_error_msg': 'Fehler beim Suchen nach Updates:\n{error}',
        'update_downloading': 'Update wird heruntergeladen...',
        'update_complete_title': 'Update abgeschlossen',
        'update_complete_msg': 'Update erfolgreich heruntergeladen!\n\nBitte starten Sie die Anwendung neu, um das Update anzuwenden.',
        'update_failed_title': 'Update fehlgeschlagen',
        'update_failed_msg': 'Update konnte nicht heruntergeladen werden:\n{error}',

        # yt-dlp updates
        'ytdlp_update_btn': 'yt-dlp aktualisieren',
        'ytdlp_checking': 'Überprüfe yt-dlp Version...',
        'ytdlp_current_version': 'Aktuelles yt-dlp: {version}',
        'ytdlp_update_available_title': 'yt-dlp Update verfügbar',
        'ytdlp_update_available_msg': 'Eine neue Version von yt-dlp ist verfügbar!\n\nAktuell: {current}\nNeueste: {latest}\n\nDies könnte Download-Probleme beheben.\nJetzt aktualisieren?',
        'ytdlp_up_to_date_title': 'yt-dlp aktuell',
        'ytdlp_up_to_date_msg': 'yt-dlp ist bereits auf der neuesten Version ({version}).',
        'ytdlp_updating': 'Aktualisiere yt-dlp...',
        'ytdlp_update_success_title': 'yt-dlp aktualisiert',
        'ytdlp_update_success_msg': 'yt-dlp wurde auf Version {version} aktualisiert.',
        'ytdlp_update_failed_title': 'yt-dlp Update fehlgeschlagen',
        'ytdlp_update_failed_msg': 'yt-dlp konnte nicht aktualisiert werden:\n{error}',
        'ytdlp_update_not_supported_title': 'Update nicht unterstützt',
        'ytdlp_update_not_supported_msg': 'yt-dlp kann in diesem Modus nicht automatisch aktualisiert werden.\n\nBitte aktualisieren Sie yt-dlp manuell oder laden Sie die neueste App-Version herunter.',
        'ytdlp_check_failed_title': 'Überprüfung fehlgeschlagen',
        'ytdlp_check_failed_msg': 'yt-dlp Version konnte nicht überprüft werden:\n{error}',
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
        'checkbox_keep_below_10mb': 'Utrzymaj wideo poniżej 10MB',
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
        'label_full_playlist': 'Pełne pobieranie playlisty (pobierz wszystkie filmy z linku playlisty)',

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
        'status_two_pass_1': 'Kodowanie przebieg 1/2 (analiza)...',
        'status_two_pass_1_progress': 'Kodowanie przebieg 1/2... {progress}%',
        'status_two_pass_2': 'Kodowanie przebieg 2/2...',
        'status_two_pass_2_progress': 'Kodowanie przebieg 2/2... {progress}%',
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
        'info_playlist_params_stripped': 'Parametry playlisty usunięte - pobieranie pojedynczego wideo',

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

        # Clipboard and download status messages
        'status_clipboard_downloading': 'Pobieranie: {url}...',
        'status_clipboard_completed_total': 'Ukończono: {completed}/{total} filmów',
        'status_downloading_detailed': 'Pobieranie... {progress}%',
        'status_downloading_with_speed': 'Pobieranie... {progress}% przy {speed}',
        'status_downloading_full': 'Pobieranie... {progress}% przy {speed} | ETA: {eta}',

        # Additional error messages
        'error_permission_denied': 'Dostęp zabroniony. Sprawdź uprawnienia zapisu dla folderu pobierania.',
        'error_os_error': 'Błąd systemu: {error}',
        'error_generic': 'Błąd: {error}',

        # Update feature
        'update_check_btn': 'Sprawdź aktualizacje',
        'update_auto_check': 'Sprawdzaj aktualizacje przy uruchomieniu',
        'update_checking': 'Sprawdzanie aktualizacji...',
        'update_available_title': 'Dostępna aktualizacja',
        'update_available_msg': 'Dostępna jest nowa wersja!\n\nObecna: v{current}\nNajnowsza: v{latest}\n\nCzy chcesz zaktualizować?',
        'update_now_btn': 'Aktualizuj teraz',
        'update_open_releases': 'Otwórz stronę wydań',
        'update_later_btn': 'Później',
        'update_up_to_date_title': 'Aktualne',
        'update_up_to_date_msg': 'Używasz najnowszej wersji (v{version}).',
        'update_error_title': 'Błąd aktualizacji',
        'update_error_msg': 'Nie udało się sprawdzić aktualizacji:\n{error}',
        'update_downloading': 'Pobieranie aktualizacji...',
        'update_complete_title': 'Aktualizacja zakończona',
        'update_complete_msg': 'Aktualizacja została pobrana pomyślnie!\n\nUruchom ponownie aplikację, aby zastosować aktualizację.',
        'update_failed_title': 'Aktualizacja nie powiodła się',
        'update_failed_msg': 'Nie udało się pobrać aktualizacji:\n{error}',

        # yt-dlp updates
        'ytdlp_update_btn': 'Aktualizuj yt-dlp',
        'ytdlp_checking': 'Sprawdzanie wersji yt-dlp...',
        'ytdlp_current_version': 'Obecny yt-dlp: {version}',
        'ytdlp_update_available_title': 'Dostępna aktualizacja yt-dlp',
        'ytdlp_update_available_msg': 'Dostępna jest nowa wersja yt-dlp!\n\nObecna: {current}\nNajnowsza: {latest}\n\nTo może naprawić problemy z pobieraniem.\nZaktualizować teraz?',
        'ytdlp_up_to_date_title': 'yt-dlp aktualny',
        'ytdlp_up_to_date_msg': 'yt-dlp jest już w najnowszej wersji ({version}).',
        'ytdlp_updating': 'Aktualizowanie yt-dlp...',
        'ytdlp_update_success_title': 'yt-dlp zaktualizowany',
        'ytdlp_update_success_msg': 'yt-dlp został zaktualizowany do wersji {version}.',
        'ytdlp_update_failed_title': 'Aktualizacja yt-dlp nie powiodła się',
        'ytdlp_update_failed_msg': 'Nie udało się zaktualizować yt-dlp:\n{error}',
        'ytdlp_update_not_supported_title': 'Aktualizacja nieobsługiwana',
        'ytdlp_update_not_supported_msg': 'Nie można automatycznie zaktualizować yt-dlp w tym trybie.\n\nZaktualizuj yt-dlp ręcznie lub pobierz najnowszą wersję aplikacji.',
        'ytdlp_check_failed_title': 'Sprawdzenie nie powiodło się',
        'ytdlp_check_failed_msg': 'Nie udało się sprawdzić wersji yt-dlp:\n{error}',
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


def set_language(lang_code):
    """Set the current language.
    
    Args:
        lang_code: Language code ('en', 'de', or 'pl')
    """
    global CURRENT_LANGUAGE
    if lang_code in TRANSLATIONS:
        CURRENT_LANGUAGE = lang_code


def get_language():
    """Get the current language code."""
    return CURRENT_LANGUAGE


def get_available_languages():
    """Get list of available language codes."""
    return list(TRANSLATIONS.keys())
