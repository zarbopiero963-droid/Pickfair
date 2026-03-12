from core.trading_engine import TradingEngine


class DummyClient:
    def place_order(self, *args, **kwargs):
        return {"status": "SUCCESS", "betId": "123"}

    def cancel_order(self, *args, **kwargs):
        return {"status": "SUCCESS"}

    def replace_order(self, *args, **kwargs):
        return {"status": "SUCCESS"}


def test_microstake_flow():
    engine = TradingEngine(client=DummyClient())

    result = engine.quick_bet(
        market_id="1.1",
        selection_id=1,
        price=2.0,
        stake=0.5,
        side="BACK",
    )

    assert result["status"] == "SUCCESS"