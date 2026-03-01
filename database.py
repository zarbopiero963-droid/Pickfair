"""
Database layer using SQLite for local storage.
Hedge-Fund Grade: Supporta concorrenza massiva (WAL) e nested transactions.
"""

import sqlite3
import os
import json
import threading
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger("DB")

def get_db_path():
    if os.name == 'nt':  # Windows
        app_data = os.environ.get('APPDATA', os.path.expanduser('~'))
        db_dir = os.path.join(app_data, 'Pickfair')
    else:  # Linux/Mac
        db_dir = os.path.join(os.path.expanduser('~'), '.pickfair')
    
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, 'betfair.db')

class Database:
    def __init__(self):
        self.db_path = get_db_path()
        self._local = threading.local()
        self._init_db()
    
    def _get_connection(self):
        """Thread-local connection con WAL mode attivato."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, timeout=20.0)
            self._local.conn.row_factory = sqlite3.Row
            # HEDGE FUND FIX: Abilita Write-Ahead Logging per letture/scritture simultanee
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            self._local.transaction_depth = 0
        return self._local.conn

    def _execute(self, query: str, params: tuple = (), commit: bool = True):
        """Esegue query gestendo transazioni annidate (SAVEPOINT)."""
        conn = self._get_connection()
        try:
            # Incrementiamo la profondità
            self._local.transaction_depth += 1
            sp_name = f"sp_{self._local.transaction_depth}"
            conn.execute(f"SAVEPOINT {sp_name}")
            
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            if commit:
                conn.execute(f"RELEASE {sp_name}")
                if self._local.transaction_depth == 1:
                    conn.commit()
            return cursor
        except Exception as e:
            if hasattr(self._local, 'transaction_depth'):
                sp_name = f"sp_{self._local.transaction_depth}"
                conn.execute(f"ROLLBACK TO {sp_name}")
            logger.error(f"[DB] DB Error: {e} | Query: {query}")
            raise
        finally:
            if hasattr(self._local, 'transaction_depth'):
                self._local.transaction_depth -= 1

    def _init_db(self):
        """Crea le tabelle se non esistono."""
        self._execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        self._execute('''
            CREATE TABLE IF NOT EXISTS bet_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                placed_at TIMESTAMP,
                event_name TEXT,
                market_id TEXT,
                market_name TEXT,
                bet_type TEXT,
                selections TEXT,
                total_stake REAL,
                potential_profit REAL,
                status TEXT
            )
        ''')
        # Aggiunta colonne sicura
        try:
            self._execute("ALTER TABLE settings ADD COLUMN password TEXT")
        except sqlite3.OperationalError:
            pass

    def save_credentials(self, username, app_key, certificate, private_key):
        data = {
            'username': username,
            'app_key': app_key,
            'certificate': certificate,
            'private_key': private_key
        }
        self._execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                      ('credentials', json.dumps(data)))

    def get_settings(self):
        cursor = self._execute("SELECT value FROM settings WHERE key = 'credentials'")
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return {}

    def save_password(self, password):
        self._execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                      ('password', password if password else ""))

    def save_session(self, token, expiry):
        self._execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                      ('session', json.dumps({'token': token, 'expiry': expiry})))

    def clear_session(self):
        self._execute("DELETE FROM settings WHERE key = 'session'")

    def save_bet(self, event_name, market_id, market_name, bet_type, selections, total_stake, potential_profit, status):
        self._execute('''
            INSERT INTO bet_history 
            (placed_at, event_name, market_id, market_name, bet_type, selections, total_stake, potential_profit, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(), event_name, market_id, market_name, 
            bet_type, json.dumps(selections), total_stake, potential_profit, status
        ))

    def get_recent_bets(self, limit=50):
        cursor = self._execute("SELECT * FROM bet_history ORDER BY placed_at DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def close(self):
        """Chiude la connessione thread-local e fa checkpoint del WAL."""
        if hasattr(self._local, 'conn') and self._local.conn:
            try:
                self._local.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._local.conn.close()
                self._local.conn = None
            except:
                pass