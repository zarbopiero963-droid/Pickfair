import json
from pathlib import Path

from tools.repo_guardrail import build_public_api_snapshot

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = ROOT / "guardrails" / "public_api_snapshot.json"


def test_public_api_matches_snapshot():
    """
    Guardrail test: verifies that the public API surface did not change.

    If you intentionally changed the API run:

        python tools/repo_guardrail.py snapshot-api
    """

    assert SNAPSHOT_PATH.exists(), (
        "Missing guardrails/public_api_snapshot.json.\n"
        "Generate it with:\n"
        "python tools/repo_guardrail.py snapshot-api"
    )

    current = build_public_api_snapshot(ROOT)
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    current_json = json.dumps(current, sort_keys=True, indent=2)
    expected_json = json.dumps(expected, sort_keys=True, indent=2)

    assert current_json == expected_json, (
        "Public API contract changed.\n\n"
        "If intentional regenerate snapshot with:\n"
        "python tools/repo_guardrail.py snapshot-api"
    )