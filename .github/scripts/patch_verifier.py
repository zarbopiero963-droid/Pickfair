#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"


SAFE_ISSUE_TYPES = {
    "missing_public_contract",
    "empty_test_file",
    "corrupted_or_non_test_content",
    "lint_failure",
    "missing_nominal_test",
}

REVIEW_ISSUE_TYPES = {
    "contract_test_failure",
    "normal_test_file",
    "test_failure",
    "runtime_failure",
    "ci_failure",
}

HUMAN_ONLY_PATH_PREFIXES = (
    ".github/scripts/",
)

HUMAN_ONLY_TEST_KEYWORDS = (
    "hft",
)

REVIEW_ONLY_TEST_PREFIXES = (
    "tests/guardrails/",
)

SAFE_TEST_PREFIXES = (
    "tests/generated/",
)


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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def normalize_path(path_str: str) -> str:
    return str(path_str or "").strip().replace("\\", "/")


def is_generated_test(path_str: str) -> bool:
    path_str = normalize_path(path_str).lower()
    return path_str.startswith(SAFE_TEST_PREFIXES)


def is_guardrail_test(path_str: str) -> bool:
    path_str = normalize_path(path_str).lower()
    return path_str.startswith(REVIEW_ONLY_TEST_PREFIXES)


def is_hft_test(path_str: str) -> bool:
    path_str = normalize_path(path_str).lower()
    return path_str.startswith("tests/") and any(k in path_str for k in HUMAN_ONLY_TEST_KEYWORDS)


def is_github_script(path_str: str) -> bool:
    path_str = normalize_path(path_str).lower()
    return path_str.startswith(HUMAN_ONLY_PATH_PREFIXES)


def is_runtime_module(path_str: str) -> bool:
    path_str = normalize_path(path_str).lower()
    if not path_str.endswith(".py"):
        return False
    if path_str.startswith("tests/"):
        return False
    if path_str.startswith(".github/"):
        return False
    return True


def build_md(data: dict) -> str:
    lines = []
    lines.append("Patch Verification")
    lines.append("")
    lines.append(f"Verdict: {data.get('verdict', '')}")
    lines.append(f"Confidence: {data.get('confidence', '')}")
    lines.append("")
    lines.append("Summary")
    lines.append(data.get("summary", ""))
    lines.append("")
    lines.append("Why")
    for item in data.get("why", []) or []:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("Likely gaps")
    for item in data.get("likely_gaps", []) or []:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("Tests to run")
    tests = data.get("tests_to_run", []) or []
    if tests:
        for item in tests:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessun test suggerito.")
    lines.append("")
    lines.append("Safe next step")
    lines.append(data.get("safe_next_step", ""))
    return "\n".join(lines)


def main() -> int:
    candidate_wrapper = read_json(AUDIT_OUT / "patch_candidate.json")
    issue_classification = read_json(AUDIT_OUT / "issue_classification.json")
    fix_context = read_json(AUDIT_OUT / "fix_context.json")
    diagnostics = read_json(AUDIT_OUT / "repo_diagnostics_context.json")
    test_gap = read_json(AUDIT_OUT / "test_gap_generation_report.json")
    targeted_tests = read_json(AUDIT_OUT / "targeted_test_results.json")

    candidate = candidate_wrapper.get("patch_candidate")
    reason = str(candidate_wrapper.get("reason", "")).strip()

    result = {
        "verdict": "reject",
        "confidence": "high",
        "summary": "",
        "why": [],
        "likely_gaps": [],
        "tests_to_run": [],
        "safe_next_step": "",
    }

    if not candidate:
        result["summary"] = "No actionable patch candidate was provided."
        result["why"] = [
            f"Patch candidate reason: {reason or 'unknown'}",
            "Non esiste un target concreto da verificare.",
        ]
        result["likely_gaps"] = [
            "Missing patch candidate",
            "Missing target file",
            "Missing remediation strategy",
        ]
        result["safe_next_step"] = (
            "Rigenerare il patch candidate dopo avere un fix context e una classificazione validi."
        )

        write_json(AUDIT_OUT / "patch_verification.json", result)
        write_text(AUDIT_OUT / "patch_verification.md", build_md(result))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    strategy = str(candidate.get("strategy", "")).strip()
    target_file = normalize_path(candidate.get("target_file", ""))
    related_source_file = normalize_path(candidate.get("related_source_file", ""))
    issue_type = str(candidate.get("issue_type", "")).strip()
    notes = candidate.get("notes", []) or []

    classified_map = {
        normalize_path(item.get("target_file", "")): item
        for item in issue_classification.get("fix_contexts", []) or []
        if normalize_path(item.get("target_file", ""))
    }

    classified_target = classified_map.get(target_file, {})
    classification = str(classified_target.get("classification", "")).strip()
    classification_reasons = classified_target.get("classification_reasons", []) or []

    targeted_failure_count = targeted_tests.get("failure_count")
    if not isinstance(targeted_failure_count, int):
        targeted_failure_count = None

    source_is_high_risk = False
    for item in diagnostics.get("complex_or_high_risk_areas", []) or []:
        if not isinstance(item, dict):
            continue
        if normalize_path(item.get("file", "")) == related_source_file and str(item.get("risk", "")).strip().lower() == "high":
            source_is_high_risk = True
            break
        if normalize_path(item.get("file", "")) == target_file and str(item.get("risk", "")).strip().lower() == "high":
            source_is_high_risk = True
            break

    if is_github_script(target_file):
        result["summary"] = "Target inside .github/scripts is not auto-reviewable."
        result["why"] = [
            "Gli script CI sono classificati come area sensibile.",
            f"Target file: {target_file}",
        ]
        result["likely_gaps"] = [
            "Workflow/CI logic patch",
            "Needs human review",
        ]
        result["safe_next_step"] = "Bloccare l'auto-fix e richiedere review manuale sullo script CI."

    elif is_hft_test(target_file):
        result["summary"] = "HFT test target is not auto-reviewable."
        result["why"] = [
            "I test HFT sono esclusi dall'auto-fix diretto.",
            f"Target file: {target_file}",
        ]
        result["likely_gaps"] = [
            "High-risk trading test",
            "Potential false-positive semantic fix",
        ]
        result["safe_next_step"] = "Richiedere review manuale o restringere il target a un modulo runtime più piccolo."

    elif classification == "HUMAN_ONLY":
        result["summary"] = "Target classified as HUMAN_ONLY."
        result["why"] = [
            f"Classification: {classification}",
            *[str(x) for x in classification_reasons[:4]],
        ]
        result["likely_gaps"] = [
            "Target too risky for conservative auto-fix",
        ]
        result["safe_next_step"] = "Saltare questo target e sceglierne uno AUTO_FIX_SAFE o AUTO_FIX_REVIEW."

    elif strategy == "generate_nominal_test" and is_generated_test(target_file):
        result["verdict"] = "approve"
        result["confidence"] = "medium"
        result["summary"] = "Generated nominal test is safe and reviewable."
        result["why"] = [
            "Il target è dentro tests/generated/.",
            "La strategia è di sola generazione test nominale.",
            f"Related source file: {related_source_file or 'unknown'}",
        ]
        if source_is_high_risk:
            result["verdict"] = "weak-approve"
            result["confidence"] = "medium"
            result["why"].append("Il modulo sorgente è ad alto rischio: approvazione declassata a weak-approve.")
        result["tests_to_run"] = [target_file]
        result["safe_next_step"] = "Applicare il test generato e lanciare il test file appena creato."

    elif classification == "AUTO_FIX_SAFE":
        result["verdict"] = "approve"
        result["confidence"] = "medium"
        result["summary"] = "Patch candidate classified as AUTO_FIX_SAFE."
        result["why"] = [
            f"Target file: {target_file}",
            f"Issue type: {issue_type}",
            f"Strategy: {strategy}",
            *[str(x) for x in classification_reasons[:4]],
        ]

        if issue_type not in SAFE_ISSUE_TYPES:
            result["verdict"] = "weak-approve"
            result["why"].append("Issue type non pienamente safe: approvazione abbassata.")
        if source_is_high_risk:
            result["verdict"] = "weak-approve"
            result["why"].append("Area ad alto rischio secondo repo diagnostics: approvazione abbassata.")
        if targeted_failure_count not in (None, 0):
            result["why"].append(
                f"Targeted tests still show {targeted_failure_count} failures: serve validazione dopo apply."
            )

        result["tests_to_run"] = [target_file]
        if related_source_file and related_source_file != target_file:
            result["tests_to_run"].append(related_source_file)
        result["safe_next_step"] = "Applicare la patch minima e rilanciare i test mirati sul target."

    elif classification == "AUTO_FIX_REVIEW":
        result["verdict"] = "review"
        result["confidence"] = "medium"
        result["summary"] = "Patch candidate is reviewable but not safe for blind approval."
        result["why"] = [
            f"Target file: {target_file}",
            f"Issue type: {issue_type}",
            f"Strategy: {strategy}",
            *[str(x) for x in classification_reasons[:4]],
        ]

        if is_guardrail_test(target_file):
            result["why"].append("Guardrail test: review necessaria.")
        if source_is_high_risk:
            result["why"].append("Source area ad alto rischio: review rafforzata.")
        if issue_type in REVIEW_ISSUE_TYPES:
            result["why"].append("Issue type reviewable ma semanticamente non banale.")

        result["tests_to_run"] = [target_file]
        if related_source_file and related_source_file != target_file:
            result["tests_to_run"].append(related_source_file)
        result["safe_next_step"] = (
            "Applicare solo con controllo successivo di patch_verifier/post_patch_review e targeted tests."
        )

    elif strategy == "runtime_target_fix" and is_runtime_module(target_file):
        result["verdict"] = "review"
        result["confidence"] = "medium"
        result["summary"] = "Runtime target is plausible but not yet strongly classified as safe."
        result["why"] = [
            f"Target file: {target_file}",
            f"Related source: {related_source_file or 'none'}",
            "Runtime module con target chiaro, ma manca una classificazione strong-safe.",
        ]
        if source_is_high_risk:
            result["why"].append("Il modulo è in area ad alto rischio.")
        result["tests_to_run"] = [target_file]
        result["safe_next_step"] = "Richiedere patch minima e validazione forte sui test mirati."

    else:
        result["summary"] = "Patch candidate is not reviewable with current evidence."
        result["why"] = [
            f"Strategy: {strategy or 'unknown'}",
            f"Target file: {target_file or 'unknown'}",
            f"Issue type: {issue_type or 'unknown'}",
            f"Classification: {classification or 'unknown'}",
        ]
        if notes:
            result["why"].extend([str(x) for x in notes[:3]])
        result["likely_gaps"] = [
            "Insufficient target confidence",
            "Patch candidate not tied to a strongly safe class",
            "Evidence not enough for approval",
        ]
        result["safe_next_step"] = (
            "Selezionare un target AUTO_FIX_SAFE oppure generare un test nominale più confinato."
        )

    result["tests_to_run"] = list(dict.fromkeys([str(x).strip() for x in result["tests_to_run"] if str(x).strip()]))

    write_json(AUDIT_OUT / "patch_verification.json", result)
    write_text(AUDIT_OUT / "patch_verification.md", build_md(result))

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())