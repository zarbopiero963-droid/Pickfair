import sys
import types
from types import SimpleNamespace

import pytest


def _install_betfair_stubs():
    if "betfairlightweight" in sys.modules:
        return
    mod = types.ModuleType("betfairlightweight")
    mod.APIClient = object
    mod.exceptions = types.SimpleNamespace(
        LoginError=Exception,
        CertsError=Exception,
        APIError=Exception,
    )
    filters_mod = types.SimpleNamespace(
        price_projection=lambda **kwargs: kwargs,
        market_filter=lambda **kwargs: kwargs,
        time_range=lambda **kwargs: kwargs,
    )
    streaming_mod = types.ModuleType("betfairlightweight.streaming")
    class StreamListener:
        pass
    streaming_mod.StreamListener = StreamListener
    mod.filters = filters_mod
    sys.modules["betfairlightweight"] = mod
    sys.modules["betfairlightweight.streaming"] = streaming_mod


_install_betfair_stubs()
from betfair_client import BetfairClient


class DummyAccountAPI:
    def __init__(self):
        self.calls = 0

    def get_account_funds(self):
        self.calls += 1
        return SimpleNamespace(available_to_bet_balance=100.0, exposure=-10.0)


class DummyBettingAPI:
    def __init__(self, price_data=None):
        self._price_data = price_data or []

    def list_market_book(self, **_kwargs):
        return self._price_data


class DummyClient:
    def __init__(self, price_data=None):
        self.account = DummyAccountAPI()
        self.betting = DummyBettingAPI(price_data=price_data)


class DummyRunnerEx:
    def __init__(self, back=None, lay=None):
        self.available_to_back = back or []
        self.available_to_lay = lay or []


class DummyPrice:
    def __init__(self, price):
        self.price = price


class DummyRunner:
    def __init__(self, selection_id, back=None, lay=None):
        self.selection_id = selection_id
        self.ex = DummyRunnerEx(back=back, lay=lay)


class DummyBook:
    def __init__(self, runners):
        self.runners = runners


def test_get_account_funds_returns_expected_shape():
    c = BetfairClient("u", "k", "cert", "key")
    c.client = DummyClient()
    funds = c.get_account_funds()
    assert funds == {"available": 100.0, "exposure": -10.0, "total": 110.0}


def test_get_fresh_price_reads_best_back_and_lay():
    books = [DummyBook(runners=[DummyRunner(11, back=[DummyPrice(2.0)], lay=[DummyPrice(2.04)])])]
    c = BetfairClient("u", "k", "cert", "key")
    c.client = DummyClient(price_data=books)
    assert c._get_fresh_price("1.1", 11, "BACK") == 2.0
    assert c._get_fresh_price("1.1", 11, "LAY") == 2.04


def test_get_account_funds_requires_connected_client():
    c = BetfairClient("u", "k", "cert", "key")
    with pytest.raises(Exception):
        c.get_account_funds()
