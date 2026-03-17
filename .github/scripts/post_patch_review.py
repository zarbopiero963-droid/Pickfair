#!/usr/bin/env python3

import json
from pathlib import Path

AUDIT_OUT = Path("audit_out")


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except:
        return {}


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2))


def main():
    verifier = read_json(AUDIT_OUT / "patch_verification.json")
    tests = read_json(AUDIT_OUT / "targeted_tests.json")

    verdict = "reject"
    reason = "unknown"

    if verifier.get("verdict") == "accept":
        if tests.get("success", False):
            verdict = "accept"
            reason = "patch_valid_and_tests_passed"
        else:
            verdict = "reject"
            reason = "tests_failed"
    else:
        verdict = "reject"
        reason = verifier.get("reason", "verifier_reject")

    result = {
        "verdict": verdict,
        "reason": reason
    }

    write_json(AUDIT_OUT / "post_patch_review.json", result)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()