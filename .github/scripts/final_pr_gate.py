#!/usr/bin/env python3

import json
import os
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


def write_output(key: str, value: str):

    github_output = os.environ.get("GITHUB_OUTPUT")

    if not github_output:
        return

    with open(github_output, "a") as f:
        f.write(f"{key}={value}\n")


def normalize(v):
    return str(v).strip().lower()


def main():

    patch_apply = read_json(AUDIT_OUT / "patch_apply_report.json")
    verification = read_json(AUDIT_OUT / "patch_verification.json")
    review = read_json(AUDIT_OUT / "post_patch_review.json")
    merge_state = read_json(AUDIT_OUT / "merge_controller_state.json")

    applied = bool(patch_apply.get("applied", False))

    verifier_verdict = normalize(verification.get("verdict", "reject"))
    review_verdict = normalize(
        review.get("review_verdict", review.get("final_verdict", "reject"))
    )

    merge_allowed = bool(merge_state.get("merge_allowed", False))
    auto_merge = bool(merge_state.get("auto_merge", False))

    reason = "unknown"
    allow_pr = False
    real_progress = False

    print("Final PR gate")

    # -----------------------------
    # NO PATCH APPLIED
    # -----------------------------

    if not applied:

        reason = "no_patch_applied"
        allow_pr = False
        real_progress = False

    # -----------------------------
    # PATCH REJECTED
    # -----------------------------

    elif verifier_verdict == "reject" or review_verdict == "reject":

        reason = "patch_rejected"
        allow_pr = False
        real_progress = False

    # -----------------------------
    # REVIEW PATCH
    # -----------------------------

    elif review_verdict == "review":

        reason = "reviewable_patch"
        allow_pr = True
        real_progress = True
        auto_merge = False

    # -----------------------------
    # WEAK APPROVE
    # -----------------------------

    elif review_verdict == "weak-approve":

        reason = "weak_approve_patch"
        allow_pr = True
        real_progress = True

    # -----------------------------
    # APPROVE
    # -----------------------------

    elif review_verdict == "approve":

        reason = "approved_patch"
        allow_pr = True
        real_progress = True

    # -----------------------------
    # FALLBACK
    # -----------------------------

    else:

        reason = "rolled_back_no_committable_change"
        allow_pr = False
        real_progress = False

    # -----------------------------
    # MERGE POLICY
    # -----------------------------

    if not merge_allowed:
        auto_merge = False

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
        exit(1)

    print("PR gate passed.")


if __name__ == "__main__":
    main()