#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"


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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize_path(path_str: str) -> str:
    raw = str(path_str or "").strip().replace("\\", "/")
    if not raw:
        return ""
    try:
        p = Path(raw)
        if p.is_absolute():
            return str(p.resolve().relative_to(ROOT)).replace("\\", "/")
    except Exception:
        pass
    return raw.lstrip("./")


def issue_rank(issue_type: str) -> int:
    rank = {
        "missing_public_contract": 0,
        "contract_test_failure": 1,
        "runtime_failure": 2,
        "lint_failure": 3,
        "test_failure": 4,
        "missing_nominal_test": 5,
        "ci_failure": 6,
        "generic": 9,
    }
    return rank.get(str(issue_type or "").strip(), 99)


def priority_rank(priority: str) -> int:
    return {"P0": 0, "P1": 1, "P2": 2}.get(str(priority or "").strip().upper(), 9)


def classify_smell(item: dict) -> str:
    issue_type = str(item.get("issue_type", "")).strip()
    target_file = normalize_path(item.get("target_file", ""))

    if issue_type in {"runtime_failure", "lint_failure", "test_failure"}:
        return "active_failure"
    if issue_type in {"missing_public_contract", "contract_test_failure"}:
        return "contract_risk"
    if issue_type == "missing_nominal_test":
        return "coverage_gap"
    if target_file.startswith("tests/"):
        return "test_area"
    return "generic"


def collect_priorities(fix_context: dict, cto_layer: dict) -> list[dict]:
    cto_map = {}
    for item in cto_layer.get("repair_order", []) or []:
        file_path = normalize_path(item.get("file", ""))
        if file_path and file_path not in cto_map:
            cto_map[file_path] = item

    items = []
    for item in fix_context.get("fix_contexts", []) or []:
        target_file = normalize_path(item.get("target_file", ""))
        if not target_file:
            continue

        related_source_file = normalize_path(item.get("related_source_file", ""))
        issue_type = str(item.get("issue_type", "")).strip() or "generic"
        priority = str(item.get("priority", "")).strip().upper() or "P2"
        cto = cto_map.get(target_file) or cto_map.get(related_source_file) or {}

        items.append(
            {
                "target_file": target_file,
                "related_source_file": related_source_file,
                "priority": priority,
                "issue_type": issue_type,
                "classification": str(item.get("classification", "")).strip(),
                "cto_priority": str(cto.get("priority", "")).strip(),
                "cto_kind": str(cto.get("kind", "")).strip(),
                "related_tests": item.get("related_tests", []) or [],
                "notes": item.get("notes", []) or [],
                "smell": classify_smell(item),
            }
        )

    items.sort(
        key=lambda x: (
            priority_rank(x.get("priority", "")),
            issue_rank(x.get("issue_type", "")),
            0 if str(x.get("classification", "")).strip() == "AUTO_FIX_SAFE" else 1,
            normalize_path(x.get("target_file", "")),
        )
    )
    return items


def extract_targets_by_priority(items: list[dict], wanted_priority: str) -> list[str]:
    out = []
    seen = set()
    for item in items:
        if str(item.get("priority", "")).strip().upper() != wanted_priority:
            continue
        target = normalize_path(item.get("target_file", ""))
        if target and target not in seen:
            seen.add(target)
            out.append(target)
    return out


def extract_tests_to_run(items: list[dict]) -> list[str]:
    out = []
    seen = set()
    for item in items:
        for test in item.get("related_tests", []) or []:
            test = normalize_path(test)
            if test and test not in seen:
                seen.add(test)
                out.append(test)
    return out[:12]


def extract_fragile_modules(items: list[dict]) -> list[str]:
    out = []
    seen = set()
    for item in items:
        target = normalize_path(item.get("target_file", ""))
        if not target or target.startswith("tests/") or target.startswith(".github/"):
            continue
        if target in seen:
            continue
        seen.add(target)
        out.append(target)
    return out[:10]


def extract_smells(items: list[dict]) -> list[str]:
    out = []
    seen = set()
    for item in items:
        smell = str(item.get("smell", "")).strip()
        if smell and smell not in seen:
            seen.add(smell)
            out.append(smell)
    return out[:8]


def build_markdown(items: list[dict]) -> str:
    p0_targets = extract_targets_by_priority(items, "P0")
    p1_targets = extract_targets_by_priority(items, "P1")
    p2_targets = extract_targets_by_priority(items, "P2")
    tests_to_run = extract_tests_to_run(items)
    fragile_modules = extract_fragile_modules(items)
    smells = extract_smells(items)

    lines = []
    lines.append("Priority Fix Order")
    lines.append("Sì. Questo file ordina i fix nel modo più utile per sbloccare la CI senza fare modifiche inutili.")
    lines.append("Strategia consigliata")
    lines.append("1. Chiudere prima i blocker di contratto pubblico.")
    lines.append("2. Rilanciare solo i test direttamente collegati.")
    lines.append("3. Solo dopo passare ai moduli fragili e agli smells.")
    lines.append("")

    lines.append("P0 — da sistemare subito")
    if p0_targets:
        for item in p0_targets:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessun P0 rilevato.")

    lines.append("P1 — fix consigliati subito dopo i P0")
    if p1_targets:
        for item in p1_targets:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessun P1 suggerito.")

    lines.append("P2 — da verificare dopo che la CI riparte")
    if p2_targets:
        for item in p2_targets:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessun P2 suggerito.")

    lines.append("Test da rilanciare prima")
    if tests_to_run:
        for item in tests_to_run:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessun test mirato disponibile.")

    lines.append("Top moduli fragili da controllare dopo i blocker")
    if fragile_modules:
        for item in fragile_modules:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessun modulo in ranking.")

    lines.append("Smells principali")
    if smells:
        for item in smells:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessuno.")

    lines.append("Ordine operativo consigliato")
    if p0_targets:
        for idx, item in enumerate(p0_targets[:5], start=1):
            lines.append(f"{idx}. {item}")
    elif p1_targets:
        for idx, item in enumerate(p1_targets[:5], start=1):
            lines.append(f"{idx}. {item}")
    else:
        lines.append("1. nessun blocker contrattuale immediato")

    lines.append("Verdetto finale")
    if p0_targets:
        lines.append("Esistono blocker reali: va sistemato prima il gruppo P0.")
    else:
        lines.append("Non emergono blocker contrattuali immediati; puoi passare ai fix sui moduli fragili.")

    return "\n".join(lines)


def main() -> int:
    fix_context = read_json(AUDIT_OUT / "fix_context.json")
    cto_layer = read_json(AUDIT_OUT / "ai_cto_layer.json")

    items = collect_priorities(fix_context, cto_layer)

    payload = {
        "items": items,
        "summary": {
            "P0_count": len(extract_targets_by_priority(items, "P0")),
            "P1_count": len(extract_targets_by_priority(items, "P1")),
            "P2_count": len(extract_targets_by_priority(items, "P2")),
            "tests_to_run_count": len(extract_tests_to_run(items)),
        },
    }

    md = build_markdown(items)

    write_json(AUDIT_OUT / "priority_fix_order.json", payload)
    write_text(AUDIT_OUT / "priority_fix_order.md", md)

    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())