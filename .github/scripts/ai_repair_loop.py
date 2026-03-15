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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def run_script(script: str) -> tuple[bool, int]:
    print("")
    print("=" * 80)
    print(f"RUNNING {script}")
    print("=" * 80)
    print("")

    result = subprocess.run(
        ["python", script],
        cwd=ROOT,
        capture_output=False,
        text=True,
    )
    return result.returncode == 0, result.returncode


def git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return (result.stdout or "").strip()


def git_diff_has_changes() -> bool:
    result = subprocess.run(
        ["git", "diff", "--quiet"],
        cwd=ROOT,
    )
    result_cached = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=ROOT,
    )
    return not (result.returncode == 0 and result_cached.returncode == 0)


def git_restore_hard(commit_sha: str) -> bool:
    result = subprocess.run(
        ["git", "reset", "--hard", commit_sha],
        cwd=ROOT,
        capture_output=False,
        text=True,
    )
    return result.returncode == 0


def count_p0() -> int:
    fix_context = read_json(AUDIT_OUT / "fix_context.json")
    contexts = fix_context.get("fix_contexts", [])
    return len([c for c in contexts if c.get("priority") == "P0"])


def failing_test_count() -> int:
    data = read_json(AUDIT_OUT / "failing_tests.json")
    return len(data.get("failing_tests", []) or [])


def targeted_failure_count() -> int | None:
    data = read_json(AUDIT_OUT / "targeted_test_results.json")
    value = data.get("failure_count", None)
    return value if isinstance(value, int) else None


def patch_generated() -> bool:
    patch = read_json(AUDIT_OUT / "patch_candidate.json")
    patches = patch.get("proposed_patches", [])
    return isinstance(patches, list) and len(patches) > 0


def patch_applied() -> bool:
    report = read_json(AUDIT_OUT / "patch_apply_report.json")
    return bool(report.get("applied", False))


def patch_verdict() -> str:
    data = read_json(AUDIT_OUT / "patch_verification.json")
    return str(data.get("verdict", "")).strip().lower()


def post_review_verdict() -> str:
    data = read_json(AUDIT_OUT / "post_patch_review.json")
    return str(data.get("final_verdict", "")).strip().lower()


def build_cycle_report(cycles: list[dict], final_status: str) -> str:
    lines = []
    lines.append("AI Repair Loop Report")
    lines.append("")
    lines.append(f"Final status: {final_status}")
    lines.append(f"Max cycles configured: {MAX_REPAIR_CYCLES}")
    lines.append("")

    for cycle in cycles:
        lines.append(f"## Cycle {cycle.get('cycle')}")
        lines.append(f"- base_commit: {cycle.get('base_commit')}")
        lines.append(f"- p0_before: {cycle.get('p0_before')}")
        lines.append(f"- p0_after: {cycle.get('p0_after')}")
        lines.append(f"- failing_tests_before: {cycle.get('failing_tests_before')}")
        lines.append(f"- failing_tests_after: {cycle.get('failing_tests_after')}")
        lines.append(f"- targeted_failures_before: {cycle.get('targeted_failures_before')}")
        lines.append(f"- targeted_failures_after: {cycle.get('targeted_failures_after')}")
        lines.append(f"- patch_generated: {cycle.get('patch_generated')}")
        lines.append(f"- patch_verifier_verdict: {cycle.get('patch_verifier_verdict')}")
        lines.append(f"- patch_applied: {cycle.get('patch_applied')}")
        lines.append(f"- post_patch_review_verdict: {cycle.get('post_patch_review_verdict')}")
        lines.append(f"- improvement_detected: {cycle.get('improvement_detected')}")
        lines.append(f"- improvement_reason: {cycle.get('improvement_reason', '')}")
        lines.append(f"- rollback_performed: {cycle.get('rollback_performed')}")
        lines.append(f"- stop_reason: {cycle.get('stop_reason', '')}")

        target_files = cycle.get("target_files", []) or []
        if target_files:
            lines.append("- target_files:")
            for item in target_files:
                lines.append(f"  - {item}")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def detect_improvement(cycle_info: dict) -> tuple[bool, str]:
    p0_before = cycle_info.get("p0_before")
    p0_after = cycle_info.get("p0_after")
    fail_before = cycle_info.get("failing_tests_before")
    fail_after = cycle_info.get("failing_tests_after")
    targeted_before = cycle_info.get("targeted_failures_before")
    targeted_after = cycle_info.get("targeted_failures_after")

    if isinstance(targeted_before, int) and isinstance(targeted_after, int):
        if targeted_after < targeted_before:
            return True, f"Targeted failures reduced from {targeted_before} to {targeted_after}."
        if targeted_after > targeted_before:
            return False, f"Targeted failures worsened from {targeted_before} to {targeted_after}."

    if isinstance(fail_before, int) and isinstance(fail_after, int):
        if fail_after < fail_before:
            return True, f"Failing tests reduced from {fail_before} to {fail_after}."
        if fail_after > fail_before:
            return False, f"Failing tests worsened from {fail_before} to {fail_after}."

    if isinstance(p0_before, int) and isinstance(p0_after, int):
        if p0_after < p0_before:
            return True, f"P0 reduced from {p0_before} to {p0_after}."
        if p0_after > p0_before:
            return False, f"P0 worsened from {p0_before} to {p0_after}."

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

    for script in scripts:
        ok, _ = run_script(script)
        if not ok:
            return False
    return True


def main() -> int:
    cycles: list[dict] = []
    final_status = "unknown"

    for cycle_number in range(1, MAX_REPAIR_CYCLES + 1):
        cycle_info = {
            "cycle": cycle_number,
            "stop_reason": "",
            "target_files": [],
            "rollback_performed": False,
        }

        print("")
        print("#" * 80)
        print(f"AI REPAIR CYCLE {cycle_number}")
        print("#" * 80)

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

        for script in setup_scripts:
            ok, code = run_script(script)
            if not ok:
                cycle_info["stop_reason"] = f"script_failed:{script}:{code}"
                cycle_info["base_commit"] = git_commit()
                cycle_info["p0_before"] = count_p0()
                cycle_info["p0_after"] = count_p0()
                cycle_info["failing_tests_before"] = failing_test_count()
                cycle_info["failing_tests_after"] = failing_test_count()
                cycle_info["targeted_failures_before"] = targeted_failure_count()
                cycle_info["targeted_failures_after"] = targeted_failure_count()
                cycle_info["patch_generated"] = False
                cycle_info["patch_verifier_verdict"] = ""
                cycle_info["patch_applied"] = False
                cycle_info["post_patch_review_verdict"] = ""
                cycle_info["improvement_detected"] = False
                cycle_info["improvement_reason"] = "Setup step failed."
                cycles.append(cycle_info)
                final_status = "setup_failed"
                write_json(AUDIT_OUT / "ai_repair_loop_state.json", {"final_status": final_status, "cycles": cycles})
                write_text(AUDIT_OUT / "ai_repair_loop_report.md", build_cycle_report(cycles, final_status))
                return 0

        base_commit = git_commit()
        cycle_info["base_commit"] = base_commit
        cycle_info["p0_before"] = count_p0()
        cycle_info["failing_tests_before"] = failing_test_count()
        cycle_info["targeted_failures_before"] = targeted_failure_count()

        ok, code = run_script(".github/scripts/patch_candidate_generator.py")
        if not ok:
            cycle_info["stop_reason"] = f"script_failed:.github/scripts/patch_candidate_generator.py:{code}"
            cycle_info["patch_generated"] = False
            cycle_info["patch_verifier_verdict"] = ""
            cycle_info["patch_applied"] = False
            cycle_info["post_patch_review_verdict"] = ""
            cycle_info["p0_after"] = count_p0()
            cycle_info["failing_tests_after"] = failing_test_count()
            cycle_info["targeted_failures_after"] = targeted_failure_count()
            cycle_info["improvement_detected"] = False
            cycle_info["improvement_reason"] = "Patch generator failed."
            cycles.append(cycle_info)
            final_status = "patch_generator_failed"
            break

        candidate = read_json(AUDIT_OUT / "patch_candidate.json")
        cycle_info["target_files"] = candidate.get("target_files", []) or []
        cycle_info["patch_generated"] = patch_generated()

        if not cycle_info["patch_generated"]:
            cycle_info["patch_verifier_verdict"] = ""
            cycle_info["patch_applied"] = False
            cycle_info["post_patch_review_verdict"] = ""
            cycle_info["p0_after"] = count_p0()
            cycle_info["failing_tests_after"] = failing_test_count()
            cycle_info["targeted_failures_after"] = targeted_failure_count()
            cycle_info["improvement_detected"] = False
            cycle_info["improvement_reason"] = "No patch generated."
            cycle_info["stop_reason"] = "no_patch_generated"
            cycles.append(cycle_info)
            final_status = "no_patch_generated"
            break

        ok, code = run_script(".github/scripts/patch_verifier.py")
        cycle_info["patch_verifier_verdict"] = patch_verdict()

        if not ok:
            cycle_info["patch_applied"] = False
            cycle_info["post_patch_review_verdict"] = ""
            cycle_info["p0_after"] = count_p0()
            cycle_info["failing_tests_after"] = failing_test_count()
            cycle_info["targeted_failures_after"] = targeted_failure_count()
            cycle_info["improvement_detected"] = False
            cycle_info["improvement_reason"] = "Patch verifier failed to run."
            cycle_info["stop_reason"] = f"script_failed:.github/scripts/patch_verifier.py:{code}"
            cycles.append(cycle_info)
            final_status = "patch_verifier_failed"
            break

        if cycle_info["patch_verifier_verdict"] not in {"approve", "weak-approve"}:
            cycle_info["patch_applied"] = False
            cycle_info["post_patch_review_verdict"] = ""
            cycle_info["p0_after"] = count_p0()
            cycle_info["failing_tests_after"] = failing_test_count()
            cycle_info["targeted_failures_after"] = targeted_failure_count()
            cycle_info["improvement_detected"] = False
            cycle_info["improvement_reason"] = "Patch verifier did not approve the patch."
            cycle_info["stop_reason"] = f"patch_verifier_{cycle_info['patch_verifier_verdict'] or 'unknown'}"
            cycles.append(cycle_info)
            final_status = "patch_rejected"
            break

        ok, code = run_script(".github/scripts/apply_patch_candidate.py")
        cycle_info["patch_applied"] = patch_applied()

        if not ok or not cycle_info["patch_applied"]:
            cycle_info["post_patch_review_verdict"] = ""
            cycle_info["p0_after"] = count_p0()
            cycle_info["failing_tests_after"] = failing_test_count()
            cycle_info["targeted_failures_after"] = targeted_failure_count()
            cycle_info["improvement_detected"] = False
            cycle_info["improvement_reason"] = "Patch was not applied."
            cycle_info["stop_reason"] = "patch_not_applied"
            cycles.append(cycle_info)
            final_status = "patch_not_applied"
            break

        if not refresh_after_apply():
            cycle_info["post_patch_review_verdict"] = ""
            cycle_info["p0_after"] = count_p0()
            cycle_info["failing_tests_after"] = failing_test_count()
            cycle_info["targeted_failures_after"] = targeted_failure_count()
            cycle_info["improvement_detected"] = False
            cycle_info["improvement_reason"] = "Post-apply refresh pipeline failed."
            cycle_info["stop_reason"] = "post_apply_refresh_failed"
            cycles.append(cycle_info)
            final_status = "post_apply_refresh_failed"
            break

        cycle_info["p0_after"] = count_p0()
        cycle_info["failing_tests_after"] = failing_test_count()
        cycle_info["targeted_failures_after"] = targeted_failure_count()

        improved, reason = detect_improvement(cycle_info)
        cycle_info["improvement_detected"] = improved
        cycle_info["improvement_reason"] = reason

        if not improved:
            restored = git_restore_hard(base_commit)
            cycle_info["rollback_performed"] = restored
            refresh_after_apply()
            cycle_info["stop_reason"] = "no_meaningful_progress"
            cycle_info["post_patch_review_verdict"] = ""
            cycles.append(cycle_info)
            final_status = "no_meaningful_progress"
            break

        ok, code = run_script(".github/scripts/post_patch_review.py")
        cycle_info["post_patch_review_verdict"] = post_review_verdict()

        if not ok:
            cycle_info["stop_reason"] = f"script_failed:.github/scripts/post_patch_review.py:{code}"
            cycles.append(cycle_info)
            final_status = "post_review_failed"
            break

        if cycle_info["post_patch_review_verdict"] == "reject":
            restored = git_restore_hard(base_commit)
            cycle_info["rollback_performed"] = restored
            refresh_after_apply()
            cycle_info["stop_reason"] = "post_patch_review_reject"
            cycles.append(cycle_info)
            final_status = "post_review_reject"
            break

        if cycle_info["p0_after"] == 0 and cycle_info["failing_tests_after"] == 0:
            cycle_info["stop_reason"] = "all_green"
            cycles.append(cycle_info)
            final_status = "all_green"
            break

        if cycle_number == MAX_REPAIR_CYCLES:
            cycle_info["stop_reason"] = "max_cycles_reached"
            cycles.append(cycle_info)
            final_status = "max_cycles_reached"
            break

        cycle_info["stop_reason"] = "continue_next_cycle"
        cycles.append(cycle_info)

    write_json(
        AUDIT_OUT / "ai_repair_loop_state.json",
        {"final_status": final_status, "cycles": cycles},
    )
    write_text(
        AUDIT_OUT / "ai_repair_loop_report.md",
        build_cycle_report(cycles, final_status),
    )

    print("")
    print("=" * 80)
    print(f"AI REPAIR LOOP FINISHED: {final_status}")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())