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


def pick_existing(name_candidates: list[str]) -> tuple[str, dict]:
    for name in name_candidates:
        path = AUDIT_OUT / name
        data = read_json(path)
        if data:
            return name, data
    return "", {}


def extract_modules_without_direct_tests(api_report: dict) -> list[str]:
    items = api_report.get("modules_without_direct_tests", []) or api_report.get("modules_without_tests", []) or []
    out = []
    seen = set()
    for item in items:
        if isinstance(item, dict):
            file_path = normalize_path(item.get("file", ""))
        else:
            file_path = normalize_path(item)
        if file_path and file_path not in seen:
            seen.add(file_path)
            out.append(file_path)
    return out[:30]


def extract_public_symbols_without_nominal_tests(api_report: dict) -> list[dict]:
    items = (
        api_report.get("public_symbols_without_nominal_tests", [])
        or api_report.get("symbols_without_tests", [])
        or []
    )
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        file_path = normalize_path(item.get("file", ""))
        symbol = str(item.get("symbol", "")).strip()
        if file_path and symbol:
            out.append(
                {
                    "file": file_path,
                    "symbol": symbol,
                    "kind": str(item.get("kind", "")).strip(),
                }
            )
    return out[:120]


def extract_dead_code_candidates(api_report: dict) -> list[dict]:
    items = api_report.get("dead_code_candidates", []) or []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        file_path = normalize_path(item.get("file", ""))
        symbol = str(item.get("symbol", "")).strip()
        if file_path or symbol:
            out.append(
                {
                    "file": file_path,
                    "symbol": symbol,
                    "reason": str(item.get("reason", "")).strip(),
                }
            )
    return out[:40]


def extract_shallow_test_files(api_report: dict) -> list[str]:
    items = api_report.get("shallow_test_files", []) or []
    out = []
    seen = set()
    for item in items:
        if isinstance(item, dict):
            file_path = normalize_path(item.get("file", ""))
        else:
            file_path = normalize_path(item)
        if file_path and file_path not in seen:
            seen.add(file_path)
            out.append(file_path)
    return out[:30]


def extract_complex_areas(autopsy_summary: dict, backlog: dict) -> list[dict]:
    out = []
    seen = set()

    for item in autopsy_summary.get("prod_top_classes", []) or []:
        if not isinstance(item, dict):
            continue
        file_path = normalize_path(item.get("file", ""))
        if not file_path or file_path in seen:
            continue
        seen.add(file_path)
        out.append(
            {
                "file": file_path,
                "kind": "prod_top_class",
                "name": str(item.get("class", "")).strip(),
                "score": item.get("score", 0),
            }
        )

    for item in backlog.get("fix_backlog", []) or backlog.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        file_path = normalize_path(item.get("file", ""))
        if not file_path or file_path in seen:
            continue
        kind = str(item.get("kind", "")).strip()
        priority = str(item.get("priority", "")).strip()
        if priority in {"P0", "P1"} or kind in {"high_complexity_module", "complex_runtime"}:
            seen.add(file_path)
            out.append(
                {
                    "file": file_path,
                    "kind": kind or "backlog_item",
                    "name": str(item.get("title", "")).strip(),
                    "score": item.get("score", 0),
                }
            )

    return out[:40]


def summarize(
    modules_without_tests: list[str],
    symbols_without_tests: list[dict],
    dead_code: list[dict],
    shallow_tests: list[str],
    complex_areas: list[dict],
    backlog_payload: dict,
) -> dict:
    backlog_items = backlog_payload.get("fix_backlog", []) or backlog_payload.get("items", []) or []
    return {
        "modules_without_direct_tests": len(modules_without_tests),
        "public_symbols_without_nominal_tests": len(symbols_without_tests),
        "dead_code_candidates": len(dead_code),
        "shallow_test_files": len(shallow_tests),
        "backlog_items": len(backlog_items),
        "top_complex_areas": len(complex_areas),
    }


def main() -> int:
    api_report_name, api_report = pick_existing(
        [
            "repo_api_report_v4.json",
            "repo_api_report.json",
        ]
    )
    autopsy_summary_name, autopsy_summary = pick_existing(
        [
            "repo_autopsy_summary.json",
            "repo_autopsy.json",
        ]
    )
    backlog_name, backlog = pick_existing(
        [
            "repo_fix_backlog.json",
        ]
    )

    modules_without_tests = extract_modules_without_direct_tests(api_report)
    symbols_without_tests = extract_public_symbols_without_nominal_tests(api_report)
    dead_code = extract_dead_code_candidates(api_report)
    shallow_tests = extract_shallow_test_files(api_report)
    complex_areas = extract_complex_areas(autopsy_summary, backlog)

    payload = {
        "sources": {
            "repo_api_report_v4": api_report_name,
            "repo_autopsy_summary": autopsy_summary_name,
            "repo_fix_backlog": backlog_name,
        },
        "summary": summarize(
            modules_without_tests,
            symbols_without_tests,
            dead_code,
            shallow_tests,
            complex_areas,
            backlog,
        ),
        "public_symbols_without_nominal_tests": symbols_without_tests,
        "modules_without_direct_tests": modules_without_tests,
        "shallow_test_files": shallow_tests,
        "dead_code_candidates": dead_code,
        "complex_or_high_risk_areas": complex_areas,
    }

    write_json(AUDIT_OUT / "repo_diagnostics_context.json", payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())