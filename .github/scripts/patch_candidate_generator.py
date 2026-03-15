#!/usr/bin/env python3

import json
import re
from pathlib import Path

from openrouter_model_router import call_openrouter

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
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


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

    if item.get("priority") == "P0":
        score += 100

    if issue_type == "empty_test_file":
        score += 180

    if issue_type == "corrupted_or_non_test_content":
        score += 170

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

    score += min(len(item.get("related_tests", []) or []), 10)
    return score


def load_target_context() -> dict:
    fix_context = read_json(AUDIT_OUT / "fix_context.json")
    global_context = read_json(AUDIT_OUT / "global_workflow_context.json")
    test_failure_context = read_json(AUDIT_OUT / "test_failure_context.json")

    fix_contexts = fix_context.get("fix_contexts", [])
    if not fix_contexts:
        return {}

    pytest_signals = global_context.get("pytest_signals", []) or []
    contracts = global_context.get("contracts", []) or []
    failing_tests = test_failure_context.get("test_failure_contexts", []) or []

    scored = []
    for item in fix_contexts:
        score = _score_fix_context(item, pytest_signals, contracts)
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)

    selected = []
    seen = set()

    for score, item in scored:
        target_file = str(item.get("target_file", "")).strip()
        if not target_file or target_file in seen:
            continue

        if item.get("priority") != "P0":
            continue

        seen.add(target_file)
        selected.append(item)

        if len(selected) >= 5:
            break

    if not selected and fix_contexts:
        selected = [fix_contexts[0]]

    files_payload = []

    for target in selected:
        target_file = ROOT / target["target_file"]
        related_tests = [ROOT / t for t in target.get("related_tests", [])]
        related_fixtures = [ROOT / t for t in target.get("related_fixtures", [])]
        related_contracts = [ROOT / t for t in target.get("related_contracts", [])]

        files_payload.append(
            {
                "target": target,
                "target_file_text": read_text(target_file)[:25000],
                "related_tests_text": {
                    str(p.relative_to(ROOT)).replace("\\", "/"): read_text(p)[:15000]
                    for p in related_tests
                    if p.exists()
                },
                "related_fixtures_text": {
                    str(p.relative_to(ROOT)).replace("\\", "/"): read_text(p)[:12000]
                    for p in related_fixtures
                    if p.exists()
                },
                "related_contracts_text": {
                    str(p.relative_to(ROOT)).replace("\\", "/"): read_text(p)[:12000]
                    for p in related_contracts
                    if p.exists()
                },
            }
        )

    return {
        "targets": selected,
        "files_payload": files_payload,
        "global_context": global_context,
        "failing_tests": failing_tests,
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
        "targets": ctx["targets"],
        "files_payload": ctx["files_payload"],
        "failing_tests": ctx["failing_tests"],
        "global_context": {
            "pytest_signals": ctx["global_context"].get("pytest_signals", [])[:20],
            "ai_root_causes": ctx["global_context"].get("ai_root_causes", [])[:10],
            "contracts": ctx["global_context"].get("contracts", [])[:20],
        },
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

    return {
        "summary": str(data.get("summary", "")).strip(),
        "target_files": [p["target_file"] for p in normalized],
        "why_this_fix": str(data.get("why_this_fix", "")).strip(),
        "proposed_patches": normalized,
        "tests_to_run": tests_to_run,
        "risk": str(data.get("risk", "unknown")).strip().lower() or "unknown",
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

        parsed = parse_json_content(content)
        normalized = normalize_patch_candidate(parsed, ctx)

        if not normalized["proposed_patches"]:
            raise RuntimeError("AI non ha prodotto patch valide")

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