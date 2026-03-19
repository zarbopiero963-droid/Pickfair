import sys
import types

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
from betfair_client import BetfairClient, with_retry  # noqa: E402


def test_betfair_client_clean_string_removes_whitespace():
    assert BetfairClient._clean_string("  ab \n c \t ") == "abc"


def test_betfair_client_adjust_price_with_slippage_back_and_lay():
    client = BetfairClient("u", "k", "cert", "key")
    assert client._adjust_price_with_slippage(2.0, "BACK", 1) < 2.0
    assert client._adjust_price_with_slippage(2.0, "LAY", 1) > 2.0
    assert client._adjust_price_with_slippage(1.02, "BACK", 10) >= 1.01
    assert client._adjust_price_with_slippage(999.0, "LAY", 10) <= 1000


def test_with_retry_retries_transient_failures(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr("betfair_client.time.sleep", lambda *_args, **_kwargs: None)

    @with_retry
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise Exception("502 bad gateway")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_with_retry_does_not_retry_non_transient_failures(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr("betfair_client.time.sleep", lambda *_args, **_kwargs: None)

    @with_retry
    def bad():
        calls["n"] += 1
        raise Exception("invalid_session")

    with pytest.raises(Exception, match="invalid_session"):
        bad()
    assert calls["n"] == 1
