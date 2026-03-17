#!/usr/bin/env python3

import json
import subprocess
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize(path: str) -> str:
    return str(path or "").replace("\\", "/").strip()


def get_tests_from_candidate(candidate: dict) -> list[str]:
    tests = candidate.get("related_tests", []) or []
    return [normalize(t) for t in tests if t]


def fallback_tests() -> list[str]:
    return [
        "tests/test_auto_updater.py",
        "tests/test_executor_manager_shutdown.py",
        "tests/test_executor_manager_parallel.py",
    ]


def run_pytest(targets: list[str]) -> tuple[bool, str]:
    if not targets:
        targets = fallback_tests()

    existing = [t for t in targets if (ROOT / t).exists()]

    if not existing:
        return False, "no_tests_found"

    cmd = ["pytest", "-q"] + existing

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        success = result.returncode == 0
        output = result.stdout + "\n" + result.stderr
        return success, output
    except Exception as e:
        return False, str(e)


def main():
    candidate_data = read_json(AUDIT_OUT / "patch_candidate.json")
    candidate = candidate_data.get("patch_candidate", {}) or {}

    targets = get_tests_from_candidate(candidate)

    success, output = run_pytest(targets)

    result = {
        "success": success,
        "targets": targets,
        "output_snippet": output[:2000],
    }

    write_json(AUDIT_OUT / "targeted_tests.json", result)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()