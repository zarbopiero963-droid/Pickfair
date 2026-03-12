from tick_dispatcher import TickDispatcher


def test_dispatch_to_multiple():
    disp = TickDispatcher()

    a, b = [], []

    disp.subscribe(lambda t: a.append(t))
    disp.subscribe(lambda t: b.append(t))

    disp.dispatch({"p": 1})

    assert a and b