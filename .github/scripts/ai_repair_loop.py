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
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return (result.stdout or "").strip()


def git_restore(commit: str):
    subprocess.run(
        ["git", "reset", "--hard", commit],
        cwd=ROOT,
    )


def count_p0() -> int:
    fix_context = read_json(AUDIT_OUT / "fix_context.json")
    items = fix_context.get("fix_contexts", [])
    return len([x for x in items if str(x.get("priority", "")).strip().upper() == "P0"])


def failing_tests() -> int:
    data = read_json(AUDIT_OUT / "failing_tests.json")
    return len(data.get("failing_tests", []))


def targeted_failures():
    data = read_json(AUDIT_OUT / "targeted_test_results.json")
    value = data.get("failure_count")
    if isinstance(value, int):
        return value
    return None


def targeted_executed_count() -> int:
    data = read_json(AUDIT_OUT / "targeted_test_results.json")
    summary = data.get("summary", {}) or {}
    return int(summary.get("executed_count", 0) or 0)


def ci_failure_count() -> int:
    data = read_json(AUDIT_OUT / "ci_failure_context.json")
    return len(data.get("ci_failures", []))


def generated_test_count() -> int:
    data = read_json(AUDIT_OUT / "test_gap_generation_report.json")
    return int(data.get("generated_count", 0) or 0)


def cto_priority_summary() -> dict:
    data = read_json(AUDIT_OUT / "ai_cto_layer.json")
    summary = data.get("summary", {}) or {}
    return {
        "P0": int(summary.get("P0", 0) or 0),
        "P1": int(summary.get("P1", 0) or 0),
        "P2": int(summary.get("P2", 0) or 0),
    }


def patch_verifier_verdict() -> str:
    data = read_json(AUDIT_OUT / "patch_verification.json")
    return str(data.get("verdict", "")).strip().lower()


def post_patch_review_verdict() -> str:
    data = read_json(AUDIT_OUT / "post_patch_review.json")
    return (
        str(data.get("review_verdict", "")).strip().lower()
        or str(data.get("final_verdict", "")).strip().lower()
    )


def patch_applied() -> bool:
    data = read_json(AUDIT_OUT / "patch_apply_report.json")
    return bool(data.get("applied", False))


def patch_target_files() -> list[str]:
    data = read_json(AUDIT_OUT / "patch_candidate.json")
    candidate = data.get("patch_candidate") or {}
    files = []

    target = str(candidate.get("target_file", "")).strip()
    related = str(candidate.get("related_source_file", "")).strip()

    if target:
        files.append(target)
    if related and related not in files:
        files.append(related)

    return files


def patch_strategy() -> str:
    data = read_json(AUDIT_OUT / "patch_candidate.json")
    candidate = data.get("patch_candidate") or {}
    return str(candidate.get("strategy", "")).strip()


def patch_issue_type() -> str:
    data = read_json(AUDIT_OUT / "patch_candidate.json")
    candidate = data.get("patch_candidate") or {}
    return str(candidate.get("issue_type", "")).strip()


def patch_classification() -> str:
    data = read_json(AUDIT_OUT / "patch_candidate.json")
    candidate = data.get("patch_candidate") or {}
    return str(candidate.get("classification", "")).strip()


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
    target_exec_before,
    target_exec_after,
    ci_before,
    ci_after,
    generated_before,
    generated_after,
    verifier_verdict,
    review_verdict,
    applied,
    contract_restored,
    minimal_change,
    logic_preserved,
    target_files,
    strategy,
    classification,
    issue_type,
):
    reasons = []

    if isinstance(target_before, int) and isinstance(target_after, int):
        if target_exec_after > 0:
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

    if isinstance(ci_before, int) and isinstance(ci_after, int):
        if ci_after < ci_before:
            reasons.append(f"CI failures reduced from {ci_before} to {ci_after}.")
        elif ci_after > ci_before:
            return False, f"CI failures worsened from {ci_before} to {ci_after}."

    if isinstance(generated_before, int) and isinstance(generated_after, int):
        if generated_after > generated_before and strategy == "generate_nominal_test":
            reasons.append(
                f"Generated nominal tests increased from {generated_before} to {generated_after}."
            )

    contract_like_files = {
        "auto_updater.py",
        "executor_manager.py",
        "tests/fixtures/system_payloads.py",
    }

    touched_contract_files = any(str(f) in contract_like_files for f in (target_files or []))
    touched_runtime_files = any(
        str(f).endswith(".py") and not str(f).startswith("tests/") and not str(f).startswith(".github/")
        for f in (target_files or [])
    )

    if (
        applied
        and verifier_verdict in {"approve", "weak-approve", "review"}
        and review_verdict in {"approve", "weak-approve", "review"}
        and contract_restored
        and minimal_change
        and logic_preserved
        and touched_contract_files
    ):
        reasons.append(
            "Contract restoration detected on key public API files with applied patch and acceptable review."
        )

    if (
        applied
        and strategy == "generate_nominal_test"
        and classification == "AUTO_FIX_SAFE"
        and verifier_verdict in {"approve", "weak-approve"}
        and review_verdict in {"approve", "weak-approve", "review"}
        and minimal_change
        and logic_preserved
    ):
        reasons.append(
            "Safe nominal test generation accepted by verifier/review with minimal change."
        )

    if (
        applied
        and classification == "AUTO_FIX_SAFE"
        and issue_type in {"missing_public_contract", "lint_failure", "missing_nominal_test"}
        and verifier_verdict in {"approve", "weak-approve"}
        and review_verdict in {"approve", "weak-approve", "review"}
        and minimal_change
        and logic_preserved
    ):
        reasons.append("Safe classified fix accepted with minimal change and logic preserved.")

    if (
        applied
        and touched_runtime_files
        and minimal_change
        and logic_preserved
        and verifier_verdict in {"approve", "weak-approve", "review"}
        and review_verdict in {"approve", "weak-approve", "review"}
        and (
            (target_exec_after > 0 and isinstance(target_after, int) and target_after == 0)
            or target_exec_after == 0
        )
    ):
        reasons.append(
            "Runtime patch produced a real diff with acceptable review outcome."
        )

    if reasons:
        return True, " | ".join(reasons)

    return False, "No measurable improvement detected."


def refresh_after_apply() -> bool:
    scripts = [
        ".github/scripts/run_targeted_tests.py",
        ".github/scripts/repo_ultra_audit_narrative.py",
        ".github/scripts/extract_failing_tests.py",
        ".github/scripts/ci_failure_aggregator.py",
        ".github/scripts/build_test_failure_context.py",
        ".github/scripts/build_fix_context.py",
        ".github/scripts/load_repo_diagnostics.py",
        ".github/scripts/ai_cto_layer.py",
        ".github/scripts/test_gap_generator.py",
        ".github/scripts/issue_classifier.py",
        ".github/scripts/repair_memory.py",
        ".github/scripts/workflow_signal_aggregator.py",
    ]

    for script in scripts:
        if not run_script(script):
            return False

    return True


def compute_repo_fully_green(cycles: list[dict]) -> bool:
    if not cycles:
        return False

    last = cycles[-1]
    p0_after = last.get("p0_after")
    fail_after = last.get("fail_after")
    target_after = last.get("target_after")
    ci_after = last.get("ci_after")

    if (
        isinstance(p0_after, int)
        and isinstance(fail_after, int)
        and isinstance(ci_after, int)
        and p0_after == 0
        and fail_after == 0
        and ci_after == 0
    ):
        return True

    if (
        isinstance(target_after, int)
        and isinstance(p0_after, int)
        and isinstance(ci_after, int)
        and target_after == 0
        and p0_after == 0
        and ci_after == 0
    ):
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
        "refresh_failed",
        "setup_failed",
        "post_patch_review_failed",
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

    for cycle in cycles:
        lines.append(f"Cycle {cycle['cycle']}")
        lines.append(f"- base_commit: {cycle['base_commit']}")
        lines.append(f"- p0_before: {cycle['p0_before']}")
        lines.append(f"- p0_after: {cycle['p0_after']}")
        lines.append(f"- failing_tests_before: {cycle['fail_before']}")
        lines.append(f"- failing_tests_after: {cycle['fail_after']}")
        lines.append(f"- targeted_before: {cycle['target_before']}")
        lines.append(f"- targeted_after: {cycle['target_after']}")
        lines.append(f"- targeted_executed_before: {cycle['target_exec_before']}")
        lines.append(f"- targeted_executed_after: {cycle['target_exec_after']}")
        lines.append(f"- ci_failures_before: {cycle['ci_before']}")
        lines.append(f"- ci_failures_after: {cycle['ci_after']}")
        lines.append(f"- generated_tests_before: {cycle['generated_before']}")
        lines.append(f"- generated_tests_after: {cycle['generated_after']}")
        lines.append(f"- cto_P0_before: {cycle['cto_before'].get('P0', 0)}")
        lines.append(f"- cto_P0_after: {cycle['cto_after'].get('P0', 0)}")
        lines.append(f"- patch_strategy: {cycle.get('patch_strategy', '')}")
        lines.append(f"- patch_issue_type: {cycle.get('patch_issue_type', '')}")
        lines.append(f"- patch_classification: {cycle.get('patch_classification', '')}")
        lines.append(f"- patch_verifier_verdict: {cycle.get('patch_verifier_verdict', '')}")
        lines.append(f"- post_patch_review_verdict: {cycle.get('post_patch_review_verdict', '')}")
        lines.append(f"- contract_restored: {cycle.get('contract_restored')}")
        lines.append(f"- minimal_change: {cycle.get('minimal_change')}")
        lines.append(f"- logic_preserved: {cycle.get('logic_preserved')}")
        lines.append(f"- improvement: {cycle['improvement']}")
        lines.append(f"- improvement_reason: {cycle.get('improvement_reason', '')}")
        lines.append(f"- rollback: {cycle['rollback']}")
        lines.append(f"- stop_reason: {cycle['stop_reason']}")
        if cycle.get("target_files"):
            lines.append("- target_files:")
            for item in cycle["target_files"]:
                lines.append(f"  - {item}")
        lines.append("")

    return "\n".join(lines)


def main():
    cycles = []
    final_status = "unknown"
    greener = False

    for cycle_no in range(1, MAX_REPAIR_CYCLES + 1):
        info = {
            "cycle": cycle_no,
            "rollback": False,
            "target_files": [],
            "cto_before": {"P0": 0, "P1": 0, "P2": 0},
            "cto_after": {"P0": 0, "P1": 0, "P2": 0},
        }

        print("")
        print("#" * 80)
        print(f"REPAIR CYCLE {cycle_no}")
        print("#" * 80)

        base_commit = git_commit()
        info["base_commit"] = base_commit

        setup_scripts = [
            ".github/scripts/repo_ultra_audit_narrative.py",
            ".github/scripts/extract_failing_tests.py",
            ".github/scripts/ai_reasoning_layer.py",
            ".github/scripts/build_priority_fix_order.py",
            ".github/scripts/ci_failure_aggregator.py",
            ".github/scripts/build_test_failure_context.py",
            ".github/scripts/build_fix_context.py",
            ".github/scripts/load_repo_diagnostics.py",
            ".github/scripts/ai_cto_layer.py",
            ".github/scripts/test_gap_generator.py",
            ".github/scripts/issue_classifier.py",
            ".github/scripts/repair_memory.py",
            ".github/scripts/workflow_signal_aggregator.py",
            ".github/scripts/run_targeted_tests.py",
        ]

        setup_failed = False
        for script in setup_scripts:
            if not run_script(script):
                setup_failed = True
                info["stop_reason"] = "setup_failed"
                info["p0_before"] = count_p0()
                info["p0_after"] = count_p0()
                info["fail_before"] = failing_tests()
                info["fail_after"] = failing_tests()
                info["target_before"] = targeted_failures()
                info["target_after"] = targeted_failures()
                info["target_exec_before"] = targeted_executed_count()
                info["target_exec_after"] = targeted_executed_count()
                info["ci_before"] = ci_failure_count()
                info["ci_after"] = ci_failure_count()
                info["generated_before"] = generated_test_count()
                info["generated_after"] = generated_test_count()
                info["cto_before"] = cto_priority_summary()
                info["cto_after"] = cto_priority_summary()
                info["patch_strategy"] = ""
                info["patch_issue_type"] = ""
                info["patch_classification"] = ""
                info["patch_verifier_verdict"] = "setup-failed"
                info["post_patch_review_verdict"] = "setup-failed"
                info["contract_restored"] = False
                info["minimal_change"] = False
                info["logic_preserved"] = False
                info["improvement"] = False
                info["improvement_reason"] = "Setup pipeline failed."
                cycles.append(info)
                final_status = "setup_failed"
                break

        if setup_failed:
            break

        info["p0_before"] = count_p0()
        info["fail_before"] = failing_tests()
        info["target_before"] = targeted_failures()
        info["target_exec_before"] = targeted_executed_count()
        info["ci_before"] = ci_failure_count()
        info["generated_before"] = generated_test_count()
        info["cto_before"] = cto_priority_summary()

        if (
            info["p0_before"] == 0
            and info["fail_before"] == 0
            and (info["target_before"] in (0, None))
            and info["ci_before"] == 0
        ):
            info["p0_after"] = 0
            info["fail_after"] = 0
            info["target_after"] = info["target_before"]
            info["target_exec_after"] = info["target_exec_before"]
            info["ci_after"] = 0
            info["generated_after"] = info["generated_before"]
            info["cto_after"] = info["cto_before"]
            info["patch_strategy"] = ""
            info["patch_issue_type"] = ""
            info["patch_classification"] = ""
            info["patch_verifier_verdict"] = "not-needed"
            info["post_patch_review_verdict"] = "not-needed"
            info["contract_restored"] = False
            info["minimal_change"] = True
            info["logic_preserved"] = True
            info["improvement"] = False
            info["improvement_reason"] = "Repository already green. No repair needed."
            info["stop_reason"] = "repository_green_stop"
            cycles.append(info)
            final_status = "all_green"
            break

        if not run_script(".github/scripts/patch_candidate_generator.py"):
            info["stop_reason"] = "patch_generation_failed"
            info["p0_after"] = count_p0()
            info["fail_after"] = failing_tests()
            info["target_after"] = targeted_failures()
            info["target_exec_after"] = targeted_executed_count()
            info["ci_after"] = ci_failure_count()
            info["generated_after"] = generated_test_count()
            info["cto_after"] = cto_priority_summary()
            info["patch_strategy"] = patch_strategy()
            info["patch_issue_type"] = patch_issue_type()
            info["patch_classification"] = patch_classification()
            info["patch_verifier_verdict"] = "not-run"
            info["post_patch_review_verdict"] = "not-run"
            info["contract_restored"] = False
            info["minimal_change"] = False
            info["logic_preserved"] = False
            info["improvement"] = False
            info["improvement_reason"] = "Patch generation failed."
            cycles.append(info)
            final_status = "patch_generation_failed"
            break

        info["target_files"] = patch_target_files()
        info["patch_strategy"] = patch_strategy()
        info["patch_issue_type"] = patch_issue_type()
        info["patch_classification"] = patch_classification()

        if not run_script(".github/scripts/patch_verifier.py"):
            info["stop_reason"] = "patch_verifier_failed"
            info["p0_after"] = count_p0()
            info["fail_after"] = failing_tests()
            info["target_after"] = targeted_failures()
            info["target_exec_after"] = targeted_executed_count()
            info["ci_after"] = ci_failure_count()
            info["generated_after"] = generated_test_count()
            info["cto_after"] = cto_priority_summary()
            info["patch_verifier_verdict"] = "failed"
            info["post_patch_review_verdict"] = "not-run"
            info["contract_restored"] = False
            info["minimal_change"] = False
            info["logic_preserved"] = False
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
            info["target_exec_after"] = targeted_executed_count()
            info["ci_after"] = ci_failure_count()
            info["generated_after"] = generated_test_count()
            info["cto_after"] = cto_priority_summary()
            info["patch_verifier_verdict"] = patch_verifier_verdict()
            info["post_patch_review_verdict"] = "not-run"
            info["contract_restored"] = False
            info["minimal_change"] = False
            info["logic_preserved"] = False
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
            info["target_exec_after"] = targeted_executed_count()
            info["ci_after"] = ci_failure_count()
            info["generated_after"] = generated_test_count()
            info["cto_after"] = cto_priority_summary()
            info["patch_verifier_verdict"] = patch_verifier_verdict()
            info["post_patch_review_verdict"] = "not-run"
            info["contract_restored"] = False
            info["minimal_change"] = False
            info["logic_preserved"] = False
            info["improvement"] = False
            info["improvement_reason"] = "Refresh after apply failed."
            cycles.append(info)
            final_status = "refresh_failed"
            break

        info["p0_after"] = count_p0()
        info["fail_after"] = failing_tests()
        info["target_after"] = targeted_failures()
        info["target_exec_after"] = targeted_executed_count()
        info["ci_after"] = ci_failure_count()
        info["generated_after"] = generated_test_count()
        info["cto_after"] = cto_priority_summary()

        if not run_script(".github/scripts/post_patch_review.py"):
            info["stop_reason"] = "post_patch_review_failed"
            info["patch_verifier_verdict"] = patch_verifier_verdict()
            info["post_patch_review_verdict"] = "failed"
            info["contract_restored"] = False
            info["minimal_change"] = False
            info["logic_preserved"] = False
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
            target_exec_before=info["target_exec_before"],
            target_exec_after=info["target_exec_after"],
            ci_before=info["ci_before"],
            ci_after=info["ci_after"],
            generated_before=info["generated_before"],
            generated_after=info["generated_after"],
            verifier_verdict=info["patch_verifier_verdict"],
            review_verdict=info["post_patch_review_verdict"],
            applied=patch_applied(),
            contract_restored=info["contract_restored"],
            minimal_change=info["minimal_change"],
            logic_preserved=info["logic_preserved"],
            target_files=info["target_files"],
            strategy=info["patch_strategy"],
            classification=info["patch_classification"],
            issue_type=info["patch_issue_type"],
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

        if info["p0_after"] == 0 and info["fail_after"] == 0 and info["ci_after"] == 0:
            info["stop_reason"] = "all_green"
            cycles.append(info)
            final_status = "all_green"
            break

        cycles.append(info)

        if cycle_no == MAX_REPAIR_CYCLES:
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