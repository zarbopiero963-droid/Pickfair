#!/usr/bin/env python3

import json
import os
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


def is_test_python(path_str: str) -> bool:
    rel = normalize_path(path_str).lower()
    return rel.startswith("tests/") and rel.endswith(".py")


def is_generated_test(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith("tests/generated/")


def is_guardrail_test(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith("tests/guardrails/")


def detect_fix_type(candidate: dict) -> str:
    issue_type = str(candidate.get("issue_type", "")).strip()
    target_file = normalize_path(candidate.get("target_file", ""))

    if issue_type:
        return issue_type

    if is_runtime_python(target_file):
        return "runtime"
    if is_generated_test(target_file):
        return "generated_test"
    if is_test_python(target_file):
        return "test"
    return "unknown"


def determine_workflow_mode() -> str:
    event_name = os.environ.get("GITHUB_EVENT_NAME", "").strip().lower()
    if event_name == "pull_request":
        return "pr_validation"
    return "full_repair"


def build_report(state: dict) -> str:
    lines = []
    lines.append("Repair Orchestrator")
    lines.append("")
    lines.append(f"Workflow mode: {state.get('workflow_mode', '')}")
    lines.append(f"Git ref: {state.get('git_ref', '')}")
    lines.append(f"Repo fully green: {'YES' if state.get('repo_fully_green') else 'NO'}")
    lines.append(f"Repo materially greener: {'YES' if state.get('repo_materially_greener') else 'NO'}")
    lines.append(f"Continuation recommended: {'YES' if state.get('continuation_recommended') else 'NO'}")
    lines.append(f"Next action from repair loop: {state.get('next_action', '')}")
    lines.append(f"Patch applied: {'YES' if state.get('patch_applied') else 'NO'}")
    lines.append(f"Patch verifier verdict: {state.get('patch_verifier_verdict', '')}")
    lines.append(f"Post patch review verdict: {state.get('post_patch_review_verdict', '')}")
    lines.append(f"Patch reviewable: {'YES' if state.get('patch_reviewable') else 'NO'}")
    lines.append(f"Existing AI PR number: {state.get('existing_ai_pr_number') or 'none'}")
    lines.append(f"Existing AI PR state: {state.get('existing_ai_pr_state') or 'none'}")
    lines.append(f"Existing AI PR head: {state.get('existing_ai_pr_head') or 'none'}")
    lines.append(f"Orchestrator action: {state.get('action', '')}")
    lines.append(f"Reason: {state.get('reason', '')}")
    lines.append(f"Fix type: {state.get('fix_type', '')}")
    return "\n".join(lines)


def main() -> int:
    workflow_mode = determine_workflow_mode()
    git_ref = os.environ.get("GITHUB_REF", "").strip()

    loop_state = read_json(AUDIT_OUT / "ai_repair_loop_state.json")
    patch_apply = read_json(AUDIT_OUT / "patch_apply_report.json")
    patch_verification = read_json(AUDIT_OUT / "patch_verification.json")
    post_patch_review = read_json(AUDIT_OUT / "post_patch_review.json")
    patch_candidate_payload = read_json(AUDIT_OUT / "patch_candidate.json")
    merge_controller = read_json(AUDIT_OUT / "merge_controller_state.json")

    candidate = patch_candidate_payload.get("patch_candidate") or {}

    repo_fully_green = bool(loop_state.get("repo_fully_green", False))
    repo_materially_greener = bool(loop_state.get("repo_materially_greener", False))
    continuation_recommended = bool(loop_state.get("continuation_recommended", False))
    next_action = str(loop_state.get("next_action", "")).strip()
    final_status = str(loop_state.get("final_status", "")).strip()

    patch_applied = bool(patch_apply.get("applied", False))
    patch_verifier_verdict = str(patch_verification.get("verdict", "")).strip().lower() or "unknown"
    post_patch_review_verdict = (
        str(post_patch_review.get("review_verdict", "")).strip().lower()
        or str(post_patch_review.get("final_verdict", "")).strip().lower()
        or "unknown"
    )

    patch_reviewable = bool(
        patch_applied
        and patch_verifier_verdict in {"approve", "weak-approve", "review"}
        and post_patch_review_verdict in {"approve", "weak-approve", "review"}
    )

    existing_ai_pr_number = os.environ.get("EXISTING_AI_PR_NUMBER", "").strip()
    existing_ai_pr_state = os.environ.get("EXISTING_AI_PR_STATE", "").strip().lower()
    existing_ai_pr_head = os.environ.get("EXISTING_AI_PR_HEAD", "").strip()

    fix_type = detect_fix_type(candidate)

    action = "stop"
    reason = "unknown"

    if workflow_mode == "pr_validation":
        action = "validate_existing_pr_only"
        reason = "pull_request_context"

    elif repo_fully_green or next_action == "repository_green_stop":
        action = "stop_green"
        reason = "repository_fully_green"

    elif not patch_applied:
        action = "repair_attempt_no_pr"
        if final_status == "patch_apply_failed":
            reason = "patch_apply_failed"
        else:
            reason = "patch_not_applied"

    elif not patch_reviewable:
        action = "repair_attempt_no_pr"
        if post_patch_review_verdict == "reject" or patch_verifier_verdict == "reject":
            reason = "patch_not_reviewable"
        elif final_status == "no_progress":
            reason = "no_progress"
        else:
            reason = "review_not_sufficient"

    elif existing_ai_pr_number and existing_ai_pr_state == "open":
        action = "update_existing_ai_pr"
        reason = "existing_ai_pr_open"

    elif repo_materially_greener or continuation_recommended:
        action = "open_ai_pr"
        reason = "reviewable_repair_available"

    elif next_action == "manual_intervention_needed" or final_status in {
        "no_progress",
        "post_patch_review_reject",
        "patch_generation_failed",
        "patch_verifier_failed",
        "patch_apply_failed",
        "refresh_failed",
        "setup_failed",
        "post_patch_review_failed",
    }:
        action = "repair_attempt_no_pr"
        reason = "manual_intervention_needed"

    else:
        decision = str(merge_controller.get("decision", "")).strip().upper()
        merge_reason = str(merge_controller.get("reason", "")).strip()
        if decision == "REVIEW_ONLY":
            action = "open_ai_pr"
            reason = merge_reason or "reviewable_patch"
        elif decision == "MERGE_READY":
            action = "open_ai_pr"
            reason = merge_reason or "merge_ready_patch"
        else:
            action = "repair_attempt_no_pr"
            reason = merge_reason or "no_pr_condition_met"

    state = {
        "workflow_mode": workflow_mode,
        "git_ref": git_ref,
        "repo_fully_green": repo_fully_green,
        "repo_materially_greener": repo_materially_greener,
        "continuation_recommended": continuation_recommended,
        "next_action": next_action,
        "final_status": final_status,
        "patch_applied": patch_applied,
        "patch_verifier_verdict": patch_verifier_verdict,
        "post_patch_review_verdict": post_patch_review_verdict,
        "patch_reviewable": patch_reviewable,
        "existing_ai_pr_number": existing_ai_pr_number,
        "existing_ai_pr_state": existing_ai_pr_state,
        "existing_ai_pr_head": existing_ai_pr_head,
        "action": action,
        "reason": reason,
        "fix_type": fix_type,
    }

    write_json(AUDIT_OUT / "repair_orchestrator_state.json", state)
    write_text(AUDIT_OUT / "repair_orchestrator_report.md", build_report(state))

    print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())