from tick_storage import TickStorage


def test_tick_storage_append():
    store = TickStorage()

    store.add_tick("1.1", {"price": 2.0})

    ticks = store.get_ticks("1.1")

    assert len(ticks) >= 1