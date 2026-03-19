#!/usr/bin/env python3

import json
import subprocess
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"
MAX_PASSES = 3


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


def run_script(script_rel: str) -> tuple[bool, str]:
    result = subprocess.run(
        ["python", script_rel],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    return result.returncode == 0, output


def normalize_path(path_str: str) -> str:
    raw = str(path_str or "").strip().replace("\\", "/")
    if not raw:
        return ""
    while raw.startswith("./"):
        raw = raw[2:]
    return raw


def load_candidate() -> dict:
    payload = read_json(AUDIT_OUT / "patch_candidate.json")
    candidate = payload.get("patch_candidate") or {}
    return candidate if isinstance(candidate, dict) else {}


def load_apply() -> dict:
    return read_json(AUDIT_OUT / "patch_apply_report.json")


def load_verify() -> dict:
    return read_json(AUDIT_OUT / "patch_verification.json")


def load_review() -> dict:
    return read_json(AUDIT_OUT / "post_patch_review.json")


def load_merge() -> dict:
    return read_json(AUDIT_OUT / "merge_controller_state.json")


def load_ci_context() -> dict:
    data = read_json(AUDIT_OUT / "ci_failure_context.json")
    if not data:
        data = read_json(AUDIT_OUT / "ci_failures.json")
    return data


def count_ci_failures() -> int:
    return len(load_ci_context().get("ci_failures") or [])


def patch_summary() -> dict:
    candidate = load_candidate()
    apply_report = load_apply()
    verify = load_verify()
    review = load_review()
    merge = load_merge()

    return {
        "target_file": normalize_path(candidate.get("target_file", "")),
        "issue_type": str(candidate.get("issue_type", "")).strip(),
        "strategy": str(candidate.get("strategy", "")).strip(),
        "classification": str(candidate.get("classification", "")).strip(),
        "applied": bool(apply_report.get("applied", False)),
        "apply_reason": str(apply_report.get("reason", "")).strip(),
        "changed_files": [normalize_path(x) for x in (apply_report.get("applied_targets", []) or []) if normalize_path(x)],
        "verify_verdict": str(verify.get("verdict", "")).strip().lower(),
        "review_verdict": str(review.get("review_verdict", review.get("final_verdict", ""))).strip().lower(),
        "merge_decision": str(merge.get("decision", "")).strip().upper(),
        "merge_reason": str(merge.get("reason", "")).strip(),
    }


def build_report(state: dict) -> str:
    lines = []
    lines.append("AI Repair Loop Report")
    lines.append("")
    lines.append(f"Final status: {state.get('final_status', '')}")
    lines.append(f"Passes executed: {state.get('passes_executed', 0)} / {state.get('max_passes', 0)}")
    lines.append(f"Real progress: {'YES' if state.get('real_progress') else 'NO'}")
    lines.append(f"Ready for PR: {'YES' if state.get('ready_for_pr') else 'NO'}")
    lines.append(f"Next action: {state.get('next_action', '')}")
    lines.append("")
    for item in state.get("passes", []) or []:
        lines.append(f"Pass {item.get('pass_no')}")
        lines.append(f"- target_file: {item.get('target_file', '')}")
        lines.append(f"- issue_type: {item.get('issue_type', '')}")
        lines.append(f"- strategy: {item.get('strategy', '')}")
        lines.append(f"- applied: {item.get('applied')}")
        lines.append(f"- apply_reason: {item.get('apply_reason', '')}")
        lines.append(f"- changed_files: {item.get('changed_files', [])}")
        lines.append(f"- verify_verdict: {item.get('verify_verdict', '')}")
        lines.append(f"- review_verdict: {item.get('review_verdict', '')}")
        lines.append(f"- merge_decision: {item.get('merge_decision', '')}")
        lines.append(f"- merge_reason: {item.get('merge_reason', '')}")
        lines.append(f"- ci_before: {item.get('ci_before')}")
        lines.append(f"- ci_after: {item.get('ci_after')}")
        lines.append(f"- progress: {item.get('progress')}")
        lines.append(f"- stop_reason: {item.get('stop_reason', '')}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    passes = []
    attempted_targets = set()
    real_progress = False
    ready_for_pr = False
    final_status = "not_started"
    next_action = "manual_review"

    base_ci = count_ci_failures()

    for pass_no in range(1, MAX_PASSES + 1):
        ok, _ = run_script(".github/scripts/patch_candidate_generator.py")
        if not ok:
            final_status = "candidate_generation_failed"
            next_action = "manual_review"
            break

        candidate = load_candidate()
        target_file = normalize_path(candidate.get("target_file", ""))

        if not candidate or not target_file:
            final_status = "no_candidate"
            next_action = "manual_review"
            break

        if target_file in attempted_targets:
            final_status = "repeated_target_no_progress"
            next_action = "manual_review"
            break

        attempted_targets.add(target_file)
        ci_before = count_ci_failures()

        run_script(".github/scripts/apply_patch_candidate.py")
        run_script(".github/scripts/patch_verifier.py")
        run_script(".github/scripts/run_targeted_tests.py")
        run_script(".github/scripts/post_patch_review.py")
        run_script(".github/scripts/merge_controller.py")

        snap = patch_summary()
        ci_after = count_ci_failures()

        progress = False
        stop_reason = ""

        if snap["applied"] and snap["changed_files"]:
            progress = True

        if ci_after < ci_before:
            progress = True

        if snap["merge_decision"] in {"MERGE_READY", "REVIEW_ONLY"}:
            progress = True

        if progress:
            real_progress = True

        if snap["merge_decision"] == "MERGE_READY":
            ready_for_pr = True
            stop_reason = "merge_ready"
            final_status = "ready_for_pr"
            next_action = "open_pr"

        elif snap["merge_decision"] == "REVIEW_ONLY":
            ready_for_pr = True
            stop_reason = "review_only_but_pr_allowed"
            final_status = "review_only_ready_for_pr"
            next_action = "open_pr"

        elif not snap["applied"]:
            stop_reason = snap["apply_reason"] or "patch_not_applied"
            final_status = "no_progress"
            next_action = "manual_review"

        elif snap["verify_verdict"] == "reject":
            stop_reason = "verifier_reject"
            final_status = "no_progress"
            next_action = "manual_review"

        elif snap["review_verdict"] == "reject":
            stop_reason = "review_reject"
            final_status = "no_progress"
            next_action = "manual_review"

        else:
            stop_reason = "no_progress"
            final_status = "no_progress"
            next_action = "manual_review"

        passes.append(
            {
                "pass_no": pass_no,
                "target_file": snap["target_file"],
                "issue_type": snap["issue_type"],
                "strategy": snap["strategy"],
                "classification": snap["classification"],
                "applied": snap["applied"],
                "apply_reason": snap["apply_reason"],
                "changed_files": snap["changed_files"],
                "verify_verdict": snap["verify_verdict"],
                "review_verdict": snap["review_verdict"],
                "merge_decision": snap["merge_decision"],
                "merge_reason": snap["merge_reason"],
                "ci_before": ci_before,
                "ci_after": ci_after,
                "progress": progress,
                "stop_reason": stop_reason,
            }
        )

        if ready_for_pr:
            break

        if not progress:
            break

    state = {
        "final_status": final_status,
        "passes_executed": len(passes),
        "max_passes": MAX_PASSES,
        "real_progress": real_progress,
        "ready_for_pr": ready_for_pr,
        "next_action": next_action,
        "base_ci_failures": base_ci,
        "passes": passes,
    }

    write_json(AUDIT_OUT / "ai_repair_loop_state.json", state)
    write_text(AUDIT_OUT / "ai_repair_loop_report.md", build_report(state))
    print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())