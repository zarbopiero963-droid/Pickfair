import json
from pathlib import Path

ARTIFACTS = Path("artifacts")

REPORT_FILE = ARTIFACTS / "repo_api_report_v4.json"

OUT_JSON = ARTIFACTS / "repo_fix_backlog.json"
OUT_MD = ARTIFACTS / "repo_fix_backlog_pretty.md"


def load_report():
    if not REPORT_FILE.exists():
        raise RuntimeError("repo_api_report_v4.json not found. Run report v4 first.")
    return json.loads(REPORT_FILE.read_text())


def build_backlog(report):

    backlog = []

    # --------------------------------------------------
    # 1 Circular imports (P0)
    # --------------------------------------------------

    for cycle in report.get("circular_imports", []):
        backlog.append(
            {
                "priority": "P0",
                "type": "architecture",
                "title": "Circular import detected",
                "description": "Break circular dependency between modules",
                "modules": cycle,
                "action": "refactor_import_structure",
            }
        )

    # --------------------------------------------------
    # 2 Modules without tests (P1)
    # --------------------------------------------------

    for item in report["coverage_nominal"]["modules_without_nominal_tests"]:
        backlog.append(
            {
                "priority": "P1",
                "type": "tests",
                "title": "Module has no tests",
                "module": item["module"],
                "file": item["file"],
                "action": "create_test_file",
            }
        )

    # --------------------------------------------------
    # 3 Public API without tests (P1)
    # --------------------------------------------------

    for item in report["coverage_nominal"]["uncovered_symbols"]:

        backlog.append(
            {
                "priority": "P1",
                "type": "tests",
                "title": "Public API without tests",
                "module": item["module"],
                "symbol": item["symbol"],
                "action": "create_unit_test",
            }
        )

    # --------------------------------------------------
    # 4 Dead code candidates (P2)
    # --------------------------------------------------

    for item in report["dead_code_candidates"]:
        backlog.append(
            {
                "priority": "P2",
                "type": "cleanup",
                "title": "Dead code candidate",
                "module": item["module"],
                "symbol": item["symbol"],
                "line": item["line"],
                "action": "review_or_delete",
            }
        )

    # --------------------------------------------------
    # 5 Refactor priority modules
    # --------------------------------------------------

    for item in report["refactor_priority"][:40]:

        backlog.append(
            {
                "priority": item["priority"],
                "type": "refactor",
                "title": "High complexity module",
                "module": item["module"],
                "file": item["file"],
                "score": item["score"],
                "uncovered_public_symbols": item["uncovered_public_symbols"],
                "action": "split_or_refactor_module",
            }
        )

    return backlog


def save_json(backlog):

    OUT_JSON.write_text(
        json.dumps(backlog, indent=2),
        encoding="utf-8",
    )


def save_markdown(backlog):

    lines = []

    lines.append("# Repository Fix Backlog")
    lines.append("")

    for item in backlog:

        lines.append(
            f"- **{item['priority']}** {item['title']}"
        )

        if "module" in item:
            lines.append(f"  - module: `{item['module']}`")

        if "symbol" in item:
            lines.append(f"  - symbol: `{item['symbol']}`")

        if "file" in item:
            lines.append(f"  - file: `{item['file']}`")

        if "modules" in item:
            lines.append(f"  - modules: `{', '.join(item['modules'])}`")

        lines.append(f"  - action: `{item['action']}`")
        lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main():

    report = load_report()

    backlog = build_backlog(report)

    save_json(backlog)
    save_markdown(backlog)

    print("===================================")
    print("FIX BACKLOG GENERATED")
    print("===================================")

    print(f"[OK] {OUT_JSON}")
    print(f"[OK] {OUT_MD}")
    print("")
    print(f"Total tasks: {len(backlog)}")


if __name__ == "__main__":
    main()