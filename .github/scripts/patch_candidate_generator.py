#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def write_text(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def normalize_path(path_str: str) -> str:
    return str(path_str or "").strip().replace("\\", "/")


def load_contexts():
    return {
        "classification": read_json(AUDIT_OUT / "issue_classification.json"),
        "repo_diag": read_json(AUDIT_OUT / "repo_diagnostics_context.json"),
        "test_gap": read_json(AUDIT_OUT / "test_gap_generation_report.json"),
        "fix_context": read_json(AUDIT_OUT / "fix_context.json"),
        "cto": read_json(AUDIT_OUT / "ai_cto_layer.json"),
    }


def classification_map(classification_payload: dict) -> dict:
    result = {}
    for item in classification_payload.get("fix_contexts", []) or []:
        target = normalize_path(item.get("target_file", ""))
        if not target:
            continue
        result[target] = item
    return result


def cto_priority_map(cto_payload: dict) -> dict:
    result = {}
    for item in cto_payload.get("repair_order", []) or []:
        file_path = normalize_path(item.get("file", ""))
        if not file_path:
            continue
        if file_path not in result:
            result[file_path] = item
    return result


def is_human_only(classified_item: dict) -> bool:
    return str(classified_item.get("classification", "")).strip() == "HUMAN_ONLY"


def is_auto_fix_safe(classified_item: dict) -> bool:
    return str(classified_item.get("classification", "")).strip() == "AUTO_FIX_SAFE"


def is_auto_fix_review(classified_item: dict) -> bool:
    return str(classified_item.get("classification", "")).strip() == "AUTO_FIX_REVIEW"


def is_runtime_target(path_str: str) -> bool:
    path_str = normalize_path(path_str).lower()
    if not path_str.endswith(".py"):
        return False
    if path_str.startswith("tests/"):
        return False
    if path_str.startswith(".github/"):
        return False
    return True


def is_generated_test(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith("tests/generated/")


def is_guardrail_test(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith("tests/guardrails/")


def is_hft_test(path_str: str) -> bool:
    path = normalize_path(path_str).lower()
    return path.startswith("tests/") and "hft" in path


def is_github_script(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith(".github/scripts/")


def get_fix_context_for_target(fix_context: dict, target_file: str) -> dict:
    target_file = normalize_path(target_file)
    for item in fix_context.get("fix_contexts", []) or []:
        if normalize_path(item.get("target_file", "")) == target_file:
            return item
    return {}


def build_notes(*groups) -> list[str]:
    out = []
    seen = set()

    for group in groups:
        for item in group or []:
            value = str(item).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            out.append(value)

    return out[:8]


def candidate_from_classified_item(
    classified_item: dict,
    cto_item: dict,
    strategy: str,
) -> dict:
    target_file = normalize_path(classified_item.get("target_file", ""))
    related_source = normalize_path(classified_item.get("related_source_file", ""))
    issue_type = str(classified_item.get("issue_type", "")).strip()

    cto_priority = str(cto_item.get("priority", "")).strip() if cto_item else ""
    cto_kind = str(cto_item.get("kind", "")).strip() if cto_item else ""
    cto_reasons = cto_item.get("reasons", []) or []

    notes = build_notes(
        classified_item.get("notes", []) or [],
        classified_item.get("classification_reasons", []) or [],
        cto_reasons,
    )

    return {
        "strategy": strategy,
        "target_file": target_file,
        "related_source_file": related_source,
        "issue_type": issue_type,
        "classification": str(classified_item.get("classification", "")).strip(),
        "cto_priority": cto_priority,
        "cto_kind": cto_kind,
        "notes": notes,
    }


def candidate_from_generated_test(test_gap: dict, cto_map: dict) -> dict | None:
    generated = test_gap.get("generated_tests", []) or []
    if not generated:
        return None

    ranked = sorted(
        generated,
        key=lambda x: (
            0 if not bool(x.get("high_risk_area", False)) else 1,
            normalize_path(x.get("source_file", "")),
        ),
    )

    picked = ranked[0]
    source_file = normalize_path(picked.get("source_file", ""))
    generated_test_file = normalize_path(picked.get("generated_test_file", ""))

    if not generated_test_file:
        return None

    cto_item = cto_map.get(source_file, {})
    notes = build_notes(
        ["generated nominal test from repo diagnostics"],
        [f"source_file={source_file}" if source_file else ""],
        cto_item.get("reasons", []) or [],
    )

    return {
        "strategy": "generate_nominal_test",
        "target_file": generated_test_file,
        "related_source_file": source_file,
        "issue_type": "missing_nominal_test",
        "classification": "AUTO_FIX_SAFE",
        "cto_priority": str(cto_item.get("priority", "")).strip(),
        "cto_kind": str(cto_item.get("kind", "")).strip(),
        "notes": notes,
    }


def choose_candidate(contexts):
    classification_payload = contexts["classification"]
    fix_context = contexts["fix_context"]
    test_gap = contexts["test_gap"]
    cto_payload = contexts["cto"]

    classified_items = classification_payload.get("fix_contexts", []) or []
    class_map = classification_map(classification_payload)
    cto_map = cto_priority_map(cto_payload)

    safe_candidates = []
    review_candidates = []
    runtime_fallbacks = []

    for item in classified_items:
        target_file = normalize_path(item.get("target_file", ""))
        if not target_file:
            continue

        if is_human_only(item):
            continue

        if is_github_script(target_file):
            continue

        if is_hft_test(target_file):
            continue

        cto_item = cto_map.get(target_file, {})
        cto_priority = str(cto_item.get("priority", "P2")).strip().upper()

        scored = (
            0 if cto_priority == "P0" else 1 if cto_priority == "P1" else 2,
            0 if is_runtime_target(target_file) else 1,
            0 if not is_guardrail_test(target_file) else 1,
            target_file,
        )

        if is_auto_fix_safe(item):
            safe_candidates.append((scored, item, cto_item))
        elif is_auto_fix_review(item):
            review_candidates.append((scored, item, cto_item))

        fx = get_fix_context_for_target(fix_context, target_file)
        issue_type = str(fx.get("issue_type", item.get("issue_type", ""))).strip()
        if issue_type == "runtime_failure" and is_runtime_target(target_file):
            runtime_fallbacks.append((scored, item, cto_item))

    if safe_candidates:
        safe_candidates.sort(key=lambda x: x[0])
        _, item, cto_item = safe_candidates[0]
        return candidate_from_classified_item(item, cto_item, "safe_auto_fix")

    if review_candidates:
        review_candidates.sort(key=lambda x: x[0])
        _, item, cto_item = review_candidates[0]
        return candidate_from_classified_item(item, cto_item, "reviewable_fix")

    if runtime_fallbacks:
        runtime_fallbacks.sort(key=lambda x: x[0])
        _, item, cto_item = runtime_fallbacks[0]
        return candidate_from_classified_item(item, cto_item, "runtime_target_fix")

    generated_test_candidate = candidate_from_generated_test(test_gap, cto_map)
    if generated_test_candidate:
        return generated_test_candidate

    # fallback minimo dal fix_context se esiste e non è pericoloso
    for item in fix_context.get("fix_contexts", []) or []:
        target_file = normalize_path(item.get("target_file", ""))
        if not target_file:
            continue
        if is_github_script(target_file) or is_hft_test(target_file):
            continue

        classified_item = class_map.get(target_file, {})
        if is_human_only(classified_item):
            continue

        if is_runtime_target(target_file) or is_generated_test(target_file):
            cto_item = cto_map.get(target_file, {})
            return candidate_from_classified_item(
                classified_item or item,
                cto_item,
                "fallback_fix_context",
            )

    return None


def render_markdown(result: dict) -> str:
    candidate = result.get("patch_candidate")
    if not candidate:
        return "Patch Candidate\n\nNo viable patch candidate found.\n"

    lines = []
    lines.append("Patch Candidate")
    lines.append("")
    lines.append(f"Reason: {result.get('reason', '')}")
    lines.append("")
    lines.append(f"Strategy: {candidate.get('strategy', '')}")
    lines.append(f"Target file: {candidate.get('target_file', '')}")
    lines.append(f"Related source file: {candidate.get('related_source_file', '')}")
    lines.append(f"Issue type: {candidate.get('issue_type', '')}")
    lines.append(f"Classification: {candidate.get('classification', '')}")
    lines.append(f"CTO priority: {candidate.get('cto_priority', '')}")
    lines.append(f"CTO kind: {candidate.get('cto_kind', '')}")
    lines.append("")
    lines.append("Notes")
    notes = candidate.get("notes", []) or []
    if notes:
        for note in notes:
            lines.append(f"- {note}")
    else:
        lines.append("- Nessuna nota disponibile.")
    lines.append("")
    return "\n".join(lines)


def main():
    contexts = load_contexts()
    candidate = choose_candidate(contexts)

    if not candidate:
        result = {
            "patch_candidate": None,
            "reason": "no_viable_target",
        }
    else:
        result = {
            "patch_candidate": candidate,
            "reason": "target_selected",
        }

    write_json(AUDIT_OUT / "patch_candidate.json", result)
    write_text(AUDIT_OUT / "patch_candidate.md", render_markdown(result))

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()