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


def load_context() -> dict:
    patch_candidate = read_json(AUDIT_OUT / "patch_candidate.json")
    fix_context = read_json(AUDIT_OUT / "fix_context.json")
    global_context = read_json(AUDIT_OUT / "global_workflow_context.json")

    target_files = patch_candidate.get("target_files", []) or []
    proposed_patches = patch_candidate.get("proposed_patches", []) or []
    tests_to_run = patch_candidate.get("tests_to_run", []) or []

    related_fix_contexts = []
    for item in fix_context.get("fix_contexts", []):
        target_file = str(item.get("target_file", "")).strip()
        if target_file in target_files:
            related_fix_contexts.append(item)

    files_payload = []

    for target_file in target_files:
        target_path = ROOT / target_file
        target_fix_context = next(
            (item for item in related_fix_contexts if item.get("target_file") == target_file),
            {},
        )

        related_tests = [ROOT / t for t in target_fix_context.get("related_tests", [])]
        related_fixtures = [ROOT / t for t in target_fix_context.get("related_fixtures", [])]
        related_contracts = [ROOT / t for t in target_fix_context.get("related_contracts", [])]

        patch_text = ""
        for item in proposed_patches:
            if item.get("target_file") == target_file:
                patch_text = str(item.get("patch", ""))
                break

        files_payload.append(
            {
                "target_file": target_file,
                "required_symbols": target_fix_context.get("required_symbols", []),
                "patch_text": patch_text,
                "target_file_text": read_text(target_path)[:25000] if target_path.exists() else "",
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
        "patch_candidate": patch_candidate,
        "related_fix_contexts": related_fix_contexts,
        "global_context": {
            "pytest_signals": global_context.get("pytest_signals", [])[:20],
            "ai_root_causes": global_context.get("ai_root_causes", [])[:10],
            "contracts": global_context.get("contracts", [])[:20],
        },
        "files_payload": files_payload,
        "tests_to_run": tests_to_run,
    }


def build_messages(ctx: dict) -> list[dict]:
    system_prompt = """
You are a conservative Python multi-file patch verifier working on the Pickfair repository.

Your job is NOT to generate a new patch.
Your job is to verify whether the proposed coordinated patch candidate appears coherent with:
- the target files
- the requested symbols
- the related tests
- the contract expectations
- the repository's rule of minimum viable fix

You MUST:
- be skeptical
- prefer backward compatibility
- detect if the patch set is too small, too risky, unrelated, or likely insufficient
- never assume the patch is correct just because it looks clean
- evaluate the patch set as a whole, but also note weak files if any

Return STRICT JSON with this schema:
{
  "summary": "short paragraph",
  "verdict": "approve|weak-approve|reject",
  "confidence": "low|medium|high",
  "why": ["string"],
  "likely_gaps": ["string"],
  "tests_to_run": ["tests/file.py"],
  "safe_next_step": "string"
}
""".strip()

    user_payload = {
        "task": "Verify whether this coordinated multi-file patch candidate is coherent with the target fix contexts and tests.",
        "patch_candidate": ctx["patch_candidate"],
        "related_fix_contexts": ctx["related_fix_contexts"],
        "global_context": ctx["global_context"],
        "files_payload": ctx["files_payload"],
        "tests_to_run": ctx["tests_to_run"],
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
        "summary": "Patch verification response was not valid JSON.",
        "verdict": "reject",
        "confidence": "low",
        "why": [],
        "likely_gaps": ["Model response was not valid JSON."],
        "tests_to_run": [],
        "safe_next_step": "Review the coordinated patch manually.",
        "raw_content": content,
    }


def normalize_verification(data: dict, ctx: dict) -> dict:
    verdict = str(data.get("verdict", "reject")).strip().lower()
    if verdict not in {"approve", "weak-approve", "reject"}:
        verdict = "reject"

    confidence = str(data.get("confidence", "low")).strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"

    why = data.get("why", [])
    if not isinstance(why, list):
        why = [str(why)]

    likely_gaps = data.get("likely_gaps", [])
    if not isinstance(likely_gaps, list):
        likely_gaps = [str(likely_gaps)]

    tests_to_run = data.get("tests_to_run", [])
    if not isinstance(tests_to_run, list):
        tests_to_run = []

    fallback_tests = sorted(
        {
            test
            for item in ctx.get("related_fix_contexts", [])
            for test in item.get("related_tests", [])
        }
    )

    if not tests_to_run:
        tests_to_run = fallback_tests

    summary = str(data.get("summary", "")).strip()
    safe_next_step = str(data.get("safe_next_step", "")).strip()

    if not summary:
        summary = "Multi-file patch verification completed."
    if not safe_next_step:
        safe_next_step = "Run the listed tests before applying or merging the coordinated patch."

    return {
        "summary": summary,
        "verdict": verdict,
        "confidence": confidence,
        "why": why,
        "likely_gaps": likely_gaps,
        "tests_to_run": tests_to_run,
        "safe_next_step": safe_next_step,
    }


def render_verification_md(data: dict, model_used: str) -> str:
    lines = []
    lines.append("Patch Verification")
    lines.append("")
    lines.append(f"Model used: {model_used}")
    lines.append("")
    lines.append(f"Verdict: {data.get('verdict', 'unknown')}")
    lines.append(f"Confidence: {data.get('confidence', 'unknown')}")
    lines.append("")
    lines.append("Summary")
    lines.append(data.get("summary", ""))
    lines.append("")
    lines.append("Why")

    why = data.get("why", [])
    if why:
        for item in why:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessuna motivazione disponibile.")

    lines.append("")
    lines.append("Likely gaps")

    gaps = data.get("likely_gaps", [])
    if gaps:
        for item in gaps:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessun gap segnalato.")

    lines.append("")
    lines.append("Tests to run")

    tests = data.get("tests_to_run", [])
    if tests:
        for test in tests:
            lines.append(f"- {test}")
    else:
        lines.append("- Nessun test suggerito.")

    lines.append("")
    lines.append("Safe next step")
    lines.append(data.get("safe_next_step", ""))
    lines.append("")

    return "\n".join(lines)


def fallback_verification(ctx: dict) -> dict:
    patch_candidate = ctx.get("patch_candidate", {})
    target_files = patch_candidate.get("target_files", []) or []

    return {
        "summary": "Patch verifier multi-file non disponibile: fallback locale.",
        "verdict": "weak-approve" if target_files else "reject",
        "confidence": "low",
        "why": [
            "La patch candidate multi-file esiste ma non è stata verificata in profondità dal verifier."
        ],
        "likely_gaps": [
            "Il comportamento atteso dai test potrebbe richiedere più del ripristino minimo dei simboli pubblici."
        ],
        "tests_to_run": sorted(
            {
                test
                for item in ctx.get("related_fix_contexts", [])
                for test in item.get("related_tests", [])
            }
        ),
        "safe_next_step": "Rilanciare manualmente i test target prima di applicare qualsiasi modifica multi-file.",
    }


def main() -> int:
    ctx = load_context()

    patch_candidate = ctx.get("patch_candidate", {})
    if not patch_candidate:
        data = {
            "summary": "Nessuna patch candidate disponibile.",
            "verdict": "reject",
            "confidence": "low",
            "why": ["Manca audit_out/patch_candidate.json"],
            "likely_gaps": [],
            "tests_to_run": [],
            "safe_next_step": "Generare prima una patch candidate.",
        }
        write_json(AUDIT_OUT / "patch_verification.json", data)
        write_text(
            AUDIT_OUT / "patch_verification.md",
            render_verification_md(data, "no-patch-candidate"),
        )
        print("Nessuna patch candidate disponibile.")
        return 0

    try:
        messages = build_messages(ctx)
        resp = call_openrouter(
            task_type="review",
            messages=messages,
        )

        content = resp["content"]
        model_used = resp["model_used"]
        raw = resp.get("raw", {})

        parsed = parse_json_content(content)
        normalized = normalize_verification(parsed, ctx)

        write_json(AUDIT_OUT / "patch_verification_raw_response.json", raw)
        write_json(AUDIT_OUT / "patch_verification.json", normalized)
        write_text(
            AUDIT_OUT / "patch_verification.md",
            render_verification_md(normalized, model_used),
        )

        print(f"Patch verifier completato. Model used: {model_used}")
        return 0

    except Exception as exc:
        data = fallback_verification(ctx)
        model_used = f"fallback-local-error-{type(exc).__name__}"
        write_json(AUDIT_OUT / "patch_verification.json", data)
        write_text(
            AUDIT_OUT / "patch_verification.md",
            render_verification_md(data, model_used),
        )
        print(f"Patch verifier fallito: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())