"""
Test Ottimizzazioni Performance

Verifica che tutti i moduli di ottimizzazione funzionino correttamente
e rispettino le garanzie di performance.
"""

import pytest
import time
import threading
from typing import List, Dict, Any

from tick_dispatcher import TickDispatcher, TickData, DispatchMode, get_tick_dispatcher
from pnl_cache import PnLCache, get_pnl_cache
from dutching_cache import DutchingCache, get_dutching_cache, cached_dutching_stakes
from automation_optimizer import AutomationOptimizer, SkipReason, get_automation_optimizer
from ui_optimizer import UIOptimizer, get_ui_optimizer, optimized_configure, optimized_set
from simulation_speed import (
    SimulationSpeedController, SimulationSpeed, 
    get_speed_controller, is_simulation_mode, set_simulation_mode
)


class TestTickDispatcher:
    """Test Tick Dispatcher con throttling."""
    
    def test_throttling_reduces_ui_updates(self):
        """Throttling riduce aggiornamenti UI."""
        dispatcher = TickDispatcher()
        
        ui_updates = []
        storage_updates = []
        
        dispatcher.register_ui_callback(lambda t: ui_updates.append(t))
        dispatcher.register_storage_callback(lambda t: storage_updates.append(t))
        
        for i in range(20):
            tick = TickData(
                market_id="1.123456",
                selection_id=i % 3,
                timestamp=time.time(),
                back_prices=[2.0],
                lay_prices=[2.02]
            )
            dispatcher.dispatch_tick(tick)
            time.sleep(0.05)
        
        assert len(storage_updates) == 20
        assert len(ui_updates) < 20
        
        stats = dispatcher.get_stats()
        assert stats["reduction_ratio"] > 0
    
    def test_simulation_mode_increases_intervals(self):
        """Modalità simulazione aumenta intervalli."""
        dispatcher = TickDispatcher()
        
        assert dispatcher.ui_interval == dispatcher.MIN_UI_UPDATE_INTERVAL
        
        dispatcher.mode = DispatchMode.SIMULATION
        
        assert dispatcher.ui_interval == dispatcher.SIM_UI_UPDATE_INTERVAL
        assert dispatcher.automation_interval == dispatcher.SIM_AUTOMATION_INTERVAL
    
    def test_all_ticks_reach_storage(self):
        """Tutti i tick raggiungono storage (full-speed)."""
        dispatcher = TickDispatcher()
        
        received = []
        dispatcher.register_storage_callback(lambda t: received.append(t))
        
        for i in range(100):
            tick = TickData(
                market_id="1.123456",
                selection_id=i,
                timestamp=time.time()
            )
            dispatcher.dispatch_tick(tick)
        
        assert len(received) == 100


class TestPnLCache:
    """Test P&L Cache."""
    
    def test_short_circuit_no_orders(self):
        """Short-circuit quando nessun ordine."""
        cache = PnLCache()
        
        prices = {1: (2.0, 2.02), 2: (3.0, 3.02)}
        orders: List[Dict] = []
        
        result = cache.get_cached_pnl("MKT1", prices, orders)
        
        assert result is not None
        assert result["total"] == 0.0
        
        stats = cache.get_stats()
        assert stats["short_circuits"] == 1
    
    def test_cache_hit_unchanged_data(self):
        """Cache hit quando dati invariati."""
        cache = PnLCache()
        
        prices = {1: (2.0, 2.02)}
        orders = [{"selection_id": 1, "side": "BACK", "stake": 10.0, "price": 2.0, "status": "MATCHED"}]
        pnl_results = {"total": 5.0, "by_selection": {1: 5.0}, "green_stakes": {1: 2.5}}
        
        cache.update_cache("MKT1", prices, orders, pnl_results)
        
        result = cache.get_cached_pnl("MKT1", prices, orders)
        
        assert result is not None
        assert result["total"] == 5.0
        
        stats = cache.get_stats()
        assert stats["hits"] == 1
    
    def test_cache_miss_changed_prices(self):
        """Cache miss quando prezzi cambiano."""
        cache = PnLCache()
        
        prices1 = {1: (2.0, 2.02)}
        prices2 = {1: (2.5, 2.52)}
        orders = [{"selection_id": 1, "side": "BACK", "stake": 10.0, "price": 2.0, "status": "MATCHED"}]
        pnl_results = {"total": 5.0, "by_selection": {1: 5.0}, "green_stakes": {1: 2.5}}
        
        cache.update_cache("MKT1", prices1, orders, pnl_results)
        
        result = cache.get_cached_pnl("MKT1", prices2, orders)
        
        assert result is None
        
        stats = cache.get_stats()
        assert stats["misses"] >= 1
    
    def test_invalidation(self):
        """Invalidazione funziona."""
        cache = PnLCache()
        
        prices = {1: (2.0, 2.02)}
        orders = [{"selection_id": 1, "side": "BACK", "stake": 10.0, "price": 2.0, "status": "MATCHED"}]
        pnl_results = {"total": 5.0, "by_selection": {1: 5.0}, "green_stakes": {1: 2.5}}
        
        cache.update_cache("MKT1", prices, orders, pnl_results)
        cache.invalidate("MKT1")
        
        result = cache.get_cached_pnl("MKT1", prices, orders)
        
        assert result is None


class TestDutchingCache:
    """Test Dutching Cache."""
    
    def test_cache_hit_same_inputs(self):
        """Cache hit con stessi input."""
        cache = DutchingCache()
        
        selections = [
            {"selectionId": 1, "price": 2.0},
            {"selectionId": 2, "price": 3.0}
        ]
        stakes = [{"selectionId": 1, "stake": 60}, {"selectionId": 2, "stake": 40}]
        
        cache.put(selections, 100.0, "BACK", 4.5, stakes, 10.0, 95.0)
        
        result = cache.get(selections, 100.0, "BACK", 4.5)
        
        assert result is not None
        assert result[1] == 10.0
        assert result[2] == 95.0
        
        stats = cache.get_stats()
        assert stats["hits"] == 1
    
    def test_cache_miss_different_stake(self):
        """Cache miss con stake diverso."""
        cache = DutchingCache()
        
        selections = [{"selectionId": 1, "price": 2.0}]
        stakes = [{"selectionId": 1, "stake": 100}]
        
        cache.put(selections, 100.0, "BACK", 4.5, stakes, 10.0, 95.0)
        
        result = cache.get(selections, 200.0, "BACK", 4.5)
        
        assert result is None
    
    def test_lru_eviction(self):
        """LRU eviction funziona."""
        cache = DutchingCache()
        cache.MAX_CACHE_SIZE = 3
        
        for i in range(5):
            selections = [{"selectionId": i, "price": 2.0}]
            cache.put(selections, 100.0, "BACK", 4.5, [], 0, 0)
        
        stats = cache.get_stats()
        assert stats["evictions"] >= 2


class TestAutomationOptimizer:
    """Test Automation Optimizer."""
    
    def test_early_exit_disabled(self):
        """Early exit quando disabilitato."""
        optimizer = AutomationOptimizer()
        
        should, reason = optimizer.should_evaluate(
            order_id="ORD1",
            auto_green_enabled=False,
            has_open_orders=True,
            market_status="OPEN",
            placed_at=time.time() - 10,
            current_pnl=5.0
        )
        
        assert should is False
        assert reason == SkipReason.DISABLED
    
    def test_early_exit_no_orders(self):
        """Early exit senza ordini aperti."""
        optimizer = AutomationOptimizer()
        
        should, reason = optimizer.should_evaluate(
            order_id="ORD1",
            auto_green_enabled=True,
            has_open_orders=False,
            market_status="OPEN",
            placed_at=time.time() - 10,
            current_pnl=5.0
        )
        
        assert should is False
        assert reason == SkipReason.NO_ORDERS
    
    def test_early_exit_market_closed(self):
        """Early exit mercato chiuso."""
        optimizer = AutomationOptimizer()
        
        should, reason = optimizer.should_evaluate(
            order_id="ORD1",
            auto_green_enabled=True,
            has_open_orders=True,
            market_status="SUSPENDED",
            placed_at=time.time() - 10,
            current_pnl=5.0
        )
        
        assert should is False
        assert reason == SkipReason.MARKET_CLOSED
    
    def test_early_exit_delay_not_elapsed(self):
        """Early exit delay non scaduto."""
        optimizer = AutomationOptimizer()
        
        should, reason = optimizer.should_evaluate(
            order_id="ORD1",
            auto_green_enabled=True,
            has_open_orders=True,
            market_status="OPEN",
            placed_at=time.time() - 1.0,
            current_pnl=5.0
        )
        
        assert should is False
        assert reason == SkipReason.DELAY_NOT_ELAPSED
    
    def test_full_evaluation_when_all_conditions_met(self):
        """Valutazione completa quando tutte le condizioni sono soddisfatte."""
        optimizer = AutomationOptimizer()
        
        should, reason = optimizer.should_evaluate(
            order_id="ORD_NEW",
            auto_green_enabled=True,
            has_open_orders=True,
            market_status="OPEN",
            placed_at=time.time() - 10,
            current_pnl=5.0
        )
        
        assert should is True
        assert reason is None
        
        stats = optimizer.get_stats()
        assert stats["full_evaluations"] >= 1
    
    def test_simulation_mode_uses_throttled_interval(self):
        """In simulazione usa intervallo throttled, non blocca."""
        optimizer = AutomationOptimizer()
        
        should, reason = optimizer.should_evaluate(
            order_id="ORD_SIM",
            auto_green_enabled=True,
            has_open_orders=True,
            market_status="OPEN",
            placed_at=time.time() - 10,
            current_pnl=5.0,
            simulation=True
        )
        
        assert should is True
        assert reason is None


class TestUIOptimizer:
    """Test UI Optimizer."""
    
    def test_skip_identical_value(self):
        """Skip quando valore identico."""
        optimizer = UIOptimizer()
        
        class MockWidget:
            pass
        
        widget = MockWidget()
        
        assert optimizer.should_update(widget, "text", "Hello") is True
        assert optimizer.should_update(widget, "text", "Hello") is False
        assert optimizer.should_update(widget, "text", "World") is True
        
        stats = optimizer.get_stats()
        assert stats["skipped_updates"] == 1
    
    def test_float_comparison_tolerance(self):
        """Tolleranza nel confronto float."""
        optimizer = UIOptimizer()
        
        class MockWidget:
            pass
        
        widget = MockWidget()
        
        assert optimizer.should_update(widget, "value", 10.0) is True
        assert optimizer.should_update(widget, "value", 10.0001) is False
        assert optimizer.should_update(widget, "value", 10.1) is True
    
    def test_configure_if_changed(self):
        """configure_if_changed funziona."""
        optimizer = UIOptimizer()
        
        configured_values = {}
        
        class MockWidget:
            def configure(self, **kwargs):
                configured_values.update(kwargs)
        
        widget = MockWidget()
        
        result1 = optimizer.configure_if_changed(widget, text="Hello", fg="red")
        assert result1 is True
        assert configured_values == {"text": "Hello", "fg": "red"}
        
        configured_values.clear()
        result2 = optimizer.configure_if_changed(widget, text="Hello", fg="red")
        assert result2 is False
        assert configured_values == {}
        
        configured_values.clear()
        result3 = optimizer.configure_if_changed(widget, text="World", fg="red")
        assert result3 is True
        assert configured_values == {"text": "World"}


class TestSimulationSpeed:
    """Test Simulation Speed Controller."""
    
    def test_speed_profiles(self):
        """Profili velocità configurati correttamente."""
        controller = SimulationSpeedController()
        
        controller.speed = SimulationSpeed.REALTIME
        assert controller.profile.tick_batch_size == 1
        
        controller.speed = SimulationSpeed.FAST
        assert controller.profile.tick_batch_size == 10
        
        controller.speed = SimulationSpeed.ULTRA_FAST
        assert controller.profile.tick_batch_size == 50
    
    def test_simulation_mode_affects_intervals(self):
        """Modalità simulazione modifica intervalli."""
        controller = SimulationSpeedController()
        
        controller.is_simulation = False
        assert controller.ui_interval == 0.25
        
        controller.is_simulation = True
        controller.speed = SimulationSpeed.FAST
        assert controller.ui_interval == 0.50
    
    def test_time_compression(self):
        """Compressione tempo funziona."""
        controller = SimulationSpeedController()
        controller.is_simulation = True
        controller.speed = SimulationSpeed.FAST
        
        compressed = controller.calculate_time_compression(10.0)
        
        assert compressed == 1.0
    
    def test_batch_processing_for_ui(self):
        """Batch processing per UI in modalità veloce."""
        controller = SimulationSpeedController()
        controller.is_simulation = True
        controller.speed = SimulationSpeed.FAST
        
        ui_updates = 0
        for i in range(25):
            if controller.should_process_tick():
                ui_updates += 1
        
        assert ui_updates < 25
    
    def test_storage_always_receives_ticks(self):
        """Storage riceve sempre tutti i tick."""
        controller = SimulationSpeedController()
        controller.is_simulation = True
        controller.speed = SimulationSpeed.ULTRA_FAST
        
        storage_count = 0
        for i in range(50):
            if controller.should_process_tick_for_storage():
                storage_count += 1
        
        assert storage_count == 50
    
    def test_automation_throttling_cycles(self):
        """Automation throttling cicla correttamente tra True e False."""
        controller = SimulationSpeedController()
        controller.is_simulation = True
        controller.speed = SimulationSpeed.FAST
        
        results = []
        for i in range(20):
            results.append(controller.should_process_tick_for_automation())
        
        true_count = sum(1 for r in results if r)
        false_count = sum(1 for r in results if not r)
        
        assert true_count > 0, "Deve processare alcune automazioni"
        assert false_count > 0, "Deve skippare alcune automazioni"
        assert true_count < 20, "Non deve processare tutte le automazioni"


class TestIntegration:
    """Test integrazione moduli ottimizzazione."""
    
    def test_combined_optimization_flow(self):
        """Flusso combinato ottimizzazioni."""
        dispatcher = TickDispatcher()
        pnl_cache = PnLCache()
        dutch_cache = DutchingCache()
        auto_opt = AutomationOptimizer()
        ui_opt = UIOptimizer()
        speed_ctrl = SimulationSpeedController()
        
        speed_ctrl.is_simulation = True
        speed_ctrl.speed = SimulationSpeed.FAST
        dispatcher.mode = DispatchMode.SIMULATION
        
        ui_updates = []
        dispatcher.register_ui_callback(lambda t: ui_updates.append(len(t)))
        
        for i in range(50):
            tick = TickData(
                market_id="1.123456",
                selection_id=i % 3,
                timestamp=time.time()
            )
            
            if speed_ctrl.should_process_tick():
                dispatcher.dispatch_tick(tick)
        
        prices = {1: (2.0, 2.02)}
        orders: List[Dict] = []
        result = pnl_cache.get_cached_pnl("MKT1", prices, orders)
        assert result is not None
        
        should, reason = auto_opt.should_evaluate(
            "ORD1", False, False, "CLOSED", None, 0
        )
        assert should is False
        
        class MockWidget:
            def configure(self, **kwargs):
                pass
        
        widget = MockWidget()
        ui_opt.configure_if_changed(widget, text="Test")
        ui_opt.configure_if_changed(widget, text="Test")
        
        stats = ui_opt.get_stats()
        assert stats["skipped_updates"] >= 1
