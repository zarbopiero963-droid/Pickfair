#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"
AUDIT_RAW = ROOT / "audit_raw"


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


def load_audit_machine() -> dict:
    return read_json(AUDIT_OUT / "audit_machine.json")


def load_ai_reasoning() -> dict:
    return read_json(AUDIT_OUT / "ai_reasoning.json")


def load_test_failure_context() -> dict:
    return read_json(AUDIT_OUT / "test_failure_context.json")


def load_pytest_log() -> str:
    return read_text(AUDIT_RAW / "pytest.log")


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
        "FAILED ",
        "ERROR ",
        "cannot import name",
    )

    signals = []
    for raw in pytest_log.splitlines():
        line = raw.strip()
        if not line:
            continue
        if any(p in line for p in patterns):
            signals.append(line)

    return signals[:80]


def build_contract_contexts(contracts: list) -> list[dict]:
    contexts = []

    for item in contracts:
        try:
            target_file = str(item[0]).strip()
            symbol = str(item[1]).strip()
        except Exception:
            continue

        related_tests = []
        related_fixtures = []
        related_contracts = []

        if target_file == "auto_updater.py":
            related_tests = ["tests/test_auto_updater.py"]
            related_contracts = [
                "tests/test_backward_compatibility.py",
                "tests/test_public_contracts_repository.py",
            ]

        elif target_file == "executor_manager.py":
            related_tests = [
                "tests/test_executor_manager.py",
                "tests/test_executor_manager_parallel.py",
                "tests/test_executor_manager_shutdown.py",
            ]
            related_contracts = [
                "tests/test_backward_compatibility.py",
                "tests/test_public_contracts_repository.py",
            ]

        elif target_file == "tests/fixtures/system_payloads.py":
            related_tests = [
                "tests/contracts/test_payload_snapshots.py",
                "tests/guardrails/test_contract_snapshot.py",
                "tests/guardrails/test_public_api_matches_snapshot.py",
            ]
            related_fixtures = ["tests/fixtures/system_payloads.py"]
            related_contracts = [
                "tests/contracts/test_payload_snapshots.py",
                "tests/guardrails/test_contract_snapshot.py",
            ]

        elif target_file == "ui/mini_ladder.py":
            related_tests = [
                "tests/test_new_components.py",
                "tests/test_toolbar_live.py",
                "tests/test_ui_components.py",
            ]
            related_fixtures = ["tests/fixtures/market_ticks.py"]

        contexts.append(
            {
                "target_file": target_file,
                "required_symbols": [symbol] if symbol else [],
                "related_tests": related_tests,
                "related_fixtures": related_fixtures,
                "related_contracts": related_contracts,
                "notes": [
                    "Simbolo pubblico richiesto dai test.",
                    "Ripristinare simbolo mancante.",
                    "Non cambiare logica interna.",
                    "Mantenere retrocompatibilità.",
                ],
                "priority": "P0",
                "issue_type": "missing_public_contract",
            }
        )

    return contexts


def build_pytest_contexts(pytest_signals: list[str]) -> list[dict]:
    contexts = []

    joined = "\n".join(pytest_signals)

    if "tests/contracts/test_payload_snapshots.py" in joined:
        contexts.append(
            {
                "target_file": "tests/contracts/test_payload_snapshots.py",
                "required_symbols": [],
                "related_tests": [
                    "tests/contracts/test_payload_snapshots.py",
                    "tests/guardrails/test_contract_snapshot.py",
                    "tests/guardrails/test_public_api_matches_snapshot.py",
                ],
                "related_fixtures": ["tests/fixtures/system_payloads.py"],
                "related_contracts": [
                    "tests/contracts/test_payload_snapshots.py",
                    "tests/guardrails/test_contract_snapshot.py",
                ],
                "notes": [
                    "Contract test direttamente coinvolto.",
                    "Il comportamento atteso è definito dal payload snapshot.",
                ],
                "priority": "P0",
                "issue_type": "contract_test_failure",
            }
        )

    return contexts


def merge_contexts(contexts: list[dict]) -> list[dict]:
    merged = {}

    for item in contexts:
        target_file = str(item.get("target_file", "")).strip()
        if not target_file:
            continue

        if target_file not in merged:
            merged[target_file] = {
                "target_file": target_file,
                "required_symbols": [],
                "related_tests": [],
                "related_fixtures": [],
                "related_contracts": [],
                "notes": [],
                "priority": item.get("priority", "P1"),
                "issue_type": item.get("issue_type", "generic"),
                "related_source_file": item.get("related_source_file", ""),
            }

        dst = merged[target_file]

        for key in [
            "required_symbols",
            "related_tests",
            "related_fixtures",
            "related_contracts",
            "notes",
        ]:
            existing = set(dst.get(key, []))
            for value in item.get(key, []):
                if value not in existing:
                    dst[key].append(value)
                    existing.add(value)

        if item.get("priority") == "P0":
            dst["priority"] = "P0"

        if not dst.get("related_source_file") and item.get("related_source_file"):
            dst["related_source_file"] = item.get("related_source_file")

    return list(merged.values())


def score_context(item: dict, pytest_signals: list[str], ai_reasoning: dict) -> int:
    score = 0

    target_file = str(item.get("target_file", "")).strip()
    required_symbols = item.get("required_symbols", []) or []
    issue_type = str(item.get("issue_type", "")).strip()

    if item.get("priority") == "P0":
        score += 100

    if issue_type == "empty_test_file":
        score += 160

    if issue_type == "corrupted_or_non_test_content":
        score += 150

    if issue_type == "missing_public_contract":
        score += 120

    if issue_type == "contract_test_failure":
        score += 110

    for line in pytest_signals:
        if target_file and target_file in line:
            score += 50

        for symbol in required_symbols:
            if symbol and symbol in line:
                score += 80

    for root in ai_reasoning.get("root_causes", []) or []:
        title = str(root.get("title", ""))
        why = str(root.get("why_it_happens", ""))

        if target_file and (target_file in title or target_file in why):
            score += 60

        for symbol in required_symbols:
            if symbol and (symbol in title or symbol in why):
                score += 90

    score += min(len(item.get("related_tests", [])), 10) * 2
    score += min(len(item.get("related_contracts", [])), 10) * 3

    return score


def main() -> int:
    audit_machine = load_audit_machine()
    ai_reasoning = load_ai_reasoning()
    test_failure_context = load_test_failure_context()
    pytest_log = load_pytest_log()

    contracts = audit_machine.get("contracts", []) or []
    pytest_signals = extract_pytest_signals(pytest_log)

    contract_contexts = build_contract_contexts(contracts)
    pytest_contexts = build_pytest_contexts(pytest_signals)
    test_contexts = test_failure_context.get("test_failure_contexts", []) or []

    contexts = merge_contexts(contract_contexts + pytest_contexts + test_contexts)

    for item in contexts:
        item["_score"] = score_context(item, pytest_signals, ai_reasoning)

    contexts.sort(key=lambda x: x.get("_score", 0), reverse=True)

    for item in contexts:
        item.pop("_score", None)

    result = {"fix_contexts": contexts}

    write_json(AUDIT_OUT / "fix_context.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())