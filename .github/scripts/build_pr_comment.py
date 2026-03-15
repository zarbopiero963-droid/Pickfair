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


def main() -> int:
    merge_summary = read_text(AUDIT_OUT / "merge_summary.md").strip()
    root_cause = read_text(AUDIT_OUT / "root_cause.md").strip()
    fix_suggestions = read_text(AUDIT_OUT / "fix_suggestions.md").strip()
    patch_candidate = read_text(AUDIT_OUT / "patch_candidate.md").strip()
    patch_verification = read_text(AUDIT_OUT / "patch_verification.md").strip()
    patch_apply_report = read_text(AUDIT_OUT / "patch_apply_report.md").strip()
    post_patch_review = read_text(AUDIT_OUT / "post_patch_review.md").strip()

    pr_body = """# AI automated patch

This PR was generated automatically by the AI repair pipeline.

Included pipeline stages:
- repository audit
- AI reasoning
- patch candidate generation
- patch verification
- patch apply
- post patch AI review

This PR is created only when:
- the patch was actually applied
- post_patch_review returned approve

Please review the artifacts and checks before merging.
"""

    pr_comment_parts = [
        "# AI Repair Report",
        "",
        "## SAFE TO MERGE",
        merge_summary or "_Missing merge summary report._",
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