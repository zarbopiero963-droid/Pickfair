from controllers.dutching_controller import DutchingController


class DummyBus:
    def publish(self, event_name, payload):
        self.last_event = (event_name, payload)


def test_liquidity_guard_blocks_low_liquidity():
    ctrl = DutchingController(bus=DummyBus(), simulation=True)

    selections = [
        {
            "selectionId": 1,
            "runnerName": "Napoli",
            "price": 2.0,
            "stake": 20.0,
            "back_ladder": [{"price": 2.0, "size": 2.0}],
            "lay_ladder": [{"price": 2.02, "size": 500}],
        }
    ]

    result = ctrl.submit_dutching(
        market_id="1.1",
        market_type="MATCH_ODDS",
        selections=selections,
        total_stake=20,
        mode="BACK",
        dry_run=False,
    )

    assert result["status"] in ("PREFLIGHT_FAILED", "VALIDATION_FAILED")


def test_liquidity_guard_lay_liability_logic():
    ctrl = DutchingController(bus=DummyBus(), simulation=True)

    selections = [
        {
            "selectionId": 1,
            "runnerName": "Napoli",
            "price": 4.0,
            "stake": 10.0,
            "side": "LAY",
            "back_ladder": [{"price": 3.95, "size": 500}],
            "lay_ladder": [{"price": 4.0, "size": 500}],
        }
    ]

    result = ctrl.submit_dutching(
        market_id="1.1",
        market_type="MATCH_ODDS",
        selections=selections,
        total_stake=10,
        mode="LAY",
        dry_run=True,
    )

    assert result["status"] == "DRY_RUN"