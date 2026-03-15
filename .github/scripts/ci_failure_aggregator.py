#!/usr/bin/env python3

import json
import re
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"
AUDIT_RAW = ROOT / "audit_raw"

MAX_SIGNALS_PER_FILE = 80
MAX_TOTAL_FAILURES = 200

SETUP_NOISE_PATTERNS = [
    re.compile(r"\bcollecting\b", re.I),
    re.compile(r"\bdownloading\b", re.I),
    re.compile(r"\binstalling collected packages\b", re.I),
    re.compile(r"\bsuccessfully installed\b", re.I),
    re.compile(r"\brun actions/checkout@", re.I),
    re.compile(r"\bsafe\.directory\b", re.I),
    re.compile(r"\binitializing the repository\b", re.I),
    re.compile(r"\bdeleting the contents of\b", re.I),
    re.compile(r"\btemporarily overriding HOME=", re.I),
    re.compile(r"\badding repository directory\b", re.I),
    re.compile(r"\bsetup python\b", re.I),
    re.compile(r"\binstall dependencies\b", re.I),
    re.compile(r"\bpip install\b", re.I),
    re.compile(r"\brequirement already satisfied\b", re.I),
    re.compile(r"\buses: actions/", re.I),
]

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
    ("cannot_import", re.compile(r"cannot import name ['\"]?([A-Za-z0-9_]+)['\"]?", re.I)),
    ("pytest_failed", re.compile(r"FAILED\s+.+", re.I)),
    ("pytest_error", re.compile(r"ERROR\s+.+", re.I)),
    ("traceback_file", re.compile(r'File "([^"]+\.py)", line \d+', re.I)),
    ("python_file_error", re.compile(r"([A-Za-z0-9_./-]+\.py):\d+(?::\d+)?.*", re.I)),
    ("ruff_code", re.compile(r"\b([A-Z]\d{3,4})\b.*", re.I)),
    ("git_error", re.compile(r"\berror:\s+.+", re.I)),
    ("process_exit", re.compile(r"Process completed with exit code \d+", re.I)),
]

WORKFLOW_HINTS = {
    "lint & static checks": ("ci_lint", "Lint & Static Checks"),
    "import smoke": ("ci_import_smoke", "Import Smoke"),
    "full test suite": ("ci_full_test_suite", "Full Test Suite"),
    "full test & coverage gate": ("ci_full_coverage_gate", "Full Test & Coverage Gate"),
    "pickfair test suite": ("ci_pickfair_test_suite", "Pickfair Test Suite"),
    "hft stress tests": ("ci_hft_stress", "HFT Stress Tests"),
    "ai guardrails": ("ci_guardrails", "AI Guardrails"),
    "guardrails": ("ci_guardrails", "AI Guardrails"),
    "tests.yml": ("ci_tests_yml", "tests.yml"),
    "run_tests.yml": ("ci_run_tests_yml", "run_tests.yml"),
    "pickfair ultra ci pipeline": ("ci_pickfair_ultra", "Pickfair Ultra CI Pipeline"),
    "pickfair ci pipeline": ("ci_pickfair_ci", "Pickfair CI Pipeline"),
}

SYMBOL_TO_FILE = {
    "ExecutorManager": "executor_manager.py",
    "AutoUpdater": "auto_updater.py",
    "SYSTEM_PAYLOAD": "tests/fixtures/system_payloads.py",
}

RUFF_CODE_TO_TYPE = {
    "F401": "lint_failure",
    "F402": "lint_failure",
    "F403": "lint_failure",
    "F404": "lint_failure",
    "F405": "lint_failure",
    "F821": "runtime_failure",
    "F822": "runtime_failure",
    "F823": "runtime_failure",
    "F841": "lint_failure",
    "E402": "lint_failure",
    "E722": "lint_failure",
    "E999": "runtime_failure",
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


def is_noise_line(line: str) -> bool:
    if not line:
        return True

    lowered = line.lower()

    if lowered in {"error", "failed", "warning"}:
        return True

    for pattern in SETUP_NOISE_PATTERNS:
        if pattern.search(line):
            return True

    return False


def detect_source_info(path: Path, text: str) -> tuple[str, str]:
    path_str = str(path.relative_to(ROOT)).lower() if path.is_absolute() else str(path).lower()
    blob = f"{path_str}\n{text[:8000].lower()}"

    for hint, value in WORKFLOW_HINTS.items():
        if hint in blob:
            return value

    file_name = path.name.lower()
    for hint, value in WORKFLOW_HINTS.items():
        if hint.replace(" ", "_") in file_name:
            return value

    return ("ci_unknown", path.name)


def probable_target_file(line: str) -> str:
    line = line or ""

    file_match = re.search(r"([A-Za-z0-9_./-]+\.py):\d+(?::\d+)?", line)
    if file_match:
        return file_match.group(1)

    traceback_match = re.search(r'File "([^"]+\.py)", line \d+', line)
    if traceback_match:
        return traceback_match.group(1)

    quoted_file = re.search(r"\b([A-Za-z0-9_./-]+\.py)\b", line)
    if quoted_file:
        return quoted_file.group(1)

    cannot_import = re.search(r"cannot import name ['\"]?([A-Za-z0-9_]+)['\"]?", line, re.I)
    if cannot_import:
        symbol = cannot_import.group(1)
        return SYMBOL_TO_FILE.get(symbol, "")

    return ""


def classify_line(line: str) -> tuple[str, str]:
    if is_noise_line(line):
        return "", ""

    for name, pattern in ERROR_PATTERNS:
        if pattern.search(line):
            return name, normalize_line(line)

    return "", ""


def infer_issue_type(error_type: str, signal: str) -> str:
    if error_type in {"ImportError", "ModuleNotFoundError", "cannot_import"}:
        return "missing_public_contract"

    if error_type in {"AssertionError", "pytest_failed", "pytest_error"}:
        return "test_failure"

    if error_type in {"TypeError", "AttributeError", "NameError", "KeyError", "RuntimeError", "SyntaxError"}:
        return "runtime_failure"

    if error_type == "ruff_code":
        code_match = re.search(r"\b([A-Z]\d{3,4})\b", signal)
        if code_match:
            code = code_match.group(1).upper()
            return RUFF_CODE_TO_TYPE.get(code, "lint_failure")
        return "lint_failure"

    if error_type == "python_file_error":
        code_match = re.search(r"\b([A-Z]\d{3,4})\b", signal)
        if code_match:
            code = code_match.group(1).upper()
            return RUFF_CODE_TO_TYPE.get(code, "lint_failure")
        return "runtime_failure"

    if error_type == "git_error":
        lowered = signal.lower()
        if "failed to push some refs" in lowered:
            return "infra_failure"
        return "ci_failure"

    if error_type == "process_exit":
        return "ci_failure"

    return "ci_failure"


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

        target_file = probable_target_file(signal)
        issue_type = infer_issue_type(error_type, signal)

        if issue_type in {"lint_failure", "runtime_failure", "test_failure", "missing_public_contract"} and not target_file:
            continue

        dedupe_key = (workflow_source, job_name, error_type, signal, target_file, issue_type)

        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        failures.append(
            {
                "source": workflow_source,
                "job": job_name,
                "log_file": str(path.relative_to(ROOT)).replace("\\", "/"),
                "error_type": error_type,
                "issue_type": issue_type,
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
    by_issue_type = {}

    for item in failures:
        src = str(item.get("source", "")).strip() or "unknown"
        typ = str(item.get("error_type", "")).strip() or "unknown"
        issue = str(item.get("issue_type", "")).strip() or "unknown"

        by_source[src] = by_source.get(src, 0) + 1
        by_type[typ] = by_type.get(typ, 0) + 1
        by_issue_type[issue] = by_issue_type.get(issue, 0) + 1

    return {
        "total_failures": len(failures),
        "by_source": by_source,
        "by_type": by_type,
        "by_issue_type": by_issue_type,
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