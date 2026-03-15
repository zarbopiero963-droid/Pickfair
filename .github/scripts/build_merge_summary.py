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


def collect_touched_files(cycles: list[dict]) -> list[str]:
    touched = []
    seen = set()

    for cycle in cycles:
        for item in cycle.get("target_files", []) or []:
            if item not in seen:
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

    p0_before_values = [c.get("p0_before") for c in cycles if c.get("p0_before") is not None]
    p0_after_values = [c.get("p0_after") for c in cycles if c.get("p0_after") is not None]

    if p0_before_values and p0_after_values:
        first_before = p0_before_values[0]
        last_after = p0_after_values[-1]

        if isinstance(first_before, int) and isinstance(last_after, int):
            if last_after < first_before:
                return True, f"P0 ridotti da {first_before} a {last_after}."
            if last_after == 0 and first_before == 0:
                return False, "Nessun P0 rilevato già all'inizio."
            if last_after == first_before:
                return False, f"Nessuna riduzione P0: ancora {last_after}."
            if last_after > first_before:
                return False, f"P0 peggiorati da {first_before} a {last_after}."

    for cycle in cycles:
        verdict = str(cycle.get("post_patch_review_verdict", "")).strip().lower()
        applied = bool(cycle.get("patch_applied", False))
        if applied and verdict == "approve":
            return True, "Almeno un ciclo ha applicato una patch approvata."

    return False, "Nessun segnale forte di miglioramento reale."


def build_cycles_section(cycles: list[dict]) -> list[str]:
    lines = []

    if not cycles:
        lines.append("Nessun ciclo disponibile.")
        return lines

    for cycle in cycles:
        lines.append(f"### Cycle {cycle.get('cycle', '?')}")
        lines.append(f"- p0_before: {cycle.get('p0_before')}")
        lines.append(f"- p0_after: {cycle.get('p0_after')}")
        lines.append(f"- patch_generated: {cycle.get('patch_generated')}")
        lines.append(f"- patch_verifier_verdict: {cycle.get('patch_verifier_verdict')}")
        lines.append(f"- patch_applied: {cycle.get('patch_applied')}")
        lines.append(f"- post_patch_review_verdict: {cycle.get('post_patch_review_verdict')}")
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
    review_status = normalize_status(review_verdict, {"approve"})

    cycles = ai_repair_loop_state.get("cycles", []) or []
    final_loop_status = str(ai_repair_loop_state.get("final_status", "")).strip() or "unknown"
    cycle_count = len(cycles)

    touched_files = collect_touched_files(cycles)
    fix_kind = collect_fix_kinds(touched_files)
    improved, improvement_reason = detect_real_improvement(cycles)
    improvement_status = "YES" if improved else "NO"

    safe_to_merge = "YES" if (
        tests_status == "PASS"
        and verifier_status == "PASS"
        and review_status == "PASS"
    ) else "NO"

    safe_badge = badge_for_safe_to_merge(safe_to_merge)
    verifier_badge = badge_for_review_verdict(verifier_verdict)
    review_badge = badge_for_review_verdict(review_verdict)
    tests_badge = "🟢 SAFE" if tests_status == "PASS" else "🔴 BLOCKED"
    improvement_badge = "🟢 SAFE" if improved else "🟡 REVIEW"

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
    lines.append("")
    lines.append("## Repair Loop Summary")
    lines.append(f"- Final loop status: {final_loop_status}")
    lines.append(f"- Repair cycles executed: {cycle_count}")
    lines.append(f"- Fix type: {fix_kind}")
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