from tick_dispatcher import TickDispatcher


def test_tick_dispatcher_multiple_subscribers():
    dispatcher = TickDispatcher()

    counters = {"a": 0, "b": 0}

    def sub_a(tick):
        counters["a"] += 1

    def sub_b(tick):
        counters["b"] += 1

    dispatcher.subscribe(sub_a)
    dispatcher.subscribe(sub_b)

    dispatcher.dispatch({"price": 2.0})

    assert counters["a"] == 1
    assert counters["b"] == 1