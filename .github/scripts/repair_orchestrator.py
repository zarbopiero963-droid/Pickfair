#!/usr/bin/env python3

import json
import os
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"

ACTIVE_AI_BRANCH = "ai-repair/current"


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


def getenv_bool(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def decide() -> dict:
    event_name = os.getenv("GITHUB_EVENT_NAME", "").strip()
    ref = os.getenv("GITHUB_REF", "").strip()

    ai_loop = read_json(AUDIT_OUT / "ai_repair_loop_state.json")
    patch_verification = read_json(AUDIT_OUT / "patch_verification.json")
    post_patch_review = read_json(AUDIT_OUT / "post_patch_review.json")
    patch_apply_report = read_json(AUDIT_OUT / "patch_apply_report.json")
    merge_summary = read_text(AUDIT_OUT / "merge_summary.md").strip()

    repo_fully_green = bool(ai_loop.get("repo_fully_green", False))
    repo_materially_greener = bool(ai_loop.get("repo_materially_greener", False))
    continuation_recommended = bool(ai_loop.get("continuation_recommended", False))
    next_action = str(ai_loop.get("next_action", "")).strip() or "unknown"

    verifier_verdict = str(patch_verification.get("verdict", "")).strip().lower()
    review_verdict = str(post_patch_review.get("final_verdict", "")).strip().lower()
    applied = bool(patch_apply_report.get("applied", False))

    existing_ai_pr_number = os.getenv("EXISTING_AI_PR_NUMBER", "").strip()
    existing_ai_pr_state = os.getenv("EXISTING_AI_PR_STATE", "").strip().lower()
    existing_ai_pr_head = os.getenv("EXISTING_AI_PR_HEAD", "").strip()

    workflow_mode = "pr_validation" if event_name == "pull_request" else "full_repair"

    reviewable = (
        applied
        and verifier_verdict in {"approve", "weak-approve", "review"}
        and review_verdict in {"approve", "review"}
    )

    action = "noop"
    reason = "unknown"

    should_run_repair = workflow_mode == "full_repair" and ref == "refs/heads/main"
    should_create_or_update_pr = False
    should_skip_new_pr_because_existing_open = False
    should_stop_repository_green = False

    if workflow_mode == "pull_request":
        action = "validate_existing_pr_only"
        reason = "pull_request_event"
    elif repo_fully_green:
        action = "stop_green"
        reason = "repository_fully_green"
        should_stop_repository_green = True
    elif existing_ai_pr_number and existing_ai_pr_state == "open":
        action = "update_existing_ai_pr"
        reason = "existing_ai_pr_open"
        should_skip_new_pr_because_existing_open = True
        should_create_or_update_pr = reviewable
    elif reviewable:
        action = "create_ai_pr"
        reason = "reviewable_patch_available"
        should_create_or_update_pr = True
    elif should_run_repair:
        action = "repair_attempt_no_pr"
        reason = "patch_not_reviewable"
    else:
        action = "noop"
        reason = "unsupported_context"

    summary_lines = [
        "Repair Orchestrator",
        "",
        f"Workflow mode: {workflow_mode}",
        f"Git ref: {ref or 'unknown'}",
        f"Repo fully green: {'YES' if repo_fully_green else 'NO'}",
        f"Repo materially greener: {'YES' if repo_materially_greener else 'NO'}",
        f"Continuation recommended: {'YES' if continuation_recommended else 'NO'}",
        f"Next action from repair loop: {next_action}",
        f"Patch applied: {'YES' if applied else 'NO'}",
        f"Patch verifier verdict: {verifier_verdict or 'unknown'}",
        f"Post patch review verdict: {review_verdict or 'unknown'}",
        f"Patch reviewable: {'YES' if reviewable else 'NO'}",
        f"Existing AI PR number: {existing_ai_pr_number or 'none'}",
        f"Existing AI PR state: {existing_ai_pr_state or 'none'}",
        f"Existing AI PR head: {existing_ai_pr_head or 'none'}",
        "",
        f"Orchestrator action: {action}",
        f"Reason: {reason}",
    ]

    if merge_summary:
        summary_lines.extend([
            "",
            "Merge summary present: YES",
        ])

    state = {
        "workflow_mode": workflow_mode,
        "action": action,
        "reason": reason,
        "active_ai_branch": ACTIVE_AI_BRANCH,
        "reviewable": reviewable,
        "repo_fully_green": repo_fully_green,
        "repo_materially_greener": repo_materially_greener,
        "continuation_recommended": continuation_recommended,
        "next_action": next_action,
        "should_run_repair": should_run_repair,
        "should_create_or_update_pr": should_create_or_update_pr,
        "should_skip_new_pr_because_existing_open": should_skip_new_pr_because_existing_open,
        "should_stop_repository_green": should_stop_repository_green,
        "existing_ai_pr_number": existing_ai_pr_number,
        "existing_ai_pr_state": existing_ai_pr_state,
        "existing_ai_pr_head": existing_ai_pr_head,
        "patch_applied": applied,
        "patch_verifier_verdict": verifier_verdict,
        "post_patch_review_verdict": review_verdict,
    }

    write_json(AUDIT_OUT / "repair_orchestrator_state.json", state)
    write_text(AUDIT_OUT / "repair_orchestrator_report.md", "\n".join(summary_lines))

    return state


def main() -> int:
    state = decide()
    print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())