#!/usr/bin/env python3

import json
import subprocess
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"


MAX_REPAIR_CYCLES = 3


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_script(script):

    print("")
    print(f"RUNNING {script}")
    print("")

    result = subprocess.run(
        ["python", script],
        cwd=ROOT,
        capture_output=False,
        text=True,
    )

    if result.returncode != 0:
        print(f"Script failed: {script}")
        return False

    return True


def count_p0():

    fix_context = read_json(AUDIT_OUT / "fix_context.json")

    contexts = fix_context.get("fix_contexts", [])

    p0 = [c for c in contexts if c.get("priority") == "P0"]

    return len(p0)


def patch_generated():

    patch = read_json(AUDIT_OUT / "patch_candidate.json")

    patches = patch.get("proposed_patches", [])

    return len(patches) > 0


def patch_applied():

    report = read_json(AUDIT_OUT / "patch_apply_report.json")

    return bool(report.get("applied", False))


def main():

    for cycle in range(1, MAX_REPAIR_CYCLES + 1):

        print("")
        print("=" * 60)
        print(f"AI REPAIR CYCLE {cycle}")
        print("=" * 60)

        run_script(".github/scripts/repo_ultra_audit_narrative.py")

        run_script(".github/scripts/build_fix_context.py")

        p0_count = count_p0()

        print("")
        print(f"P0 remaining: {p0_count}")

        if p0_count == 0:
            print("No P0 remaining. Stopping repair loop.")
            return 0

        run_script(".github/scripts/patch_candidate_generator.py")

        if not patch_generated():
            print("No patch generated. Stopping.")
            return 0

        run_script(".github/scripts/patch_verifier.py")

        verification = read_json(AUDIT_OUT / "patch_verification.json")

        verdict = str(verification.get("verdict", "")).lower()

        print(f"Verifier verdict: {verdict}")

        if verdict not in ["approve", "weak-approve"]:
            print("Patch rejected by verifier.")
            return 0

        run_script(".github/scripts/apply_patch_candidate.py")

        if not patch_applied():
            print("Patch not applied.")
            return 0

        run_script(".github/scripts/post_patch_review.py")

        review = read_json(AUDIT_OUT / "post_patch_review.json")

        verdict = str(review.get("final_verdict", "")).lower()

        print(f"Post review verdict: {verdict}")

        if verdict == "reject":
            print("Patch rejected in post review.")
            return 0

    print("")
    print("Max repair cycles reached.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())