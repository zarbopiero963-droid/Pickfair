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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def normalize_status(value: str, ok_values: set[str]) -> str:
    value = (value or "").strip().lower()
    return "PASS" if value in ok_values else "FAIL"


def badge_for_safe_to_merge(value: str) -> str:
    value = (value or "").strip().upper()
    if value == "YES":
        return "🟢 SAFE"
    return "🔴 BLOCKED"


def badge_for_review_verdict(verdict: str) -> str:
    verdict = (verdict or "").strip().lower()
    if verdict == "approve":
        return "🟢 SAFE"
    if verdict in {"weak-approve", "review"}:
        return "🟡 REVIEW"
    return "🔴 BLOCKED"


def badge_for_boolean(value: bool, positive: str = "🟢 SAFE", negative: str = "🔴 BLOCKED") -> str:
    return positive if value else negative


def collect_touched_files(cycles: list[dict]) -> list[str]:
    touched = []
    seen = set()

    for cycle in cycles:
        for item in cycle.get("target_files", []) or []:
            item = str(item).strip()
            if not item or item in seen:
                continue
            touched.append(item)
            seen.add(item)

    return touched


def classify_file_kind(path_str: str) -> str:
    path_str = (path_str or "").strip()
    if path_str.startswith("tests/"):
        return "test"
    return "module"


def collect_fix_kinds(files: list[str]) -> str:
    if not files:
        return "unknown"

    has_test = any(classify_file_kind(f) == "test" for f in files)
    has_module = any(classify_file_kind(f) == "module" for f in files)

    if has_test and has_module:
        return "module + test"
    if has_test:
        return "test"
    if has_module:
        return "module"
    return "unknown"


def detect_real_improvement(cycles: list[dict]) -> tuple[bool, str]:
    if not cycles:
        return False, "Nessun ciclo disponibile."

    first = cycles[0]
    last = cycles[-1]

    first_fail = first.get("fail_before")
    last_fail = last.get("fail_after")
    first_p0 = first.get("p0_before")
    last_p0 = last.get("p0_after")
    first_targeted = first.get("target_before")
    last_targeted = last.get("target_after")

    if isinstance(first_targeted, int) and isinstance(last_targeted, int):
        if last_targeted < first_targeted:
            return True, f"Targeted failures ridotti da {first_targeted} a {last_targeted}."
        if last_targeted > first_targeted:
            return False, f"Targeted failures peggiorati da {first_targeted} a {last_targeted}."

    if isinstance(first_fail, int) and isinstance(last_fail, int):
        if last_fail < first_fail:
            return True, f"Failing tests ridotti da {first_fail} a {last_fail}."
        if last_fail > first_fail:
            return False, f"Failing tests peggiorati da {first_fail} a {last_fail}."

    if isinstance(first_p0, int) and isinstance(last_p0, int):
        if last_p0 < first_p0:
            return True, f"P0 ridotti da {first_p0} a {last_p0}."
        if last_p0 > first_p0:
            return False, f"P0 peggiorati da {first_p0} a {last_p0}."

    for cycle in cycles:
        if cycle.get("improvement") is True:
            return True, "Miglioramento reale rilevato in almeno un ciclo."

    return False, "Nessun segnale forte di miglioramento reale."


def build_cycles_section(cycles: list[dict]) -> list[str]:
    lines = []

    if not cycles:
        lines.append("Nessun ciclo disponibile.")
        return lines

    for cycle in cycles:
        lines.append(f"### Cycle {cycle.get('cycle', '?')}")
        lines.append(f"- base_commit: {cycle.get('base_commit')}")
        lines.append(f"- p0_before: {cycle.get('p0_before')}")
        lines.append(f"- p0_after: {cycle.get('p0_after')}")
        lines.append(f"- failing_tests_before: {cycle.get('fail_before')}")
        lines.append(f"- failing_tests_after: {cycle.get('fail_after')}")
        lines.append(f"- targeted_failures_before: {cycle.get('target_before')}")
        lines.append(f"- targeted_failures_after: {cycle.get('target_after')}")
        lines.append(f"- improvement: {cycle.get('improvement')}")
        lines.append(f"- rollback: {cycle.get('rollback')}")
        lines.append(f"- stop_reason: {cycle.get('stop_reason', '')}")

        target_files = cycle.get("target_files", []) or []
        if target_files:
            lines.append("- target_files:")
            for item in target_files:
                kind = classify_file_kind(item)
                icon = "🧪" if kind == "test" else "🧩"
                lines.append(f"  - {icon} {item}")

        lines.append("")

    return lines


def main() -> int:
    patch_verification = read_json(AUDIT_OUT / "patch_verification.json")
    post_patch_review = read_json(AUDIT_OUT / "post_patch_review.json")
    patch_apply_report = read_json(AUDIT_OUT / "patch_apply_report.json")
    ai_repair_loop_state = read_json(AUDIT_OUT / "ai_repair_loop_state.json")

    verifier_verdict = str(patch_verification.get("verdict", "")).strip().lower()
    review_verdict = str(post_patch_review.get("final_verdict", "")).strip().lower()
    applied = bool(patch_apply_report.get("applied", False))

    tests_status = "PASS" if applied else "FAIL"
    verifier_status = normalize_status(verifier_verdict, {"approve", "weak-approve"})
    review_status = normalize_status(review_verdict, {"approve", "review"})

    cycles = ai_repair_loop_state.get("cycles", []) or []
    final_loop_status = str(ai_repair_loop_state.get("final_status", "")).strip() or "unknown"
    cycle_count = len(cycles)

    repo_materially_greener = bool(ai_repair_loop_state.get("repo_materially_greener", False))
    repo_fully_green = bool(ai_repair_loop_state.get("repo_fully_green", False))
    continuation_recommended = bool(ai_repair_loop_state.get("continuation_recommended", False))
    next_action = str(ai_repair_loop_state.get("next_action", "")).strip() or "unknown"

    touched_files = collect_touched_files(cycles)
    fix_kind = collect_fix_kinds(touched_files)

    improved_detected, improvement_reason = detect_real_improvement(cycles)
    improvement_status = "YES" if repo_materially_greener or improved_detected else "NO"

    safe_to_merge = "YES" if (
        tests_status == "PASS"
        and verifier_status == "PASS"
        and review_verdict != "reject"
        and (repo_materially_greener or improved_detected)
    ) else "NO"

    safe_badge = badge_for_safe_to_merge(safe_to_merge)
    verifier_badge = badge_for_review_verdict(verifier_verdict)
    review_badge = badge_for_review_verdict(review_verdict)
    tests_badge = "🟢 SAFE" if tests_status == "PASS" else "🔴 BLOCKED"
    greener_badge = badge_for_boolean(repo_materially_greener, "🟢 SAFE", "🟡 REVIEW")
    fully_green_badge = badge_for_boolean(repo_fully_green, "🟢 SAFE", "🟡 REVIEW")
    continuation_badge = badge_for_boolean(continuation_recommended, "🟡 REVIEW", "🟢 SAFE")
    improvement_badge = badge_for_boolean(
        repo_materially_greener or improved_detected,
        "🟢 SAFE",
        "🟡 REVIEW",
    )

    lines = []
    lines.append("# AI FINAL VERDICT")
    lines.append("")
    lines.append(f"## {safe_badge}")
    lines.append("")
    lines.append("| Campo | Stato | Dettaglio |")
    lines.append("|---|---|---|")
    lines.append(f"| Tests | {tests_badge} | {tests_status} |")
    lines.append(f"| Patch verifier | {verifier_badge} | {verifier_status} ({verifier_verdict or 'unknown'}) |")
    lines.append(f"| Post patch review | {review_badge} | {review_status} ({review_verdict or 'unknown'}) |")
    lines.append(f"| Safe to merge | {safe_badge} | {safe_to_merge} |")
    lines.append(f"| Repo materially greener | {greener_badge} | {'YES' if repo_materially_greener else 'NO'} |")
    lines.append(f"| Repo fully green | {fully_green_badge} | {'YES' if repo_fully_green else 'NO'} |")
    lines.append(f"| Continuation recommended | {continuation_badge} | {'YES' if continuation_recommended else 'NO'} |")
    lines.append(f"| Real improvement | {improvement_badge} | {improvement_status} |")
    lines.append("")
    lines.append("## Repair Loop Summary")
    lines.append(f"- Final loop status: {final_loop_status}")
    lines.append(f"- Repair cycles executed: {cycle_count}")
    lines.append(f"- Fix type: {fix_kind}")
    lines.append(f"- Repo materially greener: {'YES' if repo_materially_greener else 'NO'}")
    lines.append(f"- Repo fully green: {'YES' if repo_fully_green else 'NO'}")
    lines.append(f"- Continuation recommended: {'YES' if continuation_recommended else 'NO'}")
    lines.append(f"- Next action: {next_action}")
    lines.append(f"- Real improvement vs previous cycle: {improvement_badge} ({improvement_status})")
    lines.append(f"- Improvement note: {improvement_reason}")
    lines.append("")

    lines.append("## Files touched across cycles")
    if touched_files:
        for file in touched_files:
            kind = classify_file_kind(file)
            icon = "🧪" if kind == "test" else "🧩"
            lines.append(f"- {icon} {file} [{kind}]")
    else:
        lines.append("- Nessun file toccato.")
    lines.append("")

    lines.append("## Cycle details")
    lines.extend(build_cycles_section(cycles))

    if safe_to_merge == "YES":
        lines.append("Decisione: la PR sembra sicura da mergiare.")
    else:
        lines.append("Decisione: non mergiare finché il sistema non torna SAFE TO MERGE: YES.")

    lines.append("")

    write_text(AUDIT_OUT / "merge_summary.md", "\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())