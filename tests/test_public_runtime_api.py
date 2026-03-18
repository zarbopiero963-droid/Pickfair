from database import Database
from pnl_engine import PnLEngine
from core.trading_engine import TradingEngine


class DummyBus:
    def subscribe(self, *a, **k):
        pass

    def publish(self, *a, **k):
        pass


class DummyExecutor:
    def submit(self, name, fn, *a, **k):
        return fn(*a, **k)


class DummyClient:
    def place_bet(self, **k):
        return {"status": "SUCCESS", "instructionReports": []}

    def cancel_orders(self, **k):
        return {"status": "SUCCESS"}

    def replace_orders(self, **k):
        return {"status": "SUCCESS"}

    def get_current_orders(self, **k):
        return {"currentOrders": []}


def test_database_runtime_api(tmp_path):
    db = Database(db_path=str(tmp_path / "api.db"))

    db.save_settings({"theme": "dark"})
    settings = db.get_settings()

    assert settings["theme"] == "dark"

    db.close()


def test_pnl_engine_basic_contract():
    pnl = PnLEngine()

    result = pnl.calculate_profit(
        stake=10,
        odds=2.0,
        side="BACK",
    )

    assert result is not None


def test_trading_engine_initialization():
    db = type("DB", (), {
        "get_pending_sagas": lambda self: [],
        "get_simulation_settings": lambda self: {"virtual_balance": 1000}
    })()

    engine = TradingEngine(
        DummyBus(),
        db,
        lambda: DummyClient(),
        DummyExecutor()
    )

    assert engine is not None