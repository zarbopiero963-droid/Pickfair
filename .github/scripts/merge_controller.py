#!/usr/bin/env python3

import json
from pathlib import Path

AUDIT_OUT = Path("audit_out")


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_text(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def build_report(data):
    lines = []
    lines.append("Merge Controller")
    lines.append("")
    lines.append(f"Decision: {data.get('decision', '')}")
    lines.append(f"Reason: {data.get('reason', '')}")
    lines.append("")
    lines.append(f"Should merge: {'YES' if data.get('should_merge') else 'NO'}")
    lines.append(f"Should open PR: {'YES' if data.get('should_open_pr') else 'NO'}")
    lines.append(f"Auto merge safe: {'YES' if data.get('auto_merge_safe') else 'NO'}")
    lines.append("")
    lines.append(f"Patch applied: {'YES' if data.get('patch_applied') else 'NO'}")
    lines.append(f"Patch verifier verdict: {data.get('patch_verifier_verdict', '')}")
    lines.append(f"Post patch review verdict: {data.get('post_patch_review_verdict', '')}")
    lines.append(f"Targeted tests success: {'YES' if data.get('targeted_tests_success') else 'NO'}")
    lines.append("")
    lines.append("Changed files")
    changed = data.get("changed_files", []) or []
    if changed:
        for item in changed:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessun file modificato.")
    return "\n".join(lines)


def main():
    patch_apply = read_json(AUDIT_OUT / "patch_apply_report.json")
    patch_verification = read_json(AUDIT_OUT / "patch_verification.json")
    targeted_tests = read_json(AUDIT_OUT / "targeted_tests.json")
    post_patch_review = read_json(AUDIT_OUT / "post_patch_review.json")
    patch_candidate = read_json(AUDIT_OUT / "patch_candidate.json").get("patch_candidate", {}) or {}

    patch_applied = bool(patch_apply.get("applied", False))
    changed_files = patch_apply.get("applied_targets", []) or []
    verifier_verdict = str(patch_verification.get("verdict", "")).strip().lower()
    review_verdict = str(post_patch_review.get("verdict", "")).strip().lower()
    tests_success = bool(targeted_tests.get("success", False))

    decision = "BLOCK"
    reason = "unknown"
    should_merge = False
    should_open_pr = False
    auto_merge_safe = False

    if not patch_applied:
        decision = "BLOCK"
        reason = "patch_not_applied"

    elif verifier_verdict != "accept":
        decision = "BLOCK"
        reason = patch_verification.get("reason", "verifier_reject")

    elif review_verdict != "accept":
        decision = "BLOCK"
        reason = post_patch_review.get("reason", "review_reject")

    elif not changed_files:
        decision = "BLOCK"
        reason = "no_committable_change"

    elif tests_success:
        decision = "MERGE_READY"
        reason = "patch_valid_and_tests_passed"
        should_merge = True
        should_open_pr = True
        auto_merge_safe = True

    else:
        decision = "REVIEW_ONLY"
        reason = "patch_valid_but_tests_not_confirmed"
        should_merge = False
        should_open_pr = True
        auto_merge_safe = False

    result = {
        "decision": decision,
        "reason": reason,
        "should_merge": should_merge,
        "should_open_pr": should_open_pr,
        "auto_merge_safe": auto_merge_safe,
        "patch_applied": patch_applied,
        "patch_verifier_verdict": verifier_verdict,
        "post_patch_review_verdict": review_verdict,
        "targeted_tests_success": tests_success,
        "changed_files": changed_files,
        "target_file": patch_candidate.get("target_file", ""),
        "strategy": patch_candidate.get("strategy", ""),
    }

    write_json(AUDIT_OUT / "merge_controller_state.json", result)
    write_text(AUDIT_OUT / "merge_controller_report.md", build_report(result))

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()