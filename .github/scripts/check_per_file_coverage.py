import json
from pathlib import Path

COVERAGE_FILE = Path("coverage.json")

CRITICAL_FILES = {
    "database.py",
    "telegram_listener.py",
    "dutching.py",
    "controllers/dutching_controller.py",
}

def main():

    print("CRITICAL COVERAGE CHECK")

    if not COVERAGE_FILE.exists():
        print("ERROR: coverage.json not found")
        return 1

    data = json.loads(COVERAGE_FILE.read_text())
    files = data.get("files", {})

    indexed = {}
    for filename, meta in files.items():
        normalized = filename.replace("\\", "/")
        indexed[normalized] = meta

    seen = set()
    failed = []

    for file_path, meta in indexed.items():

        for critical in CRITICAL_FILES:

            if file_path.endswith(critical):

                seen.add(critical)

                pct = float(meta["summary"]["percent_covered"])

                print("")
                print("FILE:", file_path)
                print("COVERAGE:", f"{pct:.2f}%")

                if pct < 100.0:
                    print("FAIL BELOW 100")
                    failed.append((file_path, pct))
                else:
                    print("OK")

    missing = CRITICAL_FILES - seen

    if missing:
        print("ERROR missing files in coverage report")
        for m in missing:
            print(m)
        return 1

    if failed:
        print("ERROR insufficient coverage")
        for f, pct in failed:
            print(f"{f} -> {pct:.2f}%")
        return 1

    print("ALL CRITICAL FILES AT 100% COVERAGE")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())