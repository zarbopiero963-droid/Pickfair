#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def main():

    verification = read_json(AUDIT_OUT / "patch_verification.json")
    review = read_json(AUDIT_OUT / "post_patch_review.json")
    candidate = read_json(AUDIT_OUT / "patch_candidate.json")

    verifier_verdict = verification.get("verdict", "reject")
    review_verdict = review.get("review_verdict", "reject")

    classification = (
        candidate.get("patch_candidate", {})
        .get("classification", "")
    )

    result = {
        "auto_merge": False,
        "merge_reason": "",
        "merge_allowed": False
    }

    # ------------------------
    # APPROVE
    # ------------------------

    if review_verdict == "approve":

        result["auto_merge"] = True
        result["merge_allowed"] = True
        result["merge_reason"] = "review_approved"

    # ------------------------
    # WEAK APPROVE
    # ------------------------

    elif review_verdict == "weak-approve":

        if classification == "AUTO_FIX_SAFE":

            result["auto_merge"] = True
            result["merge_allowed"] = True
            result["merge_reason"] = "weak_approve_safe"

        else:

            result["auto_merge"] = False
            result["merge_allowed"] = True
            result["merge_reason"] = "weak_approve_requires_review"

    # ------------------------
    # REVIEW
    # ------------------------

    elif review_verdict == "review":

        result["auto_merge"] = False
        result["merge_allowed"] = True
        result["merge_reason"] = "review_required"

    # ------------------------
    # REJECT
    # ------------------------

    else:

        result["auto_merge"] = False
        result["merge_allowed"] = False
        result["merge_reason"] = "patch_rejected"

    write_json(
        AUDIT_OUT / "merge_decision.json",
        result
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()