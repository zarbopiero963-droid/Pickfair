#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main():
    apply = read_json(AUDIT_OUT / "patch_apply_report.json")
    verify = read_json(AUDIT_OUT / "patch_verification.json")
    review = read_json(AUDIT_OUT / "post_patch_review.json")

    applied = apply.get("applied", False)
    verifier = verify.get("verdict", "")
    review_verdict = review.get("review_verdict", "")

    stop_reason = "unknown"
    continue_loop = False

    if not applied:
        stop_reason = "no_patch_applied"

    elif verifier == "reject":
        stop_reason = "verifier_reject"

    elif review_verdict == "reject":
        stop_reason = "review_reject"

    elif review_verdict in ("approve", "weak-approve"):
        stop_reason = "ready_for_pr"

    else:
        continue_loop = True
        stop_reason = "needs_more_iterations"

    result = {
        "continue": continue_loop,
        "stop_reason": stop_reason,
        "applied": applied,
        "verifier": verifier,
        "review": review_verdict,
    }

    write_json(AUDIT_OUT / "ai_repair_loop_state.json", result)

    report = [
        "AI Repair Loop",
        "",
        f"Continue: {continue_loop}",
        f"Stop reason: {stop_reason}",
        "",
        f"Applied: {applied}",
        f"Verifier: {verifier}",
        f"Review: {review_verdict}",
    ]

    write_text(AUDIT_OUT / "ai_repair_loop_report.md", "\n".join(report))

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()