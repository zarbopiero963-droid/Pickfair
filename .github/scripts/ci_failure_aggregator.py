#!/usr/bin/env python3

import json
import re
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_RAW = ROOT / "audit_raw"
AUDIT_OUT = ROOT / "audit_out"
LOG_DIR = AUDIT_RAW / "external_ci_logs"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def detect_python_file_error(line: str):
    """
    Detect patterns like:
    --> ai/ai_pattern_engine.py:30:26
    """
    m = re.search(r"([A-Za-z0-9_./-]+\.py):\d+", line)
    if m:
        return m.group(1)
    return ""


def detect_pytest_failure(line: str):
    """
    Detect pytest test failures.
    """
    m = re.search(r"(tests/[A-Za-z0-9_./-]+\.py)", line)
    if m:
        return m.group(1)
    return ""


def classify_issue(line: str):
    line_low = line.lower()

    if "ruff" in line_low or "lint" in line_low:
        return "lint_failure"

    if "failed" in line_low and "tests/" in line_low:
        return "test_failure"

    if "error" in line_low and ".py" in line_low:
        return "runtime_failure"

    if "exit code" in line_low:
        return "ci_failure"

    return "unknown"


def parse_log(log_path: Path):
    lines = read_text(log_path).splitlines()

    issues = []

    for line in lines:

        target = detect_python_file_error(line)
        test_target = detect_pytest_failure(line)

        if target or test_target:

            target_file = target or test_target

            issue = {
                "source": "ci_pipeline",
                "job": log_path.stem,
                "log_file": str(log_path),
                "error_type": "python_file_error",
                "issue_type": classify_issue(line),
                "signal": line.strip(),
                "target_file": target_file,
            }

            issues.append(issue)

    return issues


def main():

    failures = []

    if LOG_DIR.exists():

        for log_file in LOG_DIR.glob("*.log"):

            failures.extend(parse_log(log_file))

    result = {
        "ci_failures": failures
    }

    write_json(AUDIT_OUT / "ci_failures.json", result)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()