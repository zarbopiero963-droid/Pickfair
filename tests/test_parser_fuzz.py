import random
import string

from telegram_listener import parse_signal_message


def random_string():
    return "".join(random.choice(string.ascii_letters) for _ in range(30))


def test_fuzz_parser():
    for _ in range(200):
        parse_signal_message(random_string())