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
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_target_context() -> dict:
    fix_context = read_json(AUDIT_OUT / "fix_context.json")
    global_context = read_json(AUDIT_OUT / "global_workflow_context.json")

    fix_contexts = fix_context.get("fix_contexts", [])
    if not fix_contexts:
        return {}

    target = None
    for item in fix_contexts:
        if item.get("priority") == "P0":
            target = item
            break

    if target is None:
        target = fix_contexts[0]

    target_file = ROOT / target["target_file"]
    related_tests = [ROOT / t for t in target.get("related_tests", [])]
    related_fixtures = [ROOT / t for t in target.get("related_fixtures", [])]
    related_contracts = [ROOT / t for t in target.get("related_contracts", [])]

    return {
        "target": target,
        "global_context": global_context,
        "target_file_text": read_text(target_file)[:25000],
        "related_tests_text": {
            str(p.relative_to(ROOT)).replace("\\", "/"): read_text(p)[:15000]
            for p in related_tests
        },
        "related_fixtures_text": {
            str(p.relative_to(ROOT)).replace("\\", "/"): read_text(p)[:12000]
            for p in related_fixtures
        },
        "related_contracts_text": {
            str(p.relative_to(ROOT)).replace("\\", "/"): read_text(p)[:12000]
            for p in related_contracts
        },
    }


def build_messages(ctx: dict) -> list[dict]:
    target = ctx["target"]

    system_prompt = """
You are a conservative Python patch generator working on the Pickfair repository.

You MUST:
- generate the minimum viable patch
- preserve backward compatibility
- avoid redesign
- avoid adding features
- avoid touching unrelated files
- respect tests as the primary contract
- produce a patch candidate only, not prose-first advice

Return STRICT JSON with this schema:
{
  "summary": "short summary",
  "target_file": "path.py",
  "why_this_fix": "string",
  "proposed_patch": "full unified-diff style patch as plain text",
  "tests_to_run": ["tests/file.py"],
  "risk": "low|medium|high"
}
""".strip()

    user_payload = {
        "task": "Generate the smallest safe patch candidate for the selected P0 fix context.",
        "target": target,
        "global_context": {
            "pytest_signals": ctx["global_context"].get("pytest_signals", [])[:20],
            "ai_root_causes": ctx["global_context"].get("ai_root_causes", [])[:10],
            "contracts": ctx["global_context"].get("contracts", [])[:20],
        },
        "target_file_text": ctx["target_file_text"],
        "related_tests_text": ctx["related_tests_text"],
        "related_fixtures_text": ctx["related_fixtures_text"],
        "related_contracts_text": ctx["related_contracts_text"],
    }

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def parse_json_content(content: str) -> dict:
    content = content.strip()

    try:
        return json.loads(content)
    except Exception:
        pass

    fence_match = re.search(r"```json\s*(.*?)\s*```", content, re.S)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except Exception:
            pass

    return {
        "summary": "Patch candidate response was not valid JSON.",
        "target_file": "",
        "why_this_fix": "",
        "proposed_patch": content,
        "tests_to_run": [],
        "risk": "unknown",
    }


def render_patch_candidate_md(data: dict, model_used: str) -> str:
    lines: list[str] = []
    lines.append("Patch Candidate")
    lines.append("")
    lines.append(f"Model used: {model_used}")
    lines.append("")
    lines.append(f"Summary: {data.get('summary', '')}")
    lines.append("")
    lines.append(f"Target file: {data.get('target_file', '')}")
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
    lines.append("Proposed patch")
    lines.append("")
    lines.append("```diff")
    lines.append(data.get("proposed_patch", ""))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def fallback_patch(ctx: dict) -> dict:
    target = ctx.get("target", {})
    return {
        "summary": "Patch candidate non disponibile: fallback locale.",
        "target_file": target.get("target_file", ""),
        "why_this_fix": "Il generatore patch non ha restituito JSON valido oppure non è disponibile.",
        "proposed_patch": "",
        "tests_to_run": target.get("related_tests", []),
        "risk": "unknown",
    }


def main() -> int:
    ctx = load_target_context()

    if not ctx:
        data = {
            "summary": "Nessun fix context disponibile.",
            "target_file": "",
            "why_this_fix": "",
            "proposed_patch": "",
            "tests_to_run": [],
            "risk": "unknown",
        }
        write_json(AUDIT_OUT / "patch_candidate.json", data)
        write_text(
            AUDIT_OUT / "patch_candidate.md",
            render_patch_candidate_md(data, "no-context"),
        )
        print("Nessun fix context disponibile.")
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

        write_json(AUDIT_OUT / "patch_candidate_raw_response.json", raw)
        write_json(AUDIT_OUT / "patch_candidate.json", parsed)
        write_text(
            AUDIT_OUT / "patch_candidate.md",
            render_patch_candidate_md(parsed, model_used),
        )

        print(f"Patch candidate generator completato. Model used: {model_used}")
        return 0

    except Exception as exc:
        data = fallback_patch(ctx)
        model_used = f"fallback-local-error-{type(exc).__name__}"
        write_json(AUDIT_OUT / "patch_candidate.json", data)
        write_text(
            AUDIT_OUT / "patch_candidate.md",
            render_patch_candidate_md(data, model_used),
        )
        print(f"Patch candidate generator fallito: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())