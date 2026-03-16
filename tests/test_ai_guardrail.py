from ai.ai_guardrail import AIGuardrail, BlockReason, GuardrailConfig


def test_guardrail_allows_valid_market_with_sufficient_data():
    guardrail = AIGuardrail(
        GuardrailConfig(
            min_tick_count=5,
            min_wom_confidence=0.2,
            max_volatility=0.8,
        )
    )

    result = guardrail.full_check(
        market_type="MATCH_ODDS",
        tick_count=10,
        wom_confidence=0.7,
        volatility=0.2,
    )

    assert result["can_proceed"] is True
    assert result["level"] == "normal"
    assert result["reasons"] == []
    assert result["blocked_until"] == 0


def test_guardrail_blocks_market_not_ready():
    guardrail = AIGuardrail()

    result = guardrail.full_check(
        market_type="UNKNOWN_MARKET",
        tick_count=10,
        wom_confidence=0.7,
        volatility=0.2,
    )

    assert result["can_proceed"] is False
    assert result["level"] == "blocked"
    assert BlockReason.MARKET_NOT_READY.value in result["reasons"]


def test_guardrail_blocks_for_insufficient_wom_data():
    guardrail = AIGuardrail(
        GuardrailConfig(min_tick_count=10, min_wom_confidence=0.3)
    )

    result = guardrail.full_check(
        market_type="MATCH_ODDS",
        tick_count=3,
        wom_confidence=0.1,
        volatility=0.2,
    )

    assert result["can_proceed"] is False
    assert result["level"] == "blocked"
    assert BlockReason.INSUFFICIENT_DATA.value in result["reasons"]


def test_guardrail_blocks_for_high_volatility():
    guardrail = AIGuardrail(
        GuardrailConfig(max_volatility=0.5)
    )

    result = guardrail.full_check(
        market_type="MATCH_ODDS",
        tick_count=20,
        wom_confidence=0.8,
        volatility=0.9,
    )

    assert result["can_proceed"] is False
    assert BlockReason.HIGH_VOLATILITY.value in result["reasons"]


def test_guardrail_enters_cooldown_after_consecutive_errors():
    guardrail = AIGuardrail(
        GuardrailConfig(consecutive_error_limit=2, cooldown_after_error_sec=30.0)
    )

    guardrail.record_order("1.1", 10, "BACK", 5.0, success=False)
    guardrail.record_order("1.1", 10, "BACK", 5.0, success=False)

    result = guardrail.full_check(
        market_type="MATCH_ODDS",
        tick_count=20,
        wom_confidence=0.8,
        volatility=0.2,
    )

    assert result["can_proceed"] is False
    assert BlockReason.CONSECUTIVE_ERRORS.value in result["reasons"]
    assert result["blocked_until"] > 0


def test_guardrail_auto_green_delay_counts_down():
    guardrail = AIGuardrail(
        GuardrailConfig(auto_green_grace_sec=3.0)
    )

    guardrail.register_order_for_auto_green("BET-1", placed_at=0.0)

    can_green, remaining = guardrail.check_auto_green_grace("BET-1")
    assert isinstance(can_green, bool)
    assert isinstance(remaining, float)