import json
from pathlib import Path

from tools.repo_guardrail import build_public_api_snapshot

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = ROOT / "guardrails" / "public_api_snapshot.json"

EXPECTED_CORE_MODULES = {
    "controllers.dutching_controller",
    "core.event_bus",
    "core.trading_engine",
    "telegram_listener",
}


def test_public_api_snapshot_file_exists_and_is_valid_json():
    assert SNAPSHOT_PATH.exists(), (
        "Missing guardrails/public_api_snapshot.json. "
        "Generate it with: python tools/repo_guardrail.py snapshot-api"
    )

    data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data, "public_api_snapshot.json is empty"


def test_public_api_snapshot_contains_expected_core_modules():
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    missing = sorted(EXPECTED_CORE_MODULES - set(snapshot.keys()))
    assert not missing, f"Snapshot missing expected modules: {missing}"


def test_build_public_api_snapshot_has_expected_shape():
    current = build_public_api_snapshot(ROOT)

    assert isinstance(current, dict)
    assert current, "build_public_api_snapshot() returned an empty snapshot"

    for module_name in EXPECTED_CORE_MODULES:
        assert module_name in current, f"Generated snapshot missing module: {module_name}"
        assert "classes" in current[module_name]
        assert "functions" in current[module_name]
        assert isinstance(current[module_name]["classes"], dict)
        assert isinstance(current[module_name]["functions"], dict)