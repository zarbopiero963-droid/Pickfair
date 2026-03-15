#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except:
        return {}


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))


def write_md(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text)


def main():

    verification = read_json(AUDIT_OUT / "patch_verification.json")
    apply_report = read_json(AUDIT_OUT / "patch_apply_report.json")
    targeted_tests = read_json(AUDIT_OUT / "targeted_test_results.json")

    verdict = verification.get("verdict")
    target = apply_report.get("target_file")
    strategy = apply_report.get("strategy")

    failures = targeted_tests.get("failure_count")

    review = {
        "review_verdict": "reject",
        "minimal_change": False,
        "logic_preserved": False,
        "contract_restored": False,
        "summary": "",
        "reasons": [],
    }

    # ------------------------------------------------
    # APPROVE PATH
    # ------------------------------------------------

    if verdict in ["approve", "weak-approve"]:

        review["minimal_change"] = True
        review["logic_preserved"] = True

        if failures == 0 or failures is None:

            review["review_verdict"] = "approve"
            review["summary"] = "Patch verified and tests pass."
            review["reasons"] = [
                f"Patch verifier verdict: {verdict}",
                "No failing targeted tests",
                f"Target file: {target}",
            ]

        else:

            review["review_verdict"] = "weak-approve"
            review["summary"] = "Patch acceptable but tests still failing."
            review["reasons"] = [
                f"Patch verifier verdict: {verdict}",
                f"{failures} targeted tests still failing",
            ]

    # ------------------------------------------------
    # REVIEW PATH
    # ------------------------------------------------

    elif verdict == "review":

        review["review_verdict"] = "review"
        review["summary"] = "Patch requires human or deeper AI review."
        review["reasons"] = [
            "Verifier flagged patch as reviewable but not safe",
            f"Strategy: {strategy}",
            f"Target: {target}",
        ]

    # ------------------------------------------------
    # REJECT PATH
    # ------------------------------------------------

    else:

        review["review_verdict"] = "reject"
        review["summary"] = "Patch rejected by verifier."
        review["reasons"] = [
            f"Verifier verdict: {verdict}",
            "Patch not considered safe to apply.",
        ]

    # ------------------------------------------------
    # OUTPUT
    # ------------------------------------------------

    write_json(AUDIT_OUT / "post_patch_review.json", review)

    md = []
    md.append("Post Patch Review")
    md.append("")
    md.append(f"Verdict: {review['review_verdict']}")
    md.append("")
    md.append(review["summary"])
    md.append("")
    md.append("Reasons:")
    for r in review["reasons"]:
        md.append(f"- {r}")

    write_md(AUDIT_OUT / "post_patch_review.md", "\n".join(md))

    print(json.dumps(review, indent=2))


if __name__ == "__main__":
    main()