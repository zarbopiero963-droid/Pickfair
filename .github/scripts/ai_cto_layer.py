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
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def normalize_path(path: str) -> str:
    return str(path or "").replace("\\", "/").lstrip("./").strip()


def collect_ci_failures():
    data = read_json(AUDIT_OUT / "ci_failures.json")
    return data.get("ci_failures", [])


def collect_backlog():
    data = read_json(AUDIT_OUT / "repo_fix_backlog.json")
    return data.get("fix_backlog", []) or data.get("items", [])


def collect_api_report():
    data = read_json(AUDIT_OUT / "repo_api_report_v4.json")
    return (
        data.get("api_issues", [])
        or data.get("public_symbols_without_nominal_tests", [])
        or data.get("symbols_without_tests", [])
        or []
    )


def classify_priority(issue_type: str) -> str:
    issue_type = str(issue_type or "").strip()

    if issue_type in {"missing_public_contract", "runtime_failure"}:
        return "P0"
    if issue_type in {"lint_failure", "test_failure", "ci_failure", "contract_test_failure"}:
        return "P1"
    return "P2"


def build_ci_items(ci_failures):
    out = []
    for f in ci_failures:
        issue_type = str(f.get("issue_type", "")).strip() or "ci_failure"
        target_file = normalize_path(f.get("target_file", ""))
        if not target_file:
            continue

        priority = classify_priority(issue_type)
        reasons = []
        if f.get("signal"):
            reasons.append(str(f.get("signal")).strip())
        if f.get("error_type"):
            reasons.append(f"error_type={f.get('error_type')}")

        out.append({
            "file": target_file,
            "target_file": target_file,
            "priority": priority,
            "source": "ci_failure",
            "kind": issue_type,
            "issue_type": issue_type,
            "signal": str(f.get("signal", "")).strip(),
            "reasons": reasons[:4],
        })
    return out


def build_backlog_items(backlog):
    out = []
    for b in backlog:
        if not isinstance(b, dict):
            continue

        target_file = normalize_path(b.get("file", "") or b.get("target_file", ""))
        if not target_file:
            continue

        priority = str(b.get("priority", "")).strip().upper() or "P2"
        kind = str(b.get("kind", "") or b.get("type", "")).strip() or "backlog_item"

        reasons = []
        if b.get("description"):
            reasons.append(str(b.get("description")).strip())
        if b.get("title"):
            reasons.append(str(b.get("title")).strip())

        out.append({
            "file": target_file,
            "target_file": target_file,
            "priority": priority,
            "source": "backlog",
            "kind": kind,
            "issue_type": kind,
            "signal": str(b.get("description", "") or b.get("title", "")).strip(),
            "reasons": reasons[:4],
        })
    return out


def build_api_items(api_issues):
    out = []
    for a in api_issues:
        if not isinstance(a, dict):
            continue

        target_file = normalize_path(a.get("file", ""))
        if not target_file:
            continue

        symbol = str(a.get("symbol", "")).strip()
        kind = str(a.get("kind", "") or a.get("issue", "")).strip() or "api_gap"
        issue_type = "missing_nominal_test" if symbol else "ci_failure"
        priority = "P1" if symbol else "P2"

        reasons = []
        if symbol:
            reasons.append(f"missing nominal test for symbol={symbol}")
        if a.get("detail"):
            reasons.append(str(a.get("detail")).strip())

        out.append({
            "file": target_file,
            "target_file": target_file,
            "priority": priority,
            "source": "api_report",
            "kind": kind,
            "issue_type": issue_type,
            "signal": str(a.get("detail", "") or symbol).strip(),
            "reasons": reasons[:4],
        })
    return out


def dedupe_items(items):
    merged = {}

    def rank(priority: str) -> int:
        return {"P0": 0, "P1": 1, "P2": 2}.get(str(priority or "").strip().upper(), 9)

    for item in items:
        target_file = normalize_path(item.get("file", "") or item.get("target_file", ""))
        if not target_file:
            continue

        key = target_file
        if key not in merged:
            merged[key] = dict(item)
            merged[key]["file"] = target_file
            merged[key]["target_file"] = target_file
            merged[key]["reasons"] = list(item.get("reasons", []) or [])
            continue

        current = merged[key]
        if rank(item.get("priority")) < rank(current.get("priority")):
            current["priority"] = item.get("priority")
            current["kind"] = item.get("kind")
            current["issue_type"] = item.get("issue_type")
            current["source"] = item.get("source")
            current["signal"] = item.get("signal")

        current["reasons"] = list(dict.fromkeys((current.get("reasons", []) or []) + (item.get("reasons", []) or [])))[:6]

    return list(merged.values())


def build_repair_order(items):
    priority_rank = {"P0": 0, "P1": 1, "P2": 2}
    issue_rank = {
        "missing_public_contract": 0,
        "runtime_failure": 1,
        "lint_failure": 2,
        "test_failure": 3,
        "ci_failure": 4,
        "missing_nominal_test": 5,
    }

    items.sort(
        key=lambda x: (
            priority_rank.get(str(x.get("priority", "")).strip().upper(), 9),
            issue_rank.get(str(x.get("issue_type", "")).strip(), 99),
            normalize_path(x.get("file", "")),
        )
    )
    return items


def group_priorities(items):
    grouped = {"P0": [], "P1": [], "P2": []}
    for item in items:
        p = str(item.get("priority", "P2")).strip().upper()
        if p not in grouped:
            p = "P2"
        grouped[p].append(item)
    return grouped


def main():
    ci_failures = collect_ci_failures()
    backlog = collect_backlog()
    api_issues = collect_api_report()

    items = []
    items.extend(build_ci_items(ci_failures))
    items.extend(build_backlog_items(backlog))
    items.extend(build_api_items(api_issues))

    deduped = dedupe_items(items)
    repair_order = build_repair_order(deduped)
    grouped = group_priorities(repair_order)

    result = {
        "cto_priority": grouped,
        "repair_order": repair_order,
        "summary": {
            "P0": len(grouped["P0"]),
            "P1": len(grouped["P1"]),
            "P2": len(grouped["P2"]),
            "P0_count": len(grouped["P0"]),
            "P1_count": len(grouped["P1"]),
            "P2_count": len(grouped["P2"]),
            "top_kind_counts": {
                "runtime_failure": sum(1 for x in repair_order if x.get("issue_type") == "runtime_failure"),
                "lint_failure": sum(1 for x in repair_order if x.get("issue_type") == "lint_failure"),
                "test_failure": sum(1 for x in repair_order if x.get("issue_type") == "test_failure"),
                "ci_failure": sum(1 for x in repair_order if x.get("issue_type") == "ci_failure"),
                "missing_nominal_test": sum(1 for x in repair_order if x.get("issue_type") == "missing_nominal_test"),
            },
        },
    }

    write_json(AUDIT_OUT / "ai_cto_layer.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()