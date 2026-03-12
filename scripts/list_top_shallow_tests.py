import json
from pathlib import Path

INPUT_PATH = Path("artifacts/shallow_tests_report.json")


def main():
    if not INPUT_PATH.exists():
        raise SystemExit(
            f"Missing report {INPUT_PATH}. Run scripts/find_shallow_tests.py first."
        )

    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    rows = []

    for file_result in data.get("files", []):
        for test in file_result.get("tests", []):
            if test.get("shallow_score", 0) >= 2:
                rows.append(
                    (
                        test["shallow_score"],
                        file_result["file"],
                        test["name"],
                        test["line"],
                        test["flags"],
                    )
                )

    rows.sort(reverse=True)

    print("======================================================================")
    print("TOP SHALLOW TESTS")
    print("======================================================================")
    for score, file_path, name, line, flags in rows[:50]:
        print(
            f"[score={score}] {file_path}::{name} "
            f"(line {line}) flags={', '.join(flags)}"
        )


if __name__ == "__main__":
    main()