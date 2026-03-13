from tools.ai_reasoning_guard import run_mutation_probes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_mutation_probes_are_executed():
    result = run_mutation_probes(ROOT / "guardrails" / "semantic_specs.json")

    assert "ok" in result
    assert "probes" in result
    assert isinstance(result["probes"], list)
    assert len(result["probes"]) >= 1