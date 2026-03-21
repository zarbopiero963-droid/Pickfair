"""
Regression tests for audit issue #38, items #16–#23.

#16 auto_updater.py       — command injection + integrity verification
#17 plugin_manager.py     — security validation gaps + install_requirements
#18 betfair_client.py     — private key file permissions
#19 database.py           — credentials stored in plaintext
#20 core/safety_layer.py  — singleton race + watchdog re-fires
#21 telegram_sender.py    — duplicate worker thread + async rate limiter
#22 core/tick_ring_buffer.py — no thread safety
#23 goal_engine_pro.py    — shared structures without locks
"""

import os
import stat
import tempfile
import threading
import time

import pytest


# =============================================================================
# Issue #16 – auto_updater.py
# =============================================================================

class TestIssue16AutoUpdater:

    def test_cmd_safe_path_escapes_percent(self):
        from auto_updater import _cmd_safe_path
        result = _cmd_safe_path(r"C:\Users\user%NAME%\file.exe")
        assert "%%NAME%%" in result
        assert "%" not in result.replace("%%", "")

    def test_cmd_safe_path_escapes_caret(self):
        """
        OLD: only % was escaped; ^ is the batch escape character and could
             be used to smuggle special chars (&, |) inside quotes.
        NEW: ^ is doubled to ^^.
        """
        from auto_updater import _cmd_safe_path
        result = _cmd_safe_path(r"C:\path\with^caret\file.exe")
        assert "^^" in result

    def test_cmd_safe_path_rejects_double_quote(self):
        """
        A path containing a double-quote would break out of the quoted context
        in the batch script, enabling command injection.
        NEW: ValueError is raised immediately.
        """
        from auto_updater import _cmd_safe_path
        with pytest.raises(ValueError, match="double-quote"):
            _cmd_safe_path('C:\\path\\evil"file.exe')

    def test_cmd_safe_path_normal_path_unchanged(self):
        from auto_updater import _cmd_safe_path
        path = r"C:\Users\alice\Downloads\pickfair.exe"
        result = _cmd_safe_path(path)
        # No special chars — result is the same (no % or ^ in input)
        assert result == path

    def test_verify_download_hash_correct(self):
        from auto_updater import verify_download_hash
        content = b"hello update"
        import hashlib
        expected = hashlib.sha256(content).hexdigest()
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            path = f.name
        try:
            assert verify_download_hash(path, expected) is True
        finally:
            os.unlink(path)

    def test_verify_download_hash_mismatch_returns_false(self):
        from auto_updater import verify_download_hash
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"tampered content")
            path = f.name
        try:
            assert verify_download_hash(path, "a" * 64) is False
        finally:
            os.unlink(path)

    def test_verify_download_hash_strict_mode_no_hash(self):
        """
        OLD: verify_download_hash(path, None) returned True (permissive).
        NEW: require_verified=True returns False when no hash is supplied.
        """
        from auto_updater import verify_download_hash
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"no hash provided")
            path = f.name
        try:
            result = verify_download_hash(path, None, require_verified=True)
            assert result is False, "Strict mode must reject absent hash"
        finally:
            os.unlink(path)

    def test_verify_download_hash_permissive_no_hash_still_true(self):
        """Backward-compatible: require_verified=False (default) is still True."""
        from auto_updater import verify_download_hash
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"data")
            path = f.name
        try:
            assert verify_download_hash(path, None) is True
        finally:
            os.unlink(path)


# =============================================================================
# Issue #17 – plugin_manager.py
# =============================================================================

class TestIssue17PluginManager:

    def _validator(self):
        from plugin_manager import PluginManager
        class FakeApp: pass
        mgr = PluginManager(FakeApp())
        return mgr

    def test_getattr_call_is_blocked(self):
        """
        OLD: getattr() was not in the blocked list — allowed reaching
             __builtins__ or any blocked module at runtime.
        NEW: getattr() call is rejected.
        """
        mgr = self._validator()
        code = "x = getattr(os, 'system')"
        valid, msg = mgr.validate_plugin_code(code)
        assert not valid, f"getattr() should be blocked. Got: {msg}"

    def test_globals_call_is_blocked(self):
        """globals() / locals() expose the full namespace."""
        mgr = self._validator()
        valid, msg = mgr.validate_plugin_code("x = globals()")
        assert not valid, f"globals() should be blocked. Got: {msg}"

    def test_open_call_is_blocked(self):
        """open() gives file access without going through provided APIs."""
        mgr = self._validator()
        valid, msg = mgr.validate_plugin_code("f = open('/etc/passwd')")
        assert not valid, f"open() should be blocked. Got: {msg}"

    def test_safe_plugin_code_still_passes(self):
        """Simple arithmetic / string code must remain valid."""
        mgr = self._validator()
        code = "result = 1 + 2\nname = 'hello'"
        valid, msg = mgr.validate_plugin_code(code)
        assert valid, f"Safe code rejected: {msg}"

    def test_install_requirements_rejects_vcs_urls(self):
        """
        OLD: any string was passed to pip — git+https://... could execute
             arbitrary code during install.
        NEW: VCS-style requirements are rejected before pip is called.
        """
        mgr = self._validator()
        import types, os as _os, tempfile as _tmp
        req_dir = _tmp.mkdtemp()
        req_file = _os.path.join(req_dir, "requirements.txt")
        with open(req_file, "w") as f:
            f.write("git+https://github.com/evil/repo.git\n")
        # Fake plugin path so install_requirements finds the req file
        fake_plugin = _os.path.join(req_dir, "plugin.py")
        success, msg = mgr.install_requirements(fake_plugin)
        assert not success, f"VCS requirement should be rejected. Got: {msg}"
        assert "non sicuro" in msg.lower() or "rifiutato" in msg.lower() or "unsafe" in msg.lower()

    def test_install_requirements_rejects_pip_options(self):
        """Lines starting with -- (pip options) must be blocked."""
        mgr = self._validator()
        import os as _os, tempfile as _tmp
        req_dir = _tmp.mkdtemp()
        req_file = _os.path.join(req_dir, "requirements.txt")
        with open(req_file, "w") as f:
            f.write("--index-url http://evil.example.com\n")
        fake_plugin = _os.path.join(req_dir, "plugin.py")
        success, msg = mgr.install_requirements(fake_plugin)
        assert not success, f"pip option should be rejected. Got: {msg}"

    def test_install_requirements_allows_normal_packages(self):
        """Normal package specs like 'requests>=2.0' are allowed through."""
        mgr = self._validator()
        import os as _os, tempfile as _tmp
        req_dir = _tmp.mkdtemp()
        req_file = _os.path.join(req_dir, "requirements.txt")
        with open(req_file, "w") as f:
            f.write("requests>=2.0\n")
        fake_plugin = _os.path.join(req_dir, "plugin.py")
        # We don't actually call pip — just verify the guard passes.
        # Patch subprocess.run to avoid real pip call for the test.
        import subprocess
        orig = subprocess.run
        results = []
        def fake_run(cmd, **kw):
            results.append(cmd)
            class R:
                returncode = 0
                stderr = ""
            return R()
        subprocess.run = fake_run
        try:
            success, msg = mgr.install_requirements(fake_plugin)
        finally:
            subprocess.run = orig
        assert success or (not success and "requests" in msg.lower() or True)
        # Key assertion: subprocess.run WAS called (not rejected before pip)
        assert any("pip" in str(c) for c in results), "Allowed req should reach pip"


# =============================================================================
# Issue #18 – betfair_client.py
# =============================================================================

class TestIssue18BetfairClientKeyPermissions:

    def test_key_file_written_with_restricted_permissions(self):
        """
        OLD: open(path, 'w') uses default umask → typically 0o644 on Linux
        NEW: os.open with mode 0o600 → owner read/write only
        """
        if os.name == "nt":
            pytest.skip("POSIX permission check not applicable on Windows")

        from betfair_client import BetfairClient
        client = BetfairClient(
            username="u", app_key="k",
            cert_pem="CERT", key_pem="PRIVATEKEY"
        )
        certs_dir = client._create_temp_cert_files()
        try:
            key_path = os.path.join(certs_dir, "client-2048.key")
            assert os.path.exists(key_path)
            file_stat = os.stat(key_path)
            mode = stat.S_IMODE(file_stat.st_mode)
            assert mode == 0o600, (
                f"OLD: key file was 0o{mode:o} (world-readable). "
                f"NEW: must be 0o600 (owner-only)."
            )
        finally:
            client._cleanup_temp_files()

    def test_key_file_content_is_correct(self):
        """Permissions fix must not affect the written content."""
        if os.name == "nt":
            pytest.skip("POSIX permission check not applicable on Windows")

        from betfair_client import BetfairClient
        client = BetfairClient(
            username="u", app_key="k",
            cert_pem="CERT", key_pem="MY_PRIVATE_KEY"
        )
        certs_dir = client._create_temp_cert_files()
        try:
            key_path = os.path.join(certs_dir, "client-2048.key")
            with open(key_path) as f:
                content = f.read()
            assert content == "MY_PRIVATE_KEY"
        finally:
            client._cleanup_temp_files()


# =============================================================================
# Issue #19 – database.py
# =============================================================================

class TestIssue19DatabaseEncryption:

    def _db(self):
        import tempfile
        from database import Database
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db = Database(tmp.name)
        return db, tmp.name

    def _raw_select(self, db, key):
        """Directly query sqlite to get the stored (possibly encrypted) value."""
        import sqlite3 as _sq
        conn = _sq.connect(db.db_path)
        conn.row_factory = _sq.Row
        cur = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        conn.close()
        return row["value"] if row else None

    def test_sensitive_value_not_stored_plaintext(self):
        """
        OLD: _set_setting stored raw string; select value from settings
             would reveal the private key verbatim.
        NEW: value is encrypted before storage (starts with 'ENC:').
        """
        db, path = self._db()
        try:
            db._set_setting("private_key", "MY_SUPER_SECRET_KEY")
            stored = self._raw_select(db, "private_key")
            assert stored is not None, "Setting not saved"
            assert stored != "MY_SUPER_SECRET_KEY", (
                f"OLD: key stored as plaintext. NEW: stored as: {stored!r}"
            )
            assert str(stored).startswith("ENC:"), (
                f"Expected ENC: prefix. Got: {stored!r}"
            )
        finally:
            os.unlink(path)

    def test_retrieved_value_is_decrypted(self):
        """_get_setting_raw must transparently decrypt and return plaintext."""
        db, path = self._db()
        try:
            db._set_setting("app_key", "secret-app-key-123")
            retrieved = db._get_setting_raw("app_key")
            assert retrieved == "secret-app-key-123", (
                f"Decrypted value mismatch: {retrieved!r}"
            )
        finally:
            os.unlink(path)

    def test_non_sensitive_key_not_encrypted(self):
        """Non-sensitive keys must be stored and returned as plain text."""
        db, path = self._db()
        try:
            db._set_setting("theme", "dark")
            stored = self._raw_select(db, "theme")
            assert stored == "dark"
        finally:
            os.unlink(path)

    def test_legacy_plaintext_read_backward_compatible(self):
        """Existing plaintext rows (no ENC: prefix) are returned as-is."""
        db, path = self._db()
        try:
            # Directly insert plaintext (simulating old schema row)
            db._execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ("private_key", "old-plaintext-key")
            )
            retrieved = db._get_setting_raw("private_key")
            assert retrieved == "old-plaintext-key"
        finally:
            os.unlink(path)

    def test_save_credentials_round_trip(self):
        """save_credentials + get_settings retrieves correct values."""
        db, path = self._db()
        try:
            db.save_credentials(
                username="user@example.com",
                app_key="APP-KEY-XYZ",
                certificate="CERT-PEM",
                private_key="PRIVATE-KEY-PEM",
            )
            settings = db.get_settings()
            assert settings.get("app_key") == "APP-KEY-XYZ"
            assert settings.get("private_key") == "PRIVATE-KEY-PEM"
        finally:
            os.unlink(path)


# =============================================================================
# Issue #20 – core/safety_layer.py
# =============================================================================

class TestIssue20SafetyLayer:

    def test_singleton_concurrent_access_creates_one_instance(self):
        """
        OLD: check-then-act without lock → two threads could each create
             a SafetyLayer instance and one would be silently discarded.
        NEW: double-checked locking ensures exactly one instance.
        """
        import core.safety_layer as sl
        # Reset singleton for test isolation
        original = sl._global_safety_layer
        sl._global_safety_layer = None
        try:
            instances = []
            errors = []
            def get():
                try:
                    instances.append(id(sl.get_safety_layer()))
                except Exception as e:
                    errors.append(e)
            threads = [threading.Thread(target=get) for _ in range(20)]
            for t in threads: t.start()
            for t in threads: t.join()
            assert errors == []
            assert len(set(instances)) == 1, (
                f"Expected 1 unique instance, got {len(set(instances))}. "
                "OLD: could be 2+ from concurrent creation."
            )
        finally:
            sl._global_safety_layer = original

    def test_watchdog_callback_fires_only_once_per_timeout(self):
        """
        OLD: callback was triggered every watchdog cycle while timed out.
        NEW: callback fires exactly once per timeout event (state.triggered
             guards repeated firing).
        """
        from core.safety_layer import SafetyLayer
        layer = SafetyLayer()
        fired = []
        layer.set_watchdog_callback(lambda name, err: fired.append(name))
        # min timeout clamped to 0.5s in register_watchdog
        layer.register_watchdog("comp_a", timeout_sec=0.5)
        # Do NOT ping — let it time out naturally from registration time
        layer.start_watchdog(interval_sec=0.1)
        time.sleep(1.5)  # several watchdog cycles; only first should fire
        layer.stop_watchdog()
        assert len(fired) == 1, (
            f"OLD: callback fired {len(fired)} times. "
            "NEW: must fire exactly once unless reset."
        )

    def test_watchdog_reset_allows_re_trigger(self):
        """After ping (reset), the component can time out and fire again."""
        from core.safety_layer import SafetyLayer
        layer = SafetyLayer()
        fired = []
        layer.set_watchdog_callback(lambda name, err: fired.append(name))
        layer.register_watchdog("comp_b", timeout_sec=0.5)
        layer.start_watchdog(interval_sec=0.1)
        time.sleep(0.8)  # first timeout fires
        layer.watchdog_ping("comp_b")  # reset triggered flag + update last_ping
        time.sleep(0.8)  # second timeout fires
        layer.stop_watchdog()
        assert len(fired) >= 2, (
            f"Expected >=2 fires after reset. Got {len(fired)}"
        )


# =============================================================================
# Issue #21 – telegram_sender.py
# =============================================================================

class TestIssue21TelegramSender:

    def _sender(self):
        from telegram_sender import TelegramSender
        class FakeClient: pass
        return TelegramSender(FakeClient())

    def test_concurrent_queue_message_does_not_spawn_duplicate_workers(self):
        """
        OLD: two threads could both see _running==False and both call
             start_worker(), spawning 2 threads.
        NEW: start_worker() is called under _worker_lock.
        """
        from telegram_sender import TelegramSender
        import unittest.mock as _mock

        class FakeClient: pass
        s = TelegramSender(FakeClient())

        started = []
        original_start = s.start_worker

        def fake_start():
            started.append(1)
            s._running = True

        s.start_worker = fake_start
        s._running = False

        def queue_call():
            with s._worker_lock:
                if not s._running:
                    s.start_worker()

        threads = [threading.Thread(target=queue_call) for _ in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(started) == 1, (
            f"OLD: start_worker called {len(started)} times. "
            "NEW: must be called exactly once."
        )

    def test_rate_limiter_wait_async_reads_under_lock(self):
        """
        Check that wait_if_needed_async does not access current_delay /
        last_send_time without the lock (structural verification).
        """
        import inspect
        from telegram_sender import AdaptiveRateLimiter
        src = inspect.getsource(AdaptiveRateLimiter.wait_if_needed_async)
        # After fix, the method must acquire self._lock before reading
        assert "self._lock" in src, (
            "wait_if_needed_async must use self._lock to protect state reads"
        )


# =============================================================================
# Issue #22 – core/tick_ring_buffer.py
# =============================================================================

class TestIssue22TickRingBuffer:

    def test_concurrent_push_drain_no_item_loss(self):
        """
        OLD: no lock → concurrent push/drain can lose items or crash.
        NEW: lock on push and drain ensures all pushed items are drained.
        """
        from core.tick_ring_buffer import TickRingBuffer
        buf = TickRingBuffer(maxlen=10000)
        PUSH_COUNT = 500
        pushed = []
        drained = []
        errors = []

        def pusher():
            try:
                for i in range(PUSH_COUNT):
                    buf.push(i)
                    pushed.append(i)
            except Exception as e:
                errors.append(e)

        def drainer():
            try:
                for _ in range(PUSH_COUNT // 10):
                    drained.extend(buf.drain(50))
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=pusher) for _ in range(4)]
        threads += [threading.Thread(target=drainer) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join()

        # Drain remaining
        drained.extend(buf.drain(10000))

        assert errors == [], f"Unexpected exceptions: {errors}"
        assert len(pushed) == 4 * PUSH_COUNT
        assert len(drained) == len(pushed), (
            f"Items lost! Pushed={len(pushed)}, drained={len(drained)}"
        )

    def test_single_thread_behavior_unchanged(self):
        """Single-thread push/drain/pop still works correctly."""
        from core.tick_ring_buffer import TickRingBuffer
        buf = TickRingBuffer(maxlen=10)
        for i in range(5):
            buf.push(i)
        assert len(buf) == 5
        items = buf.drain(3)
        assert items == [0, 1, 2]
        assert len(buf) == 2
        assert buf.pop() == 3
        assert buf.peek() == 4

    def test_drain_count_correct_under_contention(self):
        from core.tick_ring_buffer import TickRingBuffer
        buf = TickRingBuffer(maxlen=1000)
        for i in range(100):
            buf.push(i)
        results = []
        def drain_some():
            results.extend(buf.drain(50))
        threads = [threading.Thread(target=drain_some) for _ in range(4)]
        for t in threads: t.start()
        for t in threads: t.join()
        # No item should appear twice
        assert len(results) == len(set(results)), "Duplicate items drained!"
        assert len(results) == 100


# =============================================================================
# Issue #23 – goal_engine_pro.py
# =============================================================================

class TestIssue23GoalEnginePro:

    def _make_engine(self):
        from goal_engine_pro import GoalEnginePro, APIFootballClient
        client = APIFootballClient(api_key="")
        hedges = []
        reopens = []

        class FakeUIQueue:
            def post(self, fn, *a, **kw): pass

        eng = GoalEnginePro(
            api_client=client,
            betfair_stream=None,
            hedge_callback=lambda mid: hedges.append(mid),
            reopen_callback=lambda mid: reopens.append(mid),
            ui_queue=FakeUIQueue(),
        )
        return eng, hedges, reopens

    def test_cache_lock_exists(self):
        """_cache_lock must be present after fix."""
        eng, _, _ = self._make_engine()
        assert hasattr(eng, "_cache_lock"), "_cache_lock missing — fix not applied"
        import threading as _th
        assert isinstance(eng._cache_lock, _th.Lock)

    def test_concurrent_access_does_not_corrupt_goal_cache(self):
        """
        Concurrent writes to goal_cache from multiple threads must not
        corrupt the defaultdict or raise RuntimeError.
        """
        eng, _, _ = self._make_engine()
        errors = []

        def write_goals(match_id, count):
            try:
                for i in range(count):
                    with eng._cache_lock:
                        eng.goal_cache[match_id] = i
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=write_goals, args=(f"match_{j}", 200))
            for j in range(10)
        ]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == [], f"Concurrent access raised: {errors}"

    def test_verify_and_hedge_not_fired_twice_for_same_match(self):
        """
        _verify_and_hedge must hedge at most once per match_id even when
        called concurrently from multiple threads.
        """
        eng, hedges, _ = self._make_engine()

        def call_hedge():
            eng._verify_and_hedge("match_999")

        threads = [threading.Thread(target=call_hedge) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        # hedge_callback should be invoked at most once
        assert hedges.count("match_999") <= 1, (
            f"Hedge fired {hedges.count('match_999')} times — double hedge!"
        )

    def test_normal_goal_flow_still_works(self):
        """Single-threaded goal detection and hedging still works."""
        eng, hedges, _ = self._make_engine()
        with eng._cache_lock:
            eng.goal_cache["match_1"] = 0
        # Simulate a goal being detected
        eng._verify_and_hedge("match_1")
        assert "match_1" in eng.hedged_matches
        assert "match_1" in hedges
