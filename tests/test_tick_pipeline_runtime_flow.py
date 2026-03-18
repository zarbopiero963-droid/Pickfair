import importlib

dispatcher_mod = importlib.import_module("core.tick_dispatcher")
TickDispatcher = dispatcher_mod.TickDispatcher


def test_tick_pipeline_burst_and_multiple_subscribers():
    dispatcher = TickDispatcher()

    received_a = []
    received_b = []

    dispatcher.subscribe(lambda tick: received_a.append(tick))
    dispatcher.subscribe(lambda tick: received_b.append(tick))

    burst = [{"price": i} for i in range(50)]

    for tick in burst:
        dispatcher.dispatch(tick)

    assert len(received_a) == 50
    assert len(received_b) == 50
    assert received_a[0]["price"] == 0
    assert received_b[-1]["price"] == 49