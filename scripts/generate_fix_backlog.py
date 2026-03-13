import json
from pathlib import Path

ARTIFACTS = Path("artifacts")

REPORT_FILE = ARTIFACTS / "repo_api_report_v4.json"

OUT_JSON = ARTIFACTS / "repo_fix_backlog.json"
OUT_MD = ARTIFACTS / "repo_fix_backlog_pretty.md"


def load_report():

    if not REPORT_FILE.exists():
        raise RuntimeError("Run repo_api_report_v4.py first")

    return json.loads(REPORT_FILE.read_text())


def build_backlog(report):

    backlog = []

    # modules without tests
    for mod in report["modules_without_tests"]:

        backlog.append(
            {
                "priority": "P1",
                "type": "tests",
                "title": "Module has no tests",
                "module": mod["module"],
                "file": mod["file"],
                "action": "create_test_file",
            }
        )

    # risky modules
    for score, file, module in report["top_risky_modules"]:

        backlog.append(
            {
                "priority": "P1",
                "type": "refactor",
                "title": "High complexity module",
                "module": module,
                "file": file,
                "score": score,
                "action": "refactor_module",
            }
        )

    # dead code
    for item in report["dead_code_candidates"]:

        backlog.append(
            {
                "priority": "P2",
                "type": "cleanup",
                "title": "Dead code candidate",
                "module": item["module"],
                "symbol": item["symbol"],
                "action": "review_or_delete",
            }
        )

    return backlog


def save_json(backlog):

    OUT_JSON.write_text(
        json.dumps(backlog, indent=2),
        encoding="utf-8",
    )


def save_markdown(backlog):

    lines = ["# Repository Fix Backlog", ""]

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

        lines.append(f"  - action: `{item['action']}`")
        lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main():

    report = load_report()

    backlog = build_backlog(report)

    save_json(backlog)
    save_markdown(backlog)

    print("✔ repo_fix_backlog.json generated")
    print("✔ repo_fix_backlog_pretty.md generated")


if __name__ == "__main__":
    main()