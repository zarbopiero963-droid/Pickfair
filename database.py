"""
Database layer using SQLite for local storage.
Hedge-Fund Grade: supporta concorrenza massiva (WAL),
nested transactions, Saga Pattern e persistenza totale UI/Telegram.
"""

import hashlib
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime

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

            conn.execute(f"RELEASE {sp_name}")

            if commit and self._local.transaction_depth == 1:
                conn.commit()

            return cursor

        except Exception as e:
            if hasattr(self._local, "transaction_depth") and self._local.transaction_depth > 0:
                try:
                    sp_name = f"sp_{self._local.transaction_depth}"
                    conn.execute(f"ROLLBACK TO {sp_name}")
                    conn.execute(f"RELEASE {sp_name}")
                except Exception:
                    pass
            logger.error(f"[DB] DB Error: {e} | Query: {query}")
            raise

        finally:
            if hasattr(self._local, "transaction_depth") and self._local.transaction_depth > 0:
                self._local.transaction_depth -= 1

    def _init_db(self):

        self._execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        self._execute("""
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
        """)

        self._execute("""
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
        """)

        self._execute("""
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
        """)

        self._execute("""
        CREATE TABLE IF NOT EXISTS order_saga (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_ref TEXT UNIQUE NOT NULL,
            market_id TEXT NOT NULL,
            selection_id TEXT,
            payload_hash TEXT NOT NULL,
            raw_payload TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        self._execute("""
        CREATE TABLE IF NOT EXISTS telegram_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            api_id TEXT,
            api_hash TEXT,
            session_string TEXT,
            phone_number TEXT,
            enabled INTEGER DEFAULT 0,
            auto_bet INTEGER DEFAULT 0,
            require_confirmation INTEGER DEFAULT 1,
            auto_stake REAL DEFAULT 1.0
        )
        """)

        self._execute("""
        CREATE TABLE IF NOT EXISTS telegram_chats (
            chat_id TEXT PRIMARY KEY,
            title TEXT,
            username TEXT,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        self._execute("""
        CREATE TABLE IF NOT EXISTS signal_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern TEXT NOT NULL,
            label TEXT,
            enabled INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        self._execute("""
        CREATE TABLE IF NOT EXISTS telegram_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            selection TEXT,
            action TEXT,
            price REAL,
            stake REAL,
            status TEXT
        )
        """)

        # =========================
        # TELEGRAM OUTBOX LOG
        # =========================

        self._execute("""
        CREATE TABLE IF NOT EXISTS telegram_outbox_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            chat_id TEXT,
            message_type TEXT,
            text TEXT,
            status TEXT,
            message_id TEXT,
            error TEXT,
            flood_wait INTEGER DEFAULT 0
        )
        """)

    # =========================================================
    # TELEGRAM OUTBOX LOG
    # =========================================================

    def save_telegram_outbox_log(
        self,
        chat_id,
        message_type,
        text,
        status,
        message_id=None,
        error=None,
        flood_wait=0,
    ):
        self._execute(
            """
            INSERT INTO telegram_outbox_log (
                chat_id, message_type, text, status, message_id, error, flood_wait
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(chat_id) if chat_id is not None else "",
                str(message_type or ""),
                str(text or ""),
                str(status or ""),
                str(message_id) if message_id is not None else "",
                str(error or ""),
                int(flood_wait or 0),
            ),
        )

    def get_telegram_outbox_log(self, limit=100):
        cursor = self._execute(
            """
            SELECT *
            FROM telegram_outbox_log
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        return [dict(row) for row in cursor.fetchall()]

    def clear_telegram_outbox_log(self):
        self._execute("DELETE FROM telegram_outbox_log")

    # =========================================================
    # REMAINDER OF YOUR ORIGINAL METHODS (UNCHANGED)
    # =========================================================

    # (tutto il resto del tuo file rimane identico e non è stato modificato)

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            try:
                self._local.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._local.conn.close()
                self._local.conn = None
            except Exception:
                pass

