import importlib


def test_public_api_contract():
    telegram_listener = importlib.import_module("telegram_listener")

    required = [
        "parse_signal_message",
    ]

    for name in required:
        assert hasattr(telegram_listener, name), f"Missing API: {name}"