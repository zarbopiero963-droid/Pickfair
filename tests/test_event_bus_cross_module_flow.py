import importlib

bus_mod = importlib.import_module("core.event_bus")
EventBus = bus_mod.EventBus


def test_event_bus_cross_module_flow():
    bus = EventBus()

    path = []

    def telegram_handler(payload):
        path.append("telegram")
        bus.publish("CONTROLLER_SIGNAL", payload)

    def controller_handler(payload):
        path.append("controller")
        bus.publish("ENGINE_SIGNAL", payload)

    def engine_handler(payload):
        path.append("engine")
        bus.publish("UI_UPDATE", payload)

    def ui_handler(payload):
        path.append("ui")

    bus.subscribe("TELEGRAM_SIGNAL", telegram_handler)
    bus.subscribe("CONTROLLER_SIGNAL", controller_handler)
    bus.subscribe("ENGINE_SIGNAL", engine_handler)
    bus.subscribe("UI_UPDATE", ui_handler)

    bus.publish("TELEGRAM_SIGNAL", {"signal": "BACK"})

    assert path == ["telegram", "controller", "engine", "ui"]