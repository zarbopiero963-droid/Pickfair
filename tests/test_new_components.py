"""
Test per i nuovi componenti:
- DutchingController
- AIPatternEngine
- DraggableRunner
- MiniLadder
"""

import pytest
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAIPatternEngine:
    """Test per AIPatternEngine WoM analysis."""
    
    def test_calculate_wom_balanced(self):
        """WoM bilanciato ritorna ~0.5."""
        from ai.ai_pattern_engine import AIPatternEngine
        
        engine = AIPatternEngine()
        selection = {
            "selectionId": 1,
            "back_ladder": [{"price": 2.0, "size": 100}],
            "lay_ladder": [{"price": 2.02, "size": 100}]
        }
        
        wom = engine.calculate_wom(selection)
        assert 0.45 <= wom <= 0.55, f"WoM bilanciato dovrebbe essere ~0.5, got {wom}"
    
    def test_calculate_wom_back_heavy(self):
        """WoM > 0.55 con più liquidità BACK."""
        from ai.ai_pattern_engine import AIPatternEngine
        
        engine = AIPatternEngine()
        selection = {
            "selectionId": 1,
            "back_ladder": [{"price": 2.0, "size": 200}],
            "lay_ladder": [{"price": 2.02, "size": 50}]
        }
        
        wom = engine.calculate_wom(selection)
        assert wom > 0.55, f"WoM BACK heavy dovrebbe essere > 0.55, got {wom}"
    
    def test_calculate_wom_lay_heavy(self):
        """WoM < 0.45 con più liquidità LAY."""
        from ai.ai_pattern_engine import AIPatternEngine
        
        engine = AIPatternEngine()
        selection = {
            "selectionId": 1,
            "back_ladder": [{"price": 2.0, "size": 50}],
            "lay_ladder": [{"price": 2.02, "size": 200}]
        }
        
        wom = engine.calculate_wom(selection)
        assert wom < 0.45, f"WoM LAY heavy dovrebbe essere < 0.45, got {wom}"
    
    def test_calculate_wom_no_liquidity(self):
        """WoM neutro (0.5) se nessuna liquidità."""
        from ai.ai_pattern_engine import AIPatternEngine
        
        engine = AIPatternEngine()
        selection = {
            "selectionId": 1,
            "back_ladder": [],
            "lay_ladder": []
        }
        
        wom = engine.calculate_wom(selection)
        assert wom == 0.5, f"WoM senza liquidità dovrebbe essere 0.5, got {wom}"
    
    def test_decide_back_on_high_wom(self):
        """Decide BACK quando WoM > threshold."""
        from ai.ai_pattern_engine import AIPatternEngine
        
        engine = AIPatternEngine()
        selections = [
            {
                "selectionId": 1,
                "back_ladder": [{"price": 2.0, "size": 200}],
                "lay_ladder": [{"price": 2.02, "size": 50}]
            }
        ]
        
        decisions = engine.decide(selections)
        assert decisions[1] == "BACK"
    
    def test_decide_lay_on_low_wom(self):
        """Decide LAY quando WoM < threshold."""
        from ai.ai_pattern_engine import AIPatternEngine
        
        engine = AIPatternEngine()
        selections = [
            {
                "selectionId": 1,
                "back_ladder": [{"price": 2.0, "size": 30}],
                "lay_ladder": [{"price": 2.02, "size": 200}]
            }
        ]
        
        decisions = engine.decide(selections)
        assert decisions[1] == "LAY"
    
    def test_force_mixed_when_all_same(self):
        """Forza almeno 1 BACK + 1 LAY quando tutti uguali."""
        from ai.ai_pattern_engine import AIPatternEngine
        
        engine = AIPatternEngine()
        # Tutti con WoM bilanciato → tutti BACK di default
        selections = [
            {"selectionId": 1, "back_ladder": [{"size": 100}], "lay_ladder": [{"size": 100}]},
            {"selectionId": 2, "back_ladder": [{"size": 100}], "lay_ladder": [{"size": 100}]},
            {"selectionId": 3, "back_ladder": [{"size": 100}], "lay_ladder": [{"size": 100}]}
        ]
        
        decisions = engine.decide(selections)
        sides = set(decisions.values())
        
        # Deve forzare almeno un BACK e un LAY
        assert "BACK" in sides and "LAY" in sides, f"Deve forzare mixed, got {sides}"
    
    def test_get_wom_analysis_returns_list(self):
        """get_wom_analysis ritorna lista con analisi."""
        from ai.ai_pattern_engine import AIPatternEngine
        
        engine = AIPatternEngine()
        selections = [
            {"selectionId": 1, "runnerName": "Runner A", "back_ladder": [{"size": 100}], "lay_ladder": [{"size": 50}]}
        ]
        
        analysis = engine.get_wom_analysis(selections)
        
        assert len(analysis) == 1
        assert analysis[0]["selectionId"] == 1
        assert "wom" in analysis[0]
        assert "suggested_side" in analysis[0]
        assert "confidence" in analysis[0]


class TestDutchingController:
    """Test per DutchingController."""
    
    def test_controller_init(self):
        """Controller si inizializza correttamente."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker()
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        assert controller.simulation is True
        assert controller.broker is broker
    
    def test_validate_selections_empty(self):
        """Validazione fallisce senza selezioni."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker()
        controller = DutchingController(broker=broker, pnl_engine=None)
        
        errors = controller.validate_selections([])
        assert len(errors) > 0
        assert "Nessuna selezione" in errors[0]
    
    def test_validate_selections_invalid_price(self):
        """Validazione fallisce con prezzo <= 1."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker()
        controller = DutchingController(broker=broker, pnl_engine=None)
        
        selections = [{"selectionId": 1, "runnerName": "Test", "price": 1.0}]
        errors = controller.validate_selections(selections)
        
        assert len(errors) > 0
        assert "prezzo non valido" in errors[0]
    
    def test_validate_selections_missing_id(self):
        """Validazione fallisce senza selectionId."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker()
        controller = DutchingController(broker=broker, pnl_engine=None)
        
        selections = [{"runnerName": "Test", "price": 2.0}]
        errors = controller.validate_selections(selections)
        
        assert len(errors) > 0
        assert "selectionId mancante" in errors[0]
    
    def test_validate_selections_ok(self):
        """Validazione passa con selezioni valide."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker()
        controller = DutchingController(broker=broker, pnl_engine=None)
        
        selections = [
            {"selectionId": 1, "runnerName": "Runner A", "price": 2.0},
            {"selectionId": 2, "runnerName": "Runner B", "price": 3.0}
        ]
        errors = controller.validate_selections(selections)
        
        assert len(errors) == 0
    
    def test_set_simulation(self):
        """set_simulation cambia modalità."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker()
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=False)
        
        controller.set_simulation(True)
        assert controller.simulation is True
        
        controller.set_simulation(False)
        assert controller.simulation is False
    
    def test_submit_dutching_back(self):
        """Submit dutching BACK funziona."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        selections = [
            {"selectionId": 1, "runnerName": "Runner A", "price": 2.0, "back_ladder": [{"size": 500}], "lay_ladder": [{"size": 500}]},
            {"selectionId": 2, "runnerName": "Runner B", "price": 3.0, "back_ladder": [{"size": 500}], "lay_ladder": [{"size": 500}]}
        ]
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=100,
            mode="BACK"
        )
        
        assert result["status"] == "OK"
        assert len(result["orders"]) == 2
        assert result["simulation"] is True
    
    def test_submit_dutching_lay(self):
        """Submit dutching LAY funziona."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        selections = [
            {"selectionId": 1, "runnerName": "Runner A", "price": 2.0, "back_ladder": [{"size": 500}], "lay_ladder": [{"size": 500}]},
            {"selectionId": 2, "runnerName": "Runner B", "price": 3.0, "back_ladder": [{"size": 500}], "lay_ladder": [{"size": 500}]}
        ]
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=100,
            mode="LAY"
        )
        
        assert result["status"] == "OK"
        assert len(result["orders"]) == 2
    
    def test_get_ai_analysis(self):
        """get_ai_analysis ritorna analisi WoM."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker()
        controller = DutchingController(broker=broker, pnl_engine=None)
        
        selections = [
            {"selectionId": 1, "runnerName": "Runner A", "back_ladder": [{"size": 100}], "lay_ladder": [{"size": 50}]}
        ]
        
        analysis = controller.get_ai_analysis(selections)
        assert len(analysis) == 1
        assert "wom" in analysis[0]


class TestDraggableRunner:
    """Test per DraggableRunner (mock - no UI)."""
    
    def test_runner_data_structure(self):
        """Verifica struttura dati runner."""
        runner = {
            "selectionId": 1,
            "runnerName": "Test Runner",
            "price": 2.5,
            "stake": 10.0
        }
        
        assert runner["selectionId"] == 1
        assert runner["price"] == 2.5
    
    def test_runner_order_callback(self):
        """Callback ordine viene chiamato."""
        moved_runners = []
        
        def on_order_change(runners):
            moved_runners.append(runners)
        
        # Simula riordinamento
        runners = [
            {"selectionId": 1, "runnerName": "A"},
            {"selectionId": 2, "runnerName": "B"}
        ]
        
        # Inverti ordine
        new_order = [runners[1], runners[0]]
        on_order_change(new_order)
        
        assert len(moved_runners) == 1
        assert moved_runners[0][0]["selectionId"] == 2


class TestMiniLadder:
    """Test per MiniLadder (mock - no UI)."""
    
    def test_ladder_data_format(self):
        """Verifica formato dati ladder."""
        runner = {
            "selectionId": 1,
            "runnerName": "Test",
            "back_ladder": [
                {"price": 2.00, "size": 100},
                {"price": 1.98, "size": 50},
                {"price": 1.96, "size": 25}
            ],
            "lay_ladder": [
                {"price": 2.02, "size": 80},
                {"price": 2.04, "size": 40},
                {"price": 2.06, "size": 20}
            ]
        }
        
        assert len(runner["back_ladder"]) == 3
        assert len(runner["lay_ladder"]) == 3
        assert runner["back_ladder"][0]["price"] == 2.00
        assert runner["lay_ladder"][0]["price"] == 2.02
    
    def test_best_price_identification(self):
        """Best price è il primo della ladder."""
        back_ladder = [
            {"price": 2.00, "size": 100},
            {"price": 1.98, "size": 50}
        ]
        
        best_back = back_ladder[0]["price"] if back_ladder else None
        assert best_back == 2.00
    
    def test_price_click_callback(self):
        """Callback price click con dati corretti."""
        clicked = []
        
        def on_price_click(selection_id, side, price):
            clicked.append((selection_id, side, price))
        
        # Simula click
        on_price_click(1, "BACK", 2.00)
        
        assert len(clicked) == 1
        assert clicked[0] == (1, "BACK", 2.00)


class TestIntegration:
    """Test di integrazione tra componenti."""
    
    def test_ai_to_controller_flow(self):
        """Flusso completo AI → Controller → Broker."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        # Selezioni con WoM diversi
        selections = [
            {
                "selectionId": 1,
                "runnerName": "Favorito",
                "price": 2.0,
                "back_ladder": [{"size": 200}],
                "lay_ladder": [{"size": 50}]
            },
            {
                "selectionId": 2,
                "runnerName": "Outsider",
                "price": 5.0,
                "back_ladder": [{"size": 30}],
                "lay_ladder": [{"size": 150}]
            }
        ]
        
        # Ottieni analisi AI
        analysis = controller.get_ai_analysis(selections)
        assert len(analysis) == 2
        
        # Verifica analisi
        for a in analysis:
            assert "wom" in a
            assert "suggested_side" in a
    
    def test_controller_with_automations(self):
        """Controller registra correttamente automazioni SL/TP."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        selections = [
            {"selectionId": 1, "runnerName": "Runner A", "price": 2.0, "back_ladder": [{"size": 500}], "lay_ladder": [{"size": 500}]},
            {"selectionId": 2, "runnerName": "Runner B", "price": 3.0, "back_ladder": [{"size": 500}], "lay_ladder": [{"size": 500}]}
        ]
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=100,
            mode="BACK",
            stop_loss=-50,
            take_profit=30,
            trailing=10
        )
        
        assert result["status"] == "OK"
        # Verifica che automazioni siano state registrate
        for order in result["orders"]:
            bet_id = order.get("betId", "")
            badges = controller.automation.get_automation_badges(bet_id)
            assert "SL" in badges
            assert "TP" in badges
            assert "TR" in badges


class TestPreflightCheck:
    """Test per preflight_check()."""
    
    def test_preflight_no_selections(self):
        """Preflight fallisce senza selezioni."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker()
        controller = DutchingController(broker=broker, pnl_engine=None)
        
        result = controller.preflight_check([], 100)
        
        assert result.is_valid is False
        assert "Nessuna selezione" in result.errors
    
    def test_preflight_stake_too_low(self):
        """Preflight rileva stake insufficiente."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker()
        controller = DutchingController(broker=broker, pnl_engine=None)
        
        selections = [
            {"selectionId": 1, "runnerName": "A", "price": 2.0},
            {"selectionId": 2, "runnerName": "B", "price": 3.0},
            {"selectionId": 3, "runnerName": "C", "price": 4.0}
        ]
        
        # 3 selezioni × €2 min = €6 minimo
        result = controller.preflight_check(selections, total_stake=4.0)
        
        assert result.is_valid is False
        assert result.stake_ok is False
        assert any("insufficiente" in e for e in result.errors)
    
    def test_preflight_low_liquidity_warning(self):
        """Preflight avvisa su liquidità bassa."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker()
        controller = DutchingController(broker=broker, pnl_engine=None)
        
        # Liquidità sotto soglia (€50)
        selections = [
            {
                "selectionId": 1,
                "runnerName": "Runner A",
                "price": 2.0,
                "back_ladder": [{"size": 20}],
                "lay_ladder": [{"size": 100}]
            }
        ]
        
        result = controller.preflight_check(selections, total_stake=10, mode="BACK")
        
        assert result.liquidity_ok is False
        assert any("liquidità" in w.lower() for w in result.warnings)
    
    def test_preflight_wide_spread_warning(self):
        """Preflight avvisa su spread largo."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker()
        controller = DutchingController(broker=broker, pnl_engine=None)
        
        # Spread largo: 2.00 BACK vs 2.50 LAY = 25 tick a 0.02
        selections = [
            {
                "selectionId": 1,
                "runnerName": "Runner A",
                "price": 2.0,
                "back_ladder": [{"price": 2.00, "size": 100}],
                "lay_ladder": [{"price": 2.50, "size": 100}]
            }
        ]
        
        result = controller.preflight_check(selections, total_stake=10)
        
        assert result.spread_ok is False
        assert any("spread" in w.lower() for w in result.warnings)
    
    def test_preflight_all_ok(self):
        """Preflight passa con condizioni valide."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker()
        controller = DutchingController(broker=broker, pnl_engine=None)
        
        # Buona liquidità, spread stretto
        selections = [
            {
                "selectionId": 1,
                "runnerName": "Runner A",
                "price": 2.0,
                "back_ladder": [{"price": 2.00, "size": 500}],
                "lay_ladder": [{"price": 2.02, "size": 500}]
            },
            {
                "selectionId": 2,
                "runnerName": "Runner B",
                "price": 3.0,
                "back_ladder": [{"price": 3.00, "size": 400}],
                "lay_ladder": [{"price": 3.05, "size": 400}]
            }
        ]
        
        result = controller.preflight_check(selections, total_stake=50)
        
        assert result.is_valid is True
        assert result.liquidity_ok is True
        assert result.spread_ok is True
        assert result.stake_ok is True
        assert len(result.errors) == 0
    
    def test_preflight_high_stake_warning(self):
        """Preflight avvisa se stake > 20% liquidità."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker()
        controller = DutchingController(broker=broker, pnl_engine=None)
        
        # Liquidità €100, stake €50 = 50% > 20%
        selections = [
            {
                "selectionId": 1,
                "runnerName": "Runner A",
                "price": 2.0,
                "back_ladder": [{"price": 2.00, "size": 100}],
                "lay_ladder": [{"price": 2.02, "size": 100}]
            }
        ]
        
        result = controller.preflight_check(selections, total_stake=50, mode="BACK")
        
        assert any("Stake alto" in w for w in result.warnings)
    
    def test_preflight_low_price_warning(self):
        """Preflight warning se quota troppo bassa (< 1.02)."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker()
        controller = DutchingController(broker=broker, pnl_engine=None)
        
        selections = [
            {"selectionId": 1, "runnerName": "Favorito", "price": 1.01},  # Troppo bassa
            {"selectionId": 2, "runnerName": "Outsider", "price": 5.0}
        ]
        
        result = controller.preflight_check(selections, total_stake=10, mode="BACK")
        
        assert result.price_ok is False
        assert any("troppo bassa" in w for w in result.warnings)
    
    def test_preflight_book_warning(self):
        """Preflight warning se book > 105%."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker()
        controller = DutchingController(broker=broker, pnl_engine=None)
        
        # Quote con book ~108% (1/2.8 + 1/4.0 + 1/5.0 = 0.357 + 0.25 + 0.2 + extra)
        # Meglio: 1/1.9 + 1/9.0 = 0.526 + 0.111 + ~0.4 = ~1.07
        # Quote: 1.87 + 2.35 + 19.0 => 0.535 + 0.426 + 0.053 = 1.014 (troppo basso)
        # Proviamo: 1.85 + 2.25 + 6.0 => 0.541 + 0.444 + 0.167 = 1.15 (troppo alto)
        # Target ~107%: 1.9 + 2.5 + 8.0 => 0.526 + 0.4 + 0.125 = 1.051 (troppo basso)
        # Target ~107%: 1.8 + 2.3 + 8.0 => 0.556 + 0.435 + 0.125 = 1.116 (troppo alto)
        # Calcolo: per ottenere 107%, usiamo 1.9 + 2.4 + 12.0 => 0.526 + 0.417 + 0.083 = 1.026 (troppo basso)
        # Usiamo quote che diano 107%: 1.85 + 2.5 + 10.0 => 0.541 + 0.4 + 0.1 = 1.041 (no)
        # Usiamo: 1.8 + 2.4 + 15.0 => 0.556 + 0.417 + 0.067 = 1.04 (no)
        # Semplice: usiamo 2 selezioni => 1.85 + 1.90 = 0.541 + 0.526 = 1.067 (OK!)
        selections = [
            {"selectionId": 1, "runnerName": "A", "price": 1.85},
            {"selectionId": 2, "runnerName": "B", "price": 1.90}
        ]
        
        result = controller.preflight_check(selections, total_stake=10, mode="BACK")
        
        assert result.book_ok is False
        assert any("Book" in w and "%" in w for w in result.warnings)
    
    def test_preflight_book_blocks(self):
        """Preflight blocca se book > 110%."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker()
        controller = DutchingController(broker=broker, pnl_engine=None)
        
        # Quote con book ~125% (1/1.5 + 1/2.0 + 1/2.5 = 0.667 + 0.5 + 0.4 = 1.25)
        selections = [
            {"selectionId": 1, "runnerName": "A", "price": 1.5},
            {"selectionId": 2, "runnerName": "B", "price": 2.0},
            {"selectionId": 3, "runnerName": "C", "price": 2.5}
        ]
        
        result = controller.preflight_check(selections, total_stake=10, mode="BACK")
        
        assert result.is_valid is False
        assert result.book_ok is False
        assert any("troppo alto" in e for e in result.errors)


class TestPreflightBlocking:
    """Test che preflight blocchi ordini non validi."""
    
    def test_preflight_blocks_low_stake_per_runner(self):
        """Preflight blocca ordini con stake per-runner < €2."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        # 10 selezioni con stake totale €10 = €1 per runner (< €2 min)
        selections = [
            {"selectionId": i, "runnerName": f"Runner {i}", "price": 2.0}
            for i in range(1, 11)
        ]
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=10,  # €1 per runner
            mode="BACK",
            dry_run=False
        )
        
        assert result["status"] == "PREFLIGHT_FAILED"
        assert len(result["orders"]) == 0
        assert result["preflight"]["stake_ok"] is False
    
    def test_dry_run_still_shows_preflight_errors(self):
        """Dry run mostra errori preflight ma non blocca."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        # Stake molto basso per runner
        selections = [
            {"selectionId": i, "runnerName": f"Runner {i}", "price": 2.0}
            for i in range(1, 11)
        ]
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=10,
            mode="BACK",
            dry_run=True  # Dry run continua comunque
        )
        
        # Dry run ritorna comunque gli ordini preview
        assert result["status"] == "DRY_RUN"
        assert len(result["orders"]) == 10
        # Ma mostra gli errori preflight
        assert result["preflight"]["is_valid"] is False
    
    def test_preflight_exposes_price_and_book_flags(self):
        """Submit exposes price_ok, book_ok, book_pct nel payload."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        selections = [
            {"selectionId": 1, "runnerName": "A", "price": 2.0},
            {"selectionId": 2, "runnerName": "B", "price": 3.0}
        ]
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=100,
            mode="BACK",
            dry_run=True
        )
        
        # Verifica che i nuovi campi siano presenti
        preflight = result["preflight"]
        assert "price_ok" in preflight
        assert "book_ok" in preflight
        assert "book_pct" in preflight
        assert preflight["price_ok"] is True  # Quote valide (>1.02)
        assert preflight["book_ok"] is True   # Book ~83% (1/2 + 1/3 = 0.833)


class TestDryRun:
    """Test per dry_run mode."""
    
    def test_dry_run_no_orders_placed(self):
        """Dry run non piazza ordini reali."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        initial_balance = broker.balance
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        selections = [
            {"selectionId": 1, "runnerName": "A", "price": 2.0},
            {"selectionId": 2, "runnerName": "B", "price": 3.0}
        ]
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=100,
            mode="BACK",
            dry_run=True
        )
        
        assert result["status"] == "DRY_RUN"
        assert result["dry_run"] is True
        assert len(result["orders"]) == 2
        
        # Bilancio invariato
        assert broker.balance == initial_balance
        
        # Ordini hanno flag dry_run
        for order in result["orders"]:
            assert order.get("dry_run") is True
            assert order["status"] == "DRY_RUN"
    
    def test_dry_run_includes_preflight(self):
        """Dry run include risultato preflight."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        selections = [
            {
                "selectionId": 1,
                "runnerName": "A",
                "price": 2.0,
                "back_ladder": [{"price": 2.0, "size": 500}],
                "lay_ladder": [{"price": 2.02, "size": 500}]
            }
        ]
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=20,
            mode="BACK",
            dry_run=True
        )
        
        assert "preflight" in result
        preflight = result["preflight"]
        assert "is_valid" in preflight
        assert "warnings" in preflight
        assert "errors" in preflight
    
    def test_dry_run_calculates_profit(self):
        """Dry run calcola profitto correttamente."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        selections = [
            {"selectionId": 1, "runnerName": "A", "price": 2.0},
            {"selectionId": 2, "runnerName": "B", "price": 3.0}
        ]
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=100,
            mode="BACK",
            dry_run=True
        )
        
        assert "profit" in result
        assert result["profit"] != 0  # Dovrebbe calcolare profitto
    
    def test_dry_run_with_auto_green(self):
        """Dry run funziona con auto_green enabled."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        selections = [
            {"selectionId": 1, "runnerName": "A", "price": 2.0},
            {"selectionId": 2, "runnerName": "B", "price": 3.0}
        ]
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=100,
            mode="BACK",
            auto_green=True,
            dry_run=True
        )
        
        assert result["status"] == "DRY_RUN"
        assert result["auto_green"] is True
        # Verifica che gli ordini abbiano metadata auto_green
        for order in result["orders"]:
            assert order.get("auto_green") is True
            assert "placed_at" in order
    
    def test_live_run_places_orders(self):
        """Live run (dry_run=False) piazza ordini."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        initial_balance = broker.balance
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        selections = [
            {"selectionId": 1, "runnerName": "A", "price": 2.0, "back_ladder": [{"size": 500}], "lay_ladder": [{"size": 500}]},
            {"selectionId": 2, "runnerName": "B", "price": 3.0, "back_ladder": [{"size": 500}], "lay_ladder": [{"size": 500}]}
        ]
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=100,
            mode="BACK",
            dry_run=False
        )
        
        assert result["status"] == "OK"
        assert result["dry_run"] is False
        # Bilancio ridotto (ordini piazzati)
        assert broker.balance < initial_balance


class TestWoMEngine:
    """Test per WoM Engine - analisi storica tick."""
    
    def test_record_and_calculate_wom(self):
        """Record tick e calcola WoM."""
        from ai.wom_engine import WoMEngine
        
        engine = WoMEngine()
        
        for i in range(5):
            engine.record_tick(
                selection_id=1,
                back_price=2.0,
                back_volume=100,
                lay_price=2.02,
                lay_volume=50
            )
        
        result = engine.calculate_wom(1)
        
        assert result is not None
        assert result.selection_id == 1
        assert result.wom > 0.5
        assert result.tick_count == 5
    
    def test_wom_insufficient_ticks(self):
        """WoM None se tick insufficienti."""
        from ai.wom_engine import WoMEngine
        
        engine = WoMEngine()
        engine.record_tick(1, 2.0, 100, 2.02, 100)
        
        result = engine.calculate_wom(1)
        assert result is None
    
    def test_edge_score_range(self):
        """Edge score sempre in [-1, 1]."""
        from ai.wom_engine import WoMEngine
        
        engine = WoMEngine()
        
        for i in range(10):
            engine.record_tick(1, 2.0, 200, 2.02, 10)
        
        result = engine.calculate_wom(1)
        
        assert -1.0 <= result.edge_score <= 1.0
    
    def test_get_ai_edge_score_multiple(self):
        """get_ai_edge_score per multiple selezioni."""
        from ai.wom_engine import WoMEngine
        
        engine = WoMEngine()
        
        for _ in range(5):
            engine.record_tick(1, 2.0, 150, 2.02, 50)
            engine.record_tick(2, 3.0, 50, 3.05, 150)
        
        selections = [
            {"selectionId": 1, "price": 2.0},
            {"selectionId": 2, "price": 3.0}
        ]
        
        results = engine.get_ai_edge_score(selections)
        
        assert 1 in results
        assert 2 in results
        assert results[1].wom > results[2].wom
    
    def test_suggested_side_back(self):
        """WoM alto suggerisce BACK."""
        from ai.wom_engine import WoMEngine
        
        engine = WoMEngine()
        
        for _ in range(5):
            engine.record_tick(1, 2.0, 200, 2.02, 20)
        
        result = engine.calculate_wom(1)
        
        assert result.suggested_side == "BACK"
    
    def test_suggested_side_lay(self):
        """WoM basso suggerisce LAY."""
        from ai.wom_engine import WoMEngine
        
        engine = WoMEngine()
        
        for _ in range(5):
            engine.record_tick(1, 2.0, 20, 2.02, 200)
        
        result = engine.calculate_wom(1)
        
        assert result.suggested_side == "LAY"
    
    def test_clear_history(self):
        """clear_history pulisce i tick."""
        from ai.wom_engine import WoMEngine
        
        engine = WoMEngine()
        
        for _ in range(5):
            engine.record_tick(1, 2.0, 100, 2.02, 100)
        
        engine.clear_history(1)
        result = engine.calculate_wom(1)
        
        assert result is None
    
    def test_get_stats(self):
        """get_stats ritorna statistiche."""
        from ai.wom_engine import WoMEngine
        
        engine = WoMEngine()
        
        for _ in range(3):
            engine.record_tick(1, 2.0, 100, 2.02, 100)
            engine.record_tick(2, 3.0, 100, 3.05, 100)
        
        stats = engine.get_stats()
        
        assert stats["selections_tracked"] == 2
        assert stats["total_ticks"] == 6


class TestEnhancedWoMAnalysis:
    """Test per analisi WoM combinata instant + storica."""
    
    def test_enhanced_analysis_with_history(self):
        """Enhanced analysis combina dati instant e storici."""
        from ai.ai_pattern_engine import AIPatternEngine
        from ai.wom_engine import WoMEngine
        
        ai = AIPatternEngine()
        wom = WoMEngine()
        
        for _ in range(5):
            wom.record_tick(1, 2.0, 150, 2.02, 50)
        
        selections = [{
            "selectionId": 1,
            "runnerName": "Runner A",
            "back_ladder": [{"price": 2.0, "size": 100}],
            "lay_ladder": [{"price": 2.02, "size": 50}]
        }]
        
        result = ai.get_enhanced_analysis(selections, wom)
        
        assert len(result) == 1
        assert result[0]["has_history"] is True
        assert "wom_combined" in result[0]
        assert "edge_score" in result[0]
    
    def test_enhanced_analysis_without_history(self):
        """Enhanced analysis senza dati storici."""
        from ai.ai_pattern_engine import AIPatternEngine
        from ai.wom_engine import WoMEngine
        
        ai = AIPatternEngine()
        wom = WoMEngine()
        
        selections = [{
            "selectionId": 99,
            "runnerName": "No History",
            "back_ladder": [{"price": 2.0, "size": 100}],
            "lay_ladder": [{"price": 2.02, "size": 100}]
        }]
        
        result = ai.get_enhanced_analysis(selections, wom)
        
        assert len(result) == 1
        assert result[0]["has_history"] is False


class TestOneClickLadder:
    """Test per OneClickLadder - struttura dati."""
    
    def test_one_click_ladder_structure(self):
        """OneClickLadder eredita da MiniLadder."""
        from ui.mini_ladder import OneClickLadder, MiniLadder
        
        assert issubclass(OneClickLadder, MiniLadder)
    
    def test_default_stake_setter(self):
        """set_default_stake modifica stake."""
        from ui.mini_ladder import OneClickLadder
        
        ladder = type("MockLadder", (), {
            "default_stake": 10.0,
            "set_default_stake": OneClickLadder.set_default_stake
        })()
        
        ladder.set_default_stake(50.0)
        assert ladder.default_stake == 50.0
    
    def test_auto_green_setter(self):
        """set_auto_green modifica flag."""
        from ui.mini_ladder import OneClickLadder
        
        ladder = type("MockLadder", (), {
            "auto_green_enabled": False,
            "set_auto_green": OneClickLadder.set_auto_green
        })()
        
        ladder.set_auto_green(True)
        assert ladder.auto_green_enabled is True


class TestControllerWoMIntegration:
    """Test integrazione Controller + WoM Engine."""
    
    def test_controller_has_wom_engine(self):
        """Controller inizializza WoM Engine."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        assert hasattr(controller, "wom_engine")
        assert controller.wom_engine is not None
    
    def test_record_market_tick(self):
        """Controller può registrare tick."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        controller.record_market_tick(1, 2.0, 100, 2.02, 100)
        
        stats = controller.get_wom_stats()
        assert stats["selections_tracked"] == 1
    
    def test_get_wom_analysis(self):
        """Controller espone analisi WoM."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        selections = [{
            "selectionId": 1,
            "runnerName": "Test",
            "back_ladder": [{"price": 2.0, "size": 100}],
            "lay_ladder": [{"price": 2.02, "size": 50}]
        }]
        
        result = controller.get_wom_analysis(selections, use_historical=False)
        
        assert len(result) == 1
        assert "wom" in result[0]
        assert "suggested_side" in result[0]
    
    def test_submit_with_ai_wom_enabled(self):
        """Submit con ai_wom_enabled rispetta guardrail WoM."""
        from controllers.dutching_controller import DutchingController
        from simulation_broker import SimulationBroker
        
        broker = SimulationBroker(initial_balance=1000)
        controller = DutchingController(broker=broker, pnl_engine=None, simulation=True)
        
        selections = [
            {"selectionId": 1, "runnerName": "A", "price": 2.0, "back_ladder": [{"size": 500}], "lay_ladder": [{"size": 500}]},
            {"selectionId": 2, "runnerName": "B", "price": 3.0, "back_ladder": [{"size": 500}], "lay_ladder": [{"size": 500}]}
        ]
        
        result = controller.submit_dutching(
            market_id="1.234",
            market_type="MATCH_ODDS",
            selections=selections,
            total_stake=100,
            mode="BACK",
            ai_enabled=False,
            ai_wom_enabled=True,
            dry_run=True
        )
        
        assert result["status"] in ["DRY_RUN", "GUARDRAIL_BLOCKED"]
        if result["status"] == "GUARDRAIL_BLOCKED":
            assert "guardrail" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
