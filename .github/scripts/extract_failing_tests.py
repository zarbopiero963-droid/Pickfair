#!/usr/bin/env python3

import json
import re
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_RAW = ROOT / "audit_raw"
AUDIT_OUT = ROOT / "audit_out"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def extract_failed_tests(log: str):

    pattern = r"(FAILED|ERROR)\s+(tests\/[^\s]+::[^\s]+)"

    matches = re.findall(pattern, log)

    failed = []

    for _, test in matches:
        failed.append(test)

    return list(set(failed))


def test_to_module(test_name: str):

    file_part = test_name.split("::")[0]

    name = Path(file_part).name

    if name.startswith("test_"):
        module = name.replace("test_", "")
        module = module.replace(".py", "")

        return module + ".py"

    return ""


def main():

    log = read_text(AUDIT_RAW / "pytest.log")

    failing_tests = extract_failed_tests(log)

    targets = []

    for test in failing_tests:

        module = test_to_module(test)

        targets.append(
            {
                "test": test,
                "test_file": test.split("::")[0],
                "probable_module": module,
            }
        )

    result = {
        "failing_tests": failing_tests,
        "targets": targets,
    }

    write_json(AUDIT_OUT / "failing_tests.json", result)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()