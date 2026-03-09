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

            # FIX: il savepoint va sempre chiuso correttamente
            conn.execute(f"RELEASE {sp_name}")

            # Il commit reale solo al livello top se richiesto
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
    # CORE SETTINGS
    # =========================
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
            try:
                settings.update(json.loads(row[0]))
            except Exception:
                pass

        cursor = self._execute("SELECT value FROM settings WHERE key='password'")
        row = cursor.fetchone()
        if row:
            settings["password"] = row[0]

        cursor = self._execute("SELECT value FROM settings WHERE key='session'")
        row = cursor.fetchone()
        if row:
            try:
                session_data = json.loads(row[0])
                settings["session_token"] = session_data.get("token")
                settings["session_expiry"] = session_data.get("expiry")
            except Exception:
                pass

        cursor = self._execute("SELECT value FROM settings WHERE key='update_url'")
        row = cursor.fetchone()
        if row:
            settings["update_url"] = row[0]

        cursor = self._execute("SELECT value FROM settings WHERE key='skipped_version'")
        row = cursor.fetchone()
        if row:
            settings["skipped_version"] = row[0]

        return settings

    def save_password(self, password):
        self._execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("password", password if password else "")
        )

    def save_session(self, token, expiry):
        self._execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("session", json.dumps({"token": token, "expiry": expiry}))
        )

    def clear_session(self):
        self._execute("DELETE FROM settings WHERE key='session'")

    def save_update_url(self, url):
        self._execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("update_url", url or "")
        )

    def save_skipped_version(self, version):
        self._execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("skipped_version", version or "")
        )

    # =========================
    # OMS / SAGA
    # =========================
    def create_pending_saga(self, customer_ref, market_id, selection_id, payload_dict):
        payload_str = json.dumps(payload_dict, sort_keys=True)
        payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()
        self._execute(
            """
            INSERT INTO order_saga (customer_ref, market_id, selection_id, payload_hash, raw_payload, status)
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
        cursor = self._execute("""
            SELECT customer_ref, market_id, selection_id, raw_payload, status, created_at
            FROM order_saga
            WHERE status='PENDING'
            ORDER BY created_at ASC
        """)
        return [dict(row) for row in cursor.fetchall()]

    # =========================
    # TELEGRAM SETTINGS
    # =========================
    def get_telegram_settings(self):
        cursor = self._execute("SELECT * FROM telegram_settings WHERE id = 1")
        row = cursor.fetchone()
        if not row:
            return {}

        return {
            "api_id": row["api_id"] or "",
            "api_hash": row["api_hash"] or "",
            "session_string": row["session_string"] or "",
            "phone_number": row["phone_number"] or "",
            "enabled": bool(row["enabled"]),
            "auto_bet": bool(row["auto_bet"]),
            "require_confirmation": bool(row["require_confirmation"]),
            "auto_stake": float(row["auto_stake"] or 1.0),
        }

    def save_telegram_settings(self, settings: dict):
        current = self.get_telegram_settings()
        merged = {
            "api_id": settings.get("api_id", current.get("api_id", "")),
            "api_hash": settings.get("api_hash", current.get("api_hash", "")),
            "session_string": settings.get("session_string", current.get("session_string", "")),
            "phone_number": settings.get("phone_number", current.get("phone_number", "")),
            "enabled": 1 if settings.get("enabled", current.get("enabled", False)) else 0,
            "auto_bet": 1 if settings.get("auto_bet", current.get("auto_bet", False)) else 0,
            "require_confirmation": 1 if settings.get("require_confirmation", current.get("require_confirmation", True)) else 0,
            "auto_stake": float(settings.get("auto_stake", current.get("auto_stake", 1.0) or 1.0)),
        }

        self._execute(
            """
            INSERT INTO telegram_settings (
                id, api_id, api_hash, session_string, phone_number,
                enabled, auto_bet, require_confirmation, auto_stake
            )
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                api_id = excluded.api_id,
                api_hash = excluded.api_hash,
                session_string = excluded.session_string,
                phone_number = excluded.phone_number,
                enabled = excluded.enabled,
                auto_bet = excluded.auto_bet,
                require_confirmation = excluded.require_confirmation,
                auto_stake = excluded.auto_stake
            """,
            (
                merged["api_id"],
                merged["api_hash"],
                merged["session_string"],
                merged["phone_number"],
                merged["enabled"],
                merged["auto_bet"],
                merged["require_confirmation"],
                merged["auto_stake"],
            ),
        )

    # =========================
    # TELEGRAM CHATS
    # =========================
    def get_telegram_chats(self):
        cursor = self._execute("SELECT * FROM telegram_chats ORDER BY created_at DESC")
        return [
            {
                "chat_id": row["chat_id"],
                "title": row["title"] or "",
                "username": row["username"] or "",
                "is_active": bool(row["is_active"]),
                "created_at": row["created_at"],
            }
            for row in cursor.fetchall()
        ]

    def save_telegram_chat(self, chat_id, title="", username="", is_active=True):
        self._execute(
            """
            INSERT INTO telegram_chats (chat_id, title, username, is_active)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                title = excluded.title,
                username = excluded.username,
                is_active = excluded.is_active
            """,
            (str(chat_id), title or "", username or "", 1 if is_active else 0),
        )

    def replace_telegram_chats(self, chats: list):
        self._execute("DELETE FROM telegram_chats")
        for chat in chats:
            self.save_telegram_chat(
                chat_id=chat.get("chat_id"),
                title=chat.get("title", ""),
                username=chat.get("username", ""),
                is_active=chat.get("is_active", True),
            )

    def delete_telegram_chat(self, chat_id):
        self._execute("DELETE FROM telegram_chats WHERE chat_id = ?", (str(chat_id),))

    # =========================
    # SIGNAL PATTERNS & HISTORY
    # =========================
    def get_signal_patterns(self):
        cursor = self._execute("SELECT * FROM signal_patterns ORDER BY id DESC")
        return [
            {
                "id": row["id"],
                "pattern": row["pattern"],
                "label": row["label"] or "",
                "enabled": bool(row["enabled"]),
                "created_at": row["created_at"],
            }
            for row in cursor.fetchall()
        ]

    def save_signal_pattern(self, pattern, label="", enabled=True):
        self._execute(
            "INSERT INTO signal_patterns (pattern, label, enabled) VALUES (?, ?, ?)",
            (pattern, label or "", 1 if enabled else 0),
        )

    def delete_signal_pattern(self, pattern_id):
        self._execute("DELETE FROM signal_patterns WHERE id = ?", (int(pattern_id),))

    def update_signal_pattern(self, pattern_id, pattern=None, label=None, enabled=None):
        cursor = self._execute("SELECT * FROM signal_patterns WHERE id = ?", (int(pattern_id),))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Signal pattern non trovato: {pattern_id}")

        new_pattern = row["pattern"] if pattern is None else pattern
        new_label = row["label"] if label is None else (label or "")
        new_enabled = row["enabled"] if enabled is None else (1 if enabled else 0)

        self._execute(
            "UPDATE signal_patterns SET pattern = ?, label = ?, enabled = ? WHERE id = ?",
            (new_pattern, new_label, new_enabled, int(pattern_id)),
        )

    def toggle_signal_pattern(self, pattern_id):
        cursor = self._execute("SELECT enabled FROM signal_patterns WHERE id = ?", (int(pattern_id),))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Pattern non trovato: {pattern_id}")

        new_enabled = 0 if int(row["enabled"]) == 1 else 1
        self._execute(
            "UPDATE signal_patterns SET enabled = ? WHERE id = ?",
            (new_enabled, int(pattern_id)),
        )
        return bool(new_enabled)

    def save_received_signal(self, selection, action, price, stake, status="PENDING"):
        self._execute(
            "INSERT INTO telegram_signals (selection, action, price, stake, status) VALUES (?, ?, ?, ?, ?)",
            (selection, action, price, stake, status),
        )

    def get_received_signals(self, limit=50):
        cursor = self._execute(
            "SELECT * FROM telegram_signals ORDER BY received_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def clear_received_signals(self):
        self._execute("DELETE FROM telegram_signals")

    # =========================
    # BET HISTORY (REAL)
    # =========================
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

    def get_bet_history(self, limit=50):
        return self.get_recent_bets(limit=limit)

    def get_today_profit_loss(self):
        today = datetime.now().date().isoformat()
        cursor = self._execute("""
            SELECT COALESCE(SUM(potential_profit), 0) AS pl
            FROM bet_history
            WHERE substr(placed_at, 1, 10) = ?
              AND status IN ('MATCHED', 'PARTIALLY_MATCHED')
        """, (today,))
        row = cursor.fetchone()
        return float(row["pl"]) if row and row["pl"] is not None else 0.0

    def get_active_bets_count(self):
        cursor = self._execute("""
            SELECT COUNT(*) AS cnt
            FROM bet_history
            WHERE status IN ('MATCHED', 'PARTIALLY_MATCHED', 'PENDING', 'UNMATCHED')
        """)
        row = cursor.fetchone()
        return int(row["cnt"]) if row else 0

    # =========================
    # SIMULATION
    # =========================
    def get_simulation_settings(self):
        cursor = self._execute("SELECT value FROM settings WHERE key='simulation_settings'")
        row = cursor.fetchone()
        if row:
            try:
                return json.loads(row[0])
            except Exception:
                pass
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
        settings = self.get_simulation_settings()
        settings["virtual_balance"] = float(new_balance)
        settings["bet_count"] = int(settings.get("bet_count", 0)) + 1
        self.save_simulation_settings(settings)

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

    def add_simulated_bet(
        self,
        market_id,
        selection_id,
        runner_name,
        side,
        price,
        stake,
        event_name="",
        market_name="",
        status="MATCHED",
    ):
        self.save_simulation_bet(
            event_name=event_name,
            market_id=market_id,
            market_name=market_name,
            side=side,
            selection_id=selection_id,
            selection_name=runner_name,
            price=price,
            stake=stake,
            status=status,
        )

    def get_simulation_bets(self, limit=50):
        cursor = self._execute(
            "SELECT * FROM simulation_bet_history ORDER BY placed_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_simulation_bet_history(self, limit=50):
        return self.get_simulation_bets(limit=limit)

    # =========================
    # CASHOUT
    # =========================
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

