#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"
AUDIT_RAW = ROOT / "audit_raw"

MAX_CONTEXTS = 8
MAX_RELATED_TESTS = 3
MAX_RELATED_FIXTURES = 2
MAX_RELATED_CONTRACTS = 2
MAX_NOTES = 5


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


def unique_keep_order(items) -> list[str]:
    out = []
    seen = set()

    for item in items or []:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)

    return out


def trim_list(items, limit: int) -> list[str]:
    return unique_keep_order(items)[:limit]


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


def contract_defaults_for_file(target_file: str) -> tuple[list[str], list[str], list[str]]:
    related_tests = []
    related_fixtures = []
    related_contracts = []

    if target_file == "auto_updater.py":
        related_tests = [
            "tests/test_auto_updater.py",
        ]
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
        related_fixtures = [
            "tests/fixtures/system_payloads.py",
        ]
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
        related_fixtures = [
            "tests/fixtures/market_ticks.py",
        ]

    return (
        trim_list(related_tests, MAX_RELATED_TESTS),
        trim_list(related_fixtures, MAX_RELATED_FIXTURES),
        trim_list(related_contracts, MAX_RELATED_CONTRACTS),
    )


def build_contract_contexts(contracts: list) -> list[dict]:
    contexts = []

    for item in contracts:
        try:
            target_file = str(item[0]).strip()
            symbol = str(item[1]).strip()
        except Exception:
            continue

        if not target_file:
            continue

        related_tests, related_fixtures, related_contracts = contract_defaults_for_file(target_file)

        notes = [
            "Simbolo pubblico richiesto dai test.",
            "Ripristinare simbolo mancante con il fix più piccolo possibile.",
            "Non cambiare la logica interna oltre la retrocompatibilità necessaria.",
            "Preferire alias/wrapper/shim compatibili ai redesign.",
        ]

        contexts.append(
            {
                "target_file": target_file,
                "required_symbols": [symbol] if symbol else [],
                "related_tests": related_tests,
                "related_fixtures": related_fixtures,
                "related_contracts": related_contracts,
                "notes": trim_list(notes, MAX_NOTES),
                "priority": "P0",
                "issue_type": "missing_public_contract",
                "related_source_file": "",
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
                "related_tests": trim_list(
                    [
                        "tests/contracts/test_payload_snapshots.py",
                        "tests/guardrails/test_contract_snapshot.py",
                        "tests/guardrails/test_public_api_matches_snapshot.py",
                    ],
                    MAX_RELATED_TESTS,
                ),
                "related_fixtures": trim_list(
                    ["tests/fixtures/system_payloads.py"],
                    MAX_RELATED_FIXTURES,
                ),
                "related_contracts": trim_list(
                    [
                        "tests/contracts/test_payload_snapshots.py",
                        "tests/guardrails/test_contract_snapshot.py",
                    ],
                    MAX_RELATED_CONTRACTS,
                ),
                "notes": trim_list(
                    [
                        "Contract test direttamente coinvolto.",
                        "Il comportamento atteso è definito dal payload snapshot.",
                        "Se il problema è nel fixture contract, riparare prima il fixture o l'export mancante.",
                    ],
                    MAX_NOTES,
                ),
                "priority": "P0",
                "issue_type": "contract_test_failure",
                "related_source_file": "tests/fixtures/system_payloads.py",
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
                value = str(value).strip()
                if not value or value in existing:
                    continue
                dst[key].append(value)
                existing.add(value)

        if item.get("priority") == "P0":
            dst["priority"] = "P0"

        if not dst.get("related_source_file") and item.get("related_source_file"):
            dst["related_source_file"] = str(item.get("related_source_file", "")).strip()

    result = []
    for value in merged.values():
        value["required_symbols"] = trim_list(value.get("required_symbols", []), 4)
        value["related_tests"] = trim_list(value.get("related_tests", []), MAX_RELATED_TESTS)
        value["related_fixtures"] = trim_list(value.get("related_fixtures", []), MAX_RELATED_FIXTURES)
        value["related_contracts"] = trim_list(value.get("related_contracts", []), MAX_RELATED_CONTRACTS)
        value["notes"] = trim_list(value.get("notes", []), MAX_NOTES)
        result.append(value)

    return result


def score_context(item: dict, pytest_signals: list[str], ai_reasoning: dict) -> int:
    score = 0

    target_file = str(item.get("target_file", "")).strip()
    required_symbols = item.get("required_symbols", []) or []
    issue_type = str(item.get("issue_type", "")).strip()
    related_source_file = str(item.get("related_source_file", "")).strip()

    if item.get("priority") == "P0":
        score += 100

    if issue_type == "empty_test_file":
        score += 180
    elif issue_type == "corrupted_or_non_test_content":
        score += 170
    elif issue_type == "missing_public_contract":
        score += 150
    elif issue_type == "contract_test_failure":
        score += 130
    elif issue_type == "normal_test_file":
        score += 90

    for line in pytest_signals:
        if target_file and target_file in line:
            score += 50
        if related_source_file and related_source_file in line:
            score += 40

        for symbol in required_symbols:
            if symbol and symbol in line:
                score += 90

    for root in ai_reasoning.get("root_causes", []) or []:
        title = str(root.get("title", ""))
        why = str(root.get("why_it_happens", ""))

        if target_file and (target_file in title or target_file in why):
            score += 60

        if related_source_file and (related_source_file in title or related_source_file in why):
            score += 50

        for symbol in required_symbols:
            if symbol and (symbol in title or symbol in why):
                score += 95

    if target_file.startswith("tests/"):
        score += 10
    else:
        score += 25

    score += min(len(item.get("related_tests", [])), MAX_RELATED_TESTS) * 4
    score += min(len(item.get("related_contracts", [])), MAX_RELATED_CONTRACTS) * 5
    score += min(len(item.get("notes", [])), MAX_NOTES) * 2

    return score


def collapse_test_only_contexts(contexts: list[dict]) -> list[dict]:
    contract_targets = {
        "auto_updater.py",
        "executor_manager.py",
        "tests/fixtures/system_payloads.py",
    }

    final = []
    seen = set()

    for item in contexts:
        target_file = str(item.get("target_file", "")).strip()
        if not target_file or target_file in seen:
            continue

        related_source = str(item.get("related_source_file", "")).strip()
        issue_type = str(item.get("issue_type", "")).strip()

        if target_file.startswith("tests/") and related_source in contract_targets:
            continue

        if (
            target_file.startswith("tests/")
            and issue_type == "normal_test_file"
            and related_source
            and related_source in seen
        ):
            continue

        seen.add(target_file)
        final.append(item)

    return final


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
    contexts = collapse_test_only_contexts(contexts)
    contexts = contexts[:MAX_CONTEXTS]

    for item in contexts:
        item.pop("_score", None)

    result = {"fix_contexts": contexts}

    write_json(AUDIT_OUT / "fix_context.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())