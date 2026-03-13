from tools.ai_reasoning_guard import run_guard


def test_reasoning_guard_runs_without_ai_for_known_files():
    report = run_guard(
        [
            "controllers/dutching_controller.py",
            "telegram_listener.py",
        ]
    )

    assert "decision" in report
    assert "impact_analysis" in report
    assert "semantic_checks" in report
    assert "runtime_smokes" in report
    assert "mutation_probes" in report
    assert isinstance(report["findings"], list)