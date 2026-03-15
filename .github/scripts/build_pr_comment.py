#!/usr/bin/env python3

from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def extract_section(text: str, header: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    lines = text.splitlines()
    start = None

    for i, line in enumerate(lines):
        if line.strip() == header.strip():
            start = i
            break

    if start is None:
        return ""

    out = []
    for line in lines[start + 1 :]:
        if line.startswith("## ") and line.strip() != header.strip():
            break
        out.append(line)

    return "\n".join(out).strip()


def build_dashboard(merge_summary: str) -> str:
    lines = (merge_summary or "").splitlines()

    wanted_prefixes = [
        "Tests:",
        "Patch verifier:",
        "Post patch review:",
        "SAFE TO MERGE:",
        "- Final loop status:",
        "- Repair cycles executed:",
        "- Fix type:",
        "- Real improvement vs previous cycle:",
        "- Improvement note:",
    ]

    picked = []
    for line in lines:
        stripped = line.strip()
        for prefix in wanted_prefixes:
            if stripped.startswith(prefix):
                picked.append(stripped)
                break

    if not picked:
        return "_Dashboard non disponibile._"

    out = []
    out.append("| Campo | Valore |")
    out.append("|---|---|")

    for item in picked:
        if ":" not in item:
            continue
        left, right = item.split(":", 1)
        left = left.strip().lstrip("-").strip()
        right = right.strip()
        out.append(f"| {left} | {right} |")

    return "\n".join(out)


def main() -> int:
    merge_summary = read_text(AUDIT_OUT / "merge_summary.md").strip()
    loop_report = read_text(AUDIT_OUT / "ai_repair_loop_report.md").strip()
    root_cause = read_text(AUDIT_OUT / "root_cause.md").strip()
    fix_suggestions = read_text(AUDIT_OUT / "fix_suggestions.md").strip()
    patch_candidate = read_text(AUDIT_OUT / "patch_candidate.md").strip()
    patch_verification = read_text(AUDIT_OUT / "patch_verification.md").strip()
    patch_apply_report = read_text(AUDIT_OUT / "patch_apply_report.md").strip()
    post_patch_review = read_text(AUDIT_OUT / "post_patch_review.md").strip()

    dashboard = build_dashboard(merge_summary)

    files_touched_section = extract_section(merge_summary, "## Files touched across cycles")
    cycle_details_section = extract_section(merge_summary, "## Cycle details")

    pr_body = """# AI automated patch

This PR was generated automatically by the AI repair pipeline.

Included pipeline stages:
- repository audit
- failing test extraction
- AI reasoning
- priority fix selection
- test failure context
- fix context generation
- patch candidate generation
- patch verification
- patch apply
- post patch AI review
- multi-cycle AI repair loop
- final merge summary

This PR is created only when:
- the patch was actually applied
- post_patch_review returned approve

Please review the artifacts and checks before merging.
"""

    pr_comment_parts = [
        "# AI Repair Report",
        "",
        "## Executive Dashboard",
        dashboard or "_Dashboard non disponibile._",
        "",
        "## SAFE TO MERGE",
        merge_summary or "_Missing merge summary report._",
        "",
        "## Files touched across cycles",
        files_touched_section or "_Nessun file toccato o sezione non disponibile._",
        "",
        "## Cycle details",
        cycle_details_section or "_Dettagli ciclo non disponibili._",
        "",
        "## Repair Loop Report",
        loop_report or "_Missing repair loop report._",
        "",
        "## Root cause",
        root_cause or "_Missing root cause report._",
        "",
        "## Fix suggestions",
        fix_suggestions or "_Missing fix suggestions report._",
        "",
        "## Patch candidate",
        patch_candidate or "_Missing patch candidate report._",
        "",
        "## Patch verification",
        patch_verification or "_Missing patch verification report._",
        "",
        "## Patch apply report",
        patch_apply_report or "_Missing patch apply report._",
        "",
        "## Post patch AI review",
        post_patch_review or "_Missing post patch review report._",
        "",
    ]

    write_text(AUDIT_OUT / "pr_body.md", pr_body)
    write_text(AUDIT_OUT / "pr_comment.md", "\n".join(pr_comment_parts))

    print("PR body and PR comment built.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())