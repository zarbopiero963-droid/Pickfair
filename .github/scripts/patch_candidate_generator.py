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

    selected = []
    seen = set()

    for item in fix_contexts:
        if item.get("priority") != "P0":
            continue

        target_file = item.get("target_file", "").strip()
        if not target_file or target_file in seen:
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
    }


def build_messages(ctx: dict) -> list[dict]:
    system_prompt = """
You are a conservative Python multi-file patch generator working on the Pickfair repository.

You MUST:
- generate the minimum viable coordinated patch
- preserve backward compatibility
- avoid redesign
- avoid adding features
- avoid touching unrelated files
- respect tests as the primary contract
- only patch files explicitly present in the provided target contexts
- prefer restoring missing public symbols with the smallest compatible fix

Return STRICT JSON with this schema:
{
  "summary": "short summary",
  "target_files": ["file1.py", "file2.py"],
  "why_this_fix": "string",
  "proposed_patches": [
    {
      "target_file": "path.py",
      "patch": "full unified-diff style patch as plain text"
    }
  ],
  "tests_to_run": ["tests/file.py"],
  "risk": "low|medium|high"
}
""".strip()

    user_payload = {
        "task": "Generate the smallest safe coordinated patch candidate for the selected P0 fix contexts.",
        "targets": ctx["targets"],
        "global_context": {
            "pytest_signals": ctx["global_context"].get("pytest_signals", [])[:20],
            "ai_root_causes": ctx["global_context"].get("ai_root_causes", [])[:10],
            "contracts": ctx["global_context"].get("contracts", [])[:20],
        },
        "files_payload": ctx["files_payload"],
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

    fence_match = re.search(r"```\s*(.*?)\s*```", content, re.S)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except Exception:
            pass

    return {
        "summary": "Patch candidate response was not valid JSON.",
        "target_files": [],
        "why_this_fix": "",
        "proposed_patches": [],
        "tests_to_run": [],
        "risk": "unknown",
        "raw_content": content,
    }


def normalize_patch_candidate(data: dict, ctx: dict) -> dict:
    target_files = data.get("target_files", [])
    if not isinstance(target_files, list):
        target_files = []

    proposed_patches = data.get("proposed_patches", [])
    if not isinstance(proposed_patches, list):
        proposed_patches = []

    normalized_patches = []
    normalized_target_files = []

    allowed_target_files = {
        item.get("target_file", "").strip()
        for item in ctx.get("targets", [])
        if item.get("target_file", "").strip()
    }

    for item in proposed_patches:
        if not isinstance(item, dict):
            continue

        target_file = str(item.get("target_file", "")).strip()
        patch = str(item.get("patch", "")).strip()

        if not target_file or not patch:
            continue

        if target_file not in allowed_target_files:
            continue

        normalized_patches.append(
            {
                "target_file": target_file,
                "patch": patch,
            }
        )
        normalized_target_files.append(target_file)

    if not normalized_target_files and target_files:
        normalized_target_files = [
            str(f).strip()
            for f in target_files
            if str(f).strip() in allowed_target_files
        ]

    tests_to_run = data.get("tests_to_run", [])
    if not isinstance(tests_to_run, list):
        tests_to_run = []

    summary = str(data.get("summary", "")).strip()
    why_this_fix = str(data.get("why_this_fix", "")).strip()
    risk = str(data.get("risk", "unknown")).strip().lower()

    if risk not in {"low", "medium", "high"}:
        risk = "unknown"

    if not summary:
        summary = "Coordinated multi-file patch candidate generated."

    if not why_this_fix:
        why_this_fix = "Restore the highest-priority public contracts with the smallest coordinated fix."

    return {
        "summary": summary,
        "target_files": normalized_target_files,
        "why_this_fix": why_this_fix,
        "proposed_patches": normalized_patches,
        "tests_to_run": tests_to_run,
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


def fallback_patch(ctx: dict) -> dict:
    targets = ctx.get("targets", [])
    return {
        "summary": "Patch candidate non disponibile: fallback locale.",
        "target_files": [t.get("target_file", "") for t in targets if t.get("target_file", "")],
        "why_this_fix": "Il generatore patch non ha restituito JSON valido oppure non è disponibile.",
        "proposed_patches": [],
        "tests_to_run": sorted(
            {
                test
                for t in targets
                for test in t.get("related_tests", [])
            }
        ),
        "risk": "unknown",
    }


def main() -> int:
    ctx = load_target_context()
    if not ctx:
        data = {
            "summary": "Nessun fix context disponibile.",
            "target_files": [],
            "why_this_fix": "",
            "proposed_patches": [],
            "tests_to_run": [],
            "risk": "unknown",
        }
        write_json(AUDIT_OUT / "patch_candidate.json", data)
        write_text(AUDIT_OUT / "patch_candidate.md", render_patch_candidate_md(data, "no-context"))
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
        normalized = normalize_patch_candidate(parsed, ctx)

        write_json(AUDIT_OUT / "patch_candidate_raw_response.json", raw)
        write_json(AUDIT_OUT / "patch_candidate.json", normalized)
        write_text(AUDIT_OUT / "patch_candidate.md", render_patch_candidate_md(normalized, model_used))

        print(f"Patch candidate generator completato. Model used: {model_used}")
        return 0

    except Exception as exc:
        data = fallback_patch(ctx)
        model_used = f"fallback-local-error-{type(exc).__name__}"
        write_json(AUDIT_OUT / "patch_candidate.json", data)
        write_text(AUDIT_OUT / "patch_candidate.md", render_patch_candidate_md(data, model_used))
        print(f"Patch candidate generator fallito: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())