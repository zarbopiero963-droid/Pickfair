from ai.ai_guardrail import AIGuardrail, get_guardrail


def test_full_check_allows_safe_market():
    guardrail = AIGuardrail()

    result = guardrail.full_check(
        market_type="MATCH_ODDS",
        tick_count=30,
        wom_confidence=0.6,
        volatility=0.10,
    )

    assert result["can_proceed"] is True
    assert result["level"] in ("normal", "warning")
    assert result["reasons"] == []


def test_full_check_blocks_high_volatility():
    guardrail = AIGuardrail()

    result = guardrail.full_check(
        market_type="MATCH_ODDS",
        tick_count=30,
        wom_confidence=0.6,
        volatility=0.95,
    )

    assert result["can_proceed"] is False
    assert "high_volatility" in result["reasons"]


def test_full_check_blocks_insufficient_data():
    guardrail = AIGuardrail()

    result = guardrail.full_check(
        market_type="MATCH_ODDS",
        tick_count=5,
        wom_confidence=0.2,
        volatility=0.10,
    )

    assert result["can_proceed"] is False
    assert "insufficient_data" in result["reasons"]


def test_get_guardrail_returns_singleton():
    g1 = get_guardrail()
    g2 = get_guardrail()

    assert g1 is g2


def test_get_status_returns_expected_keys():
    guardrail = AIGuardrail()
    status = guardrail.get_status()

    assert "level" in status
    assert "consecutive_errors" in status
    assert "orders_last_minute" in status
    assert "pending_auto_green" in status
    assert "blocked_until" in status
    assert "warnings" in status
    assert "block_reasons" in status

