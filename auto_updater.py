"""
Auto-Update System for Pickfair
Checks GitHub releases for new versions and allows one-click updates.
"""

import os
import sys
import json
import threading
import webbrowser
import tempfile
import subprocess
from urllib.request import urlopen, Request
from urllib.error import URLError

# Default configuration - GitHub releases API for Pickfair
DEFAULT_UPDATE_URL = "https://api.github.com/repos/petiro/Pickfair/releases/latest"


def parse_version(version_str):
    """Parse version string like '3.4.0' into tuple (3, 4, 0)."""
    try:
        # Remove 'v' prefix if present
        version_str = version_str.lstrip('v').strip()
        parts = version_str.split('.')
        return tuple(int(p) for p in parts[:3])
    except:
        return (0, 0, 0)


def compare_versions(current, latest):
    """Compare two version strings. Returns True if latest > current."""
    current_tuple = parse_version(current)
    latest_tuple = parse_version(latest)
    return latest_tuple > current_tuple


def check_for_updates(current_version, callback=None, update_url=None):
    """
    Check GitHub for new releases.
    
    Args:
        current_version: Current app version string (e.g., "3.4.0")
        callback: Function to call with result (update_available, version, download_url, release_notes)
        update_url: URL to check for updates (GitHub API releases/latest endpoint)
    
    Returns dict with update info or None if no update available.
    """
    check_url = update_url or DEFAULT_UPDATE_URL
    
    if not check_url:
        # No update URL configured
        if callback:
            callback({'update_available': False, 'error': 'No update URL configured'})
        return None
    
    def do_check():
        try:
            # Create request with User-Agent (required by GitHub API)
            req = Request(
                check_url,
                headers={'User-Agent': 'Pickfair-Updater/1.0'}
            )
            
            with urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            latest_version = data.get('tag_name', '').lstrip('v')
            
            if compare_versions(current_version, latest_version):
                # Find the Windows executable asset
                download_url = None
                for asset in data.get('assets', []):
                    name = asset.get('name', '').lower()
                    if name.endswith('.exe') or name.endswith('.zip'):
                        download_url = asset.get('browser_download_url')
                        break
                
                # Fallback to release page if no direct download
                if not download_url:
                    download_url = data.get('html_url', '')
                
                result = {
                    'update_available': True,
                    'current_version': current_version,
                    'latest_version': latest_version,
                    'download_url': download_url,
                    'release_notes': data.get('body', ''),
                    'release_page': data.get('html_url', ''),
                    'published_at': data.get('published_at', '')
                }
                
                if callback:
                    callback(result)
                return result
            else:
                result = {'update_available': False}
                if callback:
                    callback(result)
                return result
                
        except URLError as e:
            print(f"Update check failed (network): {e}")
            if callback:
                callback({'update_available': False, 'error': str(e)})
            return None
        except Exception as e:
            print(f"Update check failed: {e}")
            if callback:
                callback({'update_available': False, 'error': str(e)})
            return None
    
    # Run in background thread to not block UI
    thread = threading.Thread(target=do_check, daemon=True)
    thread.start()


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
        req = Request(
            download_url,
            headers={'User-Agent': 'Pickfair-Updater/1.0'}
        )
        
        with urlopen(req, timeout=60) as response:
            total_size = int(response.headers.get('content-length', 0))
            
            # Get filename from URL
            filename = download_url.split('/')[-1]
            download_path = os.path.join(tempfile.gettempdir(), filename)
            
            downloaded = 0
            chunk_size = 8192
            
            with open(download_path, 'wb') as f:
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


def install_update(update_path, current_exe_path=None):
    """
    Install the downloaded update and restart the app.
    For .exe files, replace current exe and restart.
    """
    try:
        if update_path.endswith('.exe') and current_exe_path:
            # Get the directory of current executable
            app_dir = os.path.dirname(current_exe_path)
            new_exe_name = os.path.basename(current_exe_path)
            backup_path = current_exe_path + ".backup"
            
            # Create a batch script to:
            # 1. Wait for current app to close
            # 2. Replace the exe
            # 3. Start new version
            # 4. Delete itself
            batch_content = f'''@echo off
echo Aggiornamento in corso...
echo Attendere la chiusura dell'applicazione...
timeout /t 5 /nobreak > nul

REM Pulisci cartelle temporanee PyInstaller
for /d %%i in ("%TEMP%\\_MEI*") do rd /s /q "%%i" 2>nul

REM Attendi ancora per sicurezza
timeout /t 2 /nobreak > nul

if exist "{backup_path}" del /f "{backup_path}"
if exist "{current_exe_path}" move /y "{current_exe_path}" "{backup_path}"
move /y "{update_path}" "{current_exe_path}"

if exist "{current_exe_path}" (
    echo Avvio nuova versione...
    timeout /t 2 /nobreak > nul
    start "" "{current_exe_path}"
    timeout /t 5 /nobreak > nul
    if exist "{backup_path}" del /f "{backup_path}"
) else (
    echo Errore aggiornamento, ripristino backup...
    if exist "{backup_path}" move /y "{backup_path}" "{current_exe_path}"
)
del "%~f0"
'''
            
            # Save batch script in temp folder
            batch_path = os.path.join(tempfile.gettempdir(), "pickfair_update.bat")
            with open(batch_path, 'w') as f:
                f.write(batch_content)
            
            # Run the batch script (will wait for app to close)
            # CREATE_NO_WINDOW = 0x08000000 (Windows constant to hide console)
            CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen(['cmd', '/c', batch_path], creationflags=CREATE_NO_WINDOW)
            return True
            
        elif update_path.endswith('.exe'):
            # No current exe path, just run the downloaded one
            subprocess.Popen([update_path], shell=True)
            return True
        elif update_path.endswith('.zip'):
            # For zip files, open the folder (Windows-specific)
            folder = os.path.dirname(update_path)
            if sys.platform == 'win32':
                subprocess.run(['explorer', folder])
            return True
        else:
            # Open containing folder (Windows-specific)
            folder = os.path.dirname(update_path)
            if sys.platform == 'win32':
                subprocess.run(['explorer', folder])
            return True
    except Exception as e:
        print(f"Install failed: {e}")
        return False


def get_current_exe_path():
    """Get the path of the current executable."""
    if getattr(sys, 'frozen', False):
        # Running as compiled exe
        return sys.executable
    else:
        # Running as script (development)
        return None


class UpdateDialog:
    """Tkinter dialog for showing update notification with auto-install."""
    
    def __init__(self, parent, update_info):
        import tkinter as tk
        from tkinter import ttk, messagebox
        
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
        
        # Center on parent
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 450) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 400) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
        frame = ttk.Frame(self.dialog, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(frame, text="Nuovo Aggiornamento!", 
                               font=('Segoe UI', 14, 'bold'))
        title_label.pack(pady=(0, 10))
        
        # Version info
        version_text = f"Versione attuale: {update_info['current_version']}\n"
        version_text += f"Nuova versione: {update_info['latest_version']}"
        version_label = ttk.Label(frame, text=version_text, font=('Segoe UI', 11))
        version_label.pack(pady=5)
        
        # Release notes
        notes_frame = ttk.LabelFrame(frame, text="Note di rilascio", padding=10)
        notes_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        notes_text = tk.Text(notes_frame, wrap=tk.WORD, height=6, font=('Segoe UI', 9))
        notes_text.insert('1.0', update_info.get('release_notes', 'Nessuna nota disponibile'))
        notes_text.config(state=tk.DISABLED)
        notes_text.pack(fill=tk.BOTH, expand=True)
        
        # Progress bar (hidden initially)
        self.progress_frame = ttk.Frame(frame)
        self.progress_frame.pack(fill=tk.X, pady=10)
        
        self.progress_label = ttk.Label(self.progress_frame, text="")
        self.progress_label.pack()
        
        self.progress_bar = ttk.Progressbar(self.progress_frame, mode='determinate', length=380)
        self.progress_bar.pack(fill=tk.X, pady=5)
        self.progress_bar.pack_forget()  # Hide initially
        self.progress_label.pack_forget()
        
        # Buttons
        self.btn_frame = ttk.Frame(frame)
        self.btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.download_btn = tk.Button(self.btn_frame, text="Aggiorna Ora", 
                                bg='#28a745', fg='white', font=('Segoe UI', 10, 'bold'),
                                command=self._start_download)
        self.download_btn.pack(side=tk.LEFT, padx=5)
        
        self.manual_btn = ttk.Button(self.btn_frame, text="Scarica Manualmente", 
                              command=self._manual_download)
        self.manual_btn.pack(side=tk.LEFT, padx=5)
        
        self.later_btn = ttk.Button(self.btn_frame, text="Dopo", 
                              command=self._later)
        self.later_btn.pack(side=tk.RIGHT, padx=5)
    
    def _on_close(self):
        if not self.downloading:
            self.dialog.destroy()
    
    def _start_download(self):
        """Start automatic download and install."""
        self.downloading = True
        download_url = self.update_info.get('download_url')
        
        if not download_url or not download_url.endswith('.exe'):
            # Fallback to manual download
            self._manual_download()
            return
        
        # Show progress
        self.progress_label.config(text="Download in corso...")
        self.progress_label.pack()
        self.progress_bar.pack(fill=self.tk.X, pady=5)
        self.progress_bar['value'] = 0
        
        # Disable buttons
        self.download_btn.config(state=self.tk.DISABLED)
        self.manual_btn.config(state=self.tk.DISABLED)
        self.later_btn.config(state=self.tk.DISABLED)
        
        # Start download in thread
        def do_download():
            def progress_callback(downloaded, total):
                if total > 0:
                    percent = (downloaded / total) * 100
                    mb_down = downloaded / (1024 * 1024)
                    mb_total = total / (1024 * 1024)
                    self.dialog.after(0, lambda: self._update_progress(percent, mb_down, mb_total))
            
            downloaded_path = download_update(download_url, progress_callback)
            
            if downloaded_path:
                self.dialog.after(0, lambda: self._install_update(downloaded_path))
            else:
                self.dialog.after(0, self._download_failed)
        
        threading.Thread(target=do_download, daemon=True).start()
    
    def _update_progress(self, percent, mb_down, mb_total):
        self.progress_bar['value'] = percent
        self.progress_label.config(text=f"Download: {mb_down:.1f} MB / {mb_total:.1f} MB")
    
    def _install_update(self, downloaded_path):
        self.progress_label.config(text="Installazione in corso...")
        self.progress_bar['value'] = 100
        
        current_exe = get_current_exe_path()
        
        if current_exe:
            # Auto install and restart
            success = install_update(downloaded_path, current_exe)
            if success:
                self.result = 'installed'
                self.progress_label.config(text="Riavvio in corso...")
                self.dialog.after(1000, self._close_app)
            else:
                self._download_failed()
        else:
            # Development mode - just open folder
            self.messagebox.showinfo("Download Completato", 
                f"Aggiornamento scaricato in:\n{downloaded_path}\n\nSostituisci manualmente l'eseguibile.")
            self.dialog.destroy()
    
    def _close_app(self):
        """Close the application to allow update."""
        self.dialog.destroy()
        self.parent.destroy()
        sys.exit(0)
    
    def _download_failed(self):
        self.downloading = False
        self.progress_label.config(text="Download fallito!")
        self.download_btn.config(state=self.tk.NORMAL)
        self.manual_btn.config(state=self.tk.NORMAL)
        self.later_btn.config(state=self.tk.NORMAL)
        self.messagebox.showerror("Errore", "Download fallito. Prova il download manuale.")
    
    def _manual_download(self):
        self.result = 'manual'
        open_download_page(self.update_info['release_page'])
        self.dialog.destroy()
    
    def _later(self):
        self.result = 'later'
        self.dialog.destroy()
    
    def show(self):
        self.dialog.wait_window()
        return self.result


def show_update_dialog(parent, update_info):
    """Show update dialog and return user choice."""
    dialog = UpdateDialog(parent, update_info)
    return dialog.show()
