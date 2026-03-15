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
}

REVIEW_ISSUE_TYPES = {
    "contract_test_failure",
    "normal_test_file",
}

MAX_NOTES = 6


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


def is_high_risk_path(path_str: str) -> bool:
    path_str = (path_str or "").strip().lower()
    if not path_str:
        return False
    return path_str.startswith(HIGH_RISK_PATH_PREFIXES)


def contains_high_risk_keyword(values: list[str]) -> bool:
    blob = " ".join(str(v) for v in values).lower()
    return any(keyword in blob for keyword in HIGH_RISK_KEYWORDS)


def classify_one(item: dict) -> dict:
    target_file = str(item.get("target_file", "")).strip()
    issue_type = str(item.get("issue_type", "")).strip()
    notes = item.get("notes", []) or []
    related_source_file = str(item.get("related_source_file", "")).strip()
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
    elif target_file.startswith("tests/") and issue_type in {"empty_test_file", "corrupted_or_non_test_content"}:
        classification = "AUTO_FIX_SAFE"
        reasons.append("Test file vuoto o corrotto: fix locale e confinato.")
    elif issue_type in SAFE_ISSUE_TYPES:
        classification = "AUTO_FIX_SAFE"
        reasons.append("Issue type noto come sicuro per auto-fix minimo.")
    elif issue_type in REVIEW_ISSUE_TYPES:
        classification = "AUTO_FIX_REVIEW"
        reasons.append("Issue type reviewable ma non totalmente blindato.")
    else:
        classification = "AUTO_FIX_REVIEW"
        reasons.append("Issue non classificato come safe puro; richiede review.")

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
        elif classification == "AUTO_FIX_SAFE":
            reasons.append("Fix confinato al test o al contract correlato.")

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
    contexts = fix_context.get("fix_contexts", []) or []

    classified = [classify_one(item) for item in contexts]

    result = {
        "fix_contexts": classified,
        "summary": build_summary(classified),
    }

    write_json(AUDIT_OUT / "issue_classification.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())