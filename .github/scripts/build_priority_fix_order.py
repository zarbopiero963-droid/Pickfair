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


def normalize_contracts(raw_contracts):
    normalized = []

    for item in raw_contracts or []:
        if isinstance(item, dict):
            file = item.get("file", "sconosciuto")
            symbol = item.get("symbol", item.get("title", "sconosciuto"))
            normalized.append((file, symbol))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            normalized.append((str(item[0]), str(item[1])))
        elif isinstance(item, str):
            normalized.append((item, "symbol"))
    return normalized


def normalize_ranking(raw_ranking):
    normalized = []

    for item in raw_ranking or []:
        if isinstance(item, dict):
            file = item.get("file", "sconosciuto")
            score = item.get("score", "?")
            normalized.append((file, score))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            normalized.append((str(item[0]), item[1]))
        elif isinstance(item, str):
            normalized.append((item, "?"))
    return normalized


def group_fixes(contracts, ai_reasoning):
    p0 = []
    p1 = []
    p2 = []

    seen = set()

    for file, symbol in contracts:
        key = (file, symbol)
        if key in seen:
            continue
        seen.add(key)

        p0.append({
            "title": f"Ripristinare simbolo pubblico {symbol}",
            "file": file,
            "why": f"I test si aspettano {symbol} dal modulo {file}.",
            "tests": [],
        })

    for item in ai_reasoning.get("fix_suggestions", []):
        title = item.get("title", "Fix suggestion")
        files = item.get("files", [])
        change = item.get("change", "")
        risk = item.get("risk", "unknown")

        entry = {
            "title": title,
            "files": files,
            "change": change,
            "risk": risk,
        }

        if risk == "low":
            p1.append(entry)
        else:
            p2.append(entry)

    return p0, p1, p2


def collect_targeted_tests(ai_reasoning):
    tests = []
    seen = set()

    for block in ai_reasoning.get("targeted_tests", []):
        for test in block.get("tests", []):
            if test not in seen:
                seen.add(test)
                tests.append(test)

    return tests


def build_report(audit_machine, ai_reasoning):
    contracts = normalize_contracts(audit_machine.get("contracts", []))
    ranking = normalize_ranking(audit_machine.get("ranking", []))
    smells = audit_machine.get("smells", {})

    p0, p1, p2 = group_fixes(contracts, ai_reasoning)
    targeted_tests = collect_targeted_tests(ai_reasoning)

    lines = []

    lines.append("Priority Fix Order")
    lines.append("")
    lines.append("Sì. Questo file ordina i fix nel modo più utile per sbloccare la CI senza fare modifiche inutili.")
    lines.append("")
    lines.append("Strategia consigliata")
    lines.append("")
    lines.append("1. Chiudere prima i blocker di contratto pubblico.")
    lines.append("2. Rilanciare solo i test direttamente collegati.")
    lines.append("3. Solo dopo passare ai moduli fragili e agli smells.")
    lines.append("")

    lines.append("P0 — da sistemare subito")
    if p0:
        for idx, item in enumerate(p0, start=1):
            lines.append(f"{idx}. {item['title']}")
            lines.append(f"   - file: {item['file']}")
            lines.append(f"   - motivo: {item['why']}")
    else:
        lines.append("- Nessun P0 rilevato.")
    lines.append("")

    lines.append("P1 — fix consigliati subito dopo i P0")
    if p1:
        for idx, item in enumerate(p1, start=1):
            lines.append(f"{idx}. {item['title']}")
            files = item.get("files", [])
            if files:
                lines.append(f"   - file: {', '.join(files)}")
            lines.append(f"   - modifica: {item.get('change', '')}")
            lines.append(f"   - rischio: {item.get('risk', 'unknown')}")
    else:
        lines.append("- Nessun P1 suggerito.")
    lines.append("")

    lines.append("P2 — da verificare dopo che la CI riparte")
    if p2:
        for idx, item in enumerate(p2, start=1):
            lines.append(f"{idx}. {item['title']}")
            files = item.get("files", [])
            if files:
                lines.append(f"   - file: {', '.join(files)}")
            lines.append(f"   - modifica: {item.get('change', '')}")
            lines.append(f"   - rischio: {item.get('risk', 'unknown')}")
    else:
        lines.append("- Nessun P2 suggerito.")
    lines.append("")

    lines.append("Test da rilanciare prima")
    if targeted_tests:
        for test in targeted_tests:
            lines.append(f"- {test}")
    else:
        lines.append("- Nessun targeted test suggerito.")
    lines.append("")

    lines.append("Top moduli fragili da controllare dopo i blocker")
    if ranking:
        for file, score in ranking[:10]:
            lines.append(f"- {file} (score {score})")
    else:
        lines.append("- Nessun modulo in ranking.")
    lines.append("")

    lines.append("Smells principali")
    if smells:
        for key, value in smells.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- Nessuno.")
    lines.append("")

    lines.append("Ordine operativo consigliato")
    lines.append("")
    if contracts:
        unique_files = []
        seen_files = set()
        for file, _symbol in contracts:
            if file not in seen_files:
                seen_files.add(file)
                unique_files.append(file)

        for idx, file in enumerate(unique_files, start=1):
            lines.append(f"{idx}. sistemare {file}")
    else:
        lines.append("1. nessun blocker contrattuale immediato")
    lines.append("")

    lines.append("Verdetto finale")
    if contracts:
        lines.append(
            "La mossa corretta è chiudere prima i simboli pubblici mancanti. Tutto il resto viene dopo."
        )
    else:
        lines.append(
            "Non emergono blocker contrattuali immediati; puoi passare ai fix sui moduli fragili."
        )
    lines.append("")

    return "\n".join(lines)


def main():
    audit_machine = read_json(AUDIT_OUT / "audit_machine.json")
    ai_reasoning = read_json(AUDIT_OUT / "ai_reasoning.json")

    report = build_report(audit_machine, ai_reasoning)
    write_text(AUDIT_OUT / "priority_fix_order.md", report)

    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())