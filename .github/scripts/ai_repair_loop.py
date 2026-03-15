#!/usr/bin/env python3

import json
import subprocess
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"

MAX_REPAIR_CYCLES = 3


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
    print("=" * 70)
    print(f"RUNNING {script}")
    print("=" * 70)
    print("")

    result = subprocess.run(
        ["python", script],
        cwd=ROOT,
        capture_output=False,
        text=True,
    )
    return result.returncode == 0, result.returncode


def count_p0() -> int:
    fix_context = read_json(AUDIT_OUT / "fix_context.json")
    contexts = fix_context.get("fix_contexts", [])
    return len([c for c in contexts if c.get("priority") == "P0"])


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


def state_snapshot() -> dict:
    fix_context = read_json(AUDIT_OUT / "fix_context.json")
    patch_candidate = read_json(AUDIT_OUT / "patch_candidate.json")
    patch_verification = read_json(AUDIT_OUT / "patch_verification.json")
    patch_apply_report = read_json(AUDIT_OUT / "patch_apply_report.json")
    post_patch_review = read_json(AUDIT_OUT / "post_patch_review.json")

    return {
        "p0_count": len(
            [x for x in fix_context.get("fix_contexts", []) if x.get("priority") == "P0"]
        ),
        "target_files": patch_candidate.get("target_files", []),
        "proposed_patch_count": len(patch_candidate.get("proposed_patches", []) or []),
        "patch_verifier_verdict": patch_verification.get("verdict", ""),
        "patch_applied": patch_apply_report.get("applied", False),
        "post_patch_review_verdict": post_patch_review.get("final_verdict", ""),
    }


def snapshots_equivalent(a: dict, b: dict) -> bool:
    keys = [
        "p0_count",
        "target_files",
        "proposed_patch_count",
        "patch_verifier_verdict",
        "patch_applied",
        "post_patch_review_verdict",
    ]
    return {k: a.get(k) for k in keys} == {k: b.get(k) for k in keys}


def build_cycle_report(cycles: list[dict], final_status: str) -> str:
    lines = []
    lines.append("AI Repair Loop Report")
    lines.append("")
    lines.append(f"Final status: {final_status}")
    lines.append("")
    lines.append(f"Max cycles configured: {MAX_REPAIR_CYCLES}")
    lines.append("")

    for cycle in cycles:
        lines.append(f"## Cycle {cycle.get('cycle')}")
        lines.append(f"- p0_before: {cycle.get('p0_before')}")
        lines.append(f"- p0_after: {cycle.get('p0_after')}")
        lines.append(f"- patch_generated: {cycle.get('patch_generated')}")
        lines.append(f"- patch_verifier_verdict: {cycle.get('patch_verifier_verdict')}")
        lines.append(f"- patch_applied: {cycle.get('patch_applied')}")
        lines.append(f"- post_patch_review_verdict: {cycle.get('post_patch_review_verdict')}")
        lines.append(f"- stop_reason: {cycle.get('stop_reason', '')}")
        lines.append("")
        target_files = cycle.get("target_files", []) or []
        if target_files:
            lines.append("Target files:")
            for item in target_files:
                lines.append(f"- {item}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    cycles: list[dict] = []
    final_status = "unknown"
    previous_snapshot = None

    for cycle_number in range(1, MAX_REPAIR_CYCLES + 1):
        cycle_info = {
            "cycle": cycle_number,
            "stop_reason": "",
            "target_files": [],
        }

        print("")
        print("#" * 80)
        print(f"AI REPAIR CYCLE {cycle_number}")
        print("#" * 80)

        pipeline_scripts = [
            ".github/scripts/repo_ultra_audit_narrative.py",
            ".github/scripts/extract_failing_tests.py",
            ".github/scripts/ai_reasoning_layer.py",
            ".github/scripts/build_priority_fix_order.py",
            ".github/scripts/build_test_failure_context.py",
            ".github/scripts/build_fix_context.py",
            ".github/scripts/workflow_signal_aggregator.py",
            ".github/scripts/patch_candidate_generator.py",
            ".github/scripts/patch_verifier.py",
        ]

        for script in pipeline_scripts:
            ok, code = run_script(script)
            if not ok:
                cycle_info["stop_reason"] = f"script_failed:{script}:{code}"
                cycle_info["p0_before"] = count_p0()
                cycle_info["p0_after"] = count_p0()
                cycle_info["patch_generated"] = patch_generated()
                cycle_info["patch_verifier_verdict"] = patch_verdict()
                cycle_info["patch_applied"] = patch_applied()
                cycle_info["post_patch_review_verdict"] = post_review_verdict()
                cycles.append(cycle_info)

                final_status = "script_failed"
                write_json(
                    AUDIT_OUT / "ai_repair_loop_state.json",
                    {"final_status": final_status, "cycles": cycles},
                )
                write_text(
                    AUDIT_OUT / "ai_repair_loop_report.md",
                    build_cycle_report(cycles, final_status),
                )
                print(f"Stopping loop because {script} failed with exit code {code}")
                return 0

        cycle_info["p0_before"] = count_p0()

        candidate = read_json(AUDIT_OUT / "patch_candidate.json")
        cycle_info["target_files"] = candidate.get("target_files", []) or []
        cycle_info["patch_generated"] = patch_generated()
        cycle_info["patch_verifier_verdict"] = patch_verdict()

        if not cycle_info["patch_generated"]:
            cycle_info["patch_applied"] = False
            cycle_info["post_patch_review_verdict"] = ""
            cycle_info["p0_after"] = count_p0()
            cycle_info["stop_reason"] = "no_patch_generated"
            cycles.append(cycle_info)
            final_status = "no_patch_generated"
            break

        if cycle_info["patch_verifier_verdict"] not in {"approve", "weak-approve"}:
            cycle_info["patch_applied"] = False
            cycle_info["post_patch_review_verdict"] = ""
            cycle_info["p0_after"] = count_p0()
            cycle_info["stop_reason"] = f"patch_verifier_{cycle_info['patch_verifier_verdict'] or 'unknown'}"
            cycles.append(cycle_info)
            final_status = "patch_rejected"
            break

        ok, code = run_script(".github/scripts/apply_patch_candidate.py")
        cycle_info["patch_applied"] = patch_applied()

        if not ok or not cycle_info["patch_applied"]:
            cycle_info["post_patch_review_verdict"] = ""
            cycle_info["p0_after"] = count_p0()
            cycle_info["stop_reason"] = "patch_not_applied"
            cycles.append(cycle_info)
            final_status = "patch_not_applied"
            break

        ok, code = run_script(".github/scripts/post_patch_review.py")
        cycle_info["post_patch_review_verdict"] = post_review_verdict()
        cycle_info["p0_after"] = count_p0()

        if not ok:
            cycle_info["stop_reason"] = f"script_failed:.github/scripts/post_patch_review.py:{code}"
            cycles.append(cycle_info)
            final_status = "post_review_failed"
            break

        if cycle_info["post_patch_review_verdict"] == "reject":
            cycle_info["stop_reason"] = "post_patch_review_reject"
            cycles.append(cycle_info)
            final_status = "post_review_reject"
            break

        current_snapshot = state_snapshot()

        if previous_snapshot is not None and snapshots_equivalent(previous_snapshot, current_snapshot):
            cycle_info["stop_reason"] = "no_meaningful_progress"
            cycles.append(cycle_info)
            final_status = "no_meaningful_progress"
            break

        previous_snapshot = current_snapshot

        if cycle_info["p0_after"] == 0:
            cycle_info["stop_reason"] = "all_p0_resolved"
            cycles.append(cycle_info)
            final_status = "all_p0_resolved"
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