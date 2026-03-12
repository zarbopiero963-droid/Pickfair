import time

from ai.wom_engine import WoMEngine
from controllers.dutching_controller import DutchingController
from telegram_listener import TelegramListener


class DummyBus:
    def __init__(self):
        self.events = []
        self.last_event = None

    def publish(self, name, payload):
        self.last_event = (name, payload)
        self.events.append((name, payload))


def test_latency_wom_signal_generation():
    engine = WoMEngine()

    for _ in range(30):
        engine.record_tick(501, 2.0, 800.0, 2.02, 120.0)

    start = time.perf_counter()
    result = engine.get_time_window_signal(501)
    elapsed = time.perf_counter() - start

    assert result is not None
    assert elapsed < 0.03


def test_latency_controller_publish_payload():
    bus = DummyBus()
    ctrl = DutchingController(bus=bus, simulation=False)
    ctrl.current_event_name = "Juve - Milan"
    ctrl.current_market_name = "Match Odds"

    selections = [
        {
            "selectionId": 1,
            "runnerName": "Juve",
            "price": 2.0,
            "stake": 10.0,
            "back_ladder": [{"price": 2.0, "size": 10000.0}],
            "lay_ladder": [{"price": 2.02, "size": 10000.0}],
        }
    ]

    start = time.perf_counter()
    result = ctrl.submit_dutching(
        market_id="1.999",
        market_type="MATCH_ODDS",
        selections=selections,
        total_stake=10.0,
        mode="BACK",
    )
    elapsed = time.perf_counter() - start

    assert result["status"] == "SUBMITTED"
    assert bus.last_event is not None
    assert elapsed < 0.05


def test_latency_telegram_parse_master_signal():
    listener = TelegramListener(api_id=12345, api_hash="hash")

    message = (
        "🟢 MASTER SIGNAL\n"
        "event_name: Juve - Milan\n"
        "market_name: Match Odds\n"
        "selection: Juve\n"
        "action: BACK\n"
        "master_price: 2.10\n"
        "market_id: 1.123\n"
        "selection_id: 11\n"
    )

    start = time.perf_counter()
    result = listener.parse_signal(message)
    elapsed = time.perf_counter() - start

    assert result is not None
    assert elapsed < 0.02


def test_latency_telegram_parse_legacy_signal():
    listener = TelegramListener(api_id=12345, api_hash="hash")

    message = (
        "🆚 Juve - Milan\n"
        "Over 2.5\n"
        "@ 2.10\n"
        "stake 10\n"
        "punta"
    )

    start = time.perf_counter()
    result = listener.parse_signal(message)
    elapsed = time.perf_counter() - start

    assert result is not None
    assert elapsed < 0.02