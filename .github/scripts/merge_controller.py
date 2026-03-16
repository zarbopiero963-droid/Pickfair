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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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


def is_runtime_python(path_str: str) -> bool:
    rel = normalize_path(path_str).lower()
    return rel.endswith(".py") and not rel.startswith("tests/") and not rel.startswith(".github/")


def is_generated_test(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith("tests/generated/")


def is_guardrail_test(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith("tests/guardrails/")


def is_human_only_target(target_file: str, classification: str) -> bool:
    target_file = normalize_path(target_file).lower()
    classification = str(classification or "").strip()

    if classification == "HUMAN_ONLY":
        return True
    if target_file.startswith(".github/scripts/"):
        return True
    if target_file.startswith("tests/") and "hft" in target_file:
        return True

    return False


def get_last_cycle(loop_state: dict) -> dict:
    cycles = loop_state.get("cycles", []) or []
    if not cycles:
        return {}
    return cycles[-1]


def has_real_committable_change(loop_state: dict, apply_report: dict) -> bool:
    if not bool(apply_report.get("applied", False)):
        return False

    last = get_last_cycle(loop_state)
    if not last:
        return False

    if bool(last.get("rollback", False)):
        return False
    if not bool(last.get("improvement", False)):
        return False

    return True


def build_report(state: dict) -> str:
    lines = []
    lines.append("Merge Controller")
    lines.append("")
    lines.append(f"Decision: {state.get('decision', '')}")
    lines.append(f"Reason: {state.get('reason', '')}")
    lines.append("")
    lines.append(f"Should merge: {'YES' if state.get('should_merge') else 'NO'}")
    lines.append(f"Should wait existing PR: {'YES' if state.get('should_wait_existing_pr') else 'NO'}")
    lines.append(f"Should open or update PR: {'YES' if state.get('should_open_or_update_pr') else 'NO'}")
    lines.append("")
    lines.append(f"Applied: {'YES' if state.get('applied') else 'NO'}")
    lines.append(f"Real committable change: {'YES' if state.get('real_committable_change') else 'NO'}")
    lines.append(f"Verifier verdict: {state.get('verifier_verdict', '')}")
    lines.append(f"Post patch review verdict: {state.get('review_verdict', '')}")
    lines.append(f"Reviewable: {'YES' if state.get('reviewable') else 'NO'}")
    lines.append(f"Auto merge safe: {'YES' if state.get('auto_merge_safe') else 'NO'}")
    lines.append("")
    lines.append(f"Contract restored: {'YES' if state.get('contract_restored') else 'NO'}")
    lines.append(f"Minimal change: {'YES' if state.get('minimal_change') else 'NO'}")
    lines.append(f"Logic preserved: {'YES' if state.get('logic_preserved') else 'NO'}")
    lines.append(f"Verifier consistent: {'YES' if state.get('verifier_consistent') else 'NO'}")
    lines.append("")
    lines.append(f"Repo materially greener: {'YES' if state.get('repo_materially_greener') else 'NO'}")
    lines.append(f"Repo fully green: {'YES' if state.get('repo_fully_green') else 'NO'}")
    lines.append(f"Continuation recommended: {'YES' if state.get('continuation_recommended') else 'NO'}")
    lines.append(f"Loop next action: {state.get('loop_next_action', '')}")
    lines.append(f"Orchestrator action: {state.get('orchestrator_action', '')}")
    lines.append("")
    lines.append(f"Existing AI PR number: {state.get('existing_ai_pr_number') or 'none'}")
    lines.append(f"Existing AI PR state: {state.get('existing_ai_pr_state') or 'none'}")
    lines.append(f"Fix type: {state.get('fix_type', '')}")
    lines.append("")
    lines.append("Touched files")
    touched_files = state.get("touched_files", []) or []
    if touched_files:
        for file in touched_files:
            lines.append(f"- {file}")
    else:
        lines.append("- Nessun file toccato.")
    return "\n".join(lines)


def main() -> int:
    patch_candidate_payload = read_json(AUDIT_OUT / "patch_candidate.json")
    patch_verification = read_json(AUDIT_OUT / "patch_verification.json")
    post_patch_review = read_json(AUDIT_OUT / "post_patch_review.json")
    patch_apply_report = read_json(AUDIT_OUT / "patch_apply_report.json")
    issue_classification = read_json(AUDIT_OUT / "issue_classification.json")
    repair_loop_state = read_json(AUDIT_OUT / "ai_repair_loop_state.json")
    repair_orchestrator_state = read_json(AUDIT_OUT / "repair_orchestrator_state.json")
    targeted_tests = read_json(AUDIT_OUT / "targeted_test_results.json")

    candidate = patch_candidate_payload.get("patch_candidate") or {}
    if not isinstance(candidate, dict):
        candidate = {}

    target_file = normalize_path(candidate.get("target_file", ""))
    classification = str(candidate.get("classification", "")).strip()
    issue_type = str(candidate.get("issue_type", "")).strip()

    verifier_verdict = str(patch_verification.get("verdict", "")).strip().lower() or "unknown"
    review_verdict = str(post_patch_review.get("review_verdict", "")).strip().lower()
    if not review_verdict:
        review_verdict = str(post_patch_review.get("final_verdict", "")).strip().lower() or "unknown"

    applied = bool(patch_apply_report.get("applied", False))
    contract_restored = bool(post_patch_review.get("contract_restored", False))
    minimal_change = bool(post_patch_review.get("minimal_change", False))
    logic_preserved = bool(post_patch_review.get("logic_preserved", False))

    repo_materially_greener = bool(repair_loop_state.get("repo_materially_greener", False))
    repo_fully_green = bool(repair_loop_state.get("repo_fully_green", False))
    continuation_recommended = bool(repair_loop_state.get("continuation_recommended", False))
    loop_next_action = str(repair_loop_state.get("next_action", "")).strip()

    orchestrator_action = str(repair_orchestrator_state.get("action", "")).strip()
    existing_ai_pr_number = str(repair_orchestrator_state.get("existing_ai_pr_number", "")).strip()
    existing_ai_pr_state = str(repair_orchestrator_state.get("existing_ai_pr_state", "")).strip()
    fix_type = str(repair_orchestrator_state.get("fix_type", "")).strip() or issue_type

    touched_files = patch_apply_report.get("applied_targets", []) or patch_apply_report.get("target_files", []) or []
    touched_files = [normalize_path(x) for x in touched_files if normalize_path(x)]
    if not touched_files and target_file:
        touched_files = [target_file]

    real_committable_change = has_real_committable_change(repair_loop_state, patch_apply_report)
    human_only_target = is_human_only_target(target_file, classification)

    verifier_consistent = True
    if verifier_verdict == "reject" and review_verdict in {"approve", "weak-approve"}:
        verifier_consistent = False
    if verifier_verdict in {"approve", "weak-approve"} and review_verdict == "reject":
        verifier_consistent = False

    executed_count = int((targeted_tests.get("summary", {}) or {}).get("executed_count", 0) or 0)
    failure_count = targeted_tests.get("failure_count")
    if not isinstance(failure_count, int):
        failure_count = None

    reviewable = False
    auto_merge_safe = False
    decision = "BLOCK"
    reason = "block"
    should_merge = False
    should_wait_existing_pr = False
    should_open_or_update_pr = False

    if repo_fully_green or orchestrator_action == "stop_green" or loop_next_action == "repository_green_stop":
        decision = "BLOCK"
        reason = "repository_fully_green"

    elif human_only_target:
        decision = "BLOCK"
        reason = "human_only_target"

    elif not real_committable_change:
        decision = "BLOCK"
        if not applied:
            reason = "patch_not_applied"
        else:
            last_cycle = get_last_cycle(repair_loop_state)
            if bool(last_cycle.get("rollback", False)):
                reason = "rolled_back_no_committable_change"
            elif not bool(last_cycle.get("improvement", False)):
                reason = "no_real_committable_change"
            else:
                reason = "no_real_committable_change"

    elif verifier_verdict == "reject" and review_verdict == "reject":
        decision = "BLOCK"
        reason = "patch_not_reviewable"

    elif verifier_verdict == "approve" and review_verdict == "approve":
        decision = "MERGE_READY"
        reason = "approved_patch"
        reviewable = True
        auto_merge_safe = bool(
            applied
            and real_committable_change
            and minimal_change
            and logic_preserved
            and verifier_consistent
            and not is_guardrail_test(target_file)
            and (failure_count in (0, None))
        )
        should_merge = auto_merge_safe
        should_open_or_update_pr = True

    elif verifier_verdict in {"approve", "weak-approve", "review"} and review_verdict in {"approve", "weak-approve", "review"}:
        decision = "REVIEW_ONLY"
        reason = "reviewable_patch"
        reviewable = True
        auto_merge_safe = False
        should_merge = False
        should_open_or_update_pr = True

        if is_runtime_python(target_file) and issue_type in {"runtime_failure", "lint_failure"}:
            if executed_count == 0 and minimal_change and logic_preserved:
                reason = "reviewable_runtime_patch"
            elif failure_count == 0 and executed_count > 0:
                reason = "reviewable_runtime_patch_with_green_tests"

    elif existing_ai_pr_number and orchestrator_action == "update_existing_ai_pr":
        if real_committable_change and verifier_verdict in {"approve", "weak-approve", "review"} and review_verdict in {"approve", "weak-approve", "review"}:
            decision = "REVIEW_ONLY"
            reason = "update_existing_ai_pr"
            reviewable = True
            should_open_or_update_pr = True
        else:
            decision = "BLOCK"
            reason = "existing_pr_but_patch_not_committable"

    else:
        decision = "BLOCK"
        if verifier_verdict == "reject" or review_verdict == "reject":
            reason = "patch_not_reviewable"
        elif not verifier_consistent:
            reason = "verifier_inconsistent"
        elif not repo_materially_greener and loop_next_action == "manual_intervention_needed":
            reason = "no_real_improvement"
        else:
            reason = "block"

    state = {
        "decision": decision,
        "reason": reason,
        "should_merge": should_merge,
        "should_wait_existing_pr": should_wait_existing_pr,
        "should_open_or_update_pr": should_open_or_update_pr,
        "reviewable": reviewable,
        "auto_merge_safe": auto_merge_safe,
        "applied": applied,
        "real_committable_change": real_committable_change,
        "verifier_verdict": verifier_verdict,
        "review_verdict": review_verdict,
        "contract_restored": contract_restored,
        "minimal_change": minimal_change,
        "logic_preserved": logic_preserved,
        "verifier_consistent": verifier_consistent,
        "repo_materially_greener": repo_materially_greener,
        "repo_fully_green": repo_fully_green,
        "continuation_recommended": continuation_recommended,
        "loop_next_action": loop_next_action,
        "orchestrator_action": orchestrator_action,
        "existing_ai_pr_number": existing_ai_pr_number,
        "existing_ai_pr_state": existing_ai_pr_state,
        "fix_type": fix_type,
        "touched_files": touched_files,
        "primary_target": target_file,
        "primary_classification": classification,
    }

    report = build_report(state)

    write_json(AUDIT_OUT / "merge_controller_state.json", state)
    write_json(AUDIT_OUT / "merge_decision.json", state)
    write_text(AUDIT_OUT / "merge_controller_report.md", report)

    print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())