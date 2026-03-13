import json
from pathlib import Path

from tools.repo_guardrail import extract_top_level_dependencies

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_DEPS_PATH = ROOT / "guardrails" / "allowed_dependencies.json"


def test_no_unapproved_top_level_dependencies():
    assert ALLOWED_DEPS_PATH.exists(), "Missing guardrails/allowed_dependencies.json"

    allowed = set(
        json.loads(ALLOWED_DEPS_PATH.read_text(encoding="utf-8")).get(
            "allowed_dependencies",
            [],
        )
    )
    current = set(extract_top_level_dependencies(ROOT))

    unexpected = sorted(current - allowed)

    assert not unexpected, (
        "New top-level dependencies detected:\n"
        + "\n".join(f"- {dep}" for dep in unexpected)
    )