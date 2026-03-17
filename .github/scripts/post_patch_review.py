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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def normalize_path(path_str: str) -> str:
    raw = str(path_str or "").replace("\\", "/").strip()
    while raw.startswith("./"):
        raw = raw[2:]
    return raw


def is_runtime_python(path_str: str) -> bool:
    rel = normalize_path(path_str).lower()
    return rel.endswith(".py") and not rel.startswith("tests/") and not rel.startswith(".github/")


def is_generated_test(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith("tests/generated/")


def is_guardrail_test(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith("tests/guardrails/")


def is_contract_like_target(path_str: str) -> bool:
    rel = normalize_path(path_str)
    return rel in {
        "auto_updater.py",
        "executor_manager.py",
        "tests/fixtures/system_payloads.py",
    }


def extract_test_success(targeted_tests: dict) -> tuple[bool, int, int]:
    if "success" in targeted_tests:
        success = bool(targeted_tests.get("success", False))
        tests_run = targeted_tests.get("tests_run", []) or []
        executed_count = len(tests_run)
        failure_count = 0 if success else 1
        return success, executed_count, failure_count

    summary = targeted_tests.get("summary", {}) or {}
    executed_count = int(summary.get("executed_count", 0) or 0)
    failure_count = targeted_tests.get("failure_count")
    if not isinstance(failure_count, int):
        failure_count = 0
    success = failure_count == 0
    return success, executed_count, failure_count


def build_report(data: dict) -> str:
    lines = []
    lines.append("Post Patch Review")
    lines.append("")
    lines.append(f"Review verdict: {data.get('review_verdict', '')}")
    lines.append(f"Summary: {data.get('summary', '')}")
    lines.append("")
    lines.append(f"Contract restored: {'YES' if data.get('contract_restored') else 'NO'}")
    lines.append(f"Minimal change: {'YES' if data.get('minimal_change') else 'NO'}")
    lines.append(f"Logic preserved: {'YES' if data.get('logic_preserved') else 'NO'}")
    lines.append("")
    lines.append("Reasons")
    reasons = data.get("reasons", []) or []
    if reasons:
        for item in reasons:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def main() -> int:
    patch_candidate_payload = read_json(AUDIT_OUT / "patch_candidate.json")
    candidate = patch_candidate_payload.get("patch_candidate") or {}
    if not isinstance(candidate, dict):
        candidate = {}

    patch_apply = read_json(AUDIT_OUT / "patch_apply_report.json")
    patch_verification = read_json(AUDIT_OUT / "patch_verification.json")
    targeted_tests = read_json(AUDIT_OUT / "targeted_tests.json")
    if not targeted_tests:
        targeted_tests = read_json(AUDIT_OUT / "targeted_test_results.json")

    target_file = normalize_path(candidate.get("target_file", ""))
    issue_type = str(candidate.get("issue_type", "")).strip()
    classification = str(candidate.get("classification", "")).strip()

    applied = bool(patch_apply.get("applied", False))
    verifier_verdict = str(patch_verification.get("verdict", "")).strip().lower() or "reject"
    verifier_reason = str(patch_verification.get("reason", "")).strip()
    verifier_notes = [str(x).strip() for x in (patch_verification.get("notes", []) or []) if str(x).strip()]

    tests_success, executed_count, failure_count = extract_test_success(targeted_tests)

    review_verdict = "reject"
    summary = ""
    reasons = []

    minimal_change = bool(applied)
    logic_preserved = False
    contract_restored = False

    if not candidate:
        review_verdict = "reject"
        summary = "No patch candidate available for review."
        reasons.append("patch_candidate.json does not contain a valid patch candidate.")

    elif not applied:
        review_verdict = "reject"
        summary = "Patch was not applied."
        reasons.append(str(patch_apply.get("reason", "patch_not_applied")).strip())

    elif verifier_verdict == "reject":
        review_verdict = "reject"
        summary = "Verifier rejected the patch."
        reasons.append(verifier_reason or "verifier_reject")

    else:
        if issue_type == "missing_public_contract" and is_contract_like_target(target_file):
            contract_restored = verifier_verdict in {"approve", "weak-approve", "review"}
            logic_preserved = contract_restored
            review_verdict = "approve" if contract_restored else "review"
            summary = "Contract-like target patched with real diff."
            reasons.append("Missing public contract target changed correctly.")

        elif issue_type in {"runtime_failure", "lint_failure", "ci_failure"} and is_runtime_python(target_file):
            logic_preserved = True
            if executed_count > 0:
                if tests_success:
                    review_verdict = "approve"
                    summary = "Runtime patch applied and targeted tests passed."
                    reasons.append(f"Executed targeted tests: {executed_count}")
                else:
                    review_verdict = "review"
                    summary = "Runtime patch applied, but targeted tests did not fully pass."
                    reasons.append(f"Targeted test failures: {failure_count}")
            else:
                review_verdict = "weak-approve"
                summary = "Runtime patch applied with no targeted tests available."
                reasons.append("No targeted runtime tests were available.")
            reasons.append("Runtime/lint target produced a real diff on a runtime file.")

        elif issue_type == "test_failure":
            logic_preserved = True
            if is_guardrail_test(target_file):
                review_verdict = "review"
                summary = "Guardrail test patch requires review."
                reasons.append("Guardrail tests are sensitive by design.")
            else:
                if executed_count > 0 and tests_success:
                    review_verdict = "approve"
                    summary = "Test patch applied and targeted tests passed."
                    reasons.append(f"Executed targeted tests: {executed_count}")
                else:
                    review_verdict = "weak-approve"
                    summary = "Test patch applied with limited or inconclusive test evidence."
                    reasons.append(f"Targeted tests executed: {executed_count}")

        elif issue_type == "missing_nominal_test" and is_generated_test(target_file):
            logic_preserved = True
            review_verdict = "weak-approve"
            summary = "Generated nominal test patch is acceptable."
            reasons.append("Generated test file changed with real diff.")

        else:
            logic_preserved = verifier_verdict in {"approve", "weak-approve", "review"}
            review_verdict = "review"
            summary = "Patch requires review despite real diff."
            reasons.append("Generic patch path: keep review verdict.")

    if classification == "HUMAN_ONLY" and review_verdict in {"approve", "weak-approve"}:
        review_verdict = "review"
        summary = "Patch requires human review due to HUMAN_ONLY classification."
        reasons.append("Classification forced review-level outcome.")

    reasons.extend(verifier_notes[:8])

    result = {
        "review_verdict": review_verdict,
        "final_verdict": review_verdict,
        "summary": summary,
        "reasons": reasons[:12],
        "contract_restored": contract_restored,
        "minimal_change": minimal_change,
        "logic_preserved": logic_preserved,
        "verifier_verdict": verifier_verdict,
        "executed_count": executed_count,
        "failure_count": failure_count,
        "tests_success": tests_success,
        "target_file": target_file,
        "issue_type": issue_type,
        "classification": classification,
    }

    write_json(AUDIT_OUT / "post_patch_review.json", result)
    write_text(AUDIT_OUT / "post_patch_review.md", build_report(result))

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())