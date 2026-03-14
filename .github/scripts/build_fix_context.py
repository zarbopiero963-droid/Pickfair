#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"


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


def normalize_contracts(raw_contracts):
    normalized = []

    for item in raw_contracts or []:
        if isinstance(item, dict):
            normalized.append(
                {
                    "file": item.get("file", "sconosciuto"),
                    "symbol": item.get("symbol", item.get("title", "sconosciuto")),
                }
            )
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            normalized.append(
                {
                    "file": str(item[0]),
                    "symbol": str(item[1]),
                }
            )
        elif isinstance(item, str):
            normalized.append(
                {
                    "file": item,
                    "symbol": "unknown_symbol",
                }
            )

    return normalized


def infer_related_tests(target_file: str, symbol: str):
    tests = []

    if symbol == "AutoUpdater":
        tests.extend([
            "tests/test_auto_updater.py",
        ])

    if symbol == "ExecutorManager":
        tests.extend([
            "tests/test_executor_manager.py",
            "tests/test_executor_manager_shutdown.py",
            "tests/test_executor_manager_parallel.py",
        ])

    if symbol in ("OneClickLadder", "LiveMiniLadder"):
        tests.extend([
            "tests/test_new_components.py",
            "tests/test_toolbar_live.py",
            "tests/test_ui_components.py",
        ])

    if symbol == "SYSTEM_PAYLOAD":
        tests.extend([
            "tests/contracts/test_payload_snapshots.py",
            "tests/guardrails/test_contract_snapshot.py",
            "tests/guardrails/test_public_api_matches_snapshot.py",
        ])

    return sorted(set(tests))


def infer_related_fixtures(symbol: str):
    fixtures = []

    if symbol == "SYSTEM_PAYLOAD":
        fixtures.append("tests/fixtures/system_payloads.py")

    if symbol in ("OneClickLadder", "LiveMiniLadder"):
        fixtures.append("tests/fixtures/market_ticks.py")

    return sorted(set(fixtures))


def infer_related_contracts(symbol: str):
    related = []

    if symbol == "SYSTEM_PAYLOAD":
        related.extend([
            "tests/contracts/test_payload_snapshots.py",
            "tests/guardrails/test_contract_snapshot.py",
        ])

    if symbol in ("AutoUpdater", "ExecutorManager"):
        related.extend([
            "tests/test_backward_compatibility.py",
            "tests/test_public_contracts_repository.py",
        ])

    return sorted(set(related))


def build_fix_context(audit_machine: dict):
    contracts = normalize_contracts(audit_machine.get("contracts", []))
    contexts = []

    for item in contracts:
        file = item["file"]
        symbol = item["symbol"]

        contexts.append({
            "target_file": file,
            "required_symbols": [symbol],
            "related_tests": infer_related_tests(file, symbol),
            "related_fixtures": infer_related_fixtures(symbol),
            "related_contracts": infer_related_contracts(symbol),
            "notes": [
                "Leggere i test prima di proporre il fix.",
                "Proporre il fix minimo possibile.",
                "Preservare retrocompatibilità e API pubbliche.",
                "Non introdurre feature extra.",
            ],
        })

    return {
        "fix_contexts": contexts
    }


def main():
    audit_machine = read_json(AUDIT_OUT / "audit_machine.json")
    result = build_fix_context(audit_machine)
    write_json(AUDIT_OUT / "fix_context.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())