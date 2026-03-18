from tools.ai_reasoning_guard import run_guard


KNOWN_FILES = [
    "controllers/dutching_controller.py",
    "telegram_listener.py",
]


def test_reasoning_guard_runs_without_ai_for_known_files():
    report = run_guard(KNOWN_FILES)

    assert report["ok"] is True
    assert report["decision"] in {"allow", "review"}
    assert report["mode"] in {"offline", "remote"}

    assert "impact_analysis" in report
    assert "semantic_checks" in report
    assert "runtime_smokes" in report
    assert "mutation_probes" in report
    assert isinstance(report["findings"], list)
    assert isinstance(report["issues"], list)


def test_reasoning_guard_preserves_requested_files():
    report = run_guard(KNOWN_FILES)
    assert report["files_checked"] == KNOWN_FILES


def test_reasoning_guard_offline_contract_for_known_files():
    report = run_guard(KNOWN_FILES)

    impact = report["impact_analysis"]
    assert "changed_modules" in impact
    assert "impacted_modules" in impact

    semantic = report["semantic_checks"]
    assert "ok" in semantic
    assert "checks" in semantic

    runtime = report["runtime_smokes"]
    assert "ok" in runtime

    mutation = report["mutation_probes"]
    assert "ok" in mutation
    assert "probes" in mutation