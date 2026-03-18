class EventStore:

    def __init__(self):
        self.events = []

    def append(self, event):
        self.events.append(event)

    def replay(self):
        return list(self.events)


def test_event_replay():

    store = EventStore()

    for i in range(5):

        store.append({"price": i})

    assert store.replay() == store.replay()