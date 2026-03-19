"""
Auto-Update System for Pickfair
Checks GitHub releases for new versions and allows one-click updates.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import uuid
import webbrowser
from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_UPDATE_URL = "https://api.github.com/repos/petiro/Pickfair/releases/latest"


def parse_version(version_str):
    """Parse version string like '3.4.0' into tuple (3, 4, 0)."""
    try:
        version_str = version_str.lstrip("v").strip()
        parts = version_str.split(".")
        return tuple(int(p) for p in parts[:3])
    except Exception:
        return (0, 0, 0)


def compare_versions(current, latest):
    """Compare two version strings. Returns True if latest > current."""
    current_tuple = parse_version(current)
    latest_tuple = parse_version(latest)
    return latest_tuple > current_tuple


def _safe_filename_from_url(download_url, fallback="pickfair_update.bin"):
    """
    Deriva un filename locale sicuro da una URL.
    Non si fida del nome remoto.
    """
    try:
        raw_name = download_url.split("/")[-1].split("?")[0].strip()
    except Exception:
        raw_name = fallback

    if not raw_name:
        raw_name = fallback

    raw_name = os.path.basename(raw_name)

    # consenti solo caratteri sicuri
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", raw_name)

    if not safe or safe in {".", ".."}:
        safe = fallback

    # limita lunghezza
    root, ext = os.path.splitext(safe)
    root = root[:80] if root else "pickfair_update"
    ext = ext[:10]

    return f"{root}{ext}"


def _cmd_safe_path(path):
    """
    Escaping minimo per batch Windows:
    - raddoppia %
    - mantiene il path tra doppi apici
    """
    return str(path).replace("%", "%%")


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_for_updates(current_version, callback=None, update_url=None):
    """
    Check GitHub for new releases.

    Args:
        current_version: Current app version string (e.g., "3.4.0")
        callback: Function to call with result
        update_url: URL to check for updates

    Returns dict with update info or None if no update available.
    """
    check_url = update_url or DEFAULT_UPDATE_URL

    if not check_url:
        if callback:
            callback({"update_available": False, "error": "No update URL configured"})
        return None

    def do_check():
        try:
            req = Request(check_url, headers={"User-Agent": "Pickfair-Updater/1.0"})

            with urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))

            latest_version = data.get("tag_name", "").lstrip("v")

            if compare_versions(current_version, latest_version):
                download_url = None
                expected_sha256 = None

                for asset in data.get("assets", []):
                    name = asset.get("name", "").lower()
                    browser_download_url = asset.get("browser_download_url", "")

                    if name.endswith(".exe") or name.endswith(".zip"):
                        download_url = browser_download_url
                    elif "sha256" in name or name.endswith(".sha256"):
                        expected_sha256 = browser_download_url

                    if download_url:
                        break

                if not download_url:
                    download_url = data.get("html_url", "")

                result = {
                    "update_available": True,
                    "current_version": current_version,
                    "latest_version": latest_version,
                    "download_url": download_url,
                    "release_notes": data.get("body", ""),
                    "release_page": data.get("html_url", ""),
                    "published_at": data.get("published_at", ""),
                    "sha256_url": expected_sha256,
                }

                if callback:
                    callback(result)
                return result

            result = {"update_available": False}
            if callback:
                callback(result)
            return result

        except URLError as e:
            print(f"Update check failed (network): {e}")
            if callback:
                callback({"update_available": False, "error": str(e)})
            return None
        except Exception as e:
            print(f"Update check failed: {e}")
            if callback:
                callback({"update_available": False, "error": str(e)})
            return None

    thread = threading.Thread(target=do_check, daemon=True)
    thread.start()
    return None


def open_download_page(url):
    """Open the download URL in the default browser."""
    webbrowser.open(url)


def download_update(download_url, progress_callback=None):
    """
    Download the update file.

    Args:
        download_url: URL to download from
        progress_callback: Function(bytes_downloaded, total_bytes) for progress

    Returns path to downloaded file or None on failure.
    """
    try:
        req = Request(download_url, headers={"User-Agent": "Pickfair-Updater/1.0"})

        with urlopen(req, timeout=60) as response:
            total_size = int(response.headers.get("content-length", 0))
            filename = _safe_filename_from_url(download_url, fallback="pickfair_update.bin")

            unique_name = f"{uuid.uuid4().hex}_{filename}"
            download_path = os.path.join(tempfile.gettempdir(), unique_name)

            downloaded = 0
            chunk_size = 8192

            with open(download_path, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size)

            return download_path

    except Exception as e:
        print(f"Download failed: {e}")
        return None


def verify_download_hash(downloaded_path, expected_sha256=None):
    """
    Verifica SHA256 se fornito.
    Se expected_sha256 non c'è, ritorna True per compatibilità.
    """
    if not expected_sha256:
        return True

    try:
        actual = _sha256_file(downloaded_path).lower().strip()
        expected = str(expected_sha256).lower().strip()
        return actual == expected
    except Exception:
        return False


def install_update(update_path, current_exe_path=None):
    """
    Install the downloaded update and restart the app.
    For .exe files, replace current exe and restart.
    """
    try:
        update_path = os.path.abspath(update_path)

        if update_path.endswith(".exe") and current_exe_path:
            current_exe_path = os.path.abspath(current_exe_path)
            backup_path = current_exe_path + ".backup"

            safe_update_path = _cmd_safe_path(update_path)
            safe_current_exe_path = _cmd_safe_path(current_exe_path)
            safe_backup_path = _cmd_safe_path(backup_path)

            batch_content = f"""@echo off
setlocal enableextensions
echo Aggiornamento in corso...
echo Attendere la chiusura dell'applicazione...
timeout /t 5 /nobreak > nul

REM Pulisci cartelle temporanee PyInstaller
for /d %%i in ("%TEMP%\\_MEI*") do rd /s /q "%%i" 2>nul

REM Attendi ancora per sicurezza
timeout /t 2 /nobreak > nul

if exist "{safe_backup_path}" del /f /q "{safe_backup_path}"
if exist "{safe_current_exe_path}" move /y "{safe_current_exe_path}" "{safe_backup_path}"
move /y "{safe_update_path}" "{safe_current_exe_path}"

if exist "{safe_current_exe_path}" (
    echo Avvio nuova versione...
    timeout /t 2 /nobreak > nul
    start "" "{safe_current_exe_path}"
    timeout /t 5 /nobreak > nul
    if exist "{safe_backup_path}" del /f /q "{safe_backup_path}"
) else (
    echo Errore aggiornamento, ripristino backup...
    if exist "{safe_backup_path}" move /y "{safe_backup_path}" "{safe_current_exe_path}"
)

del "%~f0"
endlocal
"""

            batch_name = f"pickfair_update_{uuid.uuid4().hex}.bat"
            batch_path = os.path.join(tempfile.gettempdir(), batch_name)

            with open(batch_path, "w", encoding="utf-8", newline="\r\n") as f:
                f.write(batch_content)

            create_no_window = 0x08000000
            subprocess.Popen(
                ["cmd.exe", "/c", batch_path],
                creationflags=create_no_window,
                shell=False,
            )
            return True

        if update_path.endswith(".exe"):
            subprocess.Popen([update_path], shell=False)
            return True

        folder = os.path.dirname(update_path)
        if sys.platform == "win32":
            subprocess.run(["explorer", folder], check=False, shell=False)
        return True

    except Exception as e:
        print(f"Install failed: {e}")
        return False


def get_current_exe_path():
    """Get the path of the current executable."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return None


class _AutoUpdaterFacade:
    """Runtime compatibility facade without expanding static public API surface."""

    def __init__(self, current_version=None, enabled=False, update_url=None):
        self.enabled = enabled
        self.current_version = current_version
        self.update_url = update_url or DEFAULT_UPDATE_URL

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False

    def set_current_version(self, version):
        self.current_version = version

    def check(self, callback=None, update_url=None):
        if not self.enabled:
            result = {"update_available": False, "error": "AutoUpdater disabled"}
            if callback:
                callback(result)
            return None

        if not self.current_version:
            result = {"update_available": False, "error": "Current version not set"}
            if callback:
                callback(result)
            return None

        return check_for_updates(
            self.current_version,
            callback=callback,
            update_url=update_url or self.update_url,
        )

    def check_for_updates(self, callback=None, update_url=None):
        return self.check(callback=callback, update_url=update_url)

    def open_download_page(self, url):
        return open_download_page(url)

    def download_update(self, download_url, progress_callback=None):
        return download_update(download_url, progress_callback=progress_callback)

    def install_update(self, update_path, current_exe_path=None):
        return install_update(update_path, current_exe_path=current_exe_path)


AutoUpdater = _AutoUpdaterFacade


class UpdateDialog:
    """Tkinter dialog for showing update notification with auto-install."""

    def __init__(self, parent, update_info):
        import tkinter as tk
        from tkinter import messagebox, ttk

        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox
        self.result = None
        self.update_info = update_info
        self.parent = parent
        self.downloading = False

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Aggiornamento Disponibile")
        self.dialog.geometry("450x400")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)

        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 450) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 400) // 2
        self.dialog.geometry(f"+{x}+{y}")

        frame = ttk.Frame(self.dialog, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        title_label = ttk.Label(
            frame,
            text="Nuovo Aggiornamento!",
            font=("Segoe UI", 14, "bold"),
        )
        title_label.pack(pady=(0, 10))

        version_text = (
            f"Versione attuale: {update_info['current_version']}\n"
            f"Nuova versione: {update_info['latest_version']}"
        )
        version_label = ttk.Label(frame, text=version_text, font=("Segoe UI", 11))
        version_label.pack(pady=5)

        notes_frame = ttk.LabelFrame(frame, text="Note di rilascio", padding=10)
        notes_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        notes_text = tk.Text(notes_frame, wrap=tk.WORD, height=6, font=("Segoe UI", 9))
        notes_text.insert("1.0", update_info.get("release_notes", "Nessuna nota disponibile"))
        notes_text.config(state=tk.DISABLED)
        notes_text.pack(fill=tk.BOTH, expand=True)

        self.progress_frame = ttk.Frame(frame)
        self.progress_frame.pack(fill=tk.X, pady=10)

        self.progress_label = ttk.Label(self.progress_frame, text="")
        self.progress_label.pack()

        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            mode="determinate",
            length=380,
        )
        self.progress_bar.pack(fill=tk.X, pady=5)
        self.progress_bar.pack_forget()
        self.progress_label.pack_forget()

        self.btn_frame = ttk.Frame(frame)
        self.btn_frame.pack(fill=tk.X, pady=(10, 0))

        self.download_btn = tk.Button(
            self.btn_frame,
            text="Aggiorna Ora",
            bg="#28a745",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            command=self._start_download,
        )
        self.download_btn.pack(side=tk.LEFT, padx=5)

        self.manual_btn = ttk.Button(
            self.btn_frame,
            text="Scarica Manualmente",
            command=self._manual_download,
        )
        self.manual_btn.pack(side=tk.LEFT, padx=5)

        self.later_btn = ttk.Button(
            self.btn_frame,
            text="Dopo",
            command=self._later,
        )
        self.later_btn.pack(side=tk.RIGHT, padx=5)

    def _on_close(self):
        if not self.downloading:
            self.dialog.destroy()

    def _start_download(self):
        self.downloading = True
        download_url = self.update_info.get("download_url")

        if not download_url or not download_url.endswith(".exe"):
            self._manual_download()
            return

        self.progress_label.config(text="Download in corso...")
        self.progress_label.pack()
        self.progress_bar.pack(fill=self.tk.X, pady=5)
        self.progress_bar["value"] = 0

        self.download_btn.config(state=self.tk.DISABLED)
        self.manual_btn.config(state=self.tk.DISABLED)
        self.later_btn.config(state=self.tk.DISABLED)

        def do_download():
            def progress_callback(downloaded, total):
                if total > 0:
                    percent = (downloaded / total) * 100
                    mb_down = downloaded / (1024 * 1024)
                    mb_total = total / (1024 * 1024)
                    self.dialog.after(
                        0,
                        lambda: self._update_progress(percent, mb_down, mb_total),
                    )

            downloaded_path = download_update(download_url, progress_callback)

            if downloaded_path:
                self.dialog.after(0, lambda: self._install_update(downloaded_path))
            else:
                self.dialog.after(0, self._download_failed)

        threading.Thread(target=do_download, daemon=True).start()

    def _update_progress(self, percent, mb_down, mb_total):
        self.progress_bar["value"] = percent
        self.progress_label.config(
            text=f"Download: {mb_down:.1f} MB / {mb_total:.1f} MB"
        )

    def _install_update(self, downloaded_path):
        self.progress_label.config(text="Installazione in corso...")
        self.progress_bar["value"] = 100

        current_exe = get_current_exe_path()

        if current_exe:
            success = install_update(downloaded_path, current_exe)
            if success:
                self.result = "installed"
                self.progress_label.config(text="Riavvio in corso...")
                self.dialog.after(1000, self._close_app)
            else:
                self._download_failed()
        else:
            self.messagebox.showinfo(
                "Download Completato",
                f"Aggiornamento scaricato in:\n{downloaded_path}\n\n"
                "Sostituisci manualmente l'eseguibile.",
            )
            self.dialog.destroy()

    def _close_app(self):
        self.dialog.destroy()
        self.parent.destroy()
        sys.exit(0)

    def _download_failed(self):
        self.downloading = False
        self.progress_label.config(text="Download fallito!")
        self.download_btn.config(state=self.tk.NORMAL)
        self.manual_btn.config(state=self.tk.NORMAL)
        self.later_btn.config(state=self.tk.NORMAL)
        self.messagebox.showerror(
            "Errore",
            "Download fallito. Prova il download manuale.",
        )

    def _manual_download(self):
        self.result = "manual"
        open_download_page(self.update_info["release_page"])
        self.dialog.destroy()

    def _later(self):
        self.result = "later"
        self.dialog.destroy()

    def show(self):
        self.dialog.wait_window()
        return self.result


def show_update_dialog(parent, update_info):
    """Show update dialog and return user choice."""
    dialog = UpdateDialog(parent, update_info)
    return dialog.show()