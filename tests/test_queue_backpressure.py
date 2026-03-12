from ui_queue import UIQueue


def test_queue_basic_flow():
    q = UIQueue()

    q.post(lambda: None)

    assert q.qsize() >= 1