import json
from pathlib import Path

ARTIFACTS = Path("artifacts")

REPORT_FILE = ARTIFACTS / "repo_api_report_v4.json"
OUT_JSON = ARTIFACTS / "repo_fix_backlog.json"
OUT_MD = ARTIFACTS / "repo_fix_backlog_pretty.md"

LOW_PRIORITY_MODULES = {
    "__init__",
    "build",
    "theme",
    "trading_config",
}


def load_report():
    if not REPORT_FILE.exists():
        raise RuntimeError(
            "Missing artifacts/repo_api_report_v4.json. Run repo_api_report_v4.py first."
        )

    return json.loads(REPORT_FILE.read_text(encoding="utf-8"))


def priority_from_score(score):
    if score >= 700:
        return "P0"
    if score >= 350:
        return "P1"
    return "P2"


def build_backlog(report):
    backlog = []
    seen = set()

    # 1. moduli senza test diretto
    for item in report.get("modules_without_direct_tests", []):
        module_short = item["module"].split(".")[-1]
        if module_short in LOW_PRIORITY_MODULES:
            continue

        key = ("direct_test_missing", item["module"])
        if key in seen:
            continue
        seen.add(key)

        backlog.append(
            {
                "priority": "P1",
                "type": "tests",
                "title": "Module without direct test file",
                "module": item["module"],
                "file": item["file"],
                "action": "create_test_file",
            }
        )

    # 2. simboli pubblici non coperti nominalmente
    uncovered_by_module = {}
    for item in report.get("uncovered_public_symbols", []):
        uncovered_by_module.setdefault(item["module"], []).append(item)

    for module, items in uncovered_by_module.items():
        key = ("uncovered_symbols", module)
        if key in seen:
            continue
        seen.add(key)

        backlog.append(
            {
                "priority": "P1" if len(items) >= 4 else "P2",
                "type": "tests",
                "title": "Public symbols without nominal tests",
                "module": module,
                "file": items[0]["file"],
                "symbols": [x["symbol"] for x in items[:10]],
                "count": len(items),
                "action": "add_targeted_tests",
            }
        )

    # 3. moduli complessi
    for item in report.get("top_risky_modules", []):
        key = ("risky_module", item["module"])
        if key in seen:
            continue
        seen.add(key)

        backlog.append(
            {
                "priority": priority_from_score(item["score"]),
                "type": "refactor",
                "title": "High complexity module",
                "module": item["module"],
                "file": item["file"],
                "score": item["score"],
                "uncovered_public_symbols": item["uncovered_public_symbols"],
                "has_direct_test_file": item["has_direct_test_file"],
                "action": "refactor_module",
            }
        )

    # 4. dead code candidati veri
    for item in report.get("dead_code_candidates", []):
        key = ("dead_code", item["module"], item["symbol"])
        if key in seen:
            continue
        seen.add(key)

        backlog.append(
            {
                "priority": "P2",
                "type": "cleanup",
                "title": "Dead code candidate",
                "module": item["module"],
                "file": item["file"],
                "symbol": item["symbol"],
                "line": item["line"],
                "action": "review_or_delete",
            }
        )

    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    backlog.sort(
        key=lambda x: (
            priority_order.get(x["priority"], 9),
            x["type"],
            x.get("module", ""),
            x.get("title", ""),
        )
    )

    return backlog


def save_json(backlog):
    OUT_JSON.write_text(
        json.dumps(backlog, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def save_markdown(backlog):
    lines = ["# Repository Fix Backlog", ""]

    for item in backlog:
        lines.append(f"- **{item['priority']}** {item['title']}")

        if "module" in item:
            lines.append(f"  - module: `{item['module']}`")
        if "file" in item:
            lines.append(f"  - file: `{item['file']}`")
        if "score" in item:
            lines.append(f"  - score: `{item['score']}`")
        if "symbol" in item:
            lines.append(f"  - symbol: `{item['symbol']}`")
        if "symbols" in item:
            lines.append(f"  - symbols: `{', '.join(item['symbols'])}`")
        if "count" in item:
            lines.append(f"  - uncovered count: `{item['count']}`")
        if "has_direct_test_file" in item:
            lines.append(f"  - has direct test file: `{item['has_direct_test_file']}`")

        lines.append(f"  - action: `{item['action']}`")
        lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main():
    report = load_report()
    backlog = build_backlog(report)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    save_json(backlog)
    save_markdown(backlog)

    print(f"Generated: {OUT_JSON}")
    print(f"Generated: {OUT_MD}")


if __name__ == "__main__":
    main()