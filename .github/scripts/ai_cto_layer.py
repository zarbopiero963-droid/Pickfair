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
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def normalize(path):
    return str(path).replace("\\", "/").lstrip("./")


def collect_ci_failures():
    data = read_json(AUDIT_OUT / "ci_failures.json")
    return data.get("ci_failures", [])


def collect_backlog():
    data = read_json(AUDIT_OUT / "repo_fix_backlog.json")
    return data.get("fix_backlog", [])


def collect_api_report():
    data = read_json(AUDIT_OUT / "repo_api_report_v4.json")
    return data.get("api_issues", [])


def classify_priority(issue):

    issue_type = issue.get("issue_type", "")
    target = issue.get("target_file", "")

    if issue_type in ["runtime_failure", "ci_failure"]:
        return "P0"

    if issue_type in ["test_failure", "lint_failure"]:
        return "P1"

    if issue_type == "code_smell":
        return "P2"

    return "P2"


def build_priority_list(ci_failures, backlog, api_issues):

    items = []

    for f in ci_failures:
        priority = classify_priority(f)

        items.append({
            "priority": priority,
            "source": "ci_failure",
            "target_file": normalize(f.get("target_file")),
            "issue_type": f.get("issue_type"),
            "signal": f.get("signal")
        })

    for b in backlog:
        items.append({
            "priority": "P2",
            "source": "backlog",
            "target_file": normalize(b.get("file")),
            "issue_type": b.get("type"),
            "signal": b.get("description")
        })

    for a in api_issues:
        items.append({
            "priority": "P1",
            "source": "api_report",
            "target_file": normalize(a.get("file")),
            "issue_type": a.get("issue"),
            "signal": a.get("detail")
        })

    return items


def group_priorities(items):

    result = {
        "P0": [],
        "P1": [],
        "P2": []
    }

    for item in items:

        p = item.get("priority", "P2")

        if p not in result:
            p = "P2"

        result[p].append(item)

    return result


def main():

    ci_failures = collect_ci_failures()
    backlog = collect_backlog()
    api_issues = collect_api_report()

    items = build_priority_list(ci_failures, backlog, api_issues)

    grouped = group_priorities(items)

    result = {
        "cto_priority": grouped,
        "summary": {
            "P0_count": len(grouped["P0"]),
            "P1_count": len(grouped["P1"]),
            "P2_count": len(grouped["P2"])
        }
    }

    write_json(
        AUDIT_OUT / "ai_cto_layer.json",
        result
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()