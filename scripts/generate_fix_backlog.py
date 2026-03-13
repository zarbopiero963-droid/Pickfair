import json
from pathlib import Path

ARTIFACTS = Path("artifacts")

REPORT_FILE = ARTIFACTS / "repo_api_report_v4.json"
OUT_JSON = ARTIFACTS / "repo_fix_backlog.json"
OUT_MD = ARTIFACTS / "repo_fix_backlog_pretty.md"


def load_report():
    if not REPORT_FILE.exists():
        raise RuntimeError(
            "Missing artifacts/repo_api_report_v4.json. Run repo_api_report_v4.py first."
        )

    return json.loads(REPORT_FILE.read_text(encoding="utf-8"))


def build_backlog(report):
    backlog = []

    for mod in report.get("modules_without_tests", []):
        backlog.append(
            {
                "priority": "P1",
                "type": "tests",
                "title": "Module without tests",
                "module": mod["module"],
                "file": mod["file"],
                "action": "create_test_file",
            }
        )

    for score, file, module in report.get("top_risky_modules", []):
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

    for item in report.get("dead_code_candidates", []):
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
        if "symbol" in item:
            lines.append(f"  - symbol: `{item['symbol']}`")

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