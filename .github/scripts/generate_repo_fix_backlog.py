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


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    autopsy = read_json(AUDIT_OUT / "repo_autopsy_summary.json")
    api_report = read_json(AUDIT_OUT / "repo_api_report_v4.json")

    items = []

    for cls in autopsy.get("prod_top_classes", [])[:20]:
        method_count = int(cls.get("method_count", 0) or 0)
        priority = "P1" if method_count >= 12 else "P2"
        items.append(
            {
                "priority": priority,
                "file": cls.get("file", ""),
                "title": f"Complex production area: {cls.get('class_name', '')}",
                "action": "refactor_module" if priority == "P1" else "review_complexity",
            }
        )

    for item in api_report.get("modules_without_direct_tests", [])[:80]:
        items.append(
            {
                "priority": "P1",
                "file": item.get("file", ""),
                "title": "Module without direct tests",
                "action": "add_nominal_tests",
            }
        )

    for item in api_report.get("public_symbols_without_nominal_tests", [])[:120]:
        items.append(
            {
                "priority": "P1",
                "file": item.get("file", ""),
                "title": f"Public symbol without nominal test: {item.get('symbol', '')}",
                "action": "add_nominal_test",
            }
        )

    result = {"items": items[:200]}

    pretty_lines = ["# Repo Fix Backlog", ""]
    for item in result["items"]:
        pretty_lines.append(
            f"- [{item['priority']}] {item['file']} — {item['title']} — action={item['action']}"
        )

    write_json(AUDIT_OUT / "repo_fix_backlog.json", result)
    write_text(AUDIT_OUT / "repo_fix_backlog_pretty.md", "\n".join(pretty_lines))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())