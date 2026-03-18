"""YoutubeDownloader Translations Module

Contains all UI strings (English only).
"""

TRANSLATIONS = {
    'en': {
        # Window
        'window_title': 'YoutubeDownloader',
        'theme_dark_mode': 'Dark Mode',
        'btn_settings': 'Settings',
        'btn_help': 'Help',

        # Tabs
        'tab_trimmer': 'Trimmer',
        'tab_clipboard': 'Clipboard Mode',
        'tab_uploader': 'Uploader',

        # Help tab
        'help_header': 'How to Use YoutubeDownloader',
        'help_github_btn': 'GitHub',
        'help_clipboard_title': 'Clipboard Mode',
        'help_clipboard_text': 'Copy any YouTube URL (Ctrl+C) and it will automatically appear in the detected URLs list. You can download them individually or click "Download All" to batch download. Enable "Auto-download" to start downloading as soon as a URL is detected.',
        'help_trimmer_title': 'Trimmer',
        'help_trimmer_text': 'Paste a YouTube URL and select your desired quality. To trim a video, enable "Enable video trimming", click "Fetch Video Duration", then use the sliders or time fields to set start and end points. Frame previews show exactly what you\'re selecting.',
        'help_uploader_title': 'Uploader',
        'help_uploader_text': 'Upload local video or audio files to Catbox.moe for easy sharing. Click "Add Files" to select files, then "Upload to Catbox.moe" to upload. URLs are automatically copied to your clipboard. You can also enable auto-upload in the Trimmer tab to upload after each download.',
        'help_settings_title': 'Settings',
        'help_settings_text': 'Toggle dark mode, check for updates, and view app info.',

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
        'settings_updates': 'Updates',
        'label_quality': 'Quality:',
        'label_speed_limit': 'Speed limit:',
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
        'status_clipboard_downloading_phase': 'Downloading {phase}{info}... {progress}%',

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
        'update_restarting': 'Update complete — restarting...',
        'update_complete_title': 'Update Complete',
        'update_complete_msg': 'Update downloaded successfully!\n\nThe application will now restart.',
        'update_installer_msg': 'Your installed version cannot self-update.\n\nThe releases page will open so you can download the latest installer.',
        'update_failed_title': 'Update Failed',
        'update_failed_msg': 'Failed to download update:\n{error}',

        # yt-dlp updates
        'ytdlp_current_version': 'Current yt-dlp: {version}',
        'ytdlp_update_available_title': 'yt-dlp Update Available',
        'ytdlp_update_available_msg': 'A new version of yt-dlp is available!\n\nCurrent: {current}\nLatest: {latest}\n\nThis may fix download issues.\nUpdate now?',
        'ytdlp_updating': 'Updating yt-dlp...',
        'ytdlp_update_success_title': 'yt-dlp Updated',
        'ytdlp_update_success_msg': 'yt-dlp has been updated to version {version}.',
        'ytdlp_update_failed_title': 'yt-dlp Update Failed',
        'ytdlp_update_failed_msg': 'Failed to update yt-dlp:\n{error}',
        'ytdlp_update_not_supported_title': 'Update Not Supported',
        'ytdlp_update_not_supported_msg': 'Cannot auto-update yt-dlp in this mode.\n\nPlease update yt-dlp manually or download the latest app release.',
    },
}


def tr(key, **kwargs):
    """Get translated string with optional formatting.

    Args:
        key: Translation key (e.g., 'btn_download')
        **kwargs: Optional format arguments (e.g., progress=50)

    Returns:
        Translated and formatted string
    """
    text = TRANSLATIONS['en'].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text
