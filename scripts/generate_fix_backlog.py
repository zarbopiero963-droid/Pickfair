import json
from pathlib import Path

ARTIFACTS = Path("artifacts")

REPORT = ARTIFACTS / "repo_api_report_v4.json"

OUT_JSON = ARTIFACTS / "repo_fix_backlog.json"

OUT_MD = ARTIFACTS / "repo_fix_backlog_pretty.md"


def load_report():

    if not REPORT.exists():
        raise RuntimeError("Run repo_api_report_v4.py first")

    return json.loads(REPORT.read_text())


def build_backlog(report):

    backlog = []

    for mod in report["modules_without_tests"]:

        backlog.append(
            {
                "priority": "P1",
                "type": "tests",
                "module": mod["module"],
                "file": mod["file"],
                "action": "create_test_file",
            }
        )

    for item in report["dead_code_candidates"]:

        backlog.append(
            {
                "priority": "P2",
                "type": "cleanup",
                "module": item["module"],
                "symbol": item["symbol"],
                "action": "review_or_delete",
            }
        )

    for score, file, module in report["top_risky_modules"]:

        backlog.append(
            {
                "priority": "P1",
                "type": "refactor",
                "module": module,
                "file": file,
                "score": score,
                "action": "refactor_module",
            }
        )

    return backlog


def save(backlog):

    OUT_JSON.write_text(
        json.dumps(backlog, indent=2),
        encoding="utf-8",
    )

    lines = ["# Fix backlog", ""]

    for item in backlog:

        lines.append(
            f"- **{item['priority']}** {item['type']} → `{item.get('module','')}`"
        )

    OUT_MD.write_text("\n".join(lines))


def main():

    report = load_report()

    backlog = build_backlog(report)

    save(backlog)

    print("Backlog generated")

    print(OUT_JSON)


if __name__ == "__main__":
    main()