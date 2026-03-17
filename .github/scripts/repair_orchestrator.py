#!/usr/bin/env python3

import json
import os
from pathlib import Path

AUDIT_OUT = Path("audit_out")


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


def build_report(data: dict) -> str:
    lines = []
    lines.append("Repair Orchestrator")
    lines.append("")
    lines.append(f"Action: {data.get('action', '')}")
    lines.append(f"Reason: {data.get('reason', '')}")
    lines.append("")
    lines.append(f"Ready for PR: {'YES' if data.get('ready_for_pr') else 'NO'}")
    lines.append(f"Real progress: {'YES' if data.get('real_progress') else 'NO'}")
    lines.append(f"Loop final status: {data.get('loop_final_status', '')}")
    lines.append("")
    lines.append(f"Existing AI PR number: {data.get('existing_ai_pr_number', '') or 'none'}")
    lines.append(f"Existing AI PR state: {data.get('existing_ai_pr_state', '') or 'none'}")
    lines.append("")
    lines.append("Touched files")
    touched = data.get("touched_files", []) or []
    if touched:
        for item in touched:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def main() -> int:
    loop_state = read_json(AUDIT_OUT / "ai_repair_loop_state.json")
    merge_state = read_json(AUDIT_OUT / "merge_controller_state.json")
    patch_apply = read_json(AUDIT_OUT / "patch_apply_report.json")

    existing_ai_pr_number = os.environ.get("EXISTING_AI_PR_NUMBER", "").strip()
    existing_ai_pr_state = os.environ.get("EXISTING_AI_PR_STATE", "").strip()
    existing_ai_pr_head = os.environ.get("EXISTING_AI_PR_HEAD", "").strip()

    ready_for_pr = bool(loop_state.get("ready_for_pr", False))
    real_progress = bool(loop_state.get("real_progress", False))
    loop_final_status = str(loop_state.get("final_status", "")).strip()

    touched_files = patch_apply.get("applied_targets", []) or []
    merge_decision = str(merge_state.get("decision", "")).strip().upper()

    action = "manual_review"
    reason = "default_manual_review"

    if ready_for_pr and merge_decision in {"MERGE_READY", "REVIEW_ONLY"}:
        if existing_ai_pr_number and existing_ai_pr_state.lower() == "open":
            action = "update_existing_ai_pr"
            reason = "progress_ready_existing_pr_open"
        else:
            action = "open_new_ai_pr"
            reason = "progress_ready_no_open_pr"

    elif real_progress and loop_final_status in {"partial_progress", "review_only_ready_for_pr"}:
        action = "open_new_ai_pr"
        reason = "real_progress_review_only"

    elif real_progress:
        action = "repair_attempt_no_pr"
        reason = "progress_detected_but_not_pr_ready"

    elif loop_final_status in {"no_progress", "candidate_generation_failed", "no_candidate", "repeated_target_no_progress"}:
        action = "manual_review"
        reason = loop_final_status or "no_progress"

    result = {
        "action": action,
        "reason": reason,
        "ready_for_pr": ready_for_pr,
        "real_progress": real_progress,
        "loop_final_status": loop_final_status,
        "existing_ai_pr_number": existing_ai_pr_number,
        "existing_ai_pr_state": existing_ai_pr_state,
        "existing_ai_pr_head": existing_ai_pr_head,
        "touched_files": touched_files,
    }

    write_json(AUDIT_OUT / "repair_orchestrator_state.json", result)
    write_text(AUDIT_OUT / "repair_orchestrator_report.md", build_report(result))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())