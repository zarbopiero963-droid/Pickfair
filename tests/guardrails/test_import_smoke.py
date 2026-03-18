import importlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CRITICAL_MODULES_PATH = ROOT / "guardrails" / "critical_modules.json"


def test_critical_modules_manifest_exists_and_has_modules():
    assert CRITICAL_MODULES_PATH.exists(), "Missing guardrails/critical_modules.json"

    data = json.loads(CRITICAL_MODULES_PATH.read_text(encoding="utf-8"))
    modules = data.get("modules", [])

    assert isinstance(modules, list)
    assert modules, "critical_modules.json contains no modules"
    assert all(isinstance(module_name, str) and module_name.strip() for module_name in modules)


def test_critical_modules_import_cleanly():
    data = json.loads(CRITICAL_MODULES_PATH.read_text(encoding="utf-8"))
    modules = data.get("modules", [])

    failures = []

    for module_name in modules:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            failures.append(f"{module_name}: {exc.__class__.__name__}: {exc}")

    assert not failures, "Critical import smoke failed:\n" + "\n".join(failures)