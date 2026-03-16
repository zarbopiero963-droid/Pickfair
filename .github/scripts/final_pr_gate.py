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


def has_real_progress(loop_state: dict, apply_report: dict) -> bool:
    if not bool(apply_report.get("applied", False)):
        return False

    cycles = loop_state.get("cycles", []) or []
    if not cycles:
        return False

    last = cycles[-1]
    if bool(last.get("rollback", False)):
        return False
    if not bool(last.get("improvement", False)):
        return False

    return True


def main() -> int:
    merge_state = read_json(AUDIT_OUT / "merge_controller_state.json")
    loop_state = read_json(AUDIT_OUT / "ai_repair_loop_state.json")
    apply_report = read_json(AUDIT_OUT / "patch_apply_report.json")

    decision = str(merge_state.get("decision", "")).strip()
    reason = str(merge_state.get("reason", "")).strip()

    should_merge = bool(merge_state.get("should_merge", False))
    should_open_pr = bool(merge_state.get("should_open_or_update_pr", False))
    real_progress = has_real_progress(loop_state, apply_report)

    allow_pr = False

    if decision in {"MERGE_READY", "REVIEW_ONLY"} and should_open_pr and real_progress:
        allow_pr = True

    if not real_progress and reason in {"approved_patch", "reviewable_patch", "block"}:
        reason = "no_real_committable_change"

    print("")
    print("Final PR gate")
    print(f"Decision: {decision}")
    print(f"Reason: {reason}")
    print(f"Allow PR: {allow_pr}")
    print(f"Auto merge: {should_merge}")
    print(f"Real progress: {real_progress}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"allow_pr={str(allow_pr).lower()}\n")
            f.write(f"auto_merge={str(should_merge and allow_pr).lower()}\n")
            f.write(f"reason={reason}\n")
            f.write(f"real_progress={str(real_progress).lower()}\n")

    if not allow_pr:
        print(f"Final PR gate blocked cleanly. Reason: {reason}")
        return 0

    print("PR gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main()) 