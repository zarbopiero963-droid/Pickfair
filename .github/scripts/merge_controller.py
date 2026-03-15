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


def normalize_verdict(value: str) -> str:
    value = (value or "").strip().lower()
    if value in {"approve", "weak-approve", "review", "reject"}:
        return value
    return "unknown"


def normalize_review(value: str) -> str:
    value = (value or "").strip().lower()
    if value in {"approve", "review", "reject"}:
        return value
    return "unknown"


def collect_touched_files(cycles: list[dict]) -> list[str]:
    touched = []
    seen = set()

    for cycle in cycles or []:
        for item in cycle.get("target_files", []) or []:
            value = str(item).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            touched.append(value)

    return touched


def classify_fix_type(files: list[str]) -> str:
    if not files:
        return "unknown"

    has_tests = any(str(f).startswith("tests/") for f in files)
    has_modules = any(not str(f).startswith("tests/") for f in files)

    if has_tests and has_modules:
        return "module+test"
    if has_tests:
        return "test"
    if has_modules:
        return "module"
    return "unknown"


def decide_merge_action() -> dict:
    patch_verification = read_json(AUDIT_OUT / "patch_verification.json")
    post_patch_review = read_json(AUDIT_OUT / "post_patch_review.json")
    patch_apply_report = read_json(AUDIT_OUT / "patch_apply_report.json")
    ai_repair_loop_state = read_json(AUDIT_OUT / "ai_repair_loop_state.json")
    repair_orchestrator_state = read_json(AUDIT_OUT / "repair_orchestrator_state.json")

    verifier_verdict = normalize_verdict(patch_verification.get("verdict", ""))
    review_verdict = normalize_review(post_patch_review.get("final_verdict", ""))
    applied = bool(patch_apply_report.get("applied", False))

    contract_restored = bool(post_patch_review.get("contract_restored", False))
    minimal_change = bool(post_patch_review.get("minimal_change", False))
    logic_preserved = bool(post_patch_review.get("logic_preserved", False))
    verifier_consistent = bool(post_patch_review.get("verifier_consistent", False))

    repo_materially_greener = bool(ai_repair_loop_state.get("repo_materially_greener", False))
    repo_fully_green = bool(ai_repair_loop_state.get("repo_fully_green", False))
    continuation_recommended = bool(ai_repair_loop_state.get("continuation_recommended", False))
    loop_next_action = str(ai_repair_loop_state.get("next_action", "")).strip() or "unknown"

    orchestrator_action = str(repair_orchestrator_state.get("action", "")).strip() or "unknown"
    existing_ai_pr_number = str(repair_orchestrator_state.get("existing_ai_pr_number", "")).strip()
    existing_ai_pr_state = str(repair_orchestrator_state.get("existing_ai_pr_state", "")).strip().lower()

    cycles = ai_repair_loop_state.get("cycles", []) or []
    touched_files = collect_touched_files(cycles)
    fix_type = classify_fix_type(touched_files)

    reviewable = (
        applied
        and verifier_verdict in {"approve", "weak-approve", "review"}
        and review_verdict in {"approve", "review"}
    )

    auto_merge_safe = (
        applied
        and verifier_verdict == "approve"
        and review_verdict == "approve"
        and contract_restored
        and minimal_change
        and logic_preserved
        and verifier_consistent
        and fix_type in {"module", "test", "module+test"}
    )

    decision = "BLOCK"
    reason = "unknown"
    should_merge = False
    should_wait_existing_pr = False
    should_open_or_update_pr = False

    if repo_fully_green:
        decision = "NO_ACTION"
        reason = "repository_fully_green"
    elif existing_ai_pr_number and existing_ai_pr_state == "open" and orchestrator_action == "update_existing_ai_pr":
        decision = "WAIT_EXISTING_PR"
        reason = "existing_ai_pr_open"
        should_wait_existing_pr = True
    elif auto_merge_safe:
        decision = "MERGE_READY"
        reason = "safe_auto_merge_candidate"
        should_merge = True
        should_open_or_update_pr = True
    elif reviewable:
        decision = "REVIEW_ONLY"
        reason = "patch_reviewable_but_not_auto_merge_safe"
        should_open_or_update_pr = True
    elif orchestrator_action == "repair_attempt_no_pr":
        decision = "BLOCK"
        reason = "patch_not_reviewable"
    else:
        decision = "BLOCK"
        reason = "insufficient_evidence"

    result = {
        "decision": decision,
        "reason": reason,
        "should_merge": should_merge,
        "should_wait_existing_pr": should_wait_existing_pr,
        "should_open_or_update_pr": should_open_or_update_pr,
        "reviewable": reviewable,
        "auto_merge_safe": auto_merge_safe,
        "applied": applied,
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
    }

    return result


def render_report(data: dict) -> str:
    lines = []
    lines.append("Merge Controller")
    lines.append("")
    lines.append(f"Decision: {data.get('decision', 'unknown')}")
    lines.append(f"Reason: {data.get('reason', 'unknown')}")
    lines.append("")
    lines.append(f"Should merge: {'YES' if data.get('should_merge') else 'NO'}")
    lines.append(f"Should wait existing PR: {'YES' if data.get('should_wait_existing_pr') else 'NO'}")
    lines.append(f"Should open or update PR: {'YES' if data.get('should_open_or_update_pr') else 'NO'}")
    lines.append("")
    lines.append(f"Applied: {'YES' if data.get('applied') else 'NO'}")
    lines.append(f"Verifier verdict: {data.get('verifier_verdict', 'unknown')}")
    lines.append(f"Post patch review verdict: {data.get('review_verdict', 'unknown')}")
    lines.append(f"Reviewable: {'YES' if data.get('reviewable') else 'NO'}")
    lines.append(f"Auto merge safe: {'YES' if data.get('auto_merge_safe') else 'NO'}")
    lines.append("")
    lines.append(f"Contract restored: {'YES' if data.get('contract_restored') else 'NO'}")
    lines.append(f"Minimal change: {'YES' if data.get('minimal_change') else 'NO'}")
    lines.append(f"Logic preserved: {'YES' if data.get('logic_preserved') else 'NO'}")
    lines.append(f"Verifier consistent: {'YES' if data.get('verifier_consistent') else 'NO'}")
    lines.append("")
    lines.append(f"Repo materially greener: {'YES' if data.get('repo_materially_greener') else 'NO'}")
    lines.append(f"Repo fully green: {'YES' if data.get('repo_fully_green') else 'NO'}")
    lines.append(f"Continuation recommended: {'YES' if data.get('continuation_recommended') else 'NO'}")
    lines.append(f"Loop next action: {data.get('loop_next_action', 'unknown')}")
    lines.append(f"Orchestrator action: {data.get('orchestrator_action', 'unknown')}")
    lines.append("")
    lines.append(f"Existing AI PR number: {data.get('existing_ai_pr_number', 'none') or 'none'}")
    lines.append(f"Existing AI PR state: {data.get('existing_ai_pr_state', 'none') or 'none'}")
    lines.append(f"Fix type: {data.get('fix_type', 'unknown')}")
    lines.append("")
    lines.append("Touched files")
    files = data.get("touched_files", []) or []
    if files:
        for item in files:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessun file toccato.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    result = decide_merge_action()
    write_json(AUDIT_OUT / "merge_controller_state.json", result)
    write_text(AUDIT_OUT / "merge_controller_report.md", render_report(result))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())