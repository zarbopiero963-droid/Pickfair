import random
import string

from telegram_listener import parse_signal_message


def random_string():
    alphabet = string.ascii_letters + string.digits + " _-:=@."
    return "".join(random.choice(alphabet) for _ in range(30))


def test_fuzz_parser_never_crashes_and_returns_only_none_or_dict():
    results = []

    for _ in range(200):
        parsed = parse_signal_message(random_string())
        results.append(parsed)

    assert len(results) == 200
    assert all(item is None or isinstance(item, dict) for item in results)