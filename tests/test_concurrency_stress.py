import threading


def test_concurrency_stress(engine, broker):

    payload = {
        "market_id": "1.200",
        "selection_id": 10,
        "bet_type": "BACK",
        "price": 2,
        "stake": 5,
        "event_name": "Test",
        "market_name": "Odds",
        "runner_name": "Runner",
        "simulation_mode": False,
    }

    threads = []

    for _ in range(10):

        t = threading.Thread(target=engine._handle_quick_bet, args=(payload,))
        threads.append(t)

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    assert len(broker.orders) <= 10