#!/usr/bin/env python3

import json
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


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def normalize(path):
    if not path:
        return ""
    return str(path).replace("\\", "/").lstrip("./")


def classify_issue(ctx: dict):
    target = normalize(ctx.get("target_file", ""))
    issue_type = str(ctx.get("issue_type", "")).strip()

    if issue_type == "missing_public_contract":
        return "AUTO_FIX_SAFE"

    if issue_type == "contract_test_failure":
        return "AUTO_FIX_REVIEW"

    if issue_type == "runtime_failure":
        if target.endswith(".py") and not target.startswith("tests/"):
            return "AUTO_FIX_REVIEW"

    if issue_type == "lint_failure":
        return "AUTO_FIX_SAFE"

    if issue_type == "test_failure":
        return "AUTO_FIX_REVIEW"

    if issue_type == "ci_failure":
        return "AUTO_FIX_REVIEW"

    return "MANUAL"


def main():
    fix_context = read_json(AUDIT_OUT / "fix_context.json")

    contexts = fix_context.get("fix_contexts", [])

    classified = []

    for ctx in contexts:
        classification = classify_issue(ctx)

        classified.append(
            {
                "target_file": ctx.get("target_file", ""),
                "issue_type": ctx.get("issue_type", ""),
                "priority": ctx.get("priority", ""),
                "classification": classification,
                "related_tests": ctx.get("related_tests", []),
                "related_fixtures": ctx.get("related_fixtures", []),
                "related_contracts": ctx.get("related_contracts", []),
                "notes": ctx.get("notes", []),
            }
        )

    result = {
        "issue_classification": classified
    }

    write_json(AUDIT_OUT / "issue_classification.json", result)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()