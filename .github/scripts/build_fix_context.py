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


def infer_related_tests(symbol: str):
    tests = []

    if symbol == "AutoUpdater":
        tests.append("tests/test_auto_updater.py")

    if symbol == "ExecutorManager":
        tests.extend([
            "tests/test_executor_manager.py",
            "tests/test_executor_manager_parallel.py",
            "tests/test_executor_manager_shutdown.py",
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

    return fixtures


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

    return related


def extract_collection_blockers(pytest_log: str):
    """
    Estrae file test che bloccano la collection.
    Deve catturare sia:
    - ERROR collecting tests/...
    - ERROR tests/... - NameError ...
    - traceback con tests/...:linea
    """

    blockers = {}

    lines = pytest_log.splitlines()

    patterns = [
        r"ERROR collecting (tests/[^\s]+\.py)",
        r"ERROR (tests/[^\s]+\.py)\s+-",
        r"(tests/[^\s]+\.py):\d+",
    ]

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        matched_file = None
        for pattern in patterns:
            m = re.search(pattern, line)
            if m:
                matched_file = m.group(1)
                break

        if not matched_file:
            continue

        entry = blockers.setdefault(
            matched_file,
            {
                "target_file": matched_file,
                "required_symbols": [],
                "related_tests": [matched_file],
                "related_fixtures": [],
                "related_contracts": [],
                "notes": [
                    "Pytest collection blocker rilevato.",
                    "Il file test non viene caricato correttamente.",
                    "Riparare prima il test o il suo contenuto spurio.",
                    "Fix minimo senza cambiare la logica del test oltre il necessario.",
                ],
                "priority": "P0",
            },
        )

        lowered = line.lower()
        if "nameerror" in lowered:
            if "NameError durante collection." not in entry["notes"]:
                entry["notes"].append("NameError durante collection.")
        if "importerror" in lowered:
            if "ImportError durante collection." not in entry["notes"]:
                entry["notes"].append("ImportError durante collection.")
        if "modulenotfounderror" in lowered:
            if "ModuleNotFoundError durante collection." not in entry["notes"]:
                entry["notes"].append("ModuleNotFoundError durante collection.")

    return list(blockers.values())


def dedupe_contexts(contexts: list[dict]) -> list[dict]:
    merged = {}

    for item in contexts:
        key = item.get("target_file", "unknown")

        if key not in merged:
            merged[key] = {
                "target_file": key,
                "required_symbols": list(item.get("required_symbols", [])),
                "related_tests": list(item.get("related_tests", [])),
                "related_fixtures": list(item.get("related_fixtures", [])),
                "related_contracts": list(item.get("related_contracts", [])),
                "notes": list(item.get("notes", [])),
                "priority": item.get("priority", "P1"),
            }
            continue

        existing = merged[key]
        existing["required_symbols"] = sorted(set(existing["required_symbols"] + list(item.get("required_symbols", []))))
        existing["related_tests"] = sorted(set(existing["related_tests"] + list(item.get("related_tests", []))))
        existing["related_fixtures"] = sorted(set(existing["related_fixtures"] + list(item.get("related_fixtures", []))))
        existing["related_contracts"] = sorted(set(existing["related_contracts"] + list(item.get("related_contracts", []))))
        existing["notes"] = list(dict.fromkeys(existing["notes"] + list(item.get("notes", []))))

        # P0 batte tutto
        if item.get("priority") == "P0":
            existing["priority"] = "P0"

    def sort_key(x: dict):
        priority = x.get("priority", "P9")
        target_file = x.get("target_file", "")
        return (priority, target_file)

    return sorted(merged.values(), key=sort_key)


def build_fix_context(audit_machine: dict, pytest_log: str):
    contexts = []

    contracts = normalize_contracts(audit_machine.get("contracts", []))

    for item in contracts:
        symbol = item["symbol"]
        file = item["file"]

        contexts.append(
            {
                "target_file": file,
                "required_symbols": [symbol],
                "related_tests": infer_related_tests(symbol),
                "related_fixtures": infer_related_fixtures(symbol),
                "related_contracts": infer_related_contracts(symbol),
                "notes": [
                    "Simbolo pubblico richiesto dai test.",
                    "Ripristinare simbolo mancante.",
                    "Non cambiare logica interna.",
                    "Mantenere retrocompatibilità.",
                ],
                "priority": "P0",
            }
        )

    contexts.extend(extract_collection_blockers(pytest_log))

    return {
        "fix_contexts": dedupe_contexts(contexts)
    }


def main():
    audit_machine = read_json(AUDIT_OUT / "audit_machine.json")

    pytest_log = ""
    raw_pytest = AUDIT_RAW / "pytest.log"
    out_pytest = AUDIT_OUT / "pytest.log"

    if raw_pytest.exists():
        pytest_log = read_text(raw_pytest)
    elif out_pytest.exists():
        pytest_log = read_text(out_pytest)

    result = build_fix_context(audit_machine, pytest_log)
    write_json(AUDIT_OUT / "fix_context.json", result)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())