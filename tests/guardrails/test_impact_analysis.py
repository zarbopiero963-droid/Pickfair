import os
from pathlib import Path

from tools.repo_guardrail import impact_analysis

ROOT = Path(__file__).resolve().parents[2]


def test_impact_analysis_runs():
    raw = os.environ.get("AI_CHANGED_FILES", "").strip()
    changed_files = [x.strip() for x in raw.split(",") if x.strip()] if raw else []

    result = impact_analysis(ROOT, changed_files)

    assert "changed_modules" in result
    assert "impacted_modules" in result
    assert "impacted_paths" in result

    assert isinstance(result["changed_modules"], list)
    assert isinstance(result["impacted_modules"], list)
    assert isinstance(result["impacted_paths"], list)