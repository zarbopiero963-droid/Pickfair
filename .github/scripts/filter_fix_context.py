#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"

MAX_CONTEXTS = 8


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def read_json(path: Path):
    try:
        return json.loads(read_text(path))
    except Exception:
        return {}


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def normalize_path(p: str) -> str:
    return str(p or "").strip()


def load_repair_history():
    return read_json(AUDIT_OUT / "repair_history.json")


def load_fix_context():
    data = read_json(AUDIT_OUT / "fix_context.json")
    return data.get("fix_contexts", [])


def build_attempted_set(history: dict):
    attempted = set()

    for item in history.get("failed_repairs", []):
        attempted.add(normalize_path(item.get("target_file")))

    for item in history.get("skipped_contexts", []):
        attempted.add(normalize_path(item.get("target_file")))

    return attempted


def main():

    fix_contexts = load_fix_context()
    repair_history = load_repair_history()

    attempted = build_attempted_set(repair_history)

    filtered = []
    skipped = []

    for ctx in fix_contexts:

        target_file = normalize_path(ctx.get("target_file"))

        if not target_file:
            continue

        if target_file in attempted:
            skipped.append(ctx)
            continue

        filtered.append(ctx)

    filtered = filtered[:MAX_CONTEXTS]

    result = {
        "filtered_contexts": filtered,
        "skipped_contexts": skipped,
        "summary": {
            "total_input": len(fix_contexts),
            "filtered_out": len(skipped),
            "remaining": len(filtered),
        },
    }

    write_json(AUDIT_OUT / "filtered_fix_context.json", result)

    print(json.dumps(result, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())