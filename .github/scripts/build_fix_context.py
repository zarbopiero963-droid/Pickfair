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


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize_path(path_str: str) -> str:
    raw = str(path_str or "").strip().replace("\\", "/")
    if not raw:
        return ""
    while raw.startswith("./"):
        raw = raw[2:]
    return raw


def unique_keep(items: list[str]) -> list[str]:
    out = []
    seen = set()
    for item in items:
        value = normalize_path(item)
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def priority_for_issue(issue_type: str) -> str:
    issue_type = str(issue_type or "").strip()
    if issue_type in {"missing_public_contract", "runtime_failure", "lint_failure"}:
        return "P0"
    if issue_type in {"test_failure", "ci_failure", "contract_test_failure"}:
        return "P1"
    return "P2"


def main() -> int:
    ci_payload = read_json(AUDIT_OUT / "ci_failure_context.json")
    if not ci_payload:
        ci_payload = read_json(AUDIT_OUT / "ci_failures.json")

    tf_payload = read_json(AUDIT_OUT / "test_failure_context.json")
    tf_map = {}
    for item in tf_payload.get("test_failure_contexts", []) or []:
        key = normalize_path(item.get("target_file", ""))
        if key:
            tf_map[key] = item

    fix_contexts = []
    seen = set()

    for item in ci_payload.get("ci_failures", []) or []:
        target_file = normalize_path(item.get("target_file", ""))
        issue_type = str(item.get("issue_type", "")).strip()
        if not target_file:
            continue

        tf_ctx = tf_map.get(target_file, {})
        ctx = {
            "target_file": target_file,
            "required_symbols": [],
            "related_tests": unique_keep(tf_ctx.get("related_tests", []) or []),
            "related_fixtures": [],
            "related_contracts": [],
            "notes": [str(item.get("signal", "")).strip()] if str(item.get("signal", "")).strip() else [],
            "priority": priority_for_issue(issue_type),
            "issue_type": issue_type,
            "related_source_file": normalize_path(tf_ctx.get("related_source_file", "")),
        }

        key = (
            ctx["target_file"],
            ctx["issue_type"],
            ctx["priority"],
            ctx["related_source_file"],
        )
        if key in seen:
            continue
        seen.add(key)
        fix_contexts.append(ctx)

    result = {
        "fix_contexts": fix_contexts,
        "summary": {
            "count": len(fix_contexts),
            "P0": sum(1 for x in fix_contexts if x.get("priority") == "P0"),
            "P1": sum(1 for x in fix_contexts if x.get("priority") == "P1"),
            "P2": sum(1 for x in fix_contexts if x.get("priority") == "P2"),
        },
    }

    write_json(AUDIT_OUT / "fix_context.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())