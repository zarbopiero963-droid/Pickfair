import pytest

from betfair_client import BetfairClient


def test_client_init():
    client = BetfairClient()

    assert client is not None