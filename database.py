"""
Database layer using SQLite for local storage.
Hedge-Fund Grade: supporta concorrenza massiva (WAL),
nested transactions e Saga Pattern.
"""

import sqlite3
import os
import json
import hashlib
import threading
from datetime import datetime
import logging

logger = logging.getLogger("DB")

def get_db_path():
    if os.name == "nt":
        app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
        db_dir = os.path.join(app_data, "Pickfair")
    else:
        db_dir = os.path.join(os.path.expanduser("~"), ".pickfair")

    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "betfair.db")

class Database:
    def __init__(self):
        self.db_path = get_db_path()
        self._local = threading.local()
        self._init_db()

    def _get_connection(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, timeout=20.0)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            self._local.transaction_depth = 0
        return self._local.conn

    def _execute(self, query: str, params: tuple = (), commit: bool = True):
        conn = self._get_connection()
        try:
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
            if hasattr(self._local, "transaction_depth"):
                sp_name = f"sp_{self._local.transaction_depth}"
                conn.execute(f"ROLLBACK TO {sp_name}")
            logger.error(f"[DB] DB Error: {e} | Query: {query}")
            raise

        finally:
            if hasattr(self._local, "transaction_depth"):
                self._local.transaction_depth -= 1

    def _init_db(self):
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )

        self._execute(
            """
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
            """
        )

        self._execute(
            """
            CREATE TABLE IF NOT EXISTS simulation_bet_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                placed_at TIMESTAMP,
                event_name TEXT,
                market_id TEXT,
                market_name TEXT,
                side TEXT,
                selection_id TEXT,
                selection_name TEXT,
                price REAL,
                stake REAL,
                status TEXT,
                selections TEXT,
                total_stake REAL,
                potential_profit REAL
            )
            """
        )

        self._execute(
            """
            CREATE TABLE IF NOT EXISTS cashout_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP,
                market_id TEXT,
                selection_id TEXT,
                original_bet_id TEXT,
                cashout_bet_id TEXT,
                original_side TEXT,
                original_stake REAL,
                original_price REAL,
                cashout_side TEXT,
                cashout_stake REAL,
                cashout_price REAL,
                profit_loss REAL
            )
            """
        )

        self._execute(
            """
            CREATE TABLE IF NOT EXISTS order_saga (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_ref TEXT UNIQUE NOT NULL,
                market_id TEXT NOT NULL,
                selection_id TEXT,
                payload_hash TEXT NOT NULL,
                raw_payload TEXT NOT NULL,
                status TEXT NOT NULL,   -- PENDING | RECONCILED | FAILED
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def create_pending_saga(self, customer_ref, market_id, selection_id, payload_dict):
        payload_str = json.dumps(payload_dict, sort_keys=True)
        payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()
        self._execute(
            """
            INSERT INTO order_saga (
                customer_ref, market_id, selection_id, payload_hash, raw_payload, status
            )
            VALUES (?, ?, ?, ?, ?, 'PENDING')
            """,
            (
                customer_ref,
                market_id,
                str(selection_id) if selection_id is not None else None,
                payload_hash,
                payload_str,
            ),
        )

    def mark_saga_reconciled(self, customer_ref):
        self._execute(
            "UPDATE order_saga SET status='RECONCILED' WHERE customer_ref=?",
            (customer_ref,),
        )

    def mark_saga_failed(self, customer_ref):
        self._execute(
            "UPDATE order_saga SET status='FAILED' WHERE customer_ref=?",
            (customer_ref,),
        )

    def get_pending_sagas(self):
        cursor = self._execute(
            "SELECT customer_ref, market_id, raw_payload FROM order_saga WHERE status='PENDING'"
        )
        return [dict(row) for row in cursor.fetchall()]

    def save_credentials(self, username, app_key, certificate, private_key):
        data = {
            "username": username,
            "app_key": app_key,
            "certificate": certificate,
            "private_key": private_key,
        }
        self._execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("credentials", json.dumps(data)),
        )

    def get_settings(self):
        settings = {}
        cursor = self._execute("SELECT value FROM settings WHERE key='credentials'")
        row = cursor.fetchone()
        if row:
            try: settings.update(json.loads(row[0]))
            except Exception: pass
        cursor = self._execute("SELECT value FROM settings WHERE key='password'")
        row = cursor.fetchone()
        if row: settings["password"] = row[0]
        cursor = self._execute("SELECT value FROM settings WHERE key='session'")
        row = cursor.fetchone()
        if row:
            try:
                session_data = json.loads(row[0])
                settings["session_token"] = session_data.get("token")
                settings["session_expiry"] = session_data.get("expiry")
            except Exception: pass
        cursor = self._execute("SELECT value FROM settings WHERE key='update_url'")
        row = cursor.fetchone()
        if row: settings["update_url"] = row[0]
        cursor = self._execute("SELECT value FROM settings WHERE key='skipped_version'")
        row = cursor.fetchone()
        if row: settings["skipped_version"] = row[0]
        return settings

    def save_password(self, password):
        self._execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("password", password if password else ""),
        )

    def save_session(self, token, expiry):
        self._execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("session", json.dumps({"token": token, "expiry": expiry})),
        )

    def clear_session(self):
        self._execute("DELETE FROM settings WHERE key='session'")

    def save_update_url(self, url):
        self._execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("update_url", url or ""),
        )

    def save_skipped_version(self, version):
        self._execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("skipped_version", version or ""),
        )

    def save_bet(self, event_name, market_id, market_name, bet_type, selections, total_stake, potential_profit, status):
        self._execute(
            """
            INSERT INTO bet_history (
                placed_at, event_name, market_id, market_name,
                bet_type, selections, total_stake, potential_profit, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(),
                event_name,
                market_id,
                market_name,
                bet_type,
                json.dumps(selections),
                total_stake,
                potential_profit,
                status,
            ),
        )

    def get_recent_bets(self, limit=50):
        cursor = self._execute(
            "SELECT * FROM bet_history ORDER BY placed_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_today_profit_loss(self):
        today = datetime.now().date().isoformat()
        cursor = self._execute(
            """
            SELECT COALESCE(SUM(potential_profit), 0) AS pl
            FROM bet_history
            WHERE substr(placed_at, 1, 10) = ?
              AND status IN ('MATCHED', 'PARTIALLY_MATCHED')
            """,
            (today,),
        )
        row = cursor.fetchone()
        return float(row["pl"]) if row and row["pl"] is not None else 0.0

    def get_active_bets_count(self):
        cursor = self._execute(
            """
            SELECT COUNT(*) AS cnt
            FROM bet_history
            WHERE status IN ('MATCHED', 'PARTIALLY_MATCHED', 'PENDING', 'UNMATCHED')
            """
        )
        row = cursor.fetchone()
        return int(row["cnt"]) if row else 0

    def get_simulation_settings(self):
        cursor = self._execute(
            "SELECT value FROM settings WHERE key='simulation_settings'"
        )
        row = cursor.fetchone()
        if row:
            try: return json.loads(row[0])
            except Exception: pass
        return {
            "starting_balance": 10000.0,
            "virtual_balance": 10000.0,
            "bet_count": 0,
        }

    def save_simulation_settings(self, settings):
        self._execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("simulation_settings", json.dumps(settings)),
        )

    def increment_simulation_bet_count(self, new_balance):
        s = self.get_simulation_settings()
        s["virtual_balance"] = float(new_balance)
        s["bet_count"] = int(s.get("bet_count", 0)) + 1
        self.save_simulation_settings(s)

    def save_simulation_bet(
        self,
        event_name,
        market_id,
        market_name,
        side,
        selection_id=None,
        selection_name=None,
        price=None,
        stake=None,
        status="MATCHED",
        selections=None,
        total_stake=None,
        potential_profit=None,
    ):
        self._execute(
            """
            INSERT INTO simulation_bet_history (
                placed_at, event_name, market_id, market_name,
                side, selection_id, selection_name, price, stake,
                status, selections, total_stake, potential_profit
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(),
                event_name,
                market_id,
                market_name,
                side,
                str(selection_id) if selection_id is not None else None,
                selection_name,
                price,
                stake,
                status,
                json.dumps(selections) if selections is not None else None,
                total_stake,
                potential_profit,
            ),
        )

    def get_simulation_bets(self, limit=50):
        cursor = self._execute(
            "SELECT * FROM simulation_bet_history ORDER BY placed_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def save_cashout_transaction(
        self,
        market_id,
        selection_id,
        original_bet_id,
        cashout_bet_id,
        original_side,
        original_stake,
        original_price,
        cashout_side,
        cashout_stake,
        cashout_price,
        profit_loss,
    ):
        self._execute(
            """
            INSERT INTO cashout_history (
                created_at, market_id, selection_id, original_bet_id,
                cashout_bet_id, original_side, original_stake, original_price,
                cashout_side, cashout_stake, cashout_price, profit_loss
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(),
                market_id,
                str(selection_id),
                original_bet_id,
                cashout_bet_id,
                original_side,
                original_stake,
                original_price,
                cashout_side,
                cashout_stake,
                cashout_price,
                profit_loss,
            ),
        )

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            try:
                self._local.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._local.conn.close()
                self._local.conn = None
            except Exception:
                pass

