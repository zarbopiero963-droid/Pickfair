def test_core_architecture_imports():
    import core.event_bus
    import core.risk_middleware
    import core.trading_engine
    import database
    import ai.ai_guardrail
    import ai.ai_pattern_engine
    import ai.wom_engine
    import dutching

    assert core.event_bus is not None
    assert core.risk_middleware is not None
    assert core.trading_engine is not None
    assert database is not None
    assert ai.ai_guardrail is not None
    assert ai.ai_pattern_engine is not None
    assert ai.wom_engine is not None
    assert dutching is not None