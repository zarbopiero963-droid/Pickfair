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
            "summary": "Empty AI response",
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
        "summary": "Invalid JSON from AI",
        "target_files": [],
        "why_this_fix": "",
        "proposed_patches": [],
        "tests_to_run": [],
        "risk": "unknown",
        "raw_content": content,
    }


def load_target_context() -> dict:
    fix_context = read_json(AUDIT_OUT / "fix_context.json")
    global_context = read_json(AUDIT_OUT / "global_workflow_context.json")
    test_failure_context = read_json(AUDIT_OUT / "test_failure_context.json")

    fix_contexts = fix_context.get("fix_contexts", [])
    if not fix_contexts:
        return {}

    targets = []

    for item in fix_contexts:
        if item.get("priority") == "P0":
            targets.append(item)

    if not targets and fix_contexts:
        targets = [fix_contexts[0]]

    targets = targets[:5]

    files_payload = []

    for target in targets:
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
        "targets": targets,
        "files_payload": files_payload,
        "global_context": global_context,
        "failing_tests": test_failure_context.get("test_failure_contexts", []),
    }


def build_messages(ctx: dict) -> list[dict]:
    system_prompt = """
You are a conservative Python patch generator working on the Pickfair repository.

GENERAL RULES

- generate minimal safe patches
- preserve backward compatibility
- never redesign modules
- modify only provided files
- restore missing public contracts
- respect test expectations
- prefer fixing multiple P0 issues in one patch when closely related


TEST REPAIR RULES

Sometimes the failing file is a test file.

If a test file is:

- empty
- corrupted
- truncated
- contains non-pytest code

you must repair the test.

But NEVER create placeholder tests.

Forbidden:

assert True
pass
dummy tests

Instead generate the SMALLEST SEMANTICALLY CORRECT pytest test.

The repaired test must:

- verify real behavior
- match the related module
- reproduce the failure context
- avoid inventing new features


PATCH FORMAT

Return STRICT JSON:

{
  "summary": "...",
  "target_files": ["file.py"],
  "why_this_fix": "...",
  "proposed_patches": [
    {
      "target_file": "path.py",
      "patch": "unified diff"
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

    return {
        "summary": str(data.get("summary", "")).strip(),
        "target_files": [p["target_file"] for p in normalized],
        "why_this_fix": str(data.get("why_this_fix", "")).strip(),
        "proposed_patches": normalized,
        "tests_to_run": data.get("tests_to_run", []),
        "risk": str(data.get("risk", "unknown")).lower(),
    }


def main() -> int:
    ctx = load_target_context()

    if not ctx:
        write_text(AUDIT_OUT / "patch_candidate.md", "No context available")
        return 0

    try:
        messages = build_messages(ctx)

        resp = call_openrouter(
            task_type="patch",
            messages=messages,
        )

        content = resp.get("content", "")
        model_used = resp.get("model_used", "unknown")

        parsed = parse_json_content(content)
        normalized = normalize_patch_candidate(parsed, ctx)

        write_json(AUDIT_OUT / "patch_candidate.json", normalized)

        md = f"""
Patch Candidate

Model: {model_used}

Summary:
{normalized.get("summary","")}

Target files:
{normalized.get("target_files",[])}

Risk:
{normalized.get("risk","")}

Why this fix:
{normalized.get("why_this_fix","")}
"""

        write_text(AUDIT_OUT / "patch_candidate.md", md)

        print("Patch candidate generated")

    except Exception as exc:

        fallback = {
            "summary": "Patch generator failed",
            "why_this_fix": str(exc),
            "target_files": [],
            "proposed_patches": [],
            "tests_to_run": [],
            "risk": "unknown",
        }

        write_json(AUDIT_OUT / "patch_candidate.json", fallback)
        write_text(
            AUDIT_OUT / "patch_candidate.md",
            json.dumps(fallback, indent=2),
        )

        print("Patch generator error:", exc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())