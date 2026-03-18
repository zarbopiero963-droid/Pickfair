import pytest

from simulation_broker import SimulationBroker


def test_simulation_broker_init_sets_real_runtime_state():
    broker = SimulationBroker(initial_balance=100.0)

    assert broker.balance == 100.0
    assert broker.initial_balance == 100.0
    assert broker.commission == 4.5
    assert broker.orders == {}
    assert broker.bet_counter == 0


def test_simulation_broker_place_back_order_reduces_balance_and_stores_order():
    broker = SimulationBroker(initial_balance=100.0)

    result = broker.place_order(
        market_id="1.1",
        selection_id=10,
        side="BACK",
        price=2.0,
        size=5.0,
        runner_name="Runner A",
    )

    assert result["simulation"] is True
    assert result["side"] == "BACK"
    assert result["price"] == 2.0
    assert result["size"] == 5.0
    assert result["sizeMatched"] == 5.0
    assert result["sizeRemaining"] == 0.0
    assert result["status"] == "EXECUTION_COMPLETE"
    assert result["betId"].startswith("SIM-")

    assert broker.balance == 95.0
    assert broker.bet_counter == 1
    assert len(broker.orders) == 1


def test_simulation_broker_place_lay_order_reserves_liability():
    broker = SimulationBroker(initial_balance=100.0)

    result = broker.place_order(
        market_id="1.1",
        selection_id=20,
        side="LAY",
        price=3.0,
        size=4.0,
        runner_name="Runner B",
    )

    assert result["side"] == "LAY"
    assert result["sizeMatched"] == 4.0
    assert result["status"] == "EXECUTION_COMPLETE"

    expected_liability = 4.0 * (3.0 - 1.0)
    assert broker.balance == 100.0 - expected_liability


def test_simulation_broker_partial_match_keeps_remaining_size_open():
    broker = SimulationBroker(initial_balance=100.0)

    result = broker.place_order(
        market_id="1.1",
        selection_id=30,
        side="BACK",
        price=2.5,
        size=10.0,
        runner_name="Runner C",
        partial_match_pct=0.4,
    )

    assert result["sizeMatched"] == 4.0
    assert result["sizeRemaining"] == 6.0
    assert result["status"] == "EXECUTABLE"

    assert broker.balance == 90.0
    assert len(result["fills"]) == 1
    assert result["fills"][0]["size"] == 4.0


def test_simulation_broker_price_ladder_applies_slippage_runtime_logic():
    broker = SimulationBroker(initial_balance=100.0)

    result = broker.place_order(
        market_id="1.1",
        selection_id=40,
        side="BACK",
        price=2.0,
        size=6.0,
        runner_name="Runner D",
        price_ladder=[
            {"price": 2.0, "size": 2.0},
            {"price": 2.02, "size": 4.0},
        ],
    )

    assert result["sizeMatched"] == 6.0
    assert result["sizeRemaining"] == 0.0
    assert result["status"] == "EXECUTION_COMPLETE"
    assert result["priceRequested"] == 2.0
    assert result["price"] >= 2.0
    assert len(result["fills"]) >= 1 