#!/usr/bin/env python3

import json
import re
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"
AUDIT_RAW = ROOT / "audit_raw"

MAX_SIGNALS_PER_FILE = 80
MAX_TOTAL_FAILURES = 200


ERROR_PATTERNS = [
    ("ImportError", re.compile(r"ImportError:.*", re.I)),
    ("ModuleNotFoundError", re.compile(r"ModuleNotFoundError:.*", re.I)),
    ("AttributeError", re.compile(r"AttributeError:.*", re.I)),
    ("TypeError", re.compile(r"TypeError:.*", re.I)),
    ("NameError", re.compile(r"NameError:.*", re.I)),
    ("KeyError", re.compile(r"KeyError:.*", re.I)),
    ("AssertionError", re.compile(r"AssertionError:.*", re.I)),
    ("RuntimeError", re.compile(r"RuntimeError:.*", re.I)),
    ("SyntaxError", re.compile(r"SyntaxError:.*", re.I)),
    ("ruff", re.compile(r"\b[FWE]\d{3,4}\b.*", re.I)),
    ("lint", re.compile(r"\b(ruff|flake8|pylint|lint)\b.*", re.I)),
    ("pytest_failed", re.compile(r"FAILED\s+.+", re.I)),
    ("pytest_error", re.compile(r"ERROR\s+.+", re.I)),
    ("cannot_import", re.compile(r"cannot import name ['\"]?([A-Za-z0-9_]+)['\"]?", re.I)),
    ("process_exit", re.compile(r"Process completed with exit code \d+", re.I)),
]


WORKFLOW_HINTS = {
    "lint": ("ci_lint", "Lint & Static Checks"),
    "ruff": ("ci_lint", "Lint & Static Checks"),
    "import smoke": ("ci_import_smoke", "Import Smoke"),
    "full test suite": ("ci_full_test_suite", "Full Test Suite"),
    "full test & coverage gate": ("ci_full_coverage_gate", "Full Test & Coverage Gate"),
    "pickfair test suite": ("ci_pickfair_test_suite", "Pickfair Test Suite"),
    "hft stress tests": ("ci_hft_stress", "HFT Stress Tests"),
    "guardrails": ("ci_guardrails", "AI Guardrails"),
    "tests.yml": ("ci_tests_yml", "tests.yml"),
    "run_tests.yml": ("ci_run_tests_yml", "run_tests.yml"),
}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def list_candidate_logs() -> list[Path]:
    if not AUDIT_RAW.exists():
        return []

    candidates = []
    for p in AUDIT_RAW.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".log", ".txt", ".md", ".json"}:
            continue
        candidates.append(p)

    return sorted(candidates)


def normalize_line(line: str) -> str:
    return " ".join((line or "").strip().split())


def detect_source_info(path: Path, text: str) -> tuple[str, str]:
    path_str = str(path.relative_to(ROOT)).lower() if path.is_absolute() else str(path).lower()
    blob = f"{path_str}\n{text[:4000].lower()}"

    for hint, value in WORKFLOW_HINTS.items():
        if hint in blob:
            return value

    return ("ci_unknown", path.name)


def probable_target_file(line: str) -> str:
    line = line or ""

    file_match = re.search(r"([A-Za-z0-9_./-]+\.py):\d+", line)
    if file_match:
        return file_match.group(1)

    quoted_file = re.search(r"([A-Za-z0-9_./-]+\.py)", line)
    if quoted_file:
        return quoted_file.group(1)

    cannot_import = re.search(r"cannot import name ['\"]?([A-Za-z0-9_]+)['\"]?", line, re.I)
    if cannot_import:
        symbol = cannot_import.group(1)
        if symbol == "ExecutorManager":
            return "executor_manager.py"
        if symbol == "AutoUpdater":
            return "auto_updater.py"
        if symbol == "SYSTEM_PAYLOAD":
            return "tests/fixtures/system_payloads.py"

    if "import smoke" in line.lower():
        return "unknown_import_target"

    return ""


def classify_line(line: str) -> tuple[str, str]:
    for name, pattern in ERROR_PATTERNS:
        if pattern.search(line):
            return name, normalize_line(line)
    return "", ""


def extract_failures_from_text(path: Path, text: str) -> list[dict]:
    workflow_source, job_name = detect_source_info(path, text)
    failures = []
    seen = set()

    lines = text.splitlines()

    for raw in lines:
        line = normalize_line(raw)
        if not line:
            continue

        error_type, signal = classify_line(line)
        if not error_type:
            continue

        target_file = probable_target_file(line)
        dedupe_key = (workflow_source, job_name, error_type, signal, target_file)

        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        failures.append(
            {
                "source": workflow_source,
                "job": job_name,
                "log_file": str(path.relative_to(ROOT)).replace("\\", "/"),
                "error_type": error_type,
                "signal": signal,
                "target_file": target_file,
            }
        )

        if len(failures) >= MAX_SIGNALS_PER_FILE:
            break

    return failures


def add_summary_stats(failures: list[dict]) -> dict:
    by_source = {}
    by_type = {}

    for item in failures:
        src = str(item.get("source", "")).strip() or "unknown"
        typ = str(item.get("error_type", "")).strip() or "unknown"

        by_source[src] = by_source.get(src, 0) + 1
        by_type[typ] = by_type.get(typ, 0) + 1

    return {
        "total_failures": len(failures),
        "by_source": by_source,
        "by_type": by_type,
    }


def main() -> int:
    log_files = list_candidate_logs()
    all_failures = []

    for path in log_files:
        text = read_text(path)
        if not text.strip():
            continue

        extracted = extract_failures_from_text(path, text)
        all_failures.extend(extracted)

        if len(all_failures) >= MAX_TOTAL_FAILURES:
            all_failures = all_failures[:MAX_TOTAL_FAILURES]
            break

    result = {
        "ci_failures": all_failures,
        "summary": add_summary_stats(all_failures),
    }

    write_json(AUDIT_OUT / "ci_failure_context.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())