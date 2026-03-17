#!/usr/bin/env python3

import json
import os
from pathlib import Path

AUDIT_OUT = Path("audit_out")


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_output(key: str, value: str):
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        return
    with open(github_output, "a", encoding="utf-8") as f:
        f.write(f"{key}={value}\n")


def main():
    merge_state = read_json(AUDIT_OUT / "merge_controller_state.json")
    patch_apply = read_json(AUDIT_OUT / "patch_apply_report.json")
    patch_review = read_json(AUDIT_OUT / "post_patch_review.json")

    decision = str(merge_state.get("decision", "")).strip().upper()
    merge_reason = str(merge_state.get("reason", "")).strip() or "unknown"
    should_merge = bool(merge_state.get("should_merge", False))
    should_open_pr = bool(merge_state.get("should_open_pr", False))
    auto_merge_safe = bool(merge_state.get("auto_merge_safe", False))
    patch_applied = bool(patch_apply.get("applied", False))
    review_verdict = str(patch_review.get("verdict", "")).strip().lower()

    allow_pr = False
    auto_merge = False
    real_progress = False
    reason = merge_reason

    print("Final PR gate")

    if not patch_applied:
        allow_pr = False
        auto_merge = False
        real_progress = False
        reason = "patch_not_applied"

    elif decision == "MERGE_READY" and should_open_pr:
        allow_pr = True
        auto_merge = bool(should_merge and auto_merge_safe)
        real_progress = True
        reason = merge_reason or "merge_ready"

    elif decision == "REVIEW_ONLY" and should_open_pr:
        allow_pr = True
        auto_merge = False
        real_progress = True
        reason = merge_reason or "review_only"

    elif review_verdict == "accept" and patch_applied:
        allow_pr = True
        auto_merge = False
        real_progress = True
        reason = merge_reason or "accepted_patch"

    else:
        allow_pr = False
        auto_merge = False
        real_progress = False
        reason = merge_reason or "block"

    print(f"Decision: {'OPEN_PR' if allow_pr else 'BLOCK'}")
    print(f"Reason: {reason}")
    print(f"Allow PR: {allow_pr}")
    print(f"Auto merge: {auto_merge}")
    print(f"Real progress: {real_progress}")

    write_output("allow_pr", str(allow_pr).lower())
    write_output("auto_merge", str(auto_merge).lower())
    write_output("reason", reason)
    write_output("real_progress", str(real_progress).lower())

    if not allow_pr:
        print("Final PR gate blocked.")
        raise SystemExit(1)

    print("PR gate passed.")


if __name__ == "__main__":
    main()