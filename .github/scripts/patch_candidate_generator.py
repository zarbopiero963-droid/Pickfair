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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def normalize_path(path_str: str) -> str:
    raw = str(path_str or "").strip().replace("\\", "/")
    if not raw:
        return ""
    while raw.startswith("./"):
        raw = raw[2:]
    return raw


def repo_exists(rel_path: str) -> bool:
    rel = normalize_path(rel_path)
    return bool(rel) and (ROOT / rel).exists()


def is_runtime_python(path_str: str) -> bool:
    rel = normalize_path(path_str).lower()
    return rel.endswith(".py") and not rel.startswith("tests/") and not rel.startswith(".github/")


def is_test_python(path_str: str) -> bool:
    rel = normalize_path(path_str).lower()
    return rel.startswith("tests/") and rel.endswith(".py")


def is_generated_test(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith("tests/generated/")


def is_guardrail_test(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith("tests/guardrails/")


def is_hft_test(path_str: str) -> bool:
    rel = normalize_path(path_str).lower()
    return rel.startswith("tests/") and "hft" in rel


def is_github_script(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith(".github/scripts/")


def unique_keep(items, limit: int | None = None) -> list[str]:
    out = []
    seen = set()
    for item in items or []:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
        if limit is not None and len(out) >= limit:
            break
    return out


def build_notes(*groups) -> list[str]:
    return unique_keep(
        [str(item).strip() for group in groups for item in (group or []) if str(item).strip()],
        18,
    )


def load_issue_items(payload: dict) -> list[dict]:
    return payload.get("fix_contexts", []) or payload.get("issue_classification", []) or []


def cto_priority_map(cto_payload: dict) -> dict:
    result = {}
    for item in cto_payload.get("repair_order", []) or []:
        key = normalize_path(item.get("file", "") or item.get("target_file", ""))
        if key and key not in result:
            result[key] = item

    for bucket in ("P0", "P1", "P2"):
        for item in (cto_payload.get("cto_priority", {}) or {}).get(bucket, []) or []:
            key = normalize_path(item.get("file", "") or item.get("target_file", ""))
            if key and key not in result:
                result[key] = item
    return result


def repo_diag_symbol_map(repo_diag: dict) -> dict:
    result = {}
    for item in repo_diag.get("public_symbols_without_nominal_tests", []) or []:
        key = normalize_path(item.get("file", ""))
        if key:
            result.setdefault(key, []).append(item)
    return result


def test_failure_context_map(test_failure_ctx: dict) -> dict:
    result = {}
    for item in test_failure_ctx.get("test_failure_contexts", []) or []:
        key = normalize_path(item.get("target_file", ""))
        if key:
            result[key] = item
    return result


def ci_failure_map() -> dict:
    payload = read_json(AUDIT_OUT / "ci_failure_context.json")
    if not payload:
        payload = read_json(AUDIT_OUT / "ci_failures.json")

    result = {}
    for item in payload.get("ci_failures", []) or []:
        key = normalize_path(item.get("target_file", ""))
        if key:
            result.setdefault(key, []).append(item)
    return result


def ci_issue_counts(ci_map: dict) -> dict[str, int]:
    counts = {
        "missing_public_contract": 0,
        "runtime_failure": 0,
        "lint_failure": 0,
        "test_failure": 0,
        "ci_failure": 0,
        "missing_nominal_test": 0,
        "contract_test_failure": 0,
    }
    for items in ci_map.values():
        for item in items:
            issue_type = str(item.get("issue_type", "")).strip()
            if issue_type in counts:
                counts[issue_type] += 1
    return counts


def has_real_runtime_or_lint_pressure(ci_map: dict) -> bool:
    counts = ci_issue_counts(ci_map)
    return (counts["runtime_failure"] + counts["lint_failure"]) > 0


def detect_strategy(target_file: str, issue_type: str, classification: str) -> str:
    target_file = normalize_path(target_file)

    if issue_type == "missing_public_contract":
        return "compatibility_contract_fix"
    if issue_type == "runtime_failure":
        return "runtime_failure_safe_fix" if classification == "AUTO_FIX_SAFE" else "runtime_failure_review_fix"
    if issue_type == "lint_failure":
        return "runtime_lint_safe_fix" if is_runtime_python(target_file) else "python_lint_safe_fix"
    if issue_type == "test_failure":
        return "safe_test_fix" if classification == "AUTO_FIX_SAFE" else "reviewable_test_fix"
    if issue_type == "ci_failure":
        return "runtime_ci_fix" if is_runtime_python(target_file) else "reviewable_ci_fix"
    if issue_type == "missing_nominal_test":
        return "generate_nominal_test"
    return "reviewable_fix"


def derive_related_tests(item: dict, tf_ctx_map: dict) -> list[str]:
    target = normalize_path(item.get("target_file", ""))
    tests = list(item.get("related_tests", []) or [])

    tf_ctx = tf_ctx_map.get(target, {})
    tests.extend(tf_ctx.get("related_tests", []) or [])

    if not tests and is_runtime_python(target):
        stem = Path(target).stem
        guesses = [
            f"tests/test_{stem}.py",
            f"tests/contracts/test_{stem}.py",
            f"tests/guardrails/test_{stem}.py",
        ]
        for guess in guesses:
            if repo_exists(guess):
                tests.append(guess)

    if target.startswith("tests/") and target.endswith(".py"):
        tests.append(target)

    return unique_keep([normalize_path(x) for x in tests if normalize_path(x)], 8)


def derive_related_source(item: dict, tf_ctx_map: dict) -> str:
    target = normalize_path(item.get("target_file", ""))
    direct = normalize_path(item.get("related_source_file", ""))
    if direct:
        return direct

    tf_ctx = tf_ctx_map.get(target, {})
    derived = normalize_path(tf_ctx.get("related_source_file", ""))
    if derived:
        return derived

    if is_runtime_python(target):
        return target

    return ""


def derive_required_symbols(item: dict, repo_diag_symbols: dict) -> list[str]:
    target = normalize_path(item.get("target_file", ""))
    symbols = list(item.get("required_symbols", []) or [])
    if not symbols:
        for sym in repo_diag_symbols.get(target, [])[:4]:
            name = str(sym.get("symbol", "")).strip()
            if name:
                symbols.append(name)
    return unique_keep(symbols, 6)


def build_patch_intents(target_file: str, issue_type: str, classification: str) -> list[str]:
    target_file = normalize_path(target_file)
    intents = []

    if issue_type == "missing_public_contract":
        intents += [
            "restore_missing_public_symbol",
            "prefer_smallest_compatibility_wrapper",
            "avoid_logic_redesign",
        ]
    elif issue_type == "runtime_failure":
        intents += [
            "apply_minimal_runtime_fix",
            "prefer_guard_clause_or_compatibility_fix",
            "avoid_large_refactor",
        ]
    elif issue_type == "lint_failure":
        intents += [
            "apply_mechanical_lint_fix",
            "prefer_ruff_safe_changes",
            "avoid_behavior_changes",
        ]
    elif issue_type == "test_failure":
        intents += [
            "apply_minimal_test_fix",
            "preserve_runtime_behavior",
        ]
    elif issue_type == "ci_failure":
        intents += [
            "prefer_small_local_fix",
            "prefer_runtime_or_lint_target_if_available",
        ]
    elif issue_type == "missing_nominal_test":
        intents += [
            "generate_nominal_test",
            "avoid_mock_heavy_or_shallow_test",
        ]

    if classification == "AUTO_FIX_SAFE":
        intents.append("safe_autofix_allowed")
    elif classification == "AUTO_FIX_REVIEW":
        intents.append("reviewable_autofix_allowed")
    else:
        intents.append("manual_review_only")

    if is_runtime_python(target_file):
        intents.append("target_is_runtime_python")
    if is_generated_test(target_file):
        intents.append("target_is_generated_test")

    return unique_keep(intents, 18)


def score_item(item: dict, cto_item: dict, ci_map: dict, prefer_runtime: bool) -> tuple:
    target = normalize_path(item.get("target_file", ""))
    issue_type = str(item.get("issue_type", "")).strip()
    classification = str(item.get("classification", "")).strip()
    item_priority = str(item.get("priority", "")).strip().upper()
    cto_priority = str(cto_item.get("priority", "") or item_priority or "P2").strip().upper()

    priority_rank = {"P0": 0, "P1": 1, "P2": 2}
    issue_rank = {
        "missing_public_contract": 0,
        "runtime_failure": 1,
        "lint_failure": 2,
        "test_failure": 3,
        "ci_failure": 4,
        "missing_nominal_test": 5,
        "contract_test_failure": 6,
    }
    class_rank = {"AUTO_FIX_SAFE": 0, "AUTO_FIX_REVIEW": 1, "HUMAN_ONLY": 9}

    target_kind_rank = 9
    if is_runtime_python(target):
        target_kind_rank = 0
    elif is_test_python(target) and not is_generated_test(target) and not is_guardrail_test(target):
        target_kind_rank = 4
    elif is_guardrail_test(target):
        target_kind_rank = 7
    elif is_generated_test(target):
        target_kind_rank = 8

    ci_hits = len(ci_map.get(target, []))
    generated_penalty = 50 if (prefer_runtime and is_generated_test(target)) else 0
    runtime_bonus = -20 if (prefer_runtime and is_runtime_python(target)) else 0

    return (
        priority_rank.get(cto_priority, 9),
        issue_rank.get(issue_type, 99),
        class_rank.get(classification, 99),
        target_kind_rank,
        generated_penalty,
        runtime_bonus,
        -ci_hits,
        target,
    )


def choose_from_classified_items(
    classification_payload: dict,
    cto_map: dict,
    repo_diag_symbols: dict,
    tf_ctx_map: dict,
    ci_map: dict,
) -> dict | None:
    prefer_runtime = has_real_runtime_or_lint_pressure(ci_map)
    ranked = []

    for item in load_issue_items(classification_payload):
        target = normalize_path(item.get("target_file", ""))
        classification = str(item.get("classification", "")).strip()
        issue_type = str(item.get("issue_type", "")).strip()

        if not target:
            continue
        if classification == "HUMAN_ONLY":
            continue
        if is_github_script(target):
            continue
        if is_hft_test(target):
            continue
        if prefer_runtime and issue_type == "missing_nominal_test" and is_generated_test(target):
            continue

        cto_item = cto_map.get(target) or cto_map.get(normalize_path(item.get("related_source_file", ""))) or {}
        ranked.append((score_item(item, cto_item, ci_map, prefer_runtime), item, cto_item))

    if not ranked:
        return None

    ranked.sort(key=lambda x: x[0])
    _, best_item, cto_item = ranked[0]

    target_file = normalize_path(best_item.get("target_file", ""))
    issue_type = str(best_item.get("issue_type", "")).strip()
    classification = str(best_item.get("classification", "")).strip()
    strategy = detect_strategy(target_file, issue_type, classification)

    related_source_file = derive_related_source(best_item, tf_ctx_map)
    related_tests = derive_related_tests(best_item, tf_ctx_map)
    required_symbols = derive_required_symbols(best_item, repo_diag_symbols)

    ci_items = ci_map.get(target_file, []) or ci_map.get(related_source_file, [])
    notes = build_notes(
        best_item.get("notes", []) or [],
        best_item.get("classification_reasons", []) or [],
        cto_item.get("reasons", []) if cto_item else [],
        [x.get("signal", "") for x in ci_items[:4]],
        [
            f"strategy={strategy}",
            f"issue_type={issue_type}",
            f"classification={classification}",
            f"target_file={target_file}",
            f"related_source_file={related_source_file}" if related_source_file else "",
            f"runtime_or_lint_pressure={prefer_runtime}",
        ],
    )

    return {
        "strategy": strategy,
        "target_file": target_file,
        "related_source_file": related_source_file,
        "issue_type": issue_type,
        "classification": classification,
        "cto_priority": str(cto_item.get("priority", "")).strip(),
        "cto_kind": str(cto_item.get("kind", "")).strip(),
        "required_symbols": required_symbols,
        "related_tests": related_tests,
        "patch_intents": build_patch_intents(target_file, issue_type, classification),
        "notes": notes,
    }


def choose_generated_test_candidate(test_gap: dict, cto_map: dict, ci_map: dict) -> dict | None:
    if has_real_runtime_or_lint_pressure(ci_map):
        return None

    generated = test_gap.get("generated_tests", []) or []
    if not generated:
        return None

    picked = generated[0]
    source_file = normalize_path(picked.get("source_file", ""))
    generated_test_file = normalize_path(picked.get("generated_test_file", ""))
    if not generated_test_file:
        return None

    cto_item = cto_map.get(source_file, {})
    return {
        "strategy": "generate_nominal_test",
        "target_file": generated_test_file,
        "related_source_file": source_file,
        "issue_type": "missing_nominal_test",
        "classification": "AUTO_FIX_SAFE",
        "cto_priority": str(cto_item.get("priority", "")).strip(),
        "cto_kind": str(cto_item.get("kind", "")).strip(),
        "required_symbols": [],
        "related_tests": [generated_test_file],
        "patch_intents": [
            "generate_nominal_test",
            "safe_autofix_allowed",
            "target_is_generated_test",
        ],
        "notes": build_notes(
            [
                "fallback generated nominal test",
                f"source_file={source_file}" if source_file else "",
            ],
            cto_item.get("reasons", []) if cto_item else [],
        ),
    }


def render_markdown(result: dict) -> str:
    candidate = result.get("patch_candidate")
    if not candidate:
        return "Patch Candidate\n\nNo viable patch candidate found.\n"

    lines = []
    lines.append("Patch Candidate")
    lines.append("")
    lines.append(f"Reason: {result.get('reason', '')}")
    lines.append(f"Strategy: {candidate.get('strategy', '')}")
    lines.append(f"Target file: {candidate.get('target_file', '')}")
    lines.append(f"Related source file: {candidate.get('related_source_file', '')}")
    lines.append(f"Issue type: {candidate.get('issue_type', '')}")
    lines.append(f"Classification: {candidate.get('classification', '')}")
    lines.append(f"CTO priority: {candidate.get('cto_priority', '')}")
    lines.append(f"CTO kind: {candidate.get('cto_kind', '')}")
    lines.append("")
    lines.append("Related tests")
    tests = candidate.get("related_tests", []) or []
    if tests:
        for item in tests:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessun test correlato disponibile.")
    lines.append("")
    lines.append("Notes")
    for item in candidate.get("notes", []) or []:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    contexts = {
        "classification": read_json(AUDIT_OUT / "issue_classification.json"),
        "repo_diag": read_json(AUDIT_OUT / "repo_diagnostics_context.json"),
        "test_gap": read_json(AUDIT_OUT / "test_gap_generation_report.json"),
        "cto": read_json(AUDIT_OUT / "ai_cto_layer.json"),
        "test_failure_context": read_json(AUDIT_OUT / "test_failure_context.json"),
    }

    cto_map = cto_priority_map(contexts["cto"])
    repo_diag_symbols = repo_diag_symbol_map(contexts["repo_diag"])
    tf_ctx_map = test_failure_context_map(contexts["test_failure_context"])
    ci_map = ci_failure_map()

    candidate = choose_from_classified_items(
        contexts["classification"],
        cto_map,
        repo_diag_symbols,
        tf_ctx_map,
        ci_map,
    )

    if not candidate:
        candidate = choose_generated_test_candidate(contexts["test_gap"], cto_map, ci_map)

    if not candidate:
        result = {"patch_candidate": None, "reason": "no_viable_target"}
    else:
        result = {"patch_candidate": candidate, "reason": "target_selected"}

    write_json(AUDIT_OUT / "patch_candidate.json", result)
    write_text(AUDIT_OUT / "patch_candidate.md", render_markdown(result))

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main()) 