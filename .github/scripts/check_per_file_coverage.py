import json
from pathlib import Path

COVERAGE_FILE = Path("coverage.json")

CRITICAL_FILES = {
    "database.py",
    "telegram_listener.py",
    "dutching.py",
    "controllers/dutching_controller.py",
}

def main() -> int:
    if not COVERAGE_FILE.exists():
        print("❌ ERRORE CRITICO: coverage.json non trovato.")
        return 1

    data = json.loads(COVERAGE_FILE.read_text(encoding="utf-8"))
    files = data.get("files", {})

    indexed = {}
    for filename, meta in files.items():
        normalized = filename.replace("\\", "/")
        indexed[normalized] = meta

    failed = []
    seen_critical = set()

    for normalized_name, meta in indexed.items():
        for critical in CRITICAL_FILES:
            if normalized_name.endswith(critical):
                seen_critical.add(critical)
                pct = float(meta.get("summary", {}).get("percent_covered", 0.0))
                if pct < 100.0:
                    failed.append((normalized_name, pct))

    missing = sorted(CRITICAL_FILES - seen_critical)
    if missing:
        print("🚨 GATE FALLITO: file critici mancanti dal report coverage:")
        for name in missing:
            print(f"❌ {name}: assente da coverage.json")
        return 1

    if failed:
        print("🚨 GATE FALLITO: file critici sotto il 100%:")
        for filename, pct in failed:
            print(f"❌ {filename}: {pct:.2f}%")
        return 1

    print("✅ GATE SUPERATO: tutti i file critici sono al 100% di coverage.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
