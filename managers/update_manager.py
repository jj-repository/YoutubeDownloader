"""UpdateManager — app self-update and yt-dlp update logic.

Extracted from YouTubeDownloader (downloader_pyqt6.py).
All GUI operations are dispatched via signals to the main window thread.
"""

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QDialog, QLabel, QProgressBar, QVBoxLayout

from constants import (
    APP_VERSION,
    GITHUB_API_LATEST,
    GITHUB_RAW_URL,
    GITHUB_RELEASES_URL,
    GITHUB_REPO,
)
from managers.utils import _subprocess_kwargs

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"^v?\d+\.\d+(\.\d+)?$")


class UpdateManager(QObject):
    """Handles app self-update and yt-dlp update logic."""

    sig_show_update_dialog = pyqtSignal(str, object)  # latest_version, release_data
    sig_show_ytdlp_update = pyqtSignal(str, str)  # current_version, latest_version
    sig_show_messagebox = pyqtSignal(str, str, str)  # type, title, message
    sig_update_status = pyqtSignal(str, str)  # message, color
    sig_run_on_gui = pyqtSignal(object)  # callable for thread-safe GUI updates
    sig_request_close = pyqtSignal()

    def __init__(self, ytdlp_path: str, thread_pool: ThreadPoolExecutor, parent=None):
        super().__init__(parent)
        self.ytdlp_path = ytdlp_path
        self.thread_pool = thread_pool
        self._updating = False
        self._sha256sums_cache = {}

    @staticmethod
    def _make_progress_helpers():
        """Create progress dialog state and GUI-thread helpers.

        Returns (progress_state, create_fn, update_fn, close_fn) where:
        - progress_state: dict with dialog/label/bar refs
        - create_fn: call via sig_run_on_gui to show dialog
        - update_fn(text, pct): update label text and bar value
        - close_fn: call via sig_run_on_gui to close dialog
        """
        state = {"dialog": None, "label": None, "bar": None}

        def _create():
            dlg = QDialog()
            dlg.setWindowTitle("Downloading Update")
            dlg.setFixedSize(350, 100)
            dlg.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
            dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            dlg.setModal(True)
            layout = QVBoxLayout(dlg)
            lbl = QLabel("Downloading update...")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lbl)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            layout.addWidget(bar)
            state["dialog"] = dlg
            state["label"] = lbl
            state["bar"] = bar
            dlg.show()

        def _update(text, pct):
            if state["label"]:
                state["label"].setText(text)
            if state["bar"]:
                state["bar"].setValue(pct)

        def _close():
            if state["dialog"]:
                state["dialog"].close()
                state["dialog"] = None

        return state, _create, _update, _close

    @staticmethod
    def _validate_tag_name(tag_name: str) -> bool:
        """Validate release tag format to prevent URL manipulation."""
        return bool(_TAG_RE.match(tag_name))

    @staticmethod
    def _validate_download_url(url: str) -> bool:
        """Verify download URL points to our GitHub repo."""
        return url.startswith(f"https://github.com/{GITHUB_REPO}/")

    @staticmethod
    def cleanup_old_updates():
        """Remove leftover files from previous self-updates."""
        try:
            if getattr(sys, "frozen", False):
                exe_dir = Path(sys.executable).parent
                for pattern in ("*.old", "_update_*.bat", "_update_*.sh"):
                    for stale in exe_dir.glob(pattern):
                        try:
                            stale.unlink()
                            logger.info(f"Cleaned up old update file: {stale}")
                        except OSError:
                            pass
        except Exception as e:
            logger.error(f"Error cleaning old update files: {e}")

    # ------------------------------------------------------------------
    #  App update
    # ------------------------------------------------------------------

    def _check_for_updates(self, silent=True):
        """Check GitHub for new app version and yt-dlp updates.

        Args:
            silent: If True, don't show dialog when up-to-date or on error
        """

        self._sha256sums_cache.clear()
        ytdlp_update_available = False
        ytdlp_current = None
        ytdlp_latest = None

        try:
            logger.info("Checking for updates...")
            if not silent:
                self.sig_update_status.emit("Checking for updates...", "blue")

            # Check app update from GitHub
            try:
                request = urllib.request.Request(
                    GITHUB_API_LATEST,
                    headers={"User-Agent": f"YoutubeDownloader/{APP_VERSION}"},
                )
                with urllib.request.urlopen(request, timeout=10) as response:
                    data = json.loads(response.read().decode())

                latest_version = data.get("tag_name", "").lstrip("v")

                if latest_version and self._version_newer(latest_version, APP_VERSION):
                    logger.info(f"App update available: {APP_VERSION} -> {latest_version}")
                    self.sig_show_update_dialog.emit(latest_version, data)
                    return
                else:
                    logger.info(f"App is up to date: {APP_VERSION}")

            except Exception as e:
                logger.error(f"Error checking app updates: {e}")

            # Check yt-dlp update (PyPI for source, GitHub releases for bundled)
            try:
                ytdlp_current = self._get_ytdlp_version()
                if ytdlp_current:
                    request = urllib.request.Request(
                        "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest",
                        headers={"User-Agent": f"YoutubeDownloader/{APP_VERSION}"},
                    )
                    with urllib.request.urlopen(request, timeout=10) as response:
                        release_data = json.loads(response.read().decode())

                    ytdlp_latest = release_data.get("tag_name", "").lstrip("v")

                    if ytdlp_latest:
                        current_parsed = self._parse_ytdlp_version(ytdlp_current)
                        latest_parsed = self._parse_ytdlp_version(ytdlp_latest)

                        if latest_parsed > current_parsed:
                            logger.info(
                                f"yt-dlp update available: {ytdlp_current} -> {ytdlp_latest}"
                            )
                            ytdlp_update_available = True
                        else:
                            logger.info(f"yt-dlp is up to date: {ytdlp_current}")

            except Exception as e:
                logger.error(f"Error checking yt-dlp updates: {e}")

            # Show appropriate dialog based on what was found
            if ytdlp_update_available:
                # Must create dialog on GUI thread; use a signal
                self.sig_show_ytdlp_update.emit(ytdlp_current, ytdlp_latest)
            elif not silent:
                self.sig_show_messagebox.emit(
                    "info",
                    "Up to Date",
                    f"You are running the latest version (v{APP_VERSION}).",
                )

        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            if not silent:
                self.sig_show_messagebox.emit(
                    "error", "Update Error", f"Failed to check for updates:\n{e}"
                )

    @staticmethod
    def _version_newer(latest, current):
        """Compare version strings to check if latest is newer than current.

        Uses integer tuple comparison (e.g. (5, 18) > (5, 9)).
        Requires monotonically increasing minor version numbers —
        never release 5.2 after 5.18 (use 5.19+ instead).

        Args:
            latest: Latest version string (e.g., '5.18')
            current: Current version string (e.g., '5.17')

        Returns:
            bool: True if latest is newer than current
        """
        try:
            latest_parts = tuple(map(int, latest.split(".")))
            current_parts = tuple(map(int, current.split(".")))
            return latest_parts > current_parts
        except (ValueError, AttributeError):
            return False

    @staticmethod
    def _sha256_file(filepath) -> str:
        """Compute SHA-256 of a file using chunked reads to limit memory."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(256 * 1024), b""):
                h.update(chunk)
        return h.hexdigest().lower()

    @staticmethod
    def _compute_git_blob_sha(content):
        """Compute the git blob SHA1 hash for content (same as git hash-object)."""
        header = f"blob {len(content)}\0".encode()
        return hashlib.sha1(header + content).hexdigest()  # noqa: S324 — git blob hash, not security

    def _verify_file_against_github(self, tag_name, filename, content, headers, release_data=None):
        """Verify downloaded file against GitHub's git tree SHA and SHA-256.

        1. Git blob SHA-1 via GitHub Contents API (fast, but SHA-1 is weak).
        2. SHA-256 via release SHA256SUMS (strong, mandatory).
        """

        # Check 1: git blob SHA-1 (GitHub Contents API)
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}?ref={tag_name}"
        request = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            file_info = json.loads(response.read().decode())

        expected_sha = file_info.get("sha", "")
        actual_sha = self._compute_git_blob_sha(content)

        if actual_sha != expected_sha:
            raise RuntimeError(
                f"Integrity check failed for {filename}!\n"
                f"Expected SHA: {expected_sha[:16]}...\n"
                f"Got SHA: {actual_sha[:16]}...\n"
                f"The file may have been tampered with."
            )

        # Check 2: SHA-256 from release SHA256SUMS (mandatory)
        if not release_data:
            raise RuntimeError(f"Cannot verify {filename}: release_data required for SHA-256 check")

        actual_sha256 = hashlib.sha256(content).hexdigest().lower()
        expected_sha256 = self._get_expected_sha256(release_data, filename, headers)
        if expected_sha256:
            if actual_sha256 != expected_sha256:
                raise RuntimeError(
                    f"SHA-256 verification failed for {filename}!\n"
                    f"Expected: {expected_sha256[:16]}...\n"
                    f"Got: {actual_sha256[:16]}..."
                )
            logger.info(
                f"Integrity verified for {filename}: sha256={actual_sha256[:16]}... (enforced)"
            )
        else:
            raise RuntimeError(
                f"SHA256SUMS missing for {filename} — cannot verify integrity. Aborting update."
            )

    def _apply_update(self, release_data):
        """Download and apply update, then restart the application.

        Routes to the appropriate strategy based on how the app is running:
        - Source (.py): replace modules, then restart via Python interpreter
        - Frozen portable (onefile): download new exe, rename-dance, restart
        - Frozen installed (onedir): direct user to GitHub releases page
        """
        self._updating = True
        if getattr(sys, "frozen", False):
            if self._is_onedir_frozen():
                # Installed version -- can't self-update, point to installer
                self.sig_show_messagebox.emit(
                    "info",
                    "Update Complete",
                    "Your installed version cannot self-update.\n\n"
                    "The releases page will open so you can download the latest installer.",
                )
                self.sig_run_on_gui.emit(lambda: __import__("webbrowser").open(GITHUB_RELEASES_URL))
            else:
                self._apply_update_frozen(release_data)
        else:
            self._apply_update_source(release_data)

    def _apply_update_source(self, release_data):
        """Download, verify, and replace .py source files, then auto-restart."""

        _, _create_progress_dialog, _update_progress_dialog, _close_progress_dialog = (
            self._make_progress_helpers()
        )

        try:
            self.sig_update_status.emit("Downloading update...", "blue")
            self.sig_run_on_gui.emit(_create_progress_dialog)

            tag_name = release_data.get("tag_name", "")
            if not self._validate_tag_name(tag_name):
                raise RuntimeError(f"Invalid release tag format: {tag_name!r}")
            headers = {"User-Agent": f"YoutubeDownloader/{APP_VERSION}"}
            current_script = Path(__file__).resolve()
            script_dir = current_script.parent.parent  # managers/ -> project root

            modules = [
                "downloader_pyqt6.py",
                "constants.py",
                "managers/__init__.py",
                "managers/clipboard_manager.py",
                "managers/download_manager.py",
                "managers/encoding.py",
                "managers/trimming_manager.py",
                "managers/update_manager.py",
                "managers/upload_manager.py",
                "managers/utils.py",
            ]
            downloaded = {}

            # Download and verify all modules before replacing any
            for i, module_name in enumerate(modules):
                download_url = f"{GITHUB_RAW_URL}/{tag_name}/{module_name}"
                logger.info(f"Downloading: {download_url}")
                request = urllib.request.Request(download_url, headers=headers)

                with urllib.request.urlopen(request, timeout=60) as response:
                    total = int(response.headers.get("Content-Length", 0))
                    chunks = []
                    received = 0
                    while True:
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            break
                        chunks.append(chunk)
                        received += len(chunk)
                        if total > 0:
                            pct = int(received / total * 100)
                            text = f"Downloading {module_name} ({i + 1}/{len(modules)})... {pct}%"
                        else:
                            pct = 0
                            text = f"Downloading {module_name} ({i + 1}/{len(modules)})..."
                        self.sig_run_on_gui.emit(
                            lambda t=text, p=pct: _update_progress_dialog(t, p)
                        )
                    content = b"".join(chunks)

                self._verify_file_against_github(
                    tag_name, module_name, content, headers, release_data
                )

                try:
                    compile(content, module_name, "exec")
                except SyntaxError as e:
                    raise RuntimeError(f"{module_name} has syntax errors: {e}") from e

                downloaded[module_name] = content

            self.sig_run_on_gui.emit(_close_progress_dialog)

            # All verified -- backup and replace
            for module_name, content in downloaded.items():
                module_path = script_dir / module_name
                backup_path = module_path.with_suffix(".py.backup")
                if module_path.exists():
                    shutil.copy2(module_path, backup_path)
                    logger.info(f"Created backup: {backup_path}")

                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(
                        mode="wb", suffix=".py", delete=False, dir=str(module_path.parent)
                    ) as tmp_file:
                        tmp_file.write(content)
                        tmp_path = tmp_file.name
                    os.replace(tmp_path, str(module_path))
                    logger.info(f"Updated: {module_path}")
                except Exception:
                    if tmp_path and os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    raise

            # Clean up backup files after successful replacement
            for module_name in downloaded:
                backup_path = (script_dir / module_name).with_suffix(".py.backup")
                backup_path.unlink(missing_ok=True)

            # Auto-restart: spawn new process, then shut down
            self.sig_update_status.emit("Update complete — restarting...", "green")
            logger.info("Restarting after source update...")

            def _do_restart():
                script = str(Path(__file__).resolve().parent.parent / "downloader_pyqt6.py")
                subprocess.Popen([sys.executable, script])
                self._updating = False
                self.sig_request_close.emit()

            self.sig_run_on_gui.emit(lambda: QTimer.singleShot(500, _do_restart))

        except Exception as e:
            self._updating = False
            self.sig_run_on_gui.emit(_close_progress_dialog)
            # Rollback any modules already replaced from backups (atomic)
            for module_name in downloaded:
                backup_path = (script_dir / module_name).with_suffix(".py.backup")
                module_path = script_dir / module_name
                if backup_path.exists():
                    try:
                        tmp_rb = module_path.with_suffix(".py.rollback")
                        shutil.copy2(backup_path, tmp_rb)
                        os.replace(str(tmp_rb), str(module_path))
                        logger.info(f"Rolled back: {module_path}")
                    except Exception as rb_err:
                        logger.error(f"Rollback failed for {module_path}: {rb_err}")
            logger.error(f"Error applying update: {e}")
            self.sig_show_messagebox.emit(
                "error", "Update Failed", f"Failed to download update:\n{e}"
            )

    def _get_expected_sha256(self, release_data, asset_name, headers):
        """Fetch SHA256SUMS from release and return expected hash for asset_name.

        Caches the SHA256SUMS content per tag to avoid redundant HTTP requests
        when verifying multiple source modules in a single update.
        """

        tag_name = release_data.get("tag_name", "")
        if not self._validate_tag_name(tag_name):
            raise RuntimeError(f"Invalid release tag format: {tag_name!r}")

        if tag_name not in self._sha256sums_cache:
            sha_url = f"https://github.com/{GITHUB_REPO}/releases/download/{tag_name}/SHA256SUMS"
            try:
                req = urllib.request.Request(sha_url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as response:
                    self._sha256sums_cache[tag_name] = response.read().decode("utf-8")
            except Exception as e:
                logger.warning(f"Could not fetch SHA256SUMS: {e}")
                return None

        sha256sums = self._sha256sums_cache.get(tag_name, "")
        for line in sha256sums.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] == asset_name:
                h = parts[0].lower()
                if re.fullmatch(r"[0-9a-f]{64}", h):
                    return h
                logger.warning(f"Invalid SHA256 hash format in SHA256SUMS: {h!r}")
                return None
        return None

    def _apply_update_frozen(self, release_data):
        """Self-update a frozen portable exe via download + rename-and-replace."""

        try:
            self.sig_update_status.emit("Downloading update...", "blue")

            tag_name = release_data.get("tag_name", "")
            if not self._validate_tag_name(tag_name):
                raise RuntimeError(f"Invalid release tag format: {tag_name!r}")

            download_url = self._get_update_asset_url(release_data)
            if not download_url:
                raise RuntimeError("Could not find a download for this platform in the release.")

            headers = {"User-Agent": f"YoutubeDownloader/{APP_VERSION}"}
            exe_path = Path(sys.executable).resolve()

            if sys.platform == "win32":
                self._apply_update_frozen_windows(download_url, headers, exe_path, release_data)
            else:
                self._apply_update_frozen_linux(download_url, headers, exe_path, release_data)

        except Exception as e:
            self._updating = False
            logger.error(f"Error applying frozen update: {e}")
            self.sig_show_messagebox.emit(
                "error", "Update Failed", f"Failed to download update:\n{e}"
            )

    def _apply_update_frozen_windows(self, download_url, headers, exe_path, release_data=None):
        """Windows portable exe update: rename-dance with .bat trampoline fallback."""

        new_exe = exe_path.with_suffix(".exe.new")
        old_exe = exe_path.with_name(exe_path.stem + ".old")

        logger.info(f"Downloading update: {download_url}")

        _, _create_dlg, _update_dlg, _close_dlg = self._make_progress_helpers()
        self.sig_run_on_gui.emit(_create_dlg)

        request = urllib.request.Request(download_url, headers=headers)
        with urllib.request.urlopen(request, timeout=300) as response:
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            with open(new_exe, "wb") as f:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = int(downloaded / total * 100)
                        mb = downloaded / (1024 * 1024)
                        total_mb = total / (1024 * 1024)
                        text = f"Downloading update... {mb:.1f}/{total_mb:.1f} MB ({pct}%)"
                        self.sig_run_on_gui.emit(
                            lambda t=text, p=pct: _update_dlg(t, p),
                        )

        self.sig_run_on_gui.emit(_close_dlg)

        if downloaded < 1024:
            new_exe.unlink(missing_ok=True)
            raise RuntimeError("Downloaded file is too small — likely corrupted.")

        logger.info(f"Downloaded new exe: {new_exe} ({downloaded:,} bytes)")

        # Verify SHA-256 (mandatory — abort if checksum unavailable)
        expected_hash = None
        if release_data:
            expected_hash = self._get_expected_sha256(release_data, "YTDownloader.exe", headers)
        if not expected_hash:
            new_exe.unlink(missing_ok=True)
            raise RuntimeError(
                "SHA-256 verification unavailable — SHA256SUMS missing from release. "
                "Update aborted for security."
            )
        actual_hash = self._sha256_file(new_exe)
        if actual_hash != expected_hash:
            new_exe.unlink(missing_ok=True)
            raise RuntimeError(
                f"SHA-256 verification failed for YTDownloader.exe!\n"
                f"Expected: {expected_hash[:16]}...\n"
                f"Got: {actual_hash[:16]}..."
            )
        logger.info("SHA-256 verification passed for YTDownloader.exe")

        # Rename dance: running.exe -> .old, .new -> running.exe
        try:
            if old_exe.exists():
                old_exe.unlink()
            exe_path.rename(old_exe)
            logger.info(f"Renamed running exe aside: {exe_path} -> {old_exe}")

            try:
                new_exe.rename(exe_path)
                logger.info(f"Moved new exe into place: {new_exe} -> {exe_path}")
            except Exception:
                # Restore if moving new exe into place fails
                if old_exe.exists() and not exe_path.exists():
                    old_exe.rename(exe_path)
                raise

            # Success -- tell user to reopen
            logger.info(f"Update applied: {exe_path}")
            self.sig_update_status.emit("Update installed!", "green")
            self._updating = False
            self.sig_show_messagebox.emit(
                "info",
                "Update Installed",
                "Updated to the latest version.\n\nPlease close and reopen the app to use it.",
            )

        except OSError as rename_err:
            # Rename failed -- use bat to move file after we exit
            logger.warning(f"Rename failed ({rename_err}), falling back to bat trampoline")
            bat_fd = tempfile.NamedTemporaryFile(
                suffix=".bat", prefix="_update_", dir=exe_path.parent, delete=False
            )
            bat_path = Path(bat_fd.name)
            bat_fd.close()
            pid = os.getpid()
            # Escape batch-special characters in paths to prevent injection
            _bad_batch_chars = set('"&|^<>%')
            for p in (new_exe, exe_path):
                if _bad_batch_chars & set(str(p)):
                    raise RuntimeError(  # noqa: B904 — not re-raising, new error
                        f"Update path contains unsafe batch characters: {p}"
                    )
            bat_content = (
                "@echo off\r\n"
                f":wait\r\n"
                f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul && '
                f"(timeout /t 1 /nobreak >nul & goto wait)\r\n"
                "timeout /t 3 /nobreak >nul\r\n"
                f'move /y "{new_exe}" "{exe_path}"\r\n'
                'del "%~f0"\r\n'
            )
            bat_path.write_text(bat_content)
            logger.info(f"Wrote update trampoline: {bat_path}")
            subprocess.Popen(
                ["cmd", "/c", str(bat_path)],
                creationflags=subprocess.CREATE_NO_WINDOW,
                close_fds=True,
            )
            self._updating = False
            self.sig_show_messagebox.emit(
                "info",
                "Update Installed",
                "Updated to the latest version.\n\nPlease close and reopen the app to use it.",
            )

    def _apply_update_frozen_linux(self, download_url, headers, exe_path, release_data=None):
        """Linux portable binary update: download tar.gz, extract, replace in place."""

        logger.info(f"Downloading update: {download_url}")

        _, _create_dlg, _update_dlg, _close_dlg = self._make_progress_helpers()
        self.sig_run_on_gui.emit(_create_dlg)

        tar_tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=".tar.gz", dir=str(exe_path.parent)
        )
        tar_tmp_path = tar_tmp.name
        tar_tmp.close()

        request = urllib.request.Request(download_url, headers=headers)
        with urllib.request.urlopen(request, timeout=300) as response:
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            with open(tar_tmp_path, "wb") as f:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = int(downloaded / total * 100)
                        mb = downloaded / (1024 * 1024)
                        total_mb = total / (1024 * 1024)
                        text = f"Downloading update... {mb:.1f}/{total_mb:.1f} MB ({pct}%)"
                        self.sig_run_on_gui.emit(
                            lambda t=text, p=pct: _update_dlg(t, p),
                        )

        self.sig_run_on_gui.emit(_close_dlg)

        if downloaded < 1024:
            os.unlink(tar_tmp_path)
            raise RuntimeError("Downloaded file is too small — likely corrupted.")

        logger.info(f"Downloaded tar.gz ({downloaded:,} bytes), extracting...")

        # Verify SHA-256 (mandatory — abort if checksum unavailable)
        expected_hash = None
        if release_data:
            expected_hash = self._get_expected_sha256(
                release_data, "YTDownloader-Linux.tar.gz", headers
            )
        if not expected_hash:
            os.unlink(tar_tmp_path)
            raise RuntimeError(
                "SHA-256 verification unavailable — SHA256SUMS missing from release. "
                "Update aborted for security."
            )
        actual_hash = self._sha256_file(tar_tmp_path)
        if actual_hash != expected_hash:
            os.unlink(tar_tmp_path)
            raise RuntimeError(
                f"SHA-256 verification failed for YTDownloader-Linux.tar.gz!\n"
                f"Expected: {expected_hash[:16]}...\n"
                f"Got: {actual_hash[:16]}..."
            )
        logger.info("SHA-256 verification passed for Linux tar.gz")

        tmp_path = None
        try:
            with tarfile.open(tar_tmp_path, mode="r:gz") as tar:
                # Find the binary inside the archive
                members = tar.getmembers()
                if len(members) > 100:
                    raise RuntimeError(f"Archive has too many entries ({len(members)}), aborting.")
                binary_member = None
                for member in members:
                    if ".." in member.name or member.name.startswith("/"):
                        continue
                    if member.issym() or member.islnk():
                        continue
                    if member.isfile() and "YTDownloader" in member.name:
                        binary_member = member
                        break

                if not binary_member:
                    raise RuntimeError("Could not find YTDownloader binary in archive.")

                # Extract binary via streaming (avoids loading entire binary into memory)
                f = tar.extractfile(binary_member)
                if not f:
                    raise RuntimeError("Could not read binary from archive.")
                with tempfile.NamedTemporaryFile(delete=False, dir=str(exe_path.parent)) as tmp:
                    shutil.copyfileobj(f, tmp)
                    tmp_path = Path(tmp.name)

            if tmp_path.stat().st_size < 1024:
                raise RuntimeError("Extracted binary is too small — archive may be corrupt")
            if exe_path.is_symlink():
                raise RuntimeError(f"Refusing to overwrite symlink: {exe_path}")
            os.chmod(str(tmp_path), 0o755)  # noqa: S103 — executable needs to be runnable
            os.replace(str(tmp_path), str(exe_path))
            tmp_path = None  # successfully replaced, don't clean up
            logger.info(f"Replaced binary: {exe_path}")
        finally:
            if os.path.exists(tar_tmp_path):
                os.unlink(tar_tmp_path)
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

        # Spawn new binary and shut down
        self.sig_update_status.emit("Update complete — restarting...", "green")

        def _do_restart():
            logger.info(f"Launching updated binary: {exe_path}")
            subprocess.Popen([str(exe_path)])
            self._updating = False
            self.sig_request_close.emit()

        self.sig_run_on_gui.emit(lambda: QTimer.singleShot(500, _do_restart))

    def _is_onedir_frozen(self):
        """Check if running as PyInstaller --onedir (installed) vs --onefile (portable).

        In onedir mode, sys._MEIPASS points to the app directory (same as exe parent).
        In onefile mode, sys._MEIPASS is a temp extraction directory.
        """
        if not getattr(sys, "frozen", False):
            return False
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        return meipass == Path(sys.executable).parent

    def _get_update_asset_url(self, release_data):
        """Find the download URL for the right release asset for this platform.

        Returns:
            str or None: The browser_download_url for the matching asset
        """
        if sys.platform == "win32":
            target = "YTDownloader.exe"
        else:
            target = "YTDownloader-Linux.tar.gz"

        for asset in release_data.get("assets", []):
            if asset.get("name") == target:
                url = asset["browser_download_url"]
                if not self._validate_download_url(url):
                    logger.error(f"Rejecting download URL outside our repo: {url}")
                    return None
                return url
        return None

    # ------------------------------------------------------------------
    #  yt-dlp updates
    # ------------------------------------------------------------------

    def _get_ytdlp_version(self):
        """Get the current yt-dlp version.

        Returns:
            str: Version string (e.g., '2025.12.08') or None if failed
        """
        try:
            result = subprocess.run(
                [self.ytdlp_path, "--version"],
                capture_output=True,
                timeout=10,
                **_subprocess_kwargs,
            )
            if result.returncode == 0:
                return result.stdout.decode("utf-8", errors="replace").strip()
        except Exception as e:
            logger.error(f"Error getting yt-dlp version: {e}")
        return None

    def _get_pip_path(self):
        """Get the pip path for the venv.

        Returns:
            str: Path to pip executable or None
        """
        script_dir = Path(__file__).parent.parent  # managers/ -> project root
        if sys.platform == "win32":
            pip_path = script_dir / "venv" / "Scripts" / "pip.exe"
        else:
            pip_path = script_dir / "venv" / "bin" / "pip"

        if pip_path.exists():
            return str(pip_path)

        # Try current Python's pip
        python_bin = Path(sys.executable).parent
        if sys.platform == "win32":
            pip_path = python_bin / "pip.exe"
        else:
            pip_path = python_bin / "pip"

        if pip_path.exists():
            return str(pip_path)

        return None

    def _parse_ytdlp_version(self, version_str):
        """Parse yt-dlp version string into comparable tuple.

        Args:
            version_str: Version string (e.g., '2026.02.04')

        Returns:
            tuple: Version as tuple of integers (e.g., (2026, 2, 4))
        """
        try:
            return tuple(int(part) for part in version_str.split("."))
        except (ValueError, AttributeError):
            return (0,)

    def _apply_ytdlp_update_pip(self, pip_path):
        """Apply yt-dlp update using pip (when running from source)."""
        try:
            logger.info("Updating yt-dlp via pip...")
            self.sig_update_status.emit("Updating yt-dlp...", "blue")

            result = subprocess.run(
                [pip_path, "install", "--upgrade", "yt-dlp"],
                capture_output=True,
                timeout=120,
                **_subprocess_kwargs,
            )

            if result.returncode == 0:
                new_version = self._get_ytdlp_version() or "unknown"
                logger.info(f"yt-dlp updated successfully to {new_version}")

                self.sig_update_status.emit(f"Current yt-dlp: {new_version}", "green")
                self.sig_show_messagebox.emit(
                    "info",
                    "yt-dlp Updated",
                    f"yt-dlp has been updated to version {new_version}.",
                )
            else:
                error_msg = (
                    result.stderr.decode("utf-8", errors="replace").strip()
                    or result.stdout.decode("utf-8", errors="replace").strip()
                )
                raise RuntimeError(error_msg or "pip returned non-zero exit code")

        except subprocess.TimeoutExpired:
            logger.error("yt-dlp update timed out")
            self.sig_show_messagebox.emit(
                "error",
                "yt-dlp Update Failed",
                "Failed to update yt-dlp:\n\nUpdate timed out",
            )
        except Exception as e:
            logger.error(f"Error updating yt-dlp: {e}")
            self.sig_show_messagebox.emit(
                "error", "yt-dlp Update Failed", f"Failed to update yt-dlp:\n\n{e}"
            )

    def _apply_ytdlp_update_binary(self, latest_version):
        """Download latest yt-dlp binary from GitHub releases with SHA256 verification."""

        tmp_path = None
        try:
            logger.info("Downloading latest yt-dlp binary...")
            self.sig_update_status.emit("Updating yt-dlp...", "blue")

            headers = {"User-Agent": f"YoutubeDownloader/{APP_VERSION}"}
            exe_dir = os.path.dirname(sys.executable)

            if sys.platform == "win32":
                binary_name = "yt-dlp.exe"
                download_url = (
                    f"https://github.com/yt-dlp/yt-dlp/releases/latest/download/{binary_name}"
                )
                target_path = os.path.join(exe_dir, binary_name)
            else:
                binary_name = "yt-dlp"
                download_url = (
                    f"https://github.com/yt-dlp/yt-dlp/releases/latest/download/{binary_name}"
                )
                target_path = os.path.join(exe_dir, binary_name)

            # Download SHA256SUMS from yt-dlp releases
            sha256sums_url = (
                "https://github.com/yt-dlp/yt-dlp/releases/latest/download/SHA2-256SUMS"
            )
            sha_request = urllib.request.Request(sha256sums_url, headers=headers)
            with urllib.request.urlopen(sha_request, timeout=30) as response:
                sha256sums = response.read().decode("utf-8")

            # Find expected hash for our binary
            expected_hash = None
            for line in sha256sums.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1] == binary_name:
                    h = parts[0].lower()
                    if re.fullmatch(r"[0-9a-f]{64}", h):
                        expected_hash = h
                    break

            if not expected_hash:
                raise RuntimeError(f"Could not find SHA256 for {binary_name} in SHA2-256SUMS")
            logger.info(f"Expected SHA256 for {binary_name}: {expected_hash[:16]}...")

            # Download the binary
            tmp_fd = tempfile.NamedTemporaryFile(dir=exe_dir, delete=False, suffix=".tmp")
            tmp_path = tmp_fd.name
            tmp_fd.close()

            request = urllib.request.Request(download_url, headers=headers)
            with urllib.request.urlopen(request, timeout=120) as response:
                with open(tmp_path, "wb") as f:
                    shutil.copyfileobj(response, f)

            # Verify SHA256
            actual_hash = self._sha256_file(tmp_path)

            if actual_hash != expected_hash:
                os.remove(tmp_path)
                raise RuntimeError(
                    f"SHA256 verification failed for {binary_name}!\n"
                    f"Expected: {expected_hash[:32]}...\n"
                    f"Got: {actual_hash[:32]}...\n"
                    f"The file may have been tampered with."
                )
            logger.info(f"SHA256 verified for {binary_name}: {actual_hash[:16]}...")

            # Replace the old binary atomically
            if os.path.islink(target_path):
                raise RuntimeError(f"Refusing to overwrite symlink: {target_path}")
            os.replace(tmp_path, target_path)

            # Make executable on Linux
            if sys.platform != "win32":
                os.chmod(target_path, 0o755)  # noqa: S103 — executable needs to be runnable

            # Update the path so the app uses the new binary immediately
            self.ytdlp_path = target_path

            new_version = self._get_ytdlp_version() or latest_version
            logger.info(f"yt-dlp binary updated successfully to {new_version}")

            self.sig_update_status.emit(f"Current yt-dlp: {new_version}", "green")
            self.sig_show_messagebox.emit(
                "info",
                "yt-dlp Updated",
                f"yt-dlp has been updated to version {new_version}.",
            )

        except Exception as e:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            logger.error(f"Error downloading yt-dlp binary: {e}")
            self.sig_show_messagebox.emit(
                "error", "yt-dlp Update Failed", f"Failed to update yt-dlp:\n\n{e}"
            )
