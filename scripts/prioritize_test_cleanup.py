import json
from pathlib import Path

INPUT_PATH = Path("artifacts/shallow_tests_report.json")


def priority_for_flags(flags):
    flags = set(flags)

    if "always_true" in flags or "no_asserts" in flags:
        return "P0"

    if "type_only_module_import" in flags and "is_not_none_only" in flags:
        return "P1"

    if "is_not_none_only" in flags or "bool_in_true_false" in flags:
        return "P2"

    if "len_ge_zero" in flags:
        return "P3"

    return "P4"


def main():
    if not INPUT_PATH.exists():
        raise SystemExit(
            f"Missing input report: {INPUT_PATH}. Run scripts/find_shallow_tests.py first."
        )

    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    items = []

    for file_result in data.get("files", []):
        for test in file_result.get("tests", []):
            if test.get("shallow_score", 0) <= 0:
                continue

            priority = priority_for_flags(test.get("flags", []))
            items.append(
                {
                    "priority": priority,
                    "file": file_result["file"],
                    "test": test["name"],
                    "line": test["line"],
                    "flags": test["flags"],
                }
            )

    items.sort(key=lambda x: (x["priority"], x["file"], x["line"]))

    out_dir = Path("artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "test_cleanup_priority.json"
    out_path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

    print("======================================================================")
    print("TEST CLEANUP PRIORITY")
    print("======================================================================")
    for item in items:
        print(
            f"[{item['priority']}] {item['file']}::{item['test']} "
            f"(line {item['line']}) flags={', '.join(item['flags'])}"
        )

    print()
    print(f"[OK] Priority file written to: {out_path}")


if __name__ == "__main__":
    main()