#!/usr/bin/env python3

import json
import re
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_RAW = ROOT / "audit_raw"
AUDIT_OUT = ROOT / "audit_out"
LOG_DIR = AUDIT_RAW / "external_ci_logs"
MAX_FAILURES = 300


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


def normalize_path(path_str: str) -> str:
    return str(path_str or "").strip().replace("\\", "/").lstrip("./")


def detect_python_file_error(line: str) -> str:
    m = re.search(r"([A-Za-z0-9_./-]+\.py):\d+", line)
    if m:
        return normalize_path(m.group(1))
    return ""


def detect_pytest_failure(line: str) -> str:
    m = re.search(r"(tests/[A-Za-z0-9_./-]+\.py)", line)
    if m:
        return normalize_path(m.group(1))
    return ""


def classify_issue(line: str, target_file: str) -> tuple[str, str]:
    line_low = line.lower()
    target_low = target_file.lower()

    if "ruff" in line_low or "lint" in line_low:
        return "python_file_error", "lint_failure"

    if ("failed" in line_low or "error" in line_low) and "tests/" in line_low:
        return "pytest_failed", "test_failure"

    if target_low.endswith(".py") and not target_low.startswith("tests/"):
        if "traceback" in line_low or "runtimeerror" in line_low or "typeerror" in line_low or "attributeerror" in line_low:
            return "traceback_file", "runtime_failure"
        if "error" in line_low and ".py" in line_low:
            return "python_file_error", "runtime_failure"

    if "exit code" in line_low or "process completed with exit code" in line_low:
        return "process_exit", "ci_failure"

    if "remote: error:" in line_low or "gh013" in line_low or "failed to push" in line_low:
        return "git_error", "ci_failure"

    return "python_file_error", "ci_failure"


def parse_log(log_path: Path) -> list[dict]:
    lines = read_text(log_path).splitlines()
    issues = []
    seen = set()

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        target = detect_python_file_error(line)
        test_target = detect_pytest_failure(line)
        target_file = target or test_target

        if not target_file and "exit code" not in line.lower() and "gh013" not in line.lower() and "failed to push" not in line.lower():
            continue

        error_type, issue_type = classify_issue(line, target_file)
        key = (log_path.name, error_type, issue_type, target_file, line)
        if key in seen:
            continue
        seen.add(key)

        issues.append(
            {
                "source": "ci_pipeline",
                "job": log_path.stem,
                "log_file": str(normalize_path(log_path.relative_to(ROOT))),
                "error_type": error_type,
                "issue_type": issue_type,
                "signal": line,
                "target_file": target_file,
            }
        )

        if len(issues) >= MAX_FAILURES:
            break

    return issues


def summarize(items: list[dict]) -> dict:
    by_type = {}
    by_issue_type = {}
    by_target = {}

    for item in items:
        error_type = str(item.get("error_type", "")).strip() or "unknown"
        issue_type = str(item.get("issue_type", "")).strip() or "unknown"
        target = str(item.get("target_file", "")).strip() or "unknown"

        by_type[error_type] = by_type.get(error_type, 0) + 1
        by_issue_type[issue_type] = by_issue_type.get(issue_type, 0) + 1
        by_target[target] = by_target.get(target, 0) + 1

    return {
        "total_failures": len(items),
        "by_type": by_type,
        "by_issue_type": by_issue_type,
        "top_targets": dict(sorted(by_target.items(), key=lambda x: (-x[1], x[0]))[:20]),
    }


def main() -> int:
    failures = []

    if LOG_DIR.exists():
        for log_file in sorted(LOG_DIR.glob("*.log")):
            failures.extend(parse_log(log_file))
            if len(failures) >= MAX_FAILURES:
                failures = failures[:MAX_FAILURES]
                break

    payload = {
        "ci_failures": failures,
        "summary": summarize(failures),
    }

    write_json(AUDIT_OUT / "ci_failures.json", payload)
    write_json(AUDIT_OUT / "ci_failure_context.json", payload)

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())