#!/usr/bin/env python3

import json
import subprocess
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def read_json(path: Path):
    try:
        return json.loads(read_text(path))
    except Exception:
        return {}


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize_path(path_str: str) -> str:
    raw = str(path_str or "").strip().replace("\\", "/")
    if not raw:
        return ""
    while raw.startswith("./"):
        raw = raw[2:]
    return raw


def repo_exists(rel_path: str) -> bool:
    rel = normalize_path(rel_path)
    return bool(rel) and (ROOT / rel).exists()


def unique_keep(items: list[str]) -> list[str]:
    out = []
    seen = set()
    for item in items:
        value = normalize_path(item)
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def fallback_tests() -> list[str]:
    candidates = [
        "tests/test_auto_updater.py",
        "tests/test_executor_manager_shutdown.py",
        "tests/test_executor_manager_parallel.py",
    ]
    return [x for x in candidates if repo_exists(x)]


def gather_targets() -> list[str]:
    candidate_payload = read_json(AUDIT_OUT / "patch_candidate.json")
    candidate = candidate_payload.get("patch_candidate") or {}
    if not isinstance(candidate, dict):
        candidate = {}

    tests = unique_keep(candidate.get("related_tests", []) or [])

    if not tests:
        tf_payload = read_json(AUDIT_OUT / "test_failure_context.json")
        target_file = normalize_path(candidate.get("target_file", ""))
        for item in tf_payload.get("test_failure_contexts", []) or []:
            if normalize_path(item.get("target_file", "")) == target_file:
                tests.extend(item.get("related_tests", []) or [])
        tests = unique_keep(tests)

    existing = [t for t in tests if repo_exists(t)]
    if existing:
        return existing

    return fallback_tests()


def run_pytest(targets: list[str]) -> tuple[bool, str]:
    if not targets:
        return False, "no_tests_found"

    cmd = ["pytest", "-q"] + targets
    try:
        result = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        return result.returncode == 0, output
    except Exception as e:
        return False, str(e)


def main() -> int:
    targets = gather_targets()
    success, output = run_pytest(targets)

    result = {
        "success": success,
        "tests_run": targets,
        "targets": targets,
        "output_snippet": output[:4000],
        "summary": {
            "executed_count": len(targets),
            "failure_count": 0 if success else (1 if targets else 0),
        },
        "failure_count": 0 if success else (1 if targets else 0),
    }

    write_json(AUDIT_OUT / "targeted_tests.json", result)
    write_json(AUDIT_OUT / "targeted_test_results.json", result)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())