from tick_dispatcher import DispatchMode, TickData, TickDispatcher


def test_tick_dispatcher_storage_callbacks_receive_every_tick():
    dispatcher = TickDispatcher()
    received = []
    dispatcher.register_storage_callback(lambda tick: received.append(tick.selection_id))

    dispatcher.dispatch_tick(TickData(market_id="1.1", selection_id=11, timestamp=1.0))
    dispatcher.dispatch_tick(TickData(market_id="1.1", selection_id=22, timestamp=2.0))

    assert received == [11, 22]


def test_tick_dispatcher_ui_and_automation_dispatch_after_interval(monkeypatch):
    dispatcher = TickDispatcher()
    ui_batches = []
    auto_batches = []
    dispatcher.register_ui_callback(lambda ticks: ui_batches.append(dict(ticks)))
    dispatcher.register_automation_callback(lambda ticks: auto_batches.append(dict(ticks)))

    times = iter([0.0, 1.0])
    monkeypatch.setattr("tick_dispatcher.time.time", lambda: next(times))

    dispatcher.dispatch_tick(TickData(market_id="1.1", selection_id=11, timestamp=1.0))
    dispatcher.dispatch_tick(TickData(market_id="1.2", selection_id=22, timestamp=2.0))

    assert len(ui_batches) >= 1
    assert len(auto_batches) >= 1
    stats = dispatcher.get_stats()
    assert stats["total_ticks"] == 2


def test_tick_dispatcher_simulation_mode_has_valid_mode_property():
    dispatcher = TickDispatcher()
    dispatcher.mode = DispatchMode.SIMULATION
    assert dispatcher.mode == DispatchMode.SIMULATION
    assert dispatcher.ui_interval == dispatcher.SIM_UI_UPDATE_INTERVAL
