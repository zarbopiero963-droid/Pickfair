from pathlib import Path

from tools.ai_reasoning_guard import run_mutation_probes

ROOT = Path(__file__).resolve().parents[2]
SPECS_PATH = ROOT / "guardrails" / "semantic_specs.json"


def test_mutation_probes_are_executed():
    result = run_mutation_probes(SPECS_PATH)

    assert result["ok"] is True
    assert result["specs_path"] == str(SPECS_PATH)
    assert "artifact" in result

    probes = result["probes"]
    assert isinstance(probes, list)
    assert len(probes) >= 1


def test_mutation_probe_entries_have_minimum_contract():
    result = run_mutation_probes(SPECS_PATH)

    for probe in result["probes"]:
        assert "id" in probe
        assert "ok" in probe
        assert isinstance(probe["id"], str)
        assert isinstance(probe["ok"], bool)