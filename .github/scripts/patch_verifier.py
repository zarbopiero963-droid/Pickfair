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


def main():
    report = read_json(AUDIT_OUT / "patch_apply_report.json")

    applied = report.get("applied", False)
    changed_files = report.get("applied_targets", [])

    verdict = "reject"
    reason = "no_changes"

    if applied and changed_files:
        verdict = "accept"
        reason = "real_changes_detected"
    elif applied and not changed_files:
        verdict = "reject"
        reason = "no_committable_change"

    result = {
        "verdict": verdict,
        "reason": reason,
        "changed_files": changed_files,
    }

    write_json(AUDIT_OUT / "patch_verification.json", result)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()