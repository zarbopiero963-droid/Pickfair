import json
from pathlib import Path

COVERAGE_FILE = Path("coverage.json")

# FILE CRITICI DEL CORE TRADING ENGINE
CRITICAL_FILES = {
    "database.py",
    "dutching.py",
    "controllers/dutching_controller.py",
    "main.py",
    "telegram_listener.py",
    "telegram_sender.py",
    "core/trading_engine.py",
    "core/risk_middleware.py",
    "app_modules/telegram_module.py",
}


def main() -> int:

    print("================================")
    print("CRITICAL COVERAGE GATE START")
    print("================================")

    if not COVERAGE_FILE.exists():
        print("❌ ERRORE: coverage.json non trovato")
        return 1

    data = json.loads(COVERAGE_FILE.read_text(encoding="utf-8"))
    files = data.get("files", {})

    indexed = {}

    for filename, meta in files.items():
        normalized = filename.replace("\\", "/")
        indexed[normalized] = meta

    failed = []
    seen = set()

    print("\nAnalisi file critici...\n")

    for normalized_name, meta in indexed.items():

        for critical in CRITICAL_FILES:

            if normalized_name.endswith(critical):

                seen.add(critical)

                summary = meta.get("summary", {})

                pct = float(summary.get("percent_covered", 0.0))
                covered = summary.get("covered_lines", 0)
                missing = summary.get("missing_lines", 0)
                statements = summary.get("num_statements", 0)

                print(f"FILE: {normalized_name}")
                print(f"Statements: {statements}")
                print(f"Covered: {covered}")
                print(f"Missing: {missing}")
                print(f"Coverage: {pct:.2f}%")

                if pct < 100.0:
                    print("❌ FAIL - sotto 100%")
                    failed.append((normalized_name, pct))
                else:
                    print("✅ OK")

                print("")

    missing = sorted(CRITICAL_FILES - seen)

    if missing:

        print("🚨 GATE FALLITO: file critici mancanti dal report coverage:")

        for name in missing:
            print(f"❌ {name}: non presente nel coverage.json")

        return 1

    if failed:

        print("🚨 GATE FALLITO: file critici sotto il 100%:")

        for filename, pct in failed:
            print(f"❌ {filename} -> {pct:.2f}%")

        return 1

    print("================================")
    print("✅ GATE SUPERATO")
    print("TUTTI I FILE CRITICI SONO AL 100%")
    print("================================")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())