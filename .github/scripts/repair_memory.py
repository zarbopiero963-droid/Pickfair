#!/usr/bin/env python3

import json
import hashlib
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"

MEMORY_FILE = AUDIT_OUT / "repair_history.json"


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def compute_context_hash(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def load_memory():
    if not MEMORY_FILE.exists():
        return {
            "successful_repairs": [],
            "failed_repairs": [],
            "skipped_contexts": [],
        }

    return read_json(MEMORY_FILE)


def save_memory(memory):
    write_json(MEMORY_FILE, memory)


def register_repair_attempt(context: dict, success: bool):

    memory = load_memory()

    context_hash = compute_context_hash(context)

    entry = {
        "context_hash": context_hash,
        "target_files": context.get("target_files", []),
        "timestamp": context.get("timestamp"),
    }

    if success:
        memory["successful_repairs"].append(entry)
    else:
        memory["failed_repairs"].append(entry)

    save_memory(memory)


def context_already_attempted(context: dict) -> bool:

    memory = load_memory()

    context_hash = compute_context_hash(context)

    for item in memory.get("failed_repairs", []):
        if item.get("context_hash") == context_hash:
            return True

    for item in memory.get("successful_repairs", []):
        if item.get("context_hash") == context_hash:
            return True

    return False


def main():

    fix_context = read_json(AUDIT_OUT / "fix_context.json")

    memory = load_memory()

    filtered = []

    for ctx in fix_context.get("fix_contexts", []):

        if context_already_attempted(ctx):
            memory["skipped_contexts"].append(ctx)
            continue

        filtered.append(ctx)

    save_memory(memory)

    output = {
        "filtered_contexts": filtered
    }

    write_json(AUDIT_OUT / "filtered_fix_context.json", output)

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()