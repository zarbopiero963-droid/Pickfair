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


def load_contexts():
    return {
        "classification": read_json(AUDIT_OUT / "issue_classification.json"),
        "repo_diag": read_json(AUDIT_OUT / "repo_diagnostics_context.json"),
        "test_gap": read_json(AUDIT_OUT / "test_gap_generation_report.json"),
        "fix_context": read_json(AUDIT_OUT / "fix_context.json"),
    }


def pick_from_safe(classified):
    for item in classified:
        if item.get("classification") == "AUTO_FIX_SAFE":
            return item
    return None


def pick_from_review(classified):
    for item in classified:
        if item.get("classification") == "AUTO_FIX_REVIEW":
            return item
    return None


def pick_from_runtime_failures(fix_context):
    for item in fix_context.get("fix_contexts", []):
        if item.get("issue_type") == "runtime_failure":
            if item.get("target_file"):
                return item
    return None


def pick_from_generated_tests(test_gap):
    tests = test_gap.get("generated_tests", [])
    if not tests:
        return None

    t = tests[0]

    return {
        "issue_type": "missing_nominal_test",
        "target_file": t.get("generated_test_file"),
        "related_source_file": t.get("source_file"),
        "notes": ["generated nominal test from repo diagnostics"],
    }


def generate_patch_candidate(contexts):

    classification = contexts["classification"]
    repo_diag = contexts["repo_diag"]
    test_gap = contexts["test_gap"]
    fix_context = contexts["fix_context"]

    classified = classification.get("fix_contexts", [])

    target = None
    strategy = None

    target = pick_from_safe(classified)
    if target:
        strategy = "safe_auto_fix"

    if not target:
        target = pick_from_review(classified)
        if target:
            strategy = "reviewable_fix"

    if not target:
        target = pick_from_runtime_failures(fix_context)
        if target:
            strategy = "runtime_target_fix"

    if not target:
        target = pick_from_generated_tests(test_gap)
        if target:
            strategy = "generate_nominal_test"

    if not target:
        return None

    return {
        "strategy": strategy,
        "target_file": target.get("target_file"),
        "related_source_file": target.get("related_source_file"),
        "issue_type": target.get("issue_type"),
        "notes": target.get("notes", []),
    }


def main():

    contexts = load_contexts()

    patch = generate_patch_candidate(contexts)

    if not patch:
        result = {
            "patch_candidate": None,
            "reason": "no_viable_target",
        }

    else:
        result = {
            "patch_candidate": patch,
            "reason": "target_selected",
        }

    write_json(AUDIT_OUT / "patch_candidate.json", result)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main() 