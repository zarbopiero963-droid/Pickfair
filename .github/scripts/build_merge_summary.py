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


def main() -> int:
    patch_verification = read_json(AUDIT_OUT / "patch_verification.json")
    post_patch_review = read_json(AUDIT_OUT / "post_patch_review.json")
    patch_apply_report = read_json(AUDIT_OUT / "patch_apply_report.json")

    verifier_verdict = str(patch_verification.get("verdict", "")).strip().lower()
    review_verdict = str(post_patch_review.get("final_verdict", "")).strip().lower()
    applied = bool(patch_apply_report.get("applied", False))

    tests_status = "PASS" if applied else "FAIL"
    verifier_status = normalize_status(verifier_verdict, {"approve", "weak-approve"})
    review_status = normalize_status(review_verdict, {"approve"})

    safe_to_merge = "YES" if (
        tests_status == "PASS"
        and verifier_status == "PASS"
        and review_status == "PASS"
    ) else "NO"

    lines = []
    lines.append("# AI FINAL VERDICT")
    lines.append("")
    lines.append(f"Tests: {tests_status}")
    lines.append(f"Patch verifier: {verifier_status} ({verifier_verdict or 'unknown'})")
    lines.append(f"Post patch review: {review_status} ({review_verdict or 'unknown'})")
    lines.append("")
    lines.append(f"SAFE TO MERGE: {safe_to_merge}")
    lines.append("")

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