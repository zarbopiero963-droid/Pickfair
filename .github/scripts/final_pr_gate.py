#!/usr/bin/env python3

import json
import os
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return {}


def main():

    state = read_json(AUDIT_OUT / "merge_controller_state.json")

    decision = state.get("decision", "")
    reason = state.get("reason", "")

    should_merge = state.get("should_merge", False)
    should_open_pr = state.get("should_open_or_update_pr", False)

    allow_pr = False

    if decision in ["MERGE_READY", "REVIEW_ONLY"]:

        if should_open_pr:
            allow_pr = True

    print("")
    print("Final PR gate")
    print(f"Decision: {decision}")
    print(f"Reason: {reason}")
    print(f"Allow PR: {allow_pr}")
    print(f"Auto merge: {should_merge}")

    # export for workflow
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"allow_pr={str(allow_pr).lower()}\n")
        f.write(f"auto_merge={str(should_merge).lower()}\n")
        f.write(f"reason={reason}\n")

    if not allow_pr:
        print(f"Final PR gate blocked. Reason: {reason}")
        exit(1)

    print("PR gate passed.")


if __name__ == "__main__":
    main()