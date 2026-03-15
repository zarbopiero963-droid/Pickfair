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
    ],
    "repo_fix_backlog": [
        ROOT / "audit_out" / "repo_fix_backlog.json",
        ROOT / "repo_fix_backlog.json",
    ],
}


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


def trim_list(values, limit: int) -> list:
    out = []
    seen = set()

    for item in values or []:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False) if isinstance(item, (dict, list)) else str(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break

    return out


def normalize_public_symbols(api_report: dict) -> list[dict]:
    result = []

    candidates = (
        api_report.get("public_symbols_without_nominal_tests")
        or api_report.get("symbols_without_tests")
        or api_report.get("untested_public_symbols")
        or []
    )

    for item in candidates:
        if isinstance(item, dict):
            file_path = str(
                item.get("file")
                or item.get("path")
                or item.get("module")
                or ""
            ).strip()
            symbol = str(
                item.get("symbol")
                or item.get("name")
                or item.get("public_symbol")
                or ""
            ).strip()
        else:
            file_path = ""
            symbol = str(item).strip()

        if not symbol:
            continue

        result.append(
            {
                "symbol": symbol,
                "file": file_path,
                "risk": "medium",
                "kind": "public_symbol_without_nominal_test",
            }
        )

    return trim_list(result, 200)


def normalize_modules_without_tests(api_report: dict) -> list[dict]:
    result = []

    candidates = (
        api_report.get("modules_without_direct_tests")
        or api_report.get("modules_without_tests")
        or []
    )

    for item in candidates:
        if isinstance(item, dict):
            path = str(item.get("file") or item.get("path") or item.get("module") or "").strip()
        else:
            path = str(item).strip()

        if not path:
            continue

        result.append(
            {
                "file": path,
                "risk": "medium",
                "kind": "module_without_direct_test",
            }
        )

    return trim_list(result, 120)


def normalize_shallow_tests(api_report: dict) -> list[dict]:
    result = []

    candidates = api_report.get("shallow_tests") or api_report.get("shallow_test_files") or []

    for item in candidates:
        if isinstance(item, dict):
            path = str(item.get("file") or item.get("path") or "").strip()
        else:
            path = str(item).strip()

        if not path:
            continue

        result.append(
            {
                "file": path,
                "risk": "low",
                "kind": "shallow_test_file",
            }
        )

    return trim_list(result, 80)


def normalize_dead_code(api_report: dict) -> list[dict]:
    result = []

    candidates = api_report.get("dead_code_candidates") or api_report.get("dead_code") or []

    for item in candidates:
        if isinstance(item, dict):
            path = str(item.get("file") or item.get("path") or "").strip()
            symbol = str(item.get("symbol") or item.get("name") or "").strip()
        else:
            path = ""
            symbol = str(item).strip()

        if not path and not symbol:
            continue

        result.append(
            {
                "file": path,
                "symbol": symbol,
                "risk": "review_only",
                "kind": "dead_code_candidate",
            }
        )

    return trim_list(result, 80)


def normalize_complex_modules(autopsy: dict, backlog: dict) -> list[dict]:
    result = []

    top_classes = autopsy.get("prod_top_classes") or autopsy.get("top_classes") or []
    for item in top_classes:
        if not isinstance(item, dict):
            continue

        file_path = str(item.get("file") or item.get("path") or "").strip()
        class_name = str(item.get("class") or item.get("class_name") or "").strip()

        if not file_path:
            continue

        result.append(
            {
                "file": file_path,
                "class_name": class_name,
                "risk": "high",
                "kind": "complex_production_area",
            }
        )

    backlog_items = backlog.get("items") or backlog.get("backlog") or []
    for item in backlog_items:
        if not isinstance(item, dict):
            continue

        priority = str(item.get("priority") or "").strip().upper()
        action = str(item.get("action") or "").strip()
        file_path = str(item.get("file") or item.get("path") or "").strip()
        title = str(item.get("title") or item.get("summary") or "").strip()

        if not file_path:
            continue

        if priority not in {"P0", "P1"}:
            continue

        result.append(
            {
                "file": file_path,
                "title": title,
                "action": action,
                "risk": "high" if priority == "P0" else "medium",
                "kind": "backlog_priority_area",
                "priority": priority,
            }
        )

    return trim_list(result, 120)


def build_summary(api_report: dict, autopsy: dict, backlog: dict) -> dict:
    modules_wo_tests = api_report.get("modules_without_direct_tests")
    if not isinstance(modules_wo_tests, list):
        modules_wo_tests = api_report.get("modules_without_tests") or []

    symbols_wo_tests = (
        api_report.get("public_symbols_without_nominal_tests")
        or api_report.get("symbols_without_tests")
        or api_report.get("untested_public_symbols")
        or []
    )

    dead_code = api_report.get("dead_code_candidates") or api_report.get("dead_code") or []
    shallow_tests = api_report.get("shallow_tests") or api_report.get("shallow_test_files") or []
    backlog_items = backlog.get("items") or backlog.get("backlog") or []
    top_classes = autopsy.get("prod_top_classes") or autopsy.get("top_classes") or []

    return {
        "modules_without_direct_tests": len(modules_wo_tests) if isinstance(modules_wo_tests, list) else 0,
        "public_symbols_without_nominal_tests": len(symbols_wo_tests) if isinstance(symbols_wo_tests, list) else 0,
        "dead_code_candidates": len(dead_code) if isinstance(dead_code, list) else 0,
        "shallow_test_files": len(shallow_tests) if isinstance(shallow_tests, list) else 0,
        "backlog_items": len(backlog_items) if isinstance(backlog_items, list) else 0,
        "top_complex_areas": len(top_classes) if isinstance(top_classes, list) else 0,
    }


def main() -> int:
    resolved = {}
    payload = {}

    for key, candidates in INPUT_CANDIDATES.items():
        found = first_existing(candidates)
        resolved[key] = str(found.relative_to(ROOT)).replace("\\", "/") if found else ""
        payload[key] = read_json(found) if found else {}

    api_report = payload["repo_api_report_v4"]
    autopsy = payload["repo_autopsy_summary"]
    backlog = payload["repo_fix_backlog"]

    result = {
        "sources": resolved,
        "summary": build_summary(api_report, autopsy, backlog),
        "public_symbols_without_nominal_tests": normalize_public_symbols(api_report),
        "modules_without_direct_tests": normalize_modules_without_tests(api_report),
        "shallow_test_files": normalize_shallow_tests(api_report),
        "dead_code_candidates": normalize_dead_code(api_report),
        "complex_or_high_risk_areas": normalize_complex_modules(autopsy, backlog),
    }

    write_json(AUDIT_OUT / "repo_diagnostics_context.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())