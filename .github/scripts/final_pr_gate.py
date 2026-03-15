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


def main() -> int:
    state = read_json(AUDIT_OUT / "merge_controller_state.json")

    decision = str(state.get("decision", "")).strip()
    reason = str(state.get("reason", "")).strip()

    should_merge = bool(state.get("should_merge", False))
    should_open_pr = bool(state.get("should_open_or_update_pr", False))

    allow_pr = False

    if decision in {"MERGE_READY", "REVIEW_ONLY"} and should_open_pr:
        allow_pr = True

    print("")
    print("Final PR gate")
    print(f"Decision: {decision}")
    print(f"Reason: {reason}")
    print(f"Allow PR: {allow_pr}")
    print(f"Auto merge: {should_merge}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"allow_pr={str(allow_pr).lower()}\n")
            f.write(f"auto_merge={str(should_merge).lower()}\n")
            f.write(f"reason={reason}\n")

    if not allow_pr:
        print(f"Final PR gate blocked. Reason: {reason}")
        raise SystemExit(1)

    print("PR gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())