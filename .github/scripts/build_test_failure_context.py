#!/usr/bin/env python3

import json
import re
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"
AUDIT_RAW = ROOT / "audit_raw"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def extract_pytest_signals(pytest_log: str) -> list[str]:
    patterns = (
        "ImportError",
        "ModuleNotFoundError",
        "AttributeError",
        "TypeError",
        "RuntimeError",
        "AssertionError",
        "KeyError",
        "NameError",
        "cannot import name",
        "FAILED ",
        "ERROR ",
    )

    signals = []
    for raw in pytest_log.splitlines():
        line = raw.strip()
        if not line:
            continue
        if any(p in line for p in patterns):
            signals.append(line)

    return signals[:120]


def extract_test_files(signals: list[str]) -> list[str]:
    found = set()

    for line in signals:
        for token in line.split():
            token = token.strip("()[],: ")
            if token.startswith("tests/") and token.endswith(".py"):
                found.add(token)

    return sorted(found)


def guess_related_source_file(test_file: str) -> str:
    path = Path(test_file)
    name = path.name

    if name.startswith("test_"):
        stem = name[len("test_") : -3]

        candidates = [
            ROOT / f"{stem}.py",
            ROOT / "tests" / "fixtures" / f"{stem}.py",
            ROOT / "controllers" / f"{stem}.py",
            ROOT / "core" / f"{stem}.py",
            ROOT / "ai" / f"{stem}.py",
            ROOT / "ui" / f"{stem}.py",
            ROOT / "app_modules" / f"{stem}.py",
        ]

        for candidate in candidates:
            if candidate.exists():
                return str(candidate.relative_to(ROOT)).replace("\\", "/")

    return ""


def analyze_test_file(test_file: str) -> dict:
    path = ROOT / test_file
    text = read_text(path)

    stripped = text.strip()
    is_empty = stripped == ""
    has_test_defs = bool(re.search(r"^\s*def\s+test_[A-Za-z0-9_]+\s*\(", text, re.M))
    has_pytest_marks = bool(re.search(r"@\s*pytest\.", text))
    has_any_python = bool(stripped)

    issue_type = None
    notes = []

    if is_empty:
        issue_type = "empty_test_file"
        notes.append("Il file test è vuoto.")
        notes.append("Riparare creando il test minimo valido e coerente con il failure corrente.")
    elif has_any_python and not has_test_defs and not has_pytest_marks:
        issue_type = "corrupted_or_non_test_content"
        notes.append("Il file test non contiene test validi pytest.")
        notes.append("Possibile file corrotto, placeholder sporco o contenuto non Python utile.")
        notes.append("Riparare il file test prima di allargare il fix ai moduli di produzione.")
    else:
        issue_type = "normal_test_file"
        notes.append("File test coinvolto nel failure corrente.")

    related_source = guess_related_source_file(test_file)

    related_tests = [test_file]
    if "parallel" in test_file and (ROOT / "tests/test_executor_manager_shutdown.py").exists():
        related_tests.append("tests/test_executor_manager_shutdown.py")
    if "shutdown" in test_file and (ROOT / "tests/test_executor_manager_parallel.py").exists():
        related_tests.append("tests/test_executor_manager_parallel.py")

    context = {
        "target_file": test_file,
        "required_symbols": [],
        "related_tests": sorted(set(related_tests)),
        "related_fixtures": [],
        "related_contracts": [],
        "notes": notes,
        "priority": "P0",
        "issue_type": issue_type,
        "related_source_file": related_source,
    }

    if related_source:
        context["notes"].append(f"Modulo sorgente probabilmente collegato: {related_source}")

    return context


def main() -> int:
    pytest_log = read_text(AUDIT_RAW / "pytest.log")
    signals = extract_pytest_signals(pytest_log)
    test_files = extract_test_files(signals)

    contexts = [analyze_test_file(test_file) for test_file in test_files]

    payload = {
        "pytest_signals": signals,
        "test_failure_contexts": contexts,
    }

    write_json(AUDIT_OUT / "test_failure_context.json", payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())