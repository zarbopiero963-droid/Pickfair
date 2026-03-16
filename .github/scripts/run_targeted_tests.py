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


def normalize(p):
    return str(p).replace("\\", "/").lstrip("./")


def collect_targets():

    candidate = read_json(AUDIT_OUT / "patch_candidate.json")
    patch = candidate.get("patch_candidate", {})

    tests = patch.get("related_tests", []) or []

    targets = []

    for t in tests:
        t = normalize(t)
        if t:
            targets.append(t)

    return list(dict.fromkeys(targets))


def run_pytest(targets):

    if not targets:
        return {
            "summary": {
                "executed_count": 0
            },
            "failure_count": 0,
            "targets": []
        }

    cmd = ["pytest", "-q"] + targets

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(ROOT)
        )

        output = proc.stdout + "\n" + proc.stderr

        failures = output.count("FAILED")

        return {
            "summary": {
                "executed_count": len(targets)
            },
            "failure_count": failures,
            "targets": targets,
            "raw_output": output[:8000]
        }

    except Exception as e:

        return {
            "summary": {
                "executed_count": 0
            },
            "failure_count": 0,
            "targets": targets,
            "error": str(e)
        }


def main():

    targets = collect_targets()

    results = run_pytest(targets)

    write_json(
        AUDIT_OUT / "targeted_test_results.json",
        results
    )

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()