#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"

INPUT_CANDIDATES = {
    "repo_api_report_v4": [
        ROOT / "audit_out" / "repo_api_report_v4.json",
        ROOT / "repo_api_report_v4.json",
    ],
    "repo_autopsy_summary": [
        ROOT / "audit_out" / "repo_autopsy_summary.json",
        ROOT / "repo_autopsy_summary.json",
        ROOT / "audit_out" / "repo_autopsy.json",
        ROOT / "repo_autopsy.json",
    ],
    "repo_fix_backlog": [
        ROOT / "audit_out" / "repo_fix_backlog.json",
        ROOT / "repo_fix_backlog.json",
    ],
}

MAX_PRIORITIES = 50
MAX_REASONS = 6


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


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def first_existing(candidates: list[Path]):
    for path in candidates:
        if path.exists():
            return path
    return None


def trim_list(items, limit: int) -> list[str]:
    out = []
    seen = set()

    for item in items or []:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
        if len(out) >= limit:
            break

    return out


def normalize_path(path_str: str) -> str:
    return str(path_str or "").strip().replace("\\", "/")


def safe_int(value, default=0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def load_sources() -> tuple[dict, dict]:
    resolved = {}
    payload = {}

    for key, candidates in INPUT_CANDIDATES.items():
        found = first_existing(candidates)
        resolved[key] = str(found.relative_to(ROOT)).replace("\\", "/") if found else ""
        payload[key] = read_json(found) if found else {}

    return resolved, payload


def build_api_symbol_entries(api_report: dict) -> list[dict]:
    result = []
    items = (
        api_report.get("public_symbols_without_nominal_tests")
        or api_report.get("symbols_without_tests")
        or api_report.get("untested_public_symbols")
        or []
    )

    for item in items:
        if isinstance(item, dict):
            file_path = normalize_path(item.get("file") or item.get("path") or item.get("module") or "")
            symbol = str(item.get("symbol") or item.get("name") or item.get("public_symbol") or "").strip()
        else:
            file_path = ""
            symbol = str(item).strip()

        if not symbol:
            continue

        result.append(
            {
                "kind": "missing_nominal_tests",
                "file": file_path,
                "symbol": symbol,
                "priority": "P1",
                "reasons": [
                    "Simbolo pubblico senza test nominale.",
                    "Aumenta la sicurezza del self-healing.",
                ],
            }
        )

    return result


def build_module_without_tests_entries(api_report: dict) -> list[dict]:
    result = []
    items = (
        api_report.get("modules_without_direct_tests")
        or api_report.get("modules_without_tests")
        or []
    )

    for item in items:
        if isinstance(item, dict):
            file_path = normalize_path(item.get("file") or item.get("path") or item.get("module") or "")
        else:
            file_path = normalize_path(item)

        if not file_path:
            continue

        result.append(
            {
                "kind": "module_without_direct_tests",
                "file": file_path,
                "symbol": "",
                "priority": "P1",
                "reasons": [
                    "Modulo senza test diretti.",
                    "Meglio aggiungere smoke/nominal tests prima di patch complesse.",
                ],
            }
        )

    return result


def build_dead_code_entries(api_report: dict) -> list[dict]:
    result = []
    items = api_report.get("dead_code_candidates") or api_report.get("dead_code") or []

    for item in items:
        if isinstance(item, dict):
            file_path = normalize_path(item.get("file") or item.get("path") or "")
            symbol = str(item.get("symbol") or item.get("name") or "").strip()
        else:
            file_path = ""
            symbol = str(item).strip()

        if not file_path and not symbol:
            continue

        result.append(
            {
                "kind": "dead_code_candidate",
                "file": file_path,
                "symbol": symbol,
                "priority": "P2",
                "reasons": [
                    "Candidato codice morto.",
                    "Da rivedere manualmente prima di rimuovere.",
                ],
            }
        )

    return result


def build_autopsy_entries(autopsy: dict) -> list[dict]:
    result = []
    items = autopsy.get("prod_top_classes") or autopsy.get("top_classes") or []

    for item in items:
        if not isinstance(item, dict):
            continue

        file_path = normalize_path(item.get("file") or item.get("path") or "")
        class_name = str(item.get("class") or item.get("class_name") or "").strip()
        size_hint = safe_int(item.get("methods") or item.get("method_count") or item.get("weight") or 0)

        if not file_path:
            continue

        reasons = [
            "Area architetturalmente pesante secondo repo autopsy.",
            "Richiede patch piccole e conservative.",
        ]
        if size_hint > 0:
            reasons.append(f"Indicatore dimensione/complessità: {size_hint}.")

        result.append(
            {
                "kind": "complex_production_area",
                "file": file_path,
                "symbol": class_name,
                "priority": "P1",
                "reasons": reasons,
            }
        )

    return result


def build_backlog_entries(backlog: dict) -> list[dict]:
    result = []
    items = backlog.get("items") or backlog.get("backlog") or []

    for item in items:
        if not isinstance(item, dict):
            continue

        file_path = normalize_path(item.get("file") or item.get("path") or "")
        title = str(item.get("title") or item.get("summary") or "").strip()
        action = str(item.get("action") or "").strip()
        priority = str(item.get("priority") or "P2").strip().upper()

        if priority not in {"P0", "P1", "P2"}:
            priority = "P2"

        if not file_path and not title:
            continue

        reasons = []
        if title:
            reasons.append(title)
        if action:
            reasons.append(f"Azione suggerita: {action}")
        reasons.append(f"Priorità backlog: {priority}")

        result.append(
            {
                "kind": "backlog_priority",
                "file": file_path,
                "symbol": "",
                "priority": priority,
                "reasons": reasons,
            }
        )

    return result


def merge_entries(entries: list[dict]) -> list[dict]:
    merged = {}

    for item in entries:
        file_path = normalize_path(item.get("file", ""))
        symbol = str(item.get("symbol", "")).strip()
        kind = str(item.get("kind", "")).strip()
        priority = str(item.get("priority", "P2")).strip().upper()

        key = (file_path, symbol, kind)

        if key not in merged:
            merged[key] = {
                "kind": kind,
                "file": file_path,
                "symbol": symbol,
                "priority": priority,
                "reasons": [],
                "score": 0,
            }

        dst = merged[key]

        if priority == "P0":
            dst["priority"] = "P0"
        elif priority == "P1" and dst["priority"] != "P0":
            dst["priority"] = "P1"

        existing = set(dst["reasons"])
        for reason in item.get("reasons", []) or []:
            reason = str(reason).strip()
            if not reason or reason in existing:
                continue
            dst["reasons"].append(reason)
            existing.add(reason)

    return list(merged.values())


def score_entry(item: dict) -> int:
    score = 0

    priority = str(item.get("priority", "P2")).strip().upper()
    kind = str(item.get("kind", "")).strip()
    file_path = normalize_path(item.get("file", ""))
    symbol = str(item.get("symbol", "")).strip()

    if priority == "P0":
        score += 300
    elif priority == "P1":
        score += 180
    else:
        score += 60

    if kind == "backlog_priority":
        score += 80
    elif kind == "missing_nominal_tests":
        score += 120
    elif kind == "module_without_direct_tests":
        score += 90
    elif kind == "complex_production_area":
        score += 70
    elif kind == "dead_code_candidate":
        score += 10

    if file_path.startswith("tests/"):
        score -= 20
    elif file_path.startswith(".github/"):
        score -= 40
    elif file_path.endswith(".py"):
        score += 25

    if "hft" in file_path.lower():
        score -= 60

    if symbol:
        score += 10

    score += min(len(item.get("reasons", []) or []), MAX_REASONS) * 4
    return score


def build_repair_order(entries: list[dict]) -> list[dict]:
    for item in entries:
        item["score"] = score_entry(item)
        item["reasons"] = trim_list(item.get("reasons", []), MAX_REASONS)

    entries.sort(
        key=lambda x: (
            {"P0": 0, "P1": 1, "P2": 2}.get(str(x.get("priority", "P2")).upper(), 3),
            -int(x.get("score", 0)),
            normalize_path(x.get("file", "")),
            str(x.get("symbol", "")),
        )
    )

    result = []
    for item in entries[:MAX_PRIORITIES]:
        result.append(
            {
                "kind": item.get("kind", ""),
                "file": item.get("file", ""),
                "symbol": item.get("symbol", ""),
                "priority": item.get("priority", "P2"),
                "score": item.get("score", 0),
                "reasons": item.get("reasons", []),
            }
        )

    return result


def build_summary(repair_order: list[dict]) -> dict:
    summary = {
        "P0": 0,
        "P1": 0,
        "P2": 0,
        "top_kind_counts": {},
    }

    for item in repair_order:
        priority = str(item.get("priority", "P2")).upper()
        kind = str(item.get("kind", "")).strip()

        if priority in summary:
            summary[priority] += 1

        summary["top_kind_counts"][kind] = summary["top_kind_counts"].get(kind, 0) + 1

    return summary


def main() -> int:
    resolved, payload = load_sources()

    api_report = payload["repo_api_report_v4"]
    autopsy = payload["repo_autopsy_summary"]
    backlog = payload["repo_fix_backlog"]

    entries = []
    entries.extend(build_api_symbol_entries(api_report))
    entries.extend(build_module_without_tests_entries(api_report))
    entries.extend(build_dead_code_entries(api_report))
    entries.extend(build_autopsy_entries(autopsy))
    entries.extend(build_backlog_entries(backlog))

    merged = merge_entries(entries)
    repair_order = build_repair_order(merged)

    result = {
        "sources": resolved,
        "summary": build_summary(repair_order),
        "repair_order": repair_order,
    }

    write_json(AUDIT_OUT / "ai_cto_layer.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())