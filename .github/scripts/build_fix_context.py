#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"
AUDIT_RAW = ROOT / "audit_raw"

MAX_CONTEXTS = 12
MAX_RELATED_TESTS = 5
MAX_RELATED_FIXTURES = 3
MAX_RELATED_CONTRACTS = 3
MAX_NOTES = 8


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
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def normalize_path(path_str: str) -> str:
    raw = str(path_str or "").strip().replace("\\", "/")
    if not raw:
        return ""
    try:
        p = Path(raw)
        if p.is_absolute():
            return str(p.resolve().relative_to(ROOT)).replace("\\", "/")
    except Exception:
        pass
    return raw.lstrip("./")


def unique_keep_order(items, limit: int | None = None) -> list[str]:
    out = []
    seen = set()

    for item in items or []:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
        if limit is not None and len(out) >= limit:
            break

    return out


def trim_list(items, limit: int) -> list[str]:
    return unique_keep_order(items, limit)


def load_audit_machine() -> dict:
    return read_json(AUDIT_OUT / "audit_machine.json")


def load_ai_reasoning() -> dict:
    return read_json(AUDIT_OUT / "ai_reasoning.json")


def load_test_failure_context() -> dict:
    return read_json(AUDIT_OUT / "test_failure_context.json")


def load_ci_failure_context() -> dict:
    return read_json(AUDIT_OUT / "ci_failure_context.json")


def load_repo_diagnostics_context() -> dict:
    return read_json(AUDIT_OUT / "repo_diagnostics_context.json")


def load_ai_cto_layer() -> dict:
    return read_json(AUDIT_OUT / "ai_cto_layer.json")


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

    return signals[:120]


def guess_related_tests_for_runtime(target_file: str) -> list[str]:
    rel = normalize_path(target_file)
    if not rel or rel.startswith("tests/") or not rel.endswith(".py"):
        return []

    stem = Path(rel).stem
    guesses = [
        f"tests/test_{stem}.py",
        f"tests/contracts/test_{stem}.py",
        f"tests/guardrails/test_{stem}.py",
    ]

    existing = []
    for guess in guesses:
        if (ROOT / guess).exists():
            existing.append(guess)

    return trim_list(existing, MAX_RELATED_TESTS)


def contract_defaults_for_file(target_file: str) -> tuple[list[str], list[str], list[str]]:
    target_file = normalize_path(target_file)

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

    elif target_file.endswith(".py") and not target_file.startswith("tests/") and not target_file.startswith(".github/"):
        related_tests = guess_related_tests_for_runtime(target_file)

    return (
        trim_list(related_tests, MAX_RELATED_TESTS),
        trim_list(related_fixtures, MAX_RELATED_FIXTURES),
        trim_list(related_contracts, MAX_RELATED_CONTRACTS),
    )


def build_contract_contexts(contracts: list) -> list[dict]:
    contexts = []

    for item in contracts:
        try:
            target_file = normalize_path(str(item[0]).strip())
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


def build_from_ci_failures(ci_ctx: dict) -> list[dict]:
    contexts = []

    for item in ci_ctx.get("ci_failures", []) or []:
        target_file = normalize_path(item.get("target_file", ""))
        if not target_file:
            continue

        issue_type = str(item.get("issue_type", "")).strip() or "ci_failure"
        error_type = str(item.get("error_type", "")).strip()
        source = str(item.get("source", "")).strip()
        job = str(item.get("job", "")).strip()
        signal = str(item.get("signal", "")).strip()

        related_source_file = ""
        related_tests = []
        related_fixtures = []
        related_contracts = []

        if target_file.startswith("tests/"):
            related_tests = [target_file]
        elif target_file.endswith(".py") and not target_file.startswith(".github/"):
            related_source_file = target_file
            related_tests = guess_related_tests_for_runtime(target_file)

        notes = trim_list(
            [
                f"CI failure source: {source}" if source else "",
                f"CI job: {job}" if job else "",
                f"Error type: {error_type}" if error_type else "",
                f"Signal: {signal}" if signal else "",
                "Questo contesto proviene dai workflow CI reali del repository.",
            ],
            MAX_NOTES,
        )

        priority = "P1"
        if issue_type in {"runtime_failure", "lint_failure", "test_failure"}:
            priority = "P0"

        contexts.append(
            {
                "target_file": target_file,
                "required_symbols": [],
                "related_tests": trim_list(related_tests, MAX_RELATED_TESTS),
                "related_fixtures": trim_list(related_fixtures, MAX_RELATED_FIXTURES),
                "related_contracts": trim_list(related_contracts, MAX_RELATED_CONTRACTS),
                "notes": notes,
                "priority": priority,
                "issue_type": issue_type,
                "related_source_file": related_source_file,
            }
        )

    return contexts


def build_from_repo_diagnostics(repo_diag: dict, cto: dict) -> list[dict]:
    contexts = []

    top_runtime_candidates = []
    for item in cto.get("repair_order", []) or []:
        file_path = normalize_path(item.get("file", ""))
        if not file_path:
            continue
        if file_path.startswith("tests/") or file_path.startswith(".github/"):
            continue
        if not file_path.endswith(".py"):
            continue
        top_runtime_candidates.append(item)

    for item in top_runtime_candidates[:6]:
        file_path = normalize_path(item.get("file", ""))
        priority = str(item.get("priority", "P2")).strip().upper() or "P2"
        kind = str(item.get("kind", "")).strip()

        related_tests, related_fixtures, related_contracts = contract_defaults_for_file(file_path)

        notes = trim_list(
            [
                "Contesto derivato da AI CTO layer.",
                f"CTO priority: {priority}",
                f"CTO kind: {kind}" if kind else "",
                *[str(x).strip() for x in (item.get("reasons", []) or [])],
            ],
            MAX_NOTES,
        )

        contexts.append(
            {
                "target_file": file_path,
                "required_symbols": [],
                "related_tests": related_tests,
                "related_fixtures": related_fixtures,
                "related_contracts": related_contracts,
                "notes": notes,
                "priority": "P0" if priority == "P0" else "P1",
                "issue_type": "runtime_failure" if kind in {"complex_runtime", "high_risk_runtime"} else "ci_failure",
                "related_source_file": file_path,
            }
        )

    return contexts


def merge_contexts(contexts: list[dict]) -> list[dict]:
    merged = {}

    for item in contexts:
        target_file = normalize_path(item.get("target_file", ""))
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
                "related_source_file": normalize_path(item.get("related_source_file", "")),
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

        if str(item.get("priority", "")).upper() == "P0":
            dst["priority"] = "P0"

        incoming_issue = str(item.get("issue_type", "")).strip()
        current_issue = str(dst.get("issue_type", "")).strip()

        issue_rank = {
            "missing_public_contract": 100,
            "contract_test_failure": 90,
            "runtime_failure": 80,
            "lint_failure": 70,
            "test_failure": 60,
            "ci_failure": 50,
            "generic": 10,
        }

        if issue_rank.get(incoming_issue, 0) > issue_rank.get(current_issue, 0):
            dst["issue_type"] = incoming_issue

        if not dst.get("related_source_file") and item.get("related_source_file"):
            dst["related_source_file"] = normalize_path(item.get("related_source_file", ""))

    result = []
    for value in merged.values():
        value["required_symbols"] = trim_list(value.get("required_symbols", []), 6)
        value["related_tests"] = trim_list(value.get("related_tests", []), MAX_RELATED_TESTS)
        value["related_fixtures"] = trim_list(value.get("related_fixtures", []), MAX_RELATED_FIXTURES)
        value["related_contracts"] = trim_list(value.get("related_contracts", []), MAX_RELATED_CONTRACTS)
        value["notes"] = trim_list(value.get("notes", []), MAX_NOTES)
        result.append(value)

    return result


def score_context(item: dict, pytest_signals: list[str], ai_reasoning: dict, cto: dict) -> int:
    score = 0

    target_file = normalize_path(item.get("target_file", ""))
    required_symbols = item.get("required_symbols", []) or []
    issue_type = str(item.get("issue_type", "")).strip()
    related_source_file = normalize_path(item.get("related_source_file", ""))

    if item.get("priority") == "P0":
        score += 100

    issue_bonus = {
        "missing_public_contract": 180,
        "contract_test_failure": 160,
        "runtime_failure": 150,
        "lint_failure": 130,
        "test_failure": 120,
        "ci_failure": 90,
        "generic": 20,
    }
    score += issue_bonus.get(issue_type, 0)

    for line in pytest_signals:
        if target_file and target_file in line:
            score += 60
        if related_source_file and related_source_file in line:
            score += 45
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

    for item_cto in cto.get("repair_order", []) or []:
        file_path = normalize_path(item_cto.get("file", ""))
        if file_path == target_file or (related_source_file and file_path == related_source_file):
            priority = str(item_cto.get("priority", "P2")).strip().upper()
            if priority == "P0":
                score += 80
            elif priority == "P1":
                score += 40
            else:
                score += 15

    if target_file.startswith("tests/"):
        score += 10
    else:
        score += 30

    score += min(len(item.get("related_tests", [])), MAX_RELATED_TESTS) * 5
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
        target_file = normalize_path(item.get("target_file", ""))
        if not target_file or target_file in seen:
            continue

        related_source = normalize_path(item.get("related_source_file", ""))
        issue_type = str(item.get("issue_type", "")).strip()

        if target_file.startswith("tests/") and related_source in contract_targets:
            continue

        if (
            target_file.startswith("tests/")
            and issue_type in {"test_failure", "ci_failure"}
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
    ci_failure_context = load_ci_failure_context()
    repo_diag = load_repo_diagnostics_context()
    cto = load_ai_cto_layer()
    pytest_log = load_pytest_log()

    contracts = audit_machine.get("contracts", []) or []
    pytest_signals = extract_pytest_signals(pytest_log)

    contract_contexts = build_contract_contexts(contracts)
    pytest_contexts = build_pytest_contexts(pytest_signals)
    test_contexts = test_failure_context.get("test_failure_contexts", []) or []
    ci_contexts = build_from_ci_failures(ci_failure_context)
    diag_contexts = build_from_repo_diagnostics(repo_diag, cto)

    contexts = merge_contexts(
        contract_contexts
        + pytest_contexts
        + test_contexts
        + ci_contexts
        + diag_contexts
    )

    for item in contexts:
        item["_score"] = score_context(item, pytest_signals, ai_reasoning, cto)

    contexts.sort(key=lambda x: x.get("_score", 0), reverse=True)
    contexts = collapse_test_only_contexts(contexts)
    contexts = contexts[:MAX_CONTEXTS]

    for item in contexts:
        item.pop("_score", None)

    result = {
        "fix_contexts": contexts,
    }

    write_json(AUDIT_OUT / "fix_context.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())