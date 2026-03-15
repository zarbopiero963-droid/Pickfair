#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"

SAFE_CONTRACT_FILES = {
    "auto_updater.py",
    "executor_manager.py",
    "tests/fixtures/system_payloads.py",
}

HIGH_RISK_PATH_PREFIXES = (
    "strategies/",
    "money_management/",
    "bankroll/",
    "trading/",
    "quant/",
)

HIGH_RISK_KEYWORDS = (
    "stake",
    "bankroll",
    "money management",
    "martingale",
    "dutching strategy",
    "trading logic",
    "bet sizing",
    "risk engine",
    "execution engine",
    "pricing model",
    "quant model",
    "prediction model",
)

SAFE_ISSUE_TYPES = {
    "missing_public_contract",
    "empty_test_file",
    "corrupted_or_non_test_content",
    "lint_failure",
}

REVIEW_ISSUE_TYPES = {
    "contract_test_failure",
    "normal_test_file",
    "test_failure",
    "runtime_failure",
    "ci_failure",
}

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


def trim_list(items, limit: int) -> list[str]:
    out = []
    seen = set()

    for item in items or []:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
        if len(out) >= limit:
            break

    return out


def normalize_path(path_str: str) -> str:
    return str(path_str or "").strip().replace("\\", "/")


def is_high_risk_path(path_str: str) -> bool:
    path_str = normalize_path(path_str).lower()
    if not path_str:
        return False
    return path_str.startswith(HIGH_RISK_PATH_PREFIXES)


def contains_high_risk_keyword(values: list[str]) -> bool:
    blob = " ".join(str(v) for v in values).lower()
    return any(keyword in blob for keyword in HIGH_RISK_KEYWORDS)


def load_repo_diagnostics() -> dict:
    return read_json(AUDIT_OUT / "repo_diagnostics_context.json")


def build_high_risk_area_set(repo_diag: dict) -> set[str]:
    result = set()
    for item in repo_diag.get("complex_or_high_risk_areas", []) or []:
        if not isinstance(item, dict):
            continue
        file_path = normalize_path(item.get("file", ""))
        risk = str(item.get("risk", "")).strip().lower()
        if file_path and risk == "high":
            result.add(file_path)
    return result


def build_public_symbol_map(repo_diag: dict) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}

    for item in repo_diag.get("public_symbols_without_nominal_tests", []) or []:
        if not isinstance(item, dict):
            continue
        file_path = normalize_path(item.get("file", ""))
        symbol = str(item.get("symbol", "")).strip()
        if not file_path or not symbol:
            continue
        result.setdefault(file_path, set()).add(symbol)

    return result


def path_is_generated_test(path_str: str) -> bool:
    path_str = normalize_path(path_str).lower()
    return path_str.startswith("tests/generated/")


def path_is_guardrail_test(path_str: str) -> bool:
    path_str = normalize_path(path_str).lower()
    return path_str.startswith("tests/guardrails/")


def path_is_hft_test(path_str: str) -> bool:
    path_str = normalize_path(path_str).lower()
    return path_str.startswith("tests/") and "hft" in path_str


def path_is_github_script(path_str: str) -> bool:
    path_str = normalize_path(path_str).lower()
    return path_str.startswith(".github/scripts/")


def path_is_runtime_module(path_str: str) -> bool:
    path_str = normalize_path(path_str).lower()
    if not path_str.endswith(".py"):
        return False
    if path_str.startswith("tests/"):
        return False
    if path_str.startswith(".github/"):
        return False
    return True


def path_has_precise_runtime_target(item: dict) -> bool:
    target_file = normalize_path(item.get("target_file", ""))
    related_source = normalize_path(item.get("related_source_file", ""))

    if path_is_runtime_module(target_file):
        return True
    if path_is_runtime_module(related_source):
        return True
    return False


def classify_one(item: dict, repo_diag: dict, high_risk_areas: set[str], public_symbol_map: dict[str, set[str]]) -> dict:
    target_file = normalize_path(item.get("target_file", ""))
    issue_type = str(item.get("issue_type", "")).strip()
    notes = item.get("notes", []) or []
    related_source_file = normalize_path(item.get("related_source_file", ""))
    required_symbols = item.get("required_symbols", []) or []

    reasons = []
    classification = "AUTO_FIX_REVIEW"

    relevant_text = []
    relevant_text.extend(notes)
    relevant_text.extend(required_symbols)
    relevant_text.append(target_file)
    relevant_text.append(related_source_file)

    if target_file in SAFE_CONTRACT_FILES:
        classification = "AUTO_FIX_SAFE"
        reasons.append("Target file rientra nei contract file sicuri e piccoli.")

    elif path_is_generated_test(target_file):
        classification = "AUTO_FIX_SAFE"
        reasons.append("Test generato nominale: target sicuro per auto-fix.")

    elif path_is_guardrail_test(target_file):
        classification = "AUTO_FIX_REVIEW"
        reasons.append("Guardrail test: area delicata, consentita solo con review.")

    elif path_is_hft_test(target_file):
        classification = "HUMAN_ONLY"
        reasons.append("HFT test: area troppo delicata per auto-fix diretto.")

    elif path_is_github_script(target_file):
        classification = "HUMAN_ONLY"
        reasons.append("Script CI/GitHub: escluso dall'auto-fix diretto.")

    elif target_file.startswith("tests/") and issue_type in {"empty_test_file", "corrupted_or_non_test_content"}:
        classification = "AUTO_FIX_SAFE"
        reasons.append("Test file vuoto o corrotto: fix locale e confinato.")

    elif issue_type in SAFE_ISSUE_TYPES and path_has_precise_runtime_target(item):
        classification = "AUTO_FIX_SAFE"
        reasons.append("Issue type sicuro con target runtime chiaro.")

    elif issue_type in SAFE_ISSUE_TYPES:
        classification = "AUTO_FIX_REVIEW"
        reasons.append("Issue type sicuro ma target non abbastanza preciso.")

    elif issue_type in REVIEW_ISSUE_TYPES:
        classification = "AUTO_FIX_REVIEW"
        reasons.append("Issue reviewable ma non totalmente blindato.")

    else:
        classification = "AUTO_FIX_REVIEW"
        reasons.append("Issue non classificato come safe puro; richiede review.")

    if path_is_runtime_module(target_file) and target_file in high_risk_areas:
        if classification == "AUTO_FIX_SAFE":
            classification = "AUTO_FIX_REVIEW"
        reasons.append("Modulo runtime ad alto rischio secondo repo diagnostics.")

    if related_source_file and related_source_file in high_risk_areas:
        if classification == "AUTO_FIX_SAFE":
            classification = "AUTO_FIX_REVIEW"
        reasons.append("File sorgente correlato ad area ad alto rischio.")

    if is_high_risk_path(target_file) or is_high_risk_path(related_source_file):
        classification = "HUMAN_ONLY"
        reasons.append("Percorso ad alto rischio: area trading/quant/money management.")

    elif contains_high_risk_keyword(relevant_text):
        classification = "HUMAN_ONLY"
        reasons.append("Keyword ad alto rischio rilevate nel contesto.")

    if target_file.startswith("tests/") and related_source_file:
        if is_high_risk_path(related_source_file):
            classification = "HUMAN_ONLY"
            reasons.append("Test collegato a modulo ad alto rischio.")
        elif related_source_file in high_risk_areas and classification == "AUTO_FIX_SAFE":
            classification = "AUTO_FIX_REVIEW"
            reasons.append("Test collegato a modulo complesso: safe declassato a review.")
        elif classification == "AUTO_FIX_SAFE":
            reasons.append("Fix confinato al test o al contract correlato.")

    if path_is_runtime_module(target_file):
        known_public_symbols = public_symbol_map.get(target_file, set())
        if known_public_symbols and required_symbols:
            shared = [s for s in required_symbols if s in known_public_symbols]
            if shared:
                if classification != "HUMAN_ONLY":
                    classification = "AUTO_FIX_SAFE"
                reasons.append("Simbolo pubblico noto come scoperto dai test nominali.")

    out = dict(item)
    out["classification"] = classification
    out["classification_reasons"] = trim_list(reasons, MAX_NOTES)
    return out


def build_summary(items: list[dict]) -> dict:
    counts = {
        "AUTO_FIX_SAFE": 0,
        "AUTO_FIX_REVIEW": 0,
        "HUMAN_ONLY": 0,
    }

    for item in items:
        cls = str(item.get("classification", "")).strip()
        if cls in counts:
            counts[cls] += 1

    return counts


def main() -> int:
    fix_context = read_json(AUDIT_OUT / "fix_context.json")
    repo_diag = load_repo_diagnostics()

    contexts = fix_context.get("fix_contexts", []) or []
    high_risk_areas = build_high_risk_area_set(repo_diag)
    public_symbol_map = build_public_symbol_map(repo_diag)

    classified = [
        classify_one(item, repo_diag, high_risk_areas, public_symbol_map)
        for item in contexts
    ]

    result = {
        "fix_contexts": classified,
        "summary": build_summary(classified),
    }

    write_json(AUDIT_OUT / "issue_classification.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())