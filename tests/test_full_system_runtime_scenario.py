import importlib

listener_mod = importlib.import_module("telegram_listener")
engine_mod = importlib.import_module("core.trading_engine")

parse_signal_message = listener_mod.parse_signal_message
SignalQueue = listener_mod.SignalQueue
TradingEngine = engine_mod.TradingEngine


class DummyBus:
    def __init__(self):
        self.events = []
        self.subscribers = {}

    def publish(self, event, payload):
        self.events.append((event, payload))
        for h in self.subscribers.get(event, []):
            h(payload)

    def subscribe(self, event, handler):
        self.subscribers.setdefault(event, []).append(handler)


class DummyExecutor:
    def submit(self, name, fn, *args, **kwargs):
        return fn(*args, **kwargs)


class DummyDB:
    def __init__(self):
        self.saved_bets = []
        self.cashouts = []

    def save_bet(self, **kwargs):
        self.saved_bets.append(kwargs)

    def save_cashout_transaction(self, **kwargs):
        self.cashouts.append(kwargs)

    def get_simulation_settings(self):
        return {"virtual_balance": 1000}


class DummyClient:
    def place_bet(self, **kwargs):
        return {"status": "SUCCESS", "instructionReports": [{"sizeMatched": kwargs["size"]}]}


def test_full_system_runtime_scenario():
    message = """
    MASTER SIGNAL
    event_name: Juve - Milan
    market_name: Match Odds
    selection: Juve
    action: BACK
    master_price: 2.10
    market_id: 1.123
    selection_id: 11
    """

    parsed = parse_signal_message(message)
    queue = SignalQueue(maxsize=5)
    queue.push(parsed)

    signal = queue.pop()

    bus = DummyBus()
    db = DummyDB()
    client = DummyClient()

    engine = TradingEngine(bus, db, lambda: client, DummyExecutor())

    bet_payload = {
        "market_id": signal["market_id"],
        "selection_id": signal["selection_id"],
        "bet_type": signal["side"],
        "price": float(signal["price"]),
        "stake": 10,
        "event_name": signal["event_name"],
        "market_name": signal["market_name"],
        "runner_name": signal["selection"],
        "simulation_mode": False,
    }

    engine._handle_quick_bet(bet_payload)

    assert len(db.saved_bets) == 1

    cashout_payload = {
        "market_id": signal["market_id"],
        "selection_id": signal["selection_id"],
        "side": "LAY",
        "stake": 5,
        "price": 1.8,
        "green_up": 2,
    }

    engine._handle_cashout(cashout_payload)

    assert len(db.cashouts) == 1