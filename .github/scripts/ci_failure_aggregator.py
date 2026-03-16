#!/usr/bin/env python3

import json
import re
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_RAW = ROOT / "audit_raw"
AUDIT_OUT = ROOT / "audit_out"
LOG_DIR = AUDIT_RAW / "external_ci_logs"
MAX_FAILURES = 300

PYTHON_FILE_RE = re.compile(r"([A-Za-z0-9_./-]+\.py):(\d+)(?::(\d+))?")
TEST_FILE_RE = re.compile(r"(tests/[A-Za-z0-9_./-]+\.py)")
TRACEBACK_FILE_RE = re.compile(r'File "([^"]+\.py)", line (\d+)')
CANNOT_IMPORT_RE = re.compile(r"cannot import name ['\"]?([A-Za-z0-9_]+)['\"]?", re.I)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize_path(path_str: str) -> str:
    raw = str(path_str or "").strip().replace("\\", "/")
    if not raw:
        return ""
    return raw.lstrip("./")


def relative_log_path(path: Path) -> str:
    try:
        return normalize_path(str(path.relative_to(ROOT)))
    except Exception:
        return normalize_path(str(path))


def should_ignore_line(line: str) -> bool:
    low = line.lower().strip()
    if not low:
        return True

    ok_prefixes = (
        "[ok]",
        "ok ",
        "ok:",
        "passed ",
        "collected ",
        "platform ",
        "rootdir:",
        "plugins:",
        "cache hit",
        "cache restored",
        "restored cache",
        "using python",
        "set up job",
        "post setup",
        "post checkout",
        "cleanup",
        "checkout repository",
        "setup python",
        "install dependencies",
        "create folders",
        "verify required scripts",
    )
    if low.startswith(ok_prefixes):
        return True

    success_markers = (
        "successfully installed",
        "requirement already satisfied",
        "all required scripts found",
        "workflow mode:",
        "collecting",
        "downloading",
        "installing collected packages",
        "preparing metadata",
        "building wheel",
        "built wheel",
        "uploaded bytes",
        "artifact name is valid",
        "root directory input is valid",
        "finalizing artifact upload",
        "has been successfully uploaded",
    )
    if any(marker in low for marker in success_markers):
        return True

    noisy_markers = (
        "::debug::",
        "temporarily overriding home=",
        "adding repository directory to the temporary git global config as a safe directory",
        "/usr/bin/git config",
        "/usr/bin/git version",
        "copying '/home/runner/.gitconfig'",
        "pythonlocation:",
        "python_root_dir:",
        "ld_library_path:",
        "pkg_config_path:",
    )
    if any(marker in low for marker in noisy_markers):
        return True

    return False


def detect_target_file(line: str) -> str:
    m = PYTHON_FILE_RE.search(line)
    if m:
        return normalize_path(m.group(1))

    m = TRACEBACK_FILE_RE.search(line)
    if m:
        return normalize_path(m.group(1))

    m = TEST_FILE_RE.search(line)
    if m:
        return normalize_path(m.group(1))

    m = CANNOT_IMPORT_RE.search(line)
    if m:
        symbol = m.group(1)
        symbol_map = {
            "ExecutorManager": "executor_manager.py",
            "AutoUpdater": "auto_updater.py",
            "SYSTEM_PAYLOAD": "tests/fixtures/system_payloads.py",
        }
        if symbol in symbol_map:
            return symbol_map[symbol]

    return ""


def detect_error_type_and_issue_type(line: str, target_file: str) -> tuple[str, str]:
    low = line.lower()
    target_low = target_file.lower()

    if "ruff" in low or "f401" in low or "f841" in low or "e9" in low or "undefined name" in low:
        return "python_file_error", "lint_failure"

    if "failed [" in low or (" failed" in low and "tests/" in low):
        return "pytest_failed", "test_failure"

    if low.startswith("failed ") and "tests/" in low:
        return "pytest_failed", "test_failure"

    if "assertionerror" in low and target_low.startswith("tests/"):
        return "pytest_failed", "test_failure"

    runtime_markers = (
        "traceback",
        "typeerror",
        "attributeerror",
        "nameerror",
        "keyerror",
        "runtimeerror",
        "importerror",
        "modulenotfounderror",
        "syntaxerror",
        "cannot import name",
    )
    if any(marker in low for marker in runtime_markers):
        if target_low.endswith(".py") and not target_low.startswith("tests/"):
            return "traceback_file", "runtime_failure"
        if target_low.startswith("tests/"):
            return "pytest_failed", "test_failure"
        return "traceback_file", "ci_failure"

    if target_low.endswith(".py") and not target_low.startswith("tests/"):
        if "error" in low or "exception" in low:
            return "python_file_error", "runtime_failure"

    if "process completed with exit code" in low or "exit code 1" in low or "exit code 2" in low:
        return "process_exit", "ci_failure"

    if "gh013" in low or "repository rule violations" in low or "failed to push" in low:
        return "git_error", "ci_failure"

    if target_low.startswith("tests/"):
        return "pytest_failed", "test_failure"

    return "ci_signal", "ci_failure"


def parse_log(log_path: Path) -> list[dict]:
    lines = read_text(log_path).splitlines()
    issues = []
    seen = set()

    for raw in lines:
        line = raw.strip()
        if should_ignore_line(line):
            continue

        target_file = detect_target_file(line)

        low = line.lower()
        has_failure_signal = any(
            marker in low
            for marker in (
                "failed",
                "error",
                "traceback",
                "exception",
                "cannot import name",
                "process completed with exit code",
                "gh013",
                "repository rule violations",
                "failed to push",
                "ruff",
                "f401",
                "f841",
                "syntaxerror",
                "importerror",
                "modulenotfounderror",
            )
        )

        if not target_file and not has_failure_signal:
            continue

        error_type, issue_type = detect_error_type_and_issue_type(line, target_file)

        if issue_type == "ci_failure" and not target_file:
            # keep only truly meaningful generic CI failures
            if not any(
                marker in low
                for marker in (
                    "process completed with exit code",
                    "gh013",
                    "repository rule violations",
                    "failed to push",
                    "traceback",
                    "exception",
                )
            ):
                continue

        key = (log_path.name, error_type, issue_type, target_file, line)
        if key in seen:
            continue
        seen.add(key)

        issues.append(
            {
                "source": "ci_pipeline",
                "job": log_path.stem,
                "log_file": relative_log_path(log_path),
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
        "by_type": dict(sorted(by_type.items())),
        "by_issue_type": dict(sorted(by_issue_type.items())),
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