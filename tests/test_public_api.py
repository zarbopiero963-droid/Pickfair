import importlib


def test_telegram_listener_public_api():
    mod = importlib.import_module("telegram_listener")

    required = [
        "TelegramListener",
        "SignalQueue",
        "parse_signal_message",
    ]

    for name in required:
        assert hasattr(mod, name), f"Missing public API: {name}"