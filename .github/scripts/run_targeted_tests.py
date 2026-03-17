#!/usr/bin/env python3

import json
import subprocess
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except:
        return {}


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2))


def run_tests(test_files):
    if not test_files:
        return True, "no tests"

    cmd = ["pytest", "-q"] + test_files

    result = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True
    )

    return result.returncode == 0, result.stdout + result.stderr


def main():
    candidate = read_json(AUDIT_OUT / "patch_candidate.json").get("patch_candidate", {})

    tests = candidate.get("related_tests", [])

    success, output = run_tests(tests)

    result = {
        "tests_run": tests,
        "success": success,
        "output": output[-2000:]
    }

    write_json(AUDIT_OUT / "targeted_tests.json", result)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()