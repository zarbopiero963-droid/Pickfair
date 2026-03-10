import json
import sys
from pathlib import Path

COVERAGE_FILE = Path("coverage.json")

# I file blindati che DEVONO avere il 100% di test coverage. Nessuna scusa.
CRITICAL_FILES = {
    "database.py",
    "telegram_listener.py",
    "dutching.py",
    "controllers/dutching_controller.py"
}

def main() -> int:
    if not COVERAGE_FILE.exists():
        print("❌ ERRORE CRITICO: coverage.json non trovato.")
        return 1

    data = json.loads(COVERAGE_FILE.read_text(encoding="utf-8"))
    files = data.get("files", {})

    failed = []

    for filename, meta in files.items():
        normalized_name = filename.replace("\\", "/")
        
        # Applica il controllo rigido al 100% SOLO sui file core dichiarati
        if any(normalized_name.endswith(cf) for cf in CRITICAL_FILES):
            summary = meta.get("summary", {})
            pct = float(summary.get("percent_covered", 0.0))

            if pct < 100.0:
                failed.append((normalized_name, pct))

    if failed:
        print("🚨 GATE FALLITO: I seguenti file core sono sotto il 100% di coverage:")
        for filename, pct in failed:
            print(f"❌ {filename}: {pct:.2f}%")
        return 1

    print("✅ GATE SUPERATO: Tutti i file core critici hanno il 100% di coverage.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
