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


def is_python(path_str: str) -> bool:
    return normalize_path(path_str).lower().endswith(".py")


def is_runtime_python(path_str: str) -> bool:
    rel = normalize_path(path_str).lower()
    return rel.endswith(".py") and not rel.startswith("tests/") and not rel.startswith(".github/")


def is_generated_test(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith("tests/generated/")


def is_guardrail_test(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith("tests/guardrails/")


def is_hft_test(path_str: str) -> bool:
    rel = normalize_path(path_str).lower()
    return rel.startswith("tests/") and "hft" in rel


def is_github_script(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith(".github/scripts/")


def classify_item(item: dict) -> tuple[str, list[str]]:
    target_file = normalize_path(item.get("target_file", ""))
    issue_type = str(item.get("issue_type", "")).strip()
    notes = item.get("notes", []) or []

    reasons = []

    if not target_file:
        return "HUMAN_ONLY", ["Missing target file."]

    if is_github_script(target_file):
        return "HUMAN_ONLY", ["Workflow/script target: avoid blind auto-fix."]

    if is_hft_test(target_file):
        return "HUMAN_ONLY", ["HFT-related tests are too sensitive for blind auto-fix."]

    if is_generated_test(target_file):
        reasons.append("Generated test target: safe nominal test area.")
        return "AUTO_FIX_SAFE", reasons

    if issue_type == "missing_nominal_test":
        reasons.append("Nominal test generation is safe.")
        return "AUTO_FIX_SAFE", reasons

    if issue_type == "missing_public_contract":
        reasons.append("Public contract restoration can be auto-fixed conservatively.")
        return "AUTO_FIX_SAFE", reasons

    if issue_type == "contract_test_failure":
        reasons.append("Contract test failure should remain reviewable.")
        return "AUTO_FIX_REVIEW", reasons

    if issue_type == "lint_failure":
        if is_runtime_python(target_file):
            reasons.append("Runtime lint failure: usually local, mechanical, and safe.")
            return "AUTO_FIX_SAFE", reasons
        if is_python(target_file):
            reasons.append("Python lint failure: typically safe.")
            return "AUTO_FIX_SAFE", reasons

    if issue_type == "runtime_failure":
        if is_runtime_python(target_file):
            reasons.append("Runtime module failure: candidate for reviewable fix.")
            reasons.append("Prefer conservative local patching and targeted tests.")
            return "AUTO_FIX_REVIEW", reasons
        if is_guardrail_test(target_file):
            reasons.append("Guardrail runtime-like failure: keep under review.")
            return "AUTO_FIX_REVIEW", reasons

    if issue_type == "test_failure":
        if is_guardrail_test(target_file):
            reasons.append("Guardrail test: area delicata, consentita solo con review.")
            return "AUTO_FIX_REVIEW", reasons
        if normalize_path(target_file).startswith("tests/") and is_python(target_file):
            reasons.append("Ordinary test failure: reviewable.")
            return "AUTO_FIX_REVIEW", reasons

    if issue_type == "ci_failure":
        if is_runtime_python(target_file):
            reasons.append("CI-linked runtime target: reviewable but not blindly safe.")
            return "AUTO_FIX_REVIEW", reasons
        reasons.append("Generic CI failure without strong local proof.")
        return "HUMAN_ONLY", reasons

    if notes:
        text_blob = " ".join(str(x) for x in notes).lower()
        if "ruff" in text_blob or "lint" in text_blob:
            if is_runtime_python(target_file):
                reasons.append("Detected lint-like signal from notes on runtime target.")
                return "AUTO_FIX_SAFE", reasons
        if "failed" in text_blob and is_guardrail_test(target_file):
            reasons.append("Guardrail-related failing signal in notes.")
            return "AUTO_FIX_REVIEW", reasons

    if is_runtime_python(target_file):
        reasons.append("Fallback runtime target: keep under review.")
        return "AUTO_FIX_REVIEW", reasons

    if is_python(target_file):
        reasons.append("Fallback Python target: keep under review.")
        return "AUTO_FIX_REVIEW", reasons

    return "HUMAN_ONLY", ["Unknown/non-python target."]


def main() -> int:
    fix_context = read_json(AUDIT_OUT / "fix_context.json")
    items = fix_context.get("fix_contexts", []) or []

    classified = []
    summary = {
        "AUTO_FIX_SAFE": 0,
        "AUTO_FIX_REVIEW": 0,
        "HUMAN_ONLY": 0,
    }

    for item in items:
        cloned = dict(item)
        target_file = normalize_path(cloned.get("target_file", ""))
        cloned["target_file"] = target_file

        related_source = normalize_path(cloned.get("related_source_file", ""))
        cloned["related_source_file"] = related_source

        classification, reasons = classify_item(cloned)
        cloned["classification"] = classification
        cloned["classification_reasons"] = reasons

        summary[classification] = summary.get(classification, 0) + 1
        classified.append(cloned)

    result = {
        "fix_contexts": classified,
        "summary": summary,
    }

    write_json(AUDIT_OUT / "issue_classification.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())