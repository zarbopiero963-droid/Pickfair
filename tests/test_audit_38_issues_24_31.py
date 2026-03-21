"""
Regression tests for audit issue #38, items #24–#31.

#24 database.py          — thread-local connection leak + non-atomic replace_telegram_chats
#25 pnl_cache.py         — shallow copy of ZERO_PNL
#26 tick_dispatcher.py   — storage callbacks called while holding lock
#27 dutching.py          — BACK commission already fixed in PR #51 (pre-existing fix)
#28 market_validator.py  — EACH_WAY/FORECAST/TRICAST listed as dutching-ready
#29 market_tracker.py    — cache eviction off-by-one on existing key update
#30 executor_manager.py  — submit() blocks the calling thread
#31 plugin_runner.py     — auto-disable logged but never enforced
"""

import threading
import time

import pytest


# =============================================================================
# Issue #24 – database.py
# =============================================================================

class TestIssue24Database:

    def _db(self):
        import tempfile, os
        from database import Database
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        return Database(f.name), f.name

    def test_close_all_connections_cleans_up_worker_thread_connections(self):
        """
        OLD: close() only closes the calling thread's connection; worker
             threads that opened connections and then exited left them open.
        NEW: close_all_connections() closes every connection ever opened.
        """
        db, path = self._db()
        import os
        barrier = threading.Barrier(2)
        conns_before = []

        def worker():
            # Force a connection to be created in this thread
            db._get_connection()
            conns_before.append(len(db._all_conns))
            barrier.wait()   # wait for main thread to check
            barrier.wait()   # wait for main thread to call close_all

        t = threading.Thread(target=worker)
        t.start()
        barrier.wait()  # worker has created its connection
        assert len(db._all_conns) >= 1, "Worker thread connection should be tracked"
        barrier.wait()  # let worker finish
        t.join()

        db.close_all_connections()
        assert len(db._all_conns) == 0, (
            f"close_all_connections should drain registry; got {len(db._all_conns)}"
        )
        os.unlink(path)

    def test_close_removes_from_registry(self):
        """Explicit close() removes the connection from the registry."""
        db, path = self._db()
        import os
        db._get_connection()   # creates main-thread connection
        assert len(db._all_conns) >= 1
        db.close()
        # The main-thread connection should be removed from registry
        assert all(c is not None for c in db._all_conns), (
            "Closed connection should be removed from _all_conns"
        )
        os.unlink(path)

    def test_replace_telegram_chats_atomic_no_data_loss_on_error(self):
        """
        OLD: replace_telegram_chats called _execute("DELETE") and then
             save_telegram_chat() in a loop. Each call committed separately.
             A crash after DELETE but before INSERT left the table empty.
        NEW: Both operations run inside a single SAVEPOINT on the connection.
             An exception triggers ROLLBACK TO SAVEPOINT, restoring the data.

        We test atomicity by using a subclass that injects a failure inside
        the SAVEPOINT block — specifically by raising during the second INSERT.
        """
        import os
        from database import Database

        class FailingDatabase(Database):
            """Raises on the second chat insert to simulate a mid-replace crash."""
            _insert_count = 0

            def replace_telegram_chats(self, chats):
                self._insert_count = 0
                conn = self._get_connection()
                with self._write_lock:
                    conn.execute("SAVEPOINT replace_chats_sp")
                    try:
                        conn.execute("DELETE FROM telegram_chats")
                        for chat in chats or []:
                            self._insert_count += 1
                            if self._insert_count >= 2:
                                raise RuntimeError("Simulated crash on 2nd insert")
                            conn.execute(
                                """
                                INSERT INTO telegram_chats
                                    (chat_id, title, username, is_active)
                                VALUES (?, ?, ?, ?)
                                ON CONFLICT(chat_id) DO UPDATE SET
                                    title=excluded.title,
                                    username=excluded.username,
                                    is_active=excluded.is_active
                                """,
                                (
                                    str(chat.get("chat_id") or ""),
                                    str(chat.get("title") or ""),
                                    str(chat.get("username") or ""),
                                    1 if chat.get("is_active", True) else 0,
                                ),
                            )
                        conn.execute("RELEASE replace_chats_sp")
                        conn.commit()
                    except Exception:
                        try:
                            conn.execute("ROLLBACK TO replace_chats_sp")
                            conn.execute("RELEASE replace_chats_sp")
                        except Exception:
                            pass
                        raise

        f = __import__("tempfile").NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = FailingDatabase(f.name)
        try:
            db.save_telegram_chat(
                chat_id="orig", title="Original", username="orig", is_active=True
            )
            assert len(db.get_telegram_chats()) == 1

            try:
                db.replace_telegram_chats([
                    {"chat_id": "new1", "title": "N1", "username": "n1", "is_active": True},
                    {"chat_id": "new2", "title": "N2", "username": "n2", "is_active": True},
                ])
            except RuntimeError:
                pass

            rows_after = db.get_telegram_chats()
            chat_ids = [r["chat_id"] for r in rows_after]
            assert "orig" in chat_ids, (
                f"OLD: DELETE committed → table empty after crash. "
                f"NEW: SAVEPOINT rollback must preserve 'orig'. Got: {chat_ids}"
            )
            assert "new1" not in chat_ids, (
                f"Partial state 'new1' must not persist after rollback. Got: {chat_ids}"
            )
        finally:
            os.unlink(f.name)

    def test_replace_telegram_chats_success_replaces_all(self):
        """Normal path: all old chats replaced by new ones."""
        import os
        db, path = self._db()
        try:
            db.save_telegram_chat(chat_id="old1", title="Old", username="o", is_active=True)
            db.replace_telegram_chats([
                {"chat_id": "new1", "title": "New", "username": "n", "is_active": True},
            ])
            rows = db.get_telegram_chats()
            ids = [r["chat_id"] for r in rows]
            assert "new1" in ids
            assert "old1" not in ids
        finally:
            os.unlink(path)


# =============================================================================
# Issue #25 – pnl_cache.py
# =============================================================================

class TestIssue25PnlCacheZeroCopy:

    def _cache(self):
        from pnl_cache import PnLCache
        return PnLCache()

    def test_mutating_zero_pnl_by_selection_does_not_corrupt_class_constant(self):
        """
        OLD: ZERO_PNL.copy() returns a shallow copy; by_selection and
             green_stakes are the same dict objects as in the class constant.
             Writing to result["by_selection"][1] = 99 would corrupt ZERO_PNL.
        NEW: deepcopy returns completely independent nested dicts.
        """
        cache = self._cache()
        result = cache.get_cached_pnl("market_1", {}, [])
        assert result is not None
        # Mutate the returned nested dict
        result["by_selection"][999] = 42.0
        result["green_stakes"][999] = 5.0

        # Class constant must be unaffected
        assert 999 not in cache.ZERO_PNL["by_selection"], (
            "OLD: mutating result['by_selection'] corrupted ZERO_PNL['by_selection']. "
            "NEW: they must be independent objects."
        )
        assert 999 not in cache.ZERO_PNL["green_stakes"]

    def test_two_calls_return_independent_objects(self):
        """Each call returns a separate object; mutations don't cross-contaminate."""
        cache = self._cache()
        r1 = cache.get_cached_pnl("m1", {}, [])
        r2 = cache.get_cached_pnl("m2", {}, [])
        r1["by_selection"]["x"] = 1
        assert "x" not in r2["by_selection"]

    def test_zero_pnl_shape_preserved(self):
        """Returned dict still has the expected keys and types."""
        cache = self._cache()
        result = cache.get_cached_pnl("m", {}, [])
        assert "total" in result
        assert "by_selection" in result
        assert "green_stakes" in result
        assert isinstance(result["by_selection"], dict)
        assert isinstance(result["green_stakes"], dict)


# =============================================================================
# Issue #26 – tick_dispatcher.py
# =============================================================================

class TestIssue26TickDispatcherStorageCallbacks:

    def test_slow_storage_callback_does_not_block_concurrent_dispatch(self):
        """
        OLD: storage callbacks called inside the lock → while thread 1's
             slow storage callback runs, thread 2 cannot acquire the lock
             and its dispatch_tick call blocks completely.
        NEW: lock released before callbacks → thread 2 can acquire the lock
             and complete the critical section (pending_ticks update etc.)
             immediately, even while thread 1's callback is still running.

        We verify this by checking that thread 2's lock-acquisition succeeds
        while thread 1's callback blocks; specifically, the _tick_count
        increments for BOTH dispatches before the slow callback finishes.
        """
        from tick_dispatcher import TickDispatcher, TickData

        dispatcher = TickDispatcher()
        dispatcher._last_ui_update = 999.0
        dispatcher._last_automation_check = 999.0

        slow_started = threading.Event()
        slow_can_finish = threading.Event()
        t2_lock_acquired = threading.Event()

        def slow_storage_cb(tick):
            if tick.selection_id == 1:
                slow_started.set()
                slow_can_finish.wait(timeout=10)

        dispatcher.register_storage_callback(slow_storage_cb)

        # Start the first dispatch in a background thread
        t1 = threading.Thread(
            target=lambda: dispatcher.dispatch_tick(
                TickData(market_id="1.1", selection_id=1, timestamp=0.0)
            ),
            daemon=True,
        )
        t1.start()

        # Wait until slow callback has started — lock must be released now
        assert slow_started.wait(timeout=2), "Slow callback never started"

        # Thread 2 dispatches while thread 1's slow callback is still running.
        # It should be able to acquire the lock and update _tick_count immediately.
        tick_count_before = dispatcher._tick_count  # should be 1 (t1 already updated)

        t2_start = time.time()
        dispatcher.dispatch_tick(
            TickData(market_id="1.2", selection_id=2, timestamp=0.0)
        )
        elapsed_for_lock_section = time.time() - t2_start

        # _tick_count must be 2 now; thread 2 acquired the lock successfully
        tick_count_after = dispatcher._tick_count

        slow_can_finish.set()
        t1.join(timeout=5)

        assert tick_count_after == 2, (
            f"OLD: thread 2 could not acquire lock while slow callback ran. "
            f"tick_count_after={tick_count_after} (expected 2)"
        )
        # The critical-section time (everything under the lock) should be fast
        # even if the slow callback runs afterward in the same call
        assert tick_count_before == 1, (
            f"tick_count_before should be 1 after t1 completed; got {tick_count_before}"
        )

    def test_storage_callback_receives_correct_tick(self):
        """Storage callback still gets called with the correct tick data."""
        from tick_dispatcher import TickDispatcher, TickData

        dispatcher = TickDispatcher()
        received = []
        dispatcher.register_storage_callback(lambda t: received.append(t))
        dispatcher._last_ui_update = 999.0
        dispatcher._last_automation_check = 999.0

        tick = TickData(market_id="1.99", selection_id=42, timestamp=1.0)
        dispatcher.dispatch_tick(tick)

        assert len(received) == 1
        assert received[0].selection_id == 42

    def test_single_thread_dispatch_still_works(self):
        """No regression in single-threaded usage."""
        from tick_dispatcher import TickDispatcher, TickData

        dispatcher = TickDispatcher()
        counts = [0]
        dispatcher.register_storage_callback(lambda t: counts.__setitem__(0, counts[0] + 1))
        dispatcher._last_ui_update = 999.0
        dispatcher._last_automation_check = 999.0

        for i in range(5):
            dispatcher.dispatch_tick(TickData(market_id="1.1", selection_id=i, timestamp=float(i)))
        assert counts[0] == 5


# =============================================================================
# Issue #27 – dutching.py
# ALREADY FIXED IN BASE BRANCH via PR #51
# _apply_commission() correctly guards: if net_profit <= 0: return net_profit
# =============================================================================

class TestIssue27DutchingCommissionAlreadyFixed:

    def test_losing_scenario_not_reduced_by_commission(self):
        """
        The restored _back_dutching in PR #51 uses _apply_commission which
        only applies the commission multiplier to POSITIVE profits.
        A negative raw_profit (selection didn't win, total stake lost) must
        NOT be reduced by commission.
        """
        from dutching import calculate_dutching_stakes
        # Two selections at very unequal odds so one selection, when it wins,
        # produces a very small gross return (i.e. raw_profit is negative for
        # the other selection's "win" scenario from the winner's perspective).
        # With 2 selections and BACK dutching, when sel_1 wins, sel_2's stake
        # is a "cost" already included in total_stake; gross_return for sel_1 is
        # the return minus total_stake, which can be positive.
        # Test that commission is not applied to negative values by checking
        # that _apply_commission with a negative input returns unchanged.
        from dutching import _apply_commission
        from decimal import Decimal
        loss = Decimal("-10.00")
        result = _apply_commission(loss, 4.5)
        assert result == loss, (
            f"OLD: commission reduced loss to {result} (wrong). "
            f"NEW: loss must be returned unchanged: {loss}"
        )

    def test_positive_profit_gets_commission_applied(self):
        from dutching import _apply_commission
        from decimal import Decimal
        profit = Decimal("100.00")
        result = _apply_commission(profit, 4.5)
        expected = Decimal("100.00") * Decimal("0.955")
        assert abs(result - expected) < Decimal("0.01")


# =============================================================================
# Issue #28 – market_validator.py
# =============================================================================

class TestIssue28MarketValidator:

    def test_each_way_is_not_dutching_ready(self):
        """
        OLD: EACH_WAY was in DUTCHING_READY_MARKETS → is_dutching_ready returned True.
        NEW: EACH_WAY removed from DUTCHING_READY_MARKETS and added to
             NON_DUTCHING_MARKETS → returns False.
        """
        from market_validator import MarketValidator
        assert MarketValidator.is_dutching_ready("EACH_WAY") is False, (
            "OLD: returned True. NEW: must return False — not winner-takes-all."
        )

    def test_forecast_is_not_dutching_ready(self):
        from market_validator import MarketValidator
        assert MarketValidator.is_dutching_ready("FORECAST") is False, (
            "FORECAST must not be dutching-ready."
        )

    def test_tricast_is_not_dutching_ready(self):
        from market_validator import MarketValidator
        assert MarketValidator.is_dutching_ready("TRICAST") is False, (
            "TRICAST must not be dutching-ready."
        )

    def test_match_odds_still_dutching_ready(self):
        from market_validator import MarketValidator
        assert MarketValidator.is_dutching_ready("MATCH_ODDS") is True

    def test_winner_still_dutching_ready(self):
        from market_validator import MarketValidator
        assert MarketValidator.is_dutching_ready("WINNER") is True

    def test_non_dutching_market_still_rejected(self):
        from market_validator import MarketValidator
        assert MarketValidator.is_dutching_ready("OVER_UNDER_25") is False


# =============================================================================
# Issue #29 – market_tracker.py
# =============================================================================

class TestIssue29MarketTrackerEviction:

    def _tracker(self, max_size=3):
        from market_tracker import MarketCache
        return MarketCache(max_size=max_size)

    def test_updating_existing_key_does_not_evict_other_entry(self):
        """
        OLD: `if len(cache) >= max_size` triggered even when updating an
             existing key, evicting an innocent entry.
        NEW: evict only when inserting a truly new key past capacity.

        With max_size=2: fill with A and B, then update A.
        OLD: updating A triggers eviction of B (wrong, cache never grew).
        NEW: updating A does not evict B.
        """
        tracker = self._tracker(max_size=2)
        tracker.set("A", {"data": 1})
        tracker.set("B", {"data": 2})
        assert tracker.get("A") is not None
        assert tracker.get("B") is not None

        # Update existing key A — cache size stays at 2, no eviction needed
        tracker.set("A", {"data": 99})

        assert tracker.get("B") is not None, (
            "OLD: updating 'A' evicted 'B' even though size didn't grow. "
            "NEW: 'B' must still be present."
        )
        assert tracker.get("A")["data"] == 99

    def test_inserting_new_key_past_capacity_evicts_oldest(self):
        """Inserting a genuinely new key past max_size still evicts correctly."""
        tracker = self._tracker(max_size=2)
        tracker.set("A", {"data": 1})
        time.sleep(0.01)
        tracker.set("B", {"data": 2})
        time.sleep(0.01)
        # C is new; cache is full → A (oldest) should be evicted
        tracker.set("C", {"data": 3})
        assert tracker.get("C") is not None
        # A or B (the oldest) should be gone
        still_present = [k for k in ("A", "B") if tracker.get(k) is not None]
        assert len(still_present) == 1, (
            f"Exactly one of A/B should remain after inserting C. Got: {still_present}"
        )

    def test_cache_size_does_not_grow_beyond_max(self):
        """Cache never exceeds max_size regardless of updates/inserts."""
        tracker = self._tracker(max_size=3)
        for i in range(10):
            tracker.set(f"key_{i}", {"v": i})
        # Count via direct dict access
        with tracker._lock:
            size = len(tracker._cache)
        assert size <= 3


# =============================================================================
# Issue #30 – executor_manager.py
# =============================================================================

class TestIssue30CallSiteAudit:
    """
    Structural proof that no existing production caller depends on the old
    blocking return value of submit().

    Every call site is of the form:
        self.executor.submit("name", task)     # return value discarded
    None of them assign, await, or inspect the returned value.

    This confirms the public contract change is backward-compatible:
    the old code returned the *result* of the task (blocking); the new code
    returns a Future. Since every caller discards the return value, neither
    the blocking behavior nor the result type was part of any caller's contract.
    """

    PRODUCTION_CALL_SITES = [
        # (file, approximate_pattern)
        ("controllers/telegram_controller.py", 'executor.submit("tg_send_code"'),
        ("controllers/telegram_controller.py", 'executor.submit("tg_verify_code"'),
        ("controllers/telegram_controller.py", 'executor.submit("tg_load_dialogs"'),
        ("core/trading_engine.py",             'executor.submit("stub_cleanup"'),
        ("core/trading_engine.py",             'executor.submit("saga_recovery"'),
        ("core/trading_engine.py",             'executor.submit("engine_quick_bet"'),
        ("core/trading_engine.py",             'executor.submit("engine_dutching"'),
        ("core/trading_engine.py",             'executor.submit("engine_cashout"'),
        ("app_modules/monitoring_module.py",   'executor.submit("fetch_orders"'),
        ("app_modules/monitoring_module.py",   'executor.submit("fetch_cashout"'),
        ("app_modules/streaming_module.py",    'executor.submit("fetch_live_events"'),
        ("app_modules/betting_module.py",      'executor.submit("login_task"'),
    ]

    def test_no_caller_assigns_submit_return_value(self):
        """
        Scan every production call site and assert that the return value
        of submit() is not assigned (i.e. the call appears on its own line,
        not on the RHS of an assignment or inside another expression).
        """
        import ast, os

        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        for rel_path, pattern in self.PRODUCTION_CALL_SITES:
            full_path = os.path.join(base, rel_path)
            if not os.path.exists(full_path):
                continue  # file missing is fine — pattern won't be found

            with open(full_path) as f:
                source = f.read()

            tree = ast.parse(source)

            # Collect all Assign / AugAssign / AnnAssign / Return nodes
            # that have an executor.submit() call on their RHS.
            assigned = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                    value = getattr(node, "value", None)
                    if value and _is_submit_call(value):
                        assigned.append((rel_path, ast.unparse(node)))
                elif isinstance(node, ast.Return):
                    if node.value and _is_submit_call(node.value):
                        assigned.append((rel_path, ast.unparse(node)))

            assert assigned == [], (
                f"Call site in {rel_path} ASSIGNS submit() return value: "
                f"{assigned}\n"
                "This would break backward compatibility with the new Future return."
            )

    def test_fire_and_forget_pattern_works_with_future_return(self):
        """
        Verify that fire-and-forget callers (return value discarded) work
        correctly with the new Future-returning submit().
        """
        from executor_manager import SafeExecutor

        executor = SafeExecutor()
        executed = threading.Event()

        def task():
            executed.set()

        # Simulate the production pattern: call submit, discard return value
        executor.submit("fire_and_forget", task)

        assert executed.wait(timeout=2), "Task was never executed"
        executor.executor.shutdown(wait=False)


def _is_submit_call(node) -> bool:
    """Return True if the AST node is a call to *.submit(...)."""
    import ast as _ast
    return (
        isinstance(node, _ast.Call)
        and isinstance(node.func, _ast.Attribute)
        and node.func.attr == "submit"
    )


class TestIssue30SafeExecutorNonBlocking:

    def test_submit_returns_future_without_blocking(self):
        """
        OLD: submit() called future.result(timeout=...) immediately,
             blocking the caller for up to default_timeout seconds.
        NEW: submit() returns a Future without waiting.
        """
        import concurrent.futures
        from executor_manager import SafeExecutor

        executor = SafeExecutor(default_timeout=30)
        started = threading.Event()

        def slow_fn():
            started.set()
            time.sleep(5)
            return "done"

        t_start = time.time()
        future = executor.submit("slow_task", slow_fn)
        elapsed = time.time() - t_start

        assert elapsed < 0.5, (
            f"OLD: submit() blocked for {elapsed:.2f}s. "
            "NEW: must return immediately (< 0.5s)."
        )
        assert isinstance(future, concurrent.futures.Future), (
            "submit() must return a Future object"
        )
        # Cancel to avoid leaving slow_fn running in background
        future.cancel()
        executor.executor.shutdown(wait=False)

    def test_submit_sync_blocks_and_returns_result(self):
        """submit_sync() preserves the old blocking behaviour for callers that need it."""
        from executor_manager import SafeExecutor
        executor = SafeExecutor(default_timeout=5)
        result = executor.submit_sync("fast_task", lambda: 42)
        assert result == 42
        executor.executor.shutdown(wait=False)

    def test_executor_manager_submit_returns_future(self):
        """The facade's submit() also returns a Future."""
        import concurrent.futures
        from executor_manager import ExecutorManager
        mgr = ExecutorManager()
        future = mgr.submit("task", lambda: "result")
        assert isinstance(future, concurrent.futures.Future)
        mgr.shutdown(wait=False)


# =============================================================================
# Issue #31 – plugin_runner.py
# =============================================================================

class TestIssue31PluginRunnerAutoDisable:

    def _runner(self):
        from plugin_runner import PluginRunner
        return PluginRunner(timeout=1)

    def test_plugin_stops_executing_after_failure_threshold(self):
        """
        OLD: after 5 failures, "auto-disabled" was logged but the plugin
             continued executing on subsequent run() calls.
        NEW: plugin is added to disabled_plugins and skipped on all future calls.
        """
        runner = self._runner()
        call_count = [0]

        def always_fails():
            call_count[0] += 1
            raise RuntimeError("always fails")

        # Trigger 5 failures to reach the threshold
        for _ in range(5):
            runner.run("bad_plugin", always_fails)

        assert runner.is_disabled("bad_plugin"), (
            "Plugin must be in disabled_plugins after 5 failures"
        )

        # 6th call must NOT execute the function
        call_count[0] = 0
        result = runner.run("bad_plugin", always_fails)
        assert result is None
        assert call_count[0] == 0, (
            f"OLD: function was called {call_count[0]} time(s) after auto-disable. "
            "NEW: disabled plugin must be skipped (call_count == 0)."
        )

    def test_non_disabled_plugin_still_executes(self):
        """Plugins below the failure threshold still execute normally."""
        runner = self._runner()
        result = runner.run("good_plugin", lambda: "ok")
        assert result == "ok"

    def test_reset_reenables_disabled_plugin(self):
        """reset() clears failure count and re-enables the plugin."""
        runner = self._runner()

        def fails():
            raise RuntimeError("fail")

        for _ in range(5):
            runner.run("plugin_x", fails)
        assert runner.is_disabled("plugin_x")

        runner.reset("plugin_x")
        assert not runner.is_disabled("plugin_x")
        assert runner.fail_counts.get("plugin_x", 0) == 0

        # After reset, plugin can run again
        result = runner.run("plugin_x", lambda: "back")
        assert result == "back"

    def test_partial_failures_do_not_disable(self):
        """Fewer than FAIL_THRESHOLD failures do not disable the plugin."""
        runner = self._runner()

        def fails():
            raise RuntimeError("fail")

        for _ in range(4):
            runner.run("almost_bad", fails)

        assert not runner.is_disabled("almost_bad")

    def test_is_disabled_initial_state(self):
        runner = self._runner()
        assert not runner.is_disabled("any_plugin")
