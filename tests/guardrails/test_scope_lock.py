import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_FILES_PATH = ROOT / "guardrails" / "allowed_files.json"


def test_changed_files_are_within_allowed_scope():
    assert ALLOWED_FILES_PATH.exists(), "Missing guardrails/allowed_files.json"

    data = json.loads(ALLOWED_FILES_PATH.read_text(encoding="utf-8"))
    allowed = set(data.get("allowed_files", []))

    raw = os.environ.get("AI_CHANGED_FILES", "").strip()
    if not raw:
        return

    changed_files = [x.strip() for x in raw.split(",") if x.strip()]
    violations = [f for f in changed_files if f not in allowed]

    assert not violations, (
        "AI touched files outside allowed scope:\n"
        + "\n".join(f"- {v}" for v in violations)
    )