#!/usr/bin/env python3

import json
import subprocess
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"

MAX_REPAIR_CYCLES = 4


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


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_script(script: str) -> bool:
    print("")
    print("=" * 80)
    print(f"RUNNING {script}")
    print("=" * 80)

    result = subprocess.run(
        ["python", script],
        cwd=ROOT,
        capture_output=False,
        text=True,
    )

    return result.returncode == 0


def git_commit() -> str:
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return (r.stdout or "").strip()


def git_restore(commit: str):
    subprocess.run(
        ["git", "reset", "--hard", commit],
        cwd=ROOT,
    )


def count_p0() -> int:
    fix_context = read_json(AUDIT_OUT / "fix_context.json")
    items = fix_context.get("fix_contexts", [])
    return len([x for x in items if x.get("priority") == "P0"])


def failing_tests() -> int:
    data = read_json(AUDIT_OUT / "failing_tests.json")
    return len(data.get("failing_tests", []))


def targeted_failures():
    data = read_json(AUDIT_OUT / "targeted_test_results.json")
    v = data.get("failure_count")
    if isinstance(v, int):
        return v
    return None


def patch_verifier_verdict() -> str:
    data = read_json(AUDIT_OUT / "patch_verification.json")
    return str(data.get("verdict", "")).strip().lower()


def post_patch_review_verdict() -> str:
    data = read_json(AUDIT_OUT / "post_patch_review.json")
    return str(data.get("final_verdict", "")).strip().lower()


def patch_applied() -> bool:
    data = read_json(AUDIT_OUT / "patch_apply_report.json")
    return bool(data.get("applied", False))


def patch_target_files() -> list[str]:
    data = read_json(AUDIT_OUT / "patch_candidate.json")
    files = data.get("target_files", [])
    if isinstance(files, list):
        return [str(x).strip() for x in files if str(x).strip()]
    return []


def contract_restored_flags() -> dict:
    data = read_json(AUDIT_OUT / "post_patch_review.json")
    return {
        "contract_restored": bool(data.get("contract_restored", False)),
        "minimal_change": bool(data.get("minimal_change", False)),
        "logic_preserved": bool(data.get("logic_preserved", False)),
    }


def detect_improvement(
    *,
    p0_before,
    p0_after,
    fail_before,
    fail_after,
    target_before,
    target_after,
    verifier_verdict,
    review_verdict,
    applied,
    contract_restored,
    minimal_change,
    logic_preserved,
    target_files,
):
    reasons = []

    if isinstance(target_before, int) and isinstance(target_after, int):
        if target_after < target_before:
            reasons.append(f"Targeted failures reduced from {target_before} to {target_after}.")
        elif target_after > target_before:
            return False, f"Targeted failures worsened from {target_before} to {target_after}."

    if isinstance(fail_before, int) and isinstance(fail_after, int):
        if fail_after < fail_before:
            reasons.append(f"Failing tests reduced from {fail_before} to {fail_after}.")
        elif fail_after > fail_before:
            return False, f"Failing tests worsened from {fail_before} to {fail_after}."

    if isinstance(p0_before, int) and isinstance(p0_after, int):
        if p0_after < p0_before:
            reasons.append(f"P0 reduced from {p0_before} to {p0_after}.")
        elif p0_after > p0_before:
            return False, f"P0 worsened from {p0_before} to {p0_after}."

    contract_like_files = {
        "auto_updater.py",
        "executor_manager.py",
        "tests/fixtures/system_payloads.py",
    }

    touched_contract_files = any(f in contract_like_files for f in (target_files or []))

    if (
        applied
        and verifier_verdict in {"approve", "weak-approve"}
        and review_verdict != "reject"
        and contract_restored
        and minimal_change
        and logic_preserved
        and touched_contract_files
    ):
        reasons.append(
            "Contract restoration detected on key public API files with applied patch, acceptable verifier result, and no reject."
        )

    if reasons:
        return True, " | ".join(reasons)

    return False, "No measurable improvement detected."


def refresh_after_apply() -> bool:
    scripts = [
        ".github/scripts/run_targeted_tests.py",
        ".github/scripts/repo_ultra_audit_narrative.py",
        ".github/scripts/extract_failing_tests.py",
        ".github/scripts/build_test_failure_context.py",
        ".github/scripts/build_fix_context.py",
        ".github/scripts/workflow_signal_aggregator.py",
    ]

    for s in scripts:
        if not run_script(s):
            return False

    return True


def compute_repo_fully_green(cycles: list[dict]) -> bool:
    if not cycles:
        return False

    last = cycles[-1]
    p0_after = last.get("p0_after")
    fail_after = last.get("fail_after")
    target_after = last.get("target_after")

    if isinstance(p0_after, int) and isinstance(fail_after, int):
        if p0_after == 0 and fail_after == 0:
            return True

    if isinstance(target_after, int) and isinstance(p0_after, int):
        if target_after == 0 and p0_after == 0:
            return True

    return False


def compute_next_action(final_status: str, greener: bool, fully_green: bool) -> str:
    if fully_green:
        return "repository_green_stop"
    if greener:
        return "merge_current_pr_then_auto_rerun_on_main"
    if final_status in {
        "no_progress",
        "post_patch_review_reject",
        "patch_generation_failed",
        "patch_verifier_failed",
        "patch_apply_failed",
    }:
        return "manual_intervention_needed"
    return "inspect_latest_run"


def build_report(cycles: list[dict], final_status: str, greener: bool, fully_green: bool) -> str:
    continuation_recommended = greener and not fully_green
    next_action = compute_next_action(final_status, greener, fully_green)

    lines = []
    lines.append("AI Repair Loop Report")
    lines.append("")
    lines.append(f"Final status: {final_status}")
    lines.append(f"Max cycles: {MAX_REPAIR_CYCLES}")
    lines.append(f"Repo materially greener: {'YES' if greener else 'NO'}")
    lines.append(f"Repo fully green: {'YES' if fully_green else 'NO'}")
    lines.append(f"Continuation recommended: {'YES' if continuation_recommended else 'NO'}")
    lines.append(f"Next action: {next_action}")
    lines.append("")

    for c in cycles:
        lines.append(f"Cycle {c['cycle']}")
        lines.append(f"- base_commit: {c['base_commit']}")
        lines.append(f"- p0_before: {c['p0_before']}")
        lines.append(f"- p0_after: {c['p0_after']}")
        lines.append(f"- failing_tests_before: {c['fail_before']}")
        lines.append(f"- failing_tests_after: {c['fail_after']}")
        lines.append(f"- targeted_before: {c['target_before']}")
        lines.append(f"- targeted_after: {c['target_after']}")
        lines.append(f"- patch_verifier_verdict: {c.get('patch_verifier_verdict', '')}")
        lines.append(f"- post_patch_review_verdict: {c.get('post_patch_review_verdict', '')}")
        lines.append(f"- contract_restored: {c.get('contract_restored')}")
        lines.append(f"- minimal_change: {c.get('minimal_change')}")
        lines.append(f"- logic_preserved: {c.get('logic_preserved')}")
        lines.append(f"- improvement: {c['improvement']}")
        lines.append(f"- improvement_reason: {c.get('improvement_reason', '')}")
        lines.append(f"- rollback: {c['rollback']}")
        lines.append(f"- stop_reason: {c['stop_reason']}")
        if c.get("target_files"):
            lines.append("- target_files:")
            for item in c["target_files"]:
                lines.append(f"  - {item}")
        lines.append("")

    return "\n".join(lines)


def main():
    cycles = []
    final_status = "unknown"
    greener = False

    for cycle in range(1, MAX_REPAIR_CYCLES + 1):
        info = {
            "cycle": cycle,
            "rollback": False,
            "target_files": [],
        }

        print("")
        print("#" * 80)
        print(f"REPAIR CYCLE {cycle}")
        print("#" * 80)

        base_commit = git_commit()
        info["base_commit"] = base_commit

        setup_scripts = [
            ".github/scripts/repo_ultra_audit_narrative.py",
            ".github/scripts/extract_failing_tests.py",
            ".github/scripts/ai_reasoning_layer.py",
            ".github/scripts/build_priority_fix_order.py",
            ".github/scripts/build_test_failure_context.py",
            ".github/scripts/build_fix_context.py",
            ".github/scripts/workflow_signal_aggregator.py",
            ".github/scripts/run_targeted_tests.py",
        ]

        for s in setup_scripts:
            if not run_script(s):
                info["stop_reason"] = "setup_failed"
                info["p0_before"] = count_p0()
                info["p0_after"] = count_p0()
                info["fail_before"] = failing_tests()
                info["fail_after"] = failing_tests()
                info["target_before"] = targeted_failures()
                info["target_after"] = targeted_failures()
                info["improvement"] = False
                info["improvement_reason"] = "Setup pipeline failed."
                cycles.append(info)
                final_status = "setup_failed"
                break

        if final_status == "setup_failed":
            break

        info["p0_before"] = count_p0()
        info["fail_before"] = failing_tests()
        info["target_before"] = targeted_failures()

        if not run_script(".github/scripts/patch_candidate_generator.py"):
            info["stop_reason"] = "patch_generation_failed"
            info["p0_after"] = count_p0()
            info["fail_after"] = failing_tests()
            info["target_after"] = targeted_failures()
            info["improvement"] = False
            info["improvement_reason"] = "Patch generation failed."
            cycles.append(info)
            final_status = "patch_generation_failed"
            break

        info["target_files"] = patch_target_files()

        if not run_script(".github/scripts/patch_verifier.py"):
            info["stop_reason"] = "patch_verifier_failed"
            info["p0_after"] = count_p0()
            info["fail_after"] = failing_tests()
            info["target_after"] = targeted_failures()
            info["improvement"] = False
            info["improvement_reason"] = "Patch verifier failed."
            cycles.append(info)
            final_status = "patch_verifier_failed"
            break

        if not run_script(".github/scripts/apply_patch_candidate.py"):
            info["stop_reason"] = "patch_apply_failed"
            info["p0_after"] = count_p0()
            info["fail_after"] = failing_tests()
            info["target_after"] = targeted_failures()
            info["improvement"] = False
            info["improvement_reason"] = "Patch apply failed."
            cycles.append(info)
            final_status = "patch_apply_failed"
            break

        if not refresh_after_apply():
            info["stop_reason"] = "refresh_failed"
            info["p0_after"] = count_p0()
            info["fail_after"] = failing_tests()
            info["target_after"] = targeted_failures()
            info["improvement"] = False
            info["improvement_reason"] = "Refresh after apply failed."
            cycles.append(info)
            final_status = "refresh_failed"
            break

        info["p0_after"] = count_p0()
        info["fail_after"] = failing_tests()
        info["target_after"] = targeted_failures()

        if not run_script(".github/scripts/post_patch_review.py"):
            info["stop_reason"] = "post_patch_review_failed"
            info["improvement"] = False
            info["improvement_reason"] = "Post patch review failed to execute."
            cycles.append(info)
            final_status = "post_patch_review_failed"
            break

        info["patch_verifier_verdict"] = patch_verifier_verdict()
        info["post_patch_review_verdict"] = post_patch_review_verdict()

        flags = contract_restored_flags()
        info["contract_restored"] = flags["contract_restored"]
        info["minimal_change"] = flags["minimal_change"]
        info["logic_preserved"] = flags["logic_preserved"]

        improved, reason = detect_improvement(
            p0_before=info["p0_before"],
            p0_after=info["p0_after"],
            fail_before=info["fail_before"],
            fail_after=info["fail_after"],
            target_before=info["target_before"],
            target_after=info["target_after"],
            verifier_verdict=info["patch_verifier_verdict"],
            review_verdict=info["post_patch_review_verdict"],
            applied=patch_applied(),
            contract_restored=info["contract_restored"],
            minimal_change=info["minimal_change"],
            logic_preserved=info["logic_preserved"],
            target_files=info["target_files"],
        )

        info["improvement"] = improved
        info["improvement_reason"] = reason

        if improved:
            greener = True

        if info["post_patch_review_verdict"] == "reject":
            git_restore(base_commit)
            refresh_after_apply()
            info["rollback"] = True
            info["stop_reason"] = "post_patch_review_reject"
            cycles.append(info)
            final_status = "post_patch_review_reject"
            break

        if not improved:
            git_restore(base_commit)
            refresh_after_apply()
            info["rollback"] = True
            info["stop_reason"] = "no_progress"
            cycles.append(info)
            final_status = "no_progress"
            break

        if info["p0_after"] == 0 and info["fail_after"] == 0:
            info["stop_reason"] = "all_green"
            cycles.append(info)
            final_status = "all_green"
            break

        cycles.append(info)

        if cycle == MAX_REPAIR_CYCLES:
            final_status = "max_cycles_reached"
            break

    fully_green = compute_repo_fully_green(cycles)
    continuation_recommended = greener and not fully_green
    next_action = compute_next_action(final_status, greener, fully_green)

    report = build_report(cycles, final_status, greener, fully_green)

    write_text(AUDIT_OUT / "ai_repair_loop_report.md", report)

    write_json(
        AUDIT_OUT / "ai_repair_loop_state.json",
        {
            "final_status": final_status,
            "repo_materially_greener": greener,
            "repo_fully_green": fully_green,
            "continuation_recommended": continuation_recommended,
            "next_action": next_action,
            "cycles": cycles,
        },
    )

    print("")
    print("=" * 80)
    print(report)
    print("=" * 80)


if __name__ == "__main__":
    main() 