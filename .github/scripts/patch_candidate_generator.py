#!/usr/bin/env python3

import json
import re
from pathlib import Path

from openrouter_model_router import call_openrouter

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"

MAX_TARGETS = 3
MAX_TARGET_FILE_CHARS = 18000
MAX_RELATED_TEST_CHARS = 8000
MAX_RELATED_FIXTURE_CHARS = 5000
MAX_RELATED_CONTRACT_CHARS = 6000

MAX_PYTEST_SIGNALS = 12
MAX_AI_ROOT_CAUSES = 6
MAX_CONTRACTS = 10
MAX_FAILING_TEST_CONTEXTS = 6


CLASS_PRIORITY = {
    "AUTO_FIX_SAFE": 0,
    "AUTO_FIX_REVIEW": 1,
    "HUMAN_ONLY": 2,
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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def trimmed_text(text: str, max_chars: int) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


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


def parse_json_content(content: str) -> dict:
    content = (content or "").strip()

    if not content:
        return {
            "summary": "Patch candidate response was empty.",
            "target_files": [],
            "why_this_fix": "",
            "proposed_patches": [],
            "tests_to_run": [],
            "risk": "unknown",
            "raw_content": "",
        }

    try:
        return json.loads(content)
    except Exception:
        pass

    fence = re.search(r"```json\s*(.*?)\s*```", content, re.S | re.I)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:
            pass

    fence = re.search(r"```\s*(.*?)\s*```", content, re.S)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:
            pass

    start = content.find("{")
    if start != -1:
        depth = 0
        in_string = False
        escape = False

        for i in range(start, len(content)):
            ch = content[i]

            if escape:
                escape = False
                continue

            if ch == "\\":
                escape = True
                continue

            if ch == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = content[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except Exception:
                        break

    return {
        "summary": "Patch candidate response was not valid JSON.",
        "target_files": [],
        "why_this_fix": "",
        "proposed_patches": [],
        "tests_to_run": [],
        "risk": "unknown",
        "raw_content": content,
    }


def _score_fix_context(item: dict, pytest_signals: list[str], contracts: list) -> int:
    score = 0

    target_file = str(item.get("target_file", "")).strip()
    required_symbols = item.get("required_symbols", []) or []
    issue_type = str(item.get("issue_type", "")).strip()
    classification = str(item.get("classification", "")).strip()

    if item.get("priority") == "P0":
        score += 100

    if classification == "AUTO_FIX_SAFE":
        score += 120
    elif classification == "AUTO_FIX_REVIEW":
        score += 70
    elif classification == "HUMAN_ONLY":
        score -= 500

    if issue_type == "empty_test_file":
        score += 180
    if issue_type == "corrupted_or_non_test_content":
        score += 170
    if issue_type == "missing_public_contract":
        score += 140
    if issue_type == "contract_test_failure":
        score += 120
    if issue_type == "lint_failure":
        score += 115
    if issue_type == "runtime_failure":
        score += 120
    if issue_type == "test_failure":
        score += 110
    if issue_type == "ci_failure":
        score += 100

    for signal in pytest_signals:
        if target_file and target_file in signal:
            score += 50

        for symbol in required_symbols:
            if symbol and symbol in signal:
                score += 80

    for contract in contracts:
        try:
            contract_file = str(contract[0]).strip()
            contract_symbol = str(contract[1]).strip()
        except Exception:
            continue

        if target_file and target_file == contract_file:
            score += 60

        for symbol in required_symbols:
            if symbol and symbol == contract_symbol:
                score += 90

    score += min(len(item.get("related_tests", []) or []), 6) * 3
    score += min(len(item.get("related_contracts", [] ) or []), 4) * 4
    score += min(len(item.get("notes", []) or []), 4) * 2

    return score


def select_best_subset(paths: list[str], max_items: int) -> list[str]:
    out = []
    seen = set()

    for p in paths:
        p = str(p).strip()
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
        if len(out) >= max_items:
            break

    return out


def load_candidate_fix_contexts() -> list[dict]:
    filtered_fix_context = read_json(AUDIT_OUT / "filtered_fix_context.json")
    issue_classification = read_json(AUDIT_OUT / "issue_classification.json")

    filtered = filtered_fix_context.get("filtered_contexts", [])
    classified = issue_classification.get("fix_contexts", [])

    if filtered:
        filtered_targets = {
            str(item.get("target_file", "")).strip(): item
            for item in filtered
            if str(item.get("target_file", "")).strip()
        }

        out = []
        for item in classified:
            target_file = str(item.get("target_file", "")).strip()
            if not target_file:
                continue
            if target_file not in filtered_targets:
                continue
            out.append(item)

        if out:
            return out

    return classified or []


def load_target_context() -> dict:
    fix_contexts = load_candidate_fix_contexts()
    global_context = read_json(AUDIT_OUT / "global_workflow_context.json")
    test_failure_context = read_json(AUDIT_OUT / "test_failure_context.json")
    issue_classification = read_json(AUDIT_OUT / "issue_classification.json")
    repair_history = read_json(AUDIT_OUT / "repair_history.json")

    if not fix_contexts:
        return {}

    pytest_signals = global_context.get("pytest_signals", []) or []
    contracts = global_context.get("contracts", []) or []
    failing_tests = test_failure_context.get("test_failure_contexts", []) or []

    filtered_contexts = []
    for item in fix_contexts:
        classification = str(item.get("classification", "")).strip()
        if classification == "HUMAN_ONLY":
            continue
        filtered_contexts.append(item)

    if not filtered_contexts:
        return {}

    scored = []
    for item in filtered_contexts:
        score = _score_fix_context(item, pytest_signals, contracts)
        class_rank = CLASS_PRIORITY.get(str(item.get("classification", "")).strip(), 99)
        scored.append((class_rank, -score, item))

    scored.sort(key=lambda x: (x[0], x[1]))

    selected = []
    seen = set()

    for _, _, item in scored:
        target_file = str(item.get("target_file", "")).strip()
        if not target_file or target_file in seen:
            continue

        if item.get("priority") != "P0":
            continue

        seen.add(target_file)
        selected.append(item)

        if len(selected) >= MAX_TARGETS:
            break

    if not selected and filtered_contexts:
        safe_first = [
            x for x in filtered_contexts
            if str(x.get("classification", "")).strip() == "AUTO_FIX_SAFE"
        ]
        if safe_first:
            selected = [safe_first[0]]
        else:
            selected = [filtered_contexts[0]]

    files_payload = []

    for target in selected:
        target_file_rel = target["target_file"]
        target_file = ROOT / target_file_rel

        related_tests_rel = select_best_subset(target.get("related_tests", []) or [], 3)
        related_fixtures_rel = select_best_subset(target.get("related_fixtures", []) or [], 2)
        related_contracts_rel = select_best_subset(target.get("related_contracts", []) or [], 2)

        related_tests = [ROOT / t for t in related_tests_rel]
        related_fixtures = [ROOT / t for t in related_fixtures_rel]
        related_contracts = [ROOT / t for t in related_contracts_rel]

        files_payload.append(
            {
                "target": {
                    "target_file": target.get("target_file", ""),
                    "required_symbols": target.get("required_symbols", []) or [],
                    "related_tests": related_tests_rel,
                    "related_fixtures": related_fixtures_rel,
                    "related_contracts": related_contracts_rel,
                    "notes": trim_list(target.get("notes", []) or [], 5),
                    "priority": target.get("priority", ""),
                    "issue_type": target.get("issue_type", ""),
                    "related_source_file": target.get("related_source_file", ""),
                    "classification": target.get("classification", ""),
                    "classification_reasons": trim_list(
                        target.get("classification_reasons", []) or [], 4
                    ),
                },
                "target_file_text": trimmed_text(read_text(target_file), MAX_TARGET_FILE_CHARS),
                "related_tests_text": {
                    str(p.relative_to(ROOT)).replace("\\", "/"): trimmed_text(
                        read_text(p), MAX_RELATED_TEST_CHARS
                    )
                    for p in related_tests
                    if p.exists()
                },
                "related_fixtures_text": {
                    str(p.relative_to(ROOT)).replace("\\", "/"): trimmed_text(
                        read_text(p), MAX_RELATED_FIXTURE_CHARS
                    )
                    for p in related_fixtures
                    if p.exists()
                },
                "related_contracts_text": {
                    str(p.relative_to(ROOT)).replace("\\", "/"): trimmed_text(
                        read_text(p), MAX_RELATED_CONTRACT_CHARS
                    )
                    for p in related_contracts
                    if p.exists()
                },
            }
        )

    normalized_failing_tests = []
    for item in failing_tests[:MAX_FAILING_TEST_CONTEXTS]:
        if not isinstance(item, dict):
            continue
        normalized_failing_tests.append(
            {
                "target_file": str(item.get("target_file", "")).strip(),
                "issue_type": str(item.get("issue_type", "")).strip(),
                "related_source_file": str(item.get("related_source_file", "")).strip(),
                "notes": trim_list(item.get("notes", []) or [], 4),
            }
        )

    return {
        "targets": selected,
        "files_payload": files_payload,
        "global_context": {
            "pytest_signals": (global_context.get("pytest_signals", []) or [])[:MAX_PYTEST_SIGNALS],
            "ai_root_causes": (global_context.get("ai_root_causes", []) or [])[:MAX_AI_ROOT_CAUSES],
            "contracts": (global_context.get("contracts", []) or [])[:MAX_CONTRACTS],
        },
        "failing_tests": normalized_failing_tests,
        "classification_summary": issue_classification.get("summary", {}),
        "repair_history_summary": {
            "successful_repairs": len(repair_history.get("successful_repairs", []) or []),
            "failed_repairs": len(repair_history.get("failed_repairs", []) or []),
            "skipped_contexts": len(repair_history.get("skipped_contexts", []) or []),
        },
    }


def build_messages(ctx: dict) -> list[dict]:
    system_prompt = """
You are a conservative Python patch generator working on the Pickfair repository.

Rules:
- generate minimal safe patches
- preserve backward compatibility
- avoid redesign
- fix only provided files
- restore missing public contracts
- respect tests
- prefer solving multiple closely-related P0 blockers in one coordinated patch
- if a failing test file is empty, corrupted, or contains non-test content, repair the test file itself with the minimum valid pytest test
- when repairing a broken test file, do not invent large new behaviors; write the smallest meaningful test consistent with the related source file and the failure context
- NEVER patch targets classified as HUMAN_ONLY
- prefer AUTO_FIX_SAFE targets over AUTO_FIX_REVIEW targets
- for AUTO_FIX_REVIEW targets, keep changes even smaller and avoid business-logic redesign
- assume filtered_fix_context already removed previously attempted contexts; do not broaden scope beyond the provided targets

Return STRICT JSON:
{
  "summary": "...",
  "target_files": ["file.py"],
  "why_this_fix": "...",
  "proposed_patches": [
    {
      "target_file": "path.py",
      "patch": "unified diff patch"
    }
  ],
  "tests_to_run": [],
  "risk": "low|medium|high"
}
""".strip()

    user_payload = {
        "task": "Generate the smallest safe coordinated patch candidate for the selected P0 fix contexts.",
        "classification_summary": ctx.get("classification_summary", {}),
        "repair_history_summary": ctx.get("repair_history_summary", {}),
        "targets": [
            {
                "target_file": str(x.get("target_file", "")).strip(),
                "required_symbols": x.get("required_symbols", []) or [],
                "priority": x.get("priority", ""),
                "issue_type": x.get("issue_type", ""),
                "classification": x.get("classification", ""),
                "classification_reasons": trim_list(
                    x.get("classification_reasons", []) or [], 4
                ),
                "related_tests": select_best_subset(x.get("related_tests", []) or [], 3),
                "related_contracts": select_best_subset(x.get("related_contracts", []) or [], 2),
                "notes": trim_list(x.get("notes", []) or [], 5),
            }
            for x in ctx["targets"]
        ],
        "files_payload": ctx["files_payload"],
        "failing_tests": ctx["failing_tests"],
        "global_context": ctx["global_context"],
    }

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def normalize_patch_candidate(data: dict, ctx: dict) -> dict:
    allowed_files = {
        item["target_file"]
        for item in ctx.get("targets", [])
        if item.get("target_file")
    }

    patches = data.get("proposed_patches", [])
    if not isinstance(patches, list):
        patches = []

    normalized = []

    for item in patches:
        if not isinstance(item, dict):
            continue

        target_file = str(item.get("target_file", "")).strip()
        patch = str(item.get("patch", "")).strip()

        if target_file not in allowed_files:
            continue
        if not patch:
            continue

        normalized.append(
            {
                "target_file": target_file,
                "patch": patch,
            }
        )

    tests_to_run = data.get("tests_to_run", [])
    if not isinstance(tests_to_run, list):
        tests_to_run = []

    risk = str(data.get("risk", "unknown")).strip().lower()
    if risk not in {"low", "medium", "high"}:
        risk = "unknown"

    summary = str(data.get("summary", "")).strip()
    why_this_fix = str(data.get("why_this_fix", "")).strip()

    if not summary:
        summary = "Coordinated patch candidate generated."
    if not why_this_fix:
        why_this_fix = "Restore the highest-priority public contracts with the smallest coordinated fix."

    return {
        "summary": summary,
        "target_files": [p["target_file"] for p in normalized],
        "why_this_fix": why_this_fix,
        "proposed_patches": normalized,
        "tests_to_run": [str(x).strip() for x in tests_to_run if str(x).strip()],
        "risk": risk,
    }


def render_patch_candidate_md(data: dict, model_used: str) -> str:
    lines = []
    lines.append("Patch Candidate")
    lines.append("")
    lines.append(f"Model used: {model_used}")
    lines.append("")
    lines.append(f"Summary: {data.get('summary', '')}")
    lines.append("")
    lines.append("Target files:")

    target_files = data.get("target_files", [])
    if target_files:
        for file in target_files:
            lines.append(f"- {file}")
    else:
        lines.append("- Nessun file target disponibile.")

    lines.append("")
    lines.append(f"Risk: {data.get('risk', '')}")
    lines.append("")
    lines.append("Why this fix")
    lines.append(data.get("why_this_fix", ""))
    lines.append("")
    lines.append("Tests to run")

    tests = data.get("tests_to_run", [])
    if tests:
        for test in tests:
            lines.append(f"- {test}")
    else:
        lines.append("- Nessun test suggerito.")

    lines.append("")
    lines.append("Proposed patches")
    lines.append("")

    proposed = data.get("proposed_patches", [])
    if proposed:
        for item in proposed:
            lines.append(f"Target file: {item.get('target_file', '')}")
            lines.append("")
            lines.append("```diff")
            lines.append(item.get("patch", ""))
            lines.append("```")
            lines.append("")
    else:
        lines.append("_Nessuna patch disponibile._")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    ctx = load_target_context()

    if not ctx:
        data = {
            "summary": "No fix context available",
            "target_files": [],
            "why_this_fix": "",
            "proposed_patches": [],
            "tests_to_run": [],
            "risk": "unknown",
        }
        write_json(AUDIT_OUT / "patch_candidate.json", data)
        write_text(AUDIT_OUT / "patch_candidate.md", "No context.")
        return 0

    try:
        messages = build_messages(ctx)

        resp = call_openrouter(
            task_type="patch",
            messages=messages,
        )

        content = resp["content"]
        model_used = resp["model_used"]
        raw = resp.get("raw", {})

        parsed = parse_json_content(content)
        normalized = normalize_patch_candidate(parsed, ctx)

        if not normalized["proposed_patches"]:
            raise RuntimeError("AI non ha prodotto patch valide")

        write_json(AUDIT_OUT / "patch_candidate_raw_response.json", raw)
        write_json(AUDIT_OUT / "patch_candidate.json", normalized)
        write_text(
            AUDIT_OUT / "patch_candidate.md",
            render_patch_candidate_md(normalized, model_used),
        )

        print("Patch candidate generator completato")
        print("Model:", model_used)
        return 0

    except Exception as exc:
        fallback = {
            "summary": "Patch candidate generator failed",
            "target_files": [],
            "why_this_fix": str(exc),
            "proposed_patches": [],
            "tests_to_run": [],
            "risk": "unknown",
        }

        write_json(AUDIT_OUT / "patch_candidate.json", fallback)
        write_text(
            AUDIT_OUT / "patch_candidate.md",
            json.dumps(fallback, indent=2, ensure_ascii=False),
        )

        print("Patch candidate generator fallito:", exc)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())