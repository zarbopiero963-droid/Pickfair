def test_core_architecture_imports():
    import betfair_client
    import order_manager
    import circuit_breaker
    import executor_manager
    import market_tracker
    import tick_dispatcher
    import trading_config

    assert betfair_client is not None
    assert order_manager is not None
    assert circuit_breaker is not None