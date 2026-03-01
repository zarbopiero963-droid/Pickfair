"""
Test di Carico - Performance e stress testing

Verifica:
1. 100 ricalcoli AI in <1s
2. Simulazione tick replay + auto-green
3. SafetyLogger sotto carico
4. SafeModeManager thread-safety
"""

import pytest
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List
import random

from dutching import calculate_dutching_stakes, calculate_ai_mixed_stakes
from automation_engine import should_auto_green, get_auto_green_remaining_delay
from safety_logger import SafetyLogger, get_safety_logger, SafetyEventType
from safe_mode import SafeModeManager, get_safe_mode_manager, reset_safe_mode


class MockOrder:
    """Mock order per test."""
    def __init__(self, meta: dict):
        self.meta = meta


class TestAICalculationPerformance:
    """Test performance calcoli AI."""
    
    def test_100_dutching_calculations_under_1_second(self):
        """100 calcoli dutching standard in <1s."""
        selections = [
            {"selectionId": 1, "runnerName": "Home", "price": 2.0},
            {"selectionId": 2, "runnerName": "Draw", "price": 3.5},
            {"selectionId": 3, "runnerName": "Away", "price": 4.0}
        ]
        
        start = time.perf_counter()
        
        for i in range(100):
            stake = 50.0 + (i % 50)
            results, profit, book = calculate_dutching_stakes(
                selections, stake, commission=4.5
            )
            assert len(results) == 3
        
        elapsed = time.perf_counter() - start
        
        assert elapsed < 1.0, f"100 calcoli dutching in {elapsed:.3f}s (max 1.0s)"
    
    def test_100_ai_mixed_attempts_under_5_seconds(self):
        """100 tentativi AI Mixed in <5s (include errori attesi, calcolo complesso)."""
        selections_sets = [
            [
                {"selectionId": 1, "runnerName": "A", "price": 1.5 + (i * 0.1)},
                {"selectionId": 2, "runnerName": "B", "price": 3.0 + (i * 0.05)},
                {"selectionId": 3, "runnerName": "C", "price": 5.0 - (i * 0.02)}
            ]
            for i in range(10)
        ]
        
        start = time.perf_counter()
        success_count = 0
        error_count = 0
        
        for i in range(100):
            selections = selections_sets[i % len(selections_sets)]
            stake = 50.0 + (i % 100)
            
            try:
                results, profit, book = calculate_ai_mixed_stakes(
                    selections, stake, commission=4.5, min_stake=2.0
                )
                if results:
                    success_count += 1
            except ValueError:
                error_count += 1
        
        elapsed = time.perf_counter() - start
        
        assert elapsed < 5.0, f"100 tentativi AI Mixed in {elapsed:.3f}s (max 5.0s)"
        assert success_count + error_count == 100
    
    def test_concurrent_calculations(self):
        """Calcoli concorrenti thread-safe."""
        selections = [
            {"selectionId": 1, "runnerName": "Home", "price": 2.5},
            {"selectionId": 2, "runnerName": "Draw", "price": 3.2},
            {"selectionId": 3, "runnerName": "Away", "price": 3.8}
        ]
        
        results_list: List[bool] = []
        lock = threading.Lock()
        
        def calculate():
            try:
                results, profit, book = calculate_dutching_stakes(
                    selections, 100.0, commission=4.5
                )
                with lock:
                    results_list.append(len(results) == 3)
            except Exception as e:
                with lock:
                    results_list.append(False)
        
        threads = [threading.Thread(target=calculate) for _ in range(50)]
        
        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.perf_counter() - start
        
        assert all(results_list), "Tutti i calcoli concorrenti devono riuscire"
        assert len(results_list) == 50
        assert elapsed < 2.0, f"50 calcoli concorrenti in {elapsed:.3f}s (max 2.0s)"


class TestTickReplayWithAutoGreen:
    """Test tick replay simulato con auto-green check."""
    
    def test_tick_stream_simulation(self):
        """Simula 1000 tick updates con check auto-green."""
        base_time = time.time()
        
        orders = [
            MockOrder({
                "auto_green": True,
                "placed_at": base_time - 3.0,
                "simulation": False
            }),
            MockOrder({
                "auto_green": True,
                "placed_at": base_time - 1.0,
                "simulation": False
            }),
            MockOrder({
                "auto_green": False,
                "placed_at": base_time - 5.0,
                "simulation": False
            })
        ]
        
        start = time.perf_counter()
        
        eligible_count = 0
        for tick in range(1000):
            for order in orders:
                if should_auto_green(order, "OPEN"):
                    eligible_count += 1
                
                remaining = get_auto_green_remaining_delay(order)
        
        elapsed = time.perf_counter() - start
        
        assert elapsed < 0.5, f"1000 tick checks in {elapsed:.3f}s (max 0.5s)"
        assert eligible_count == 1000
    
    def test_rapid_order_state_changes(self):
        """Test cambio stato rapido ordini."""
        start = time.perf_counter()
        
        for i in range(500):
            order = MockOrder({
                "auto_green": i % 2 == 0,
                "placed_at": time.time() - (i * 0.01),
                "simulation": i % 3 == 0
            })
            
            market_states = ["OPEN", "SUSPENDED", "CLOSED"]
            for state in market_states:
                should_auto_green(order, state)
        
        elapsed = time.perf_counter() - start
        
        assert elapsed < 1.0, f"1500 state checks in {elapsed:.3f}s (max 1.0s)"


class TestSafetyLoggerPerformance:
    """Test performance SafetyLogger."""
    
    def test_1000_log_entries_performance(self, tmp_path, monkeypatch):
        """1000 log entries sotto carico."""
        monkeypatch.setattr(
            'safety_logger.SafetyLogger._get_log_directory',
            lambda self: tmp_path
        )
        
        SafetyLogger._instance = None
        logger = SafetyLogger()
        
        start = time.perf_counter()
        
        for i in range(1000):
            event_type = [
                SafetyEventType.MIXED_DUTCHING_ERROR,
                SafetyEventType.AI_BLOCKED_MARKET,
                SafetyEventType.AUTO_GREEN_DENIED
            ][i % 3]
            
            logger.log_event(
                event_type,
                f"Test message {i}",
                {"iteration": i, "value": f"data_{i}"}
            )
        
        elapsed = time.perf_counter() - start
        
        SafetyLogger._instance = None
        
        assert elapsed < 2.0, f"1000 log entries in {elapsed:.3f}s (max 2.0s)"
    
    def test_concurrent_logging(self, tmp_path, monkeypatch):
        """Logging concorrente thread-safe."""
        monkeypatch.setattr(
            'safety_logger.SafetyLogger._get_log_directory',
            lambda self: tmp_path
        )
        
        SafetyLogger._instance = None
        logger = SafetyLogger()
        
        def log_entries(thread_id: int):
            for i in range(100):
                logger.log_event(
                    SafetyEventType.AUTO_GREEN_DENIED,
                    f"Thread {thread_id} entry {i}",
                    {"thread": thread_id}
                )
        
        start = time.perf_counter()
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(log_entries, i) for i in range(10)]
            for f in as_completed(futures):
                f.result()
        
        elapsed = time.perf_counter() - start
        
        SafetyLogger._instance = None
        
        assert elapsed < 3.0, f"1000 log entries concorrenti in {elapsed:.3f}s (max 3.0s)"


class TestSafeModePerformance:
    """Test performance SafeModeManager."""
    
    def test_rapid_error_reporting(self):
        """Report errori rapidi senza blocchi."""
        SafeModeManager._instance = None
        manager = SafeModeManager()
        
        start = time.perf_counter()
        
        triggered_at = None
        for i in range(100):
            if manager.report_error("TestError", f"Error {i}"):
                triggered_at = i
                break
            manager.report_success()
        
        elapsed = time.perf_counter() - start
        
        SafeModeManager._instance = None
        
        assert elapsed < 0.5, f"100 error/success cycles in {elapsed:.3f}s (max 0.5s)"
    
    def test_concurrent_error_reporting(self):
        """Error reporting concorrente thread-safe."""
        SafeModeManager._instance = None
        manager = SafeModeManager()
        
        trigger_count = [0]
        lock = threading.Lock()
        
        def report_errors(thread_id: int):
            for i in range(10):
                if manager.report_error("ConcurrentError", f"T{thread_id}-E{i}"):
                    with lock:
                        trigger_count[0] += 1
                time.sleep(0.001)
        
        start = time.perf_counter()
        
        threads = [threading.Thread(target=report_errors, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        elapsed = time.perf_counter() - start
        
        SafeModeManager._instance = None
        
        assert trigger_count[0] <= 1, "Safe Mode deve attivarsi al massimo una volta"
        assert elapsed < 2.0, f"Concurrent error reporting in {elapsed:.3f}s (max 2.0s)"
    
    def test_status_query_performance(self):
        """Query stato performance."""
        SafeModeManager._instance = None
        manager = SafeModeManager()
        
        for i in range(5):
            manager.report_error("SetupError", f"Error {i}")
        
        start = time.perf_counter()
        
        for _ in range(10000):
            status = manager.get_status_info()
            _ = manager.is_safe_mode_active
            _ = manager.consecutive_errors
        
        elapsed = time.perf_counter() - start
        
        SafeModeManager._instance = None
        
        assert elapsed < 1.0, f"30000 status queries in {elapsed:.3f}s (max 1.0s)"


class TestIntegrationStress:
    """Test integrazione sotto stress."""
    
    def test_full_workflow_stress(self, tmp_path, monkeypatch):
        """Workflow completo sotto stress."""
        monkeypatch.setattr(
            'safety_logger.SafetyLogger._get_log_directory',
            lambda self: tmp_path
        )
        
        SafetyLogger._instance = None
        SafeModeManager._instance = None
        
        logger = SafetyLogger()
        manager = SafeModeManager()
        
        selections = [
            {"selectionId": 1, "runnerName": "A", "price": 2.5},
            {"selectionId": 2, "runnerName": "B", "price": 3.0},
            {"selectionId": 3, "runnerName": "C", "price": 4.0}
        ]
        
        start = time.perf_counter()
        
        for i in range(100):
            try:
                results, profit, book = calculate_dutching_stakes(
                    selections, 100.0, commission=4.5
                )
                manager.report_success()
            except Exception as e:
                manager.report_error("DutchingError", str(e))
                logger.log_mixed_dutching_error(str(e), f"MKT_{i}")
            
            order = MockOrder({
                "auto_green": True,
                "placed_at": time.time() - 3.0,
                "simulation": False
            })
            
            if not should_auto_green(order, "OPEN"):
                logger.log_auto_green_denied(
                    "Check failed",
                    f"ORD_{i}",
                    "OPEN"
                )
        
        elapsed = time.perf_counter() - start
        
        SafetyLogger._instance = None
        SafeModeManager._instance = None
        
        assert elapsed < 2.0, f"100 full workflows in {elapsed:.3f}s (max 2.0s)"
        assert not manager.is_safe_mode_active, "Safe Mode non deve attivarsi con successi"
