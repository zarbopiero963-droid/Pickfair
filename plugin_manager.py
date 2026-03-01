"""
Pickfair Plugin Manager
Sistema di plugin con protezioni di sicurezza e thread isolation
"""

import os
import sys
import ast
import threading
import importlib.util
import subprocess
import time
import traceback
from typing import Dict, List, Callable, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path

# --- HEDGE-FUND STABLE FIX ---
from plugin_runner import PluginRunner
# -----------------------------

@dataclass
class PluginInfo:
    """Information about a plugin."""
    name: str
    version: str = "1.0.0"
    author: str = "Unknown"
    description: str = ""
    enabled: bool = True
    verified: bool = False
    path: str = ""
    module: Any = None
    error: str = ""
    
    # Runtime stats
    load_time: float = 0.0
    last_error: str = ""
    execution_count: int = 0

class PluginSecurityError(Exception):
    """Raised when plugin fails security validation."""
    pass

class PluginTimeoutError(Exception):
    """Raised when plugin execution times out."""
    pass

class PluginManager:
    """Manages plugin loading, validation, and execution with security measures."""
    
    # Blocked dangerous functions/imports
    BLOCKED_PATTERNS = [
        'eval(', 'exec(', 'compile(',
        'os.system', 'os.popen', 'os.spawn',
        'subprocess.call', 'subprocess.run', 'subprocess.Popen',
        '__import__', 'importlib.import_module',
        'open("/etc', 'open("C:\\Windows', 'open("C:/Windows',
        'shutil.rmtree', 'os.remove', 'os.unlink', 'os.rmdir',
        'socket.socket', 'urllib.request',
    ]
    
    # Allowed imports for plugins
    ALLOWED_IMPORTS = [
        'math', 'random', 'datetime', 'time', 'json', 're',
        'collections', 'itertools', 'functools', 'operator',
        'numpy', 'pandas', 'matplotlib',
        'tkinter', 'customtkinter',
    ]
    
    # Resource limits
    MAX_MEMORY_MB = 100
    MAX_EXECUTION_TIME = 10  # seconds
    MAX_CPU_PERCENT = 50
    
    def __init__(self, app, plugins_dir: str = None):
        """Initialize plugin manager.
        
        Args:
            app: Main application instance
            plugins_dir: Directory for plugins (default: %APPDATA%/Pickfair/plugins)
        """
        self.app = app
        self.plugins: Dict[str, PluginInfo] = {}
        self.hooks: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()
        
        # --- HEDGE-FUND STABLE FIX ---
        self.plugin_runner = PluginRunner(timeout=self.MAX_EXECUTION_TIME)
        # -----------------------------
        
        # Setup plugins directory
        if plugins_dir:
            self.plugins_dir = Path(plugins_dir)
        else:
            if sys.platform == 'win32':
                appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
                self.plugins_dir = Path(appdata) / 'Pickfair' / 'plugins'
            else:
                self.plugins_dir = Path.home() / '.pickfair' / 'plugins'
        
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        
        # Allowed paths for file access (store as Path objects for safe comparison)
        self.allowed_paths = [
            self.plugins_dir.resolve(),
            (self.plugins_dir.parent / 'data').resolve(),
            (self.plugins_dir.parent / 'logs').resolve(),
        ]
        
        # Create data directory for plugins
        (self.plugins_dir.parent / 'data').mkdir(exist_ok=True)
    
    # Dangerous module names to block completely
    BLOCKED_MODULES = ['subprocess', 'socket', 'urllib', 'http', 'ftplib', 'smtplib', 'ctypes', 'multiprocessing']
    
    # Dangerous function calls in specific modules
    BLOCKED_CALLS = {
        'os': ['system', 'popen', 'spawn', 'spawnl', 'spawnle', 'spawnlp', 'spawnlpe', 
               'spawnv', 'spawnve', 'spawnvp', 'spawnvpe', 'remove', 'unlink', 'rmdir'],
        'shutil': ['rmtree', 'move', 'copytree'],
        'builtins': ['eval', 'exec', 'compile', '__import__'],
    }
    
    def validate_plugin_code(self, code: str, plugin_name: str = "unknown") -> tuple:
        """Validate plugin code for security issues using AST analysis.
        
        Returns:
            (is_valid: bool, message: str)
        """
        # Parse AST
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Errore di sintassi: {e}"
        
        # Track imported module aliases
        module_aliases = {}  # alias -> actual module name
        
        for node in ast.walk(tree):
            # Check imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split('.')[0]
                    actual_name = alias.asname or alias.name
                    module_aliases[actual_name.split('.')[0]] = module_name
                    
                    if module_name in self.BLOCKED_MODULES:
                        return False, f"Modulo vietato: {module_name}"
            
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split('.')[0]
                    if module_name in self.BLOCKED_MODULES:
                        return False, f"Modulo vietato: {module_name}"
                    
                    # Track aliases for from imports
                    for alias in node.names:
                        actual_name = alias.asname or alias.name
                        module_aliases[actual_name] = f"{module_name}.{alias.name}"
            
            # Check function calls
            elif isinstance(node, ast.Call):
                func = node.func
                
                # Check for dangerous builtins: eval(), exec(), compile()
                if isinstance(func, ast.Name):
                    if func.id in ['eval', 'exec', 'compile', '__import__']:
                        return False, f"Funzione vietata: {func.id}()"
                
                # Check for dangerous attribute calls: os.system(), etc.
                elif isinstance(func, ast.Attribute):
                    if isinstance(func.value, ast.Name):
                        obj_name = func.value.id
                        method_name = func.attr
                        
                        # Resolve alias to actual module
                        actual_module = module_aliases.get(obj_name, obj_name)
                        base_module = actual_module.split('.')[0]
                        
                        # Check if this is a blocked call
                        if base_module in self.BLOCKED_CALLS:
                            if method_name in self.BLOCKED_CALLS[base_module]:
                                return False, f"Chiamata vietata: {obj_name}.{method_name}()"
                        
                        # Block entire modules
                        if base_module in self.BLOCKED_MODULES:
                            return False, f"Chiamata a modulo vietato: {obj_name}.{method_name}()"
        
        return True, "Validazione OK"
    
    def validate_plugin_file(self, filepath: str) -> tuple:
        """Validate a plugin file.
        
        Returns:
            (is_valid: bool, message: str)
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                code = f.read()
            return self.validate_plugin_code(code, os.path.basename(filepath))
        except Exception as e:
            return False, f"Errore lettura file: {e}"
    
    def safe_file_access(self, filepath: str, mode: str = 'r') -> bool:
        """Check if file access is allowed (sandbox) securely preventing path traversal."""
        try:
            target_path = Path(filepath).resolve()
            for allowed in self.allowed_paths:
                if target_path.is_relative_to(allowed):
                    return True
            return False
        except Exception:
            return False
    
    def install_requirements(self, plugin_path: str) -> tuple:
        """Install plugin requirements from requirements.txt.
        
        Returns:
            (success: bool, message: str)
        """
        req_file = os.path.join(os.path.dirname(plugin_path), 'requirements.txt')
        
        if not os.path.exists(req_file):
            return True, "Nessun requirements.txt"
        
        try:
            # Read requirements
            with open(req_file, 'r') as f:
                requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            if not requirements:
                return True, "Requirements vuoto"
            
            # Install using pip
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--quiet'] + requirements,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                return True, f"Installate {len(requirements)} librerie"
            else:
                return False, f"Errore pip: {result.stderr[:200]}"
                
        except subprocess.TimeoutExpired:
            return False, "Timeout installazione librerie"
        except Exception as e:
            return False, f"Errore: {e}"
    
    def load_plugin(self, filepath: str, enable: bool = True) -> tuple:
        """Load a plugin from file.
        
        Returns:
            (success: bool, plugin_info: PluginInfo, message: str)
        """
        plugin_name = os.path.splitext(os.path.basename(filepath))[0]
        
        # Validate first
        is_valid, msg = self.validate_plugin_file(filepath)
        if not is_valid:
            info = PluginInfo(name=plugin_name, enabled=False, error=msg, path=filepath)
            return False, info, msg
        
        # Install requirements if present
        req_ok, req_msg = self.install_requirements(filepath)
        if not req_ok:
            info = PluginInfo(name=plugin_name, enabled=False, error=req_msg, path=filepath)
            return False, info, req_msg
        
        # Load module
        start_time = time.time()
        try:
            spec = importlib.util.spec_from_file_location(plugin_name, filepath)
            module = importlib.util.module_from_spec(spec)
            
            # Execute in timeout thread (daemon=True so it won't block app shutdown)
            load_error = [None]
            def do_load():
                try:
                    spec.loader.exec_module(module)
                except Exception as e:
                    load_error[0] = e
            
            thread = threading.Thread(target=do_load, daemon=True)
            thread.start()
            thread.join(timeout=self.MAX_EXECUTION_TIME)
            
            if thread.is_alive():
                return False, PluginInfo(name=plugin_name, enabled=False, error="Timeout caricamento", path=filepath), "Plugin timeout durante il caricamento"
            
            if load_error[0]:
                raise load_error[0]
            
            load_time = time.time() - start_time
            
            # Get plugin metadata
            info = PluginInfo(
                name=getattr(module, 'PLUGIN_NAME', plugin_name),
                version=getattr(module, 'PLUGIN_VERSION', '1.0.0'),
                author=getattr(module, 'PLUGIN_AUTHOR', 'Unknown'),
                description=getattr(module, 'PLUGIN_DESCRIPTION', ''),
                enabled=enable,
                verified=False,
                path=filepath,
                module=module,
                load_time=load_time
            )
            
            # Register plugin
            with self._lock:
                self.plugins[plugin_name] = info
            
            # Call register function if exists
            if enable and hasattr(module, 'register'):
                self._run_plugin_safe(lambda: module.register(self.app), plugin_name)
            
            return True, info, f"Plugin caricato in {load_time:.2f}s"
            
        except Exception as e:
            error_msg = f"Errore caricamento: {traceback.format_exc()}"
            info = PluginInfo(name=plugin_name, enabled=False, error=str(e), path=filepath)
            return False, info, error_msg
    
    def unload_plugin(self, plugin_name: str) -> tuple:
        """Unload a plugin.
        
        Returns:
            (success: bool, message: str)
        """
        with self._lock:
            if plugin_name not in self.plugins:
                return False, "Plugin non trovato"
            
            info = self.plugins[plugin_name]
            
            # Call unregister if exists
            if info.module and hasattr(info.module, 'unregister'):
                try:
                    self._run_plugin_safe(lambda: info.module.unregister(self.app), plugin_name)
                except:
                    pass
            
            # Remove from hooks
            for hook_name in list(self.hooks.keys()):
                self.hooks[hook_name] = [h for h in self.hooks[hook_name] 
                                         if not getattr(h, '_plugin_name', None) == plugin_name]
            
            del self.plugins[plugin_name]
            return True, "Plugin scaricato"
    
    def enable_plugin(self, plugin_name: str) -> tuple:
        """Enable a disabled plugin."""
        with self._lock:
            if plugin_name not in self.plugins:
                return False, "Plugin non trovato"
            
            info = self.plugins[plugin_name]
            if info.enabled:
                return True, "Gia abilitato"
            
            info.enabled = True
            
            if info.module and hasattr(info.module, 'register'):
                self._run_plugin_safe(lambda: info.module.register(self.app), plugin_name)
            
            return True, "Plugin abilitato"
    
    def disable_plugin(self, plugin_name: str) -> tuple:
        """Disable an enabled plugin."""
        with self._lock:
            if plugin_name not in self.plugins:
                return False, "Plugin non trovato"
            
            info = self.plugins[plugin_name]
            if not info.enabled:
                return True, "Gia disabilitato"
            
            info.enabled = False
            
            if info.module and hasattr(info.module, 'unregister'):
                self._run_plugin_safe(lambda: info.module.unregister(self.app), plugin_name)
            
            return True, "Plugin disabilitato"
    
    def _run_plugin_safe(self, func: Callable, plugin_name: str, *args, **kwargs) -> Any:
        """Execute a plugin function safely via ThreadPoolExecutor."""
        return self.plugin_runner.run(plugin_name, func, *args, **kwargs)
    
    def register_hook(self, hook_name: str, callback: Callable, plugin_name: str = None):
        """Register a hook callback from a plugin."""
        if hook_name not in self.hooks:
            self.hooks[hook_name] = []
        
        # Tag callback with plugin name for cleanup
        callback._plugin_name = plugin_name
        self.hooks[hook_name].append(callback)
    
    def call_hook(self, hook_name: str, *args, **kwargs) -> List[Any]:
        """Call all registered callbacks for a hook.
        
        Returns:
            List of results from callbacks
        """
        results = []
        if hook_name not in self.hooks:
            return results
        
        for callback in self.hooks[hook_name]:
            plugin_name = getattr(callback, '_plugin_name', 'unknown')
            try:
                result = self._run_plugin_safe(
                    lambda: callback(*args, **kwargs),
                    plugin_name
                )
                if result is not None:
                    results.append(result)
            except Exception as e:
                print(f"[Plugin Hook Error] {plugin_name}: {e}")
        
        return results
    
    def load_all_plugins(self):
        """Load all plugins from plugins directory."""
        if not self.plugins_dir.exists():
            return
        
        for filepath in self.plugins_dir.glob('*.py'):
            if filepath.name.startswith('_'):
                continue
            
            print(f"[Plugin] Caricamento: {filepath.name}")
            success, info, msg = self.load_plugin(str(filepath))
            if success:
                print(f"[Plugin] OK: {info.name} v{info.version}")
            else:
                print(f"[Plugin] ERRORE: {msg}")
    
    def get_plugin_list(self) -> List[PluginInfo]:
        """Get list of all plugins."""
        with self._lock:
            return list(self.plugins.values())
    
    def install_plugin_from_file(self, source_path: str) -> tuple:
        """Install a plugin from external file.
        
        Returns:
            (success: bool, message: str)
        """
        filename = os.path.basename(source_path)
        dest_path = self.plugins_dir / filename
        
        # Validate before copying
        is_valid, msg = self.validate_plugin_file(source_path)
        if not is_valid:
            return False, f"Plugin non valido: {msg}"
        
        # Copy to plugins directory
        try:
            import shutil
            shutil.copy2(source_path, dest_path)
        except Exception as e:
            return False, f"Errore copia: {e}"
        
        # Load the plugin
        success, info, msg = self.load_plugin(str(dest_path))
        if success:
            return True, f"Plugin {info.name} installato"
        else:
            # Remove failed plugin
            try:
                os.remove(dest_path)
            except:
                pass
            return False, msg
    
    def uninstall_plugin(self, plugin_name: str) -> tuple:
        """Uninstall a plugin completely.
        
        Returns:
            (success: bool, message: str)
        """
        if plugin_name not in self.plugins:
            return False, "Plugin non trovato"
        
        info = self.plugins[plugin_name]
        filepath = info.path
        
        # Unload first
        self.unload_plugin(plugin_name)
        
        # Delete file
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            return True, "Plugin disinstallato"
        except Exception as e:
            return False, f"Errore rimozione file: {e}"


# Plugin API - functions available to plugins
class PluginAPI:
    """API exposed to plugins for interacting with the app."""
    
    def __init__(self, manager: PluginManager, plugin_name: str):
        self.manager = manager
        self.plugin_name = plugin_name
        self.app = manager.app
    
    def add_tab(self, title: str, create_func: Callable):
        """Add a new tab to the main interface."""
        if hasattr(self.app, 'add_plugin_tab'):
            self.app.add_plugin_tab(title, create_func, self.plugin_name)
    
    def remove_tab(self, title: str):
        """Remove a tab added by this plugin."""
        if hasattr(self.app, 'remove_plugin_tab'):
            self.app.remove_plugin_tab(title, self.plugin_name)
    
    def register_hook(self, hook_name: str, callback: Callable):
        """Register a hook callback."""
        self.manager.register_hook(hook_name, callback, self.plugin_name)
    
    def add_event_filter(self, name: str, filter_func: Callable):
        """Add a custom event filter."""
        if hasattr(self.app, 'add_event_filter'):
            self.app.add_event_filter(name, filter_func, self.plugin_name)
    
    def get_current_market(self):
        """Get current market data."""
        return getattr(self.app, 'current_market', None)
    
    def get_current_selections(self):
        """Get current market selections."""
        return getattr(self.app, 'current_selections', [])
    
    def show_notification(self, title: str, message: str):
        """Show a notification to the user."""
        from tkinter import messagebox
        messagebox.showinfo(title, message)
    
    def log(self, message: str):
        """Log a message."""
        print(f"[Plugin:{self.plugin_name}] {message}")
    
    def get_data_path(self) -> str:
        """Get path to plugin data directory."""
        data_dir = self.manager.plugins_dir.parent / 'data' / self.plugin_name
        data_dir.mkdir(exist_ok=True)
        return str(data_dir)
    
    def save_data(self, filename: str, data: dict):
        """Save plugin data to JSON file (sandboxed)."""
        import json
        filepath = os.path.join(self.get_data_path(), filename)
        
        # Enforce sandbox - only allow writing to plugin data directory
        if not self.manager.safe_file_access(filepath, 'w'):
            raise PermissionError(f"Accesso file negato: {filepath}")
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load_data(self, filename: str, default: dict = None) -> dict:
        """Load plugin data from JSON file (sandboxed)."""
        import json
        filepath = os.path.join(self.get_data_path(), filename)
        
        # Enforce sandbox - only allow reading from plugin data directory
        if not self.manager.safe_file_access(filepath, 'r'):
            raise PermissionError(f"Accesso file negato: {filepath}")
        
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
        return default or {}