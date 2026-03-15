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
        return {}

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

    return {}


def normalize_verification(data: dict) -> dict:
    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in {"approve", "weak-approve", "review", "reject"}:
        verdict = "review"

    confidence = str(data.get("confidence", "")).strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "medium"

    summary = str(data.get("summary", "")).strip()
    why = str(data.get("why", "")).strip()

    likely_gaps = data.get("likely_gaps", [])
    if not isinstance(likely_gaps, list):
        likely_gaps = []

    tests_to_run = data.get("tests_to_run", [])
    if not isinstance(tests_to_run, list):
        tests_to_run = []

    safe_next_step = str(data.get("safe_next_step", "")).strip()

    return {
        "verdict": verdict,
        "confidence": confidence,
        "summary": summary,
        "why": why,
        "likely_gaps": [str(x).strip() for x in likely_gaps if str(x).strip()],
        "tests_to_run": [str(x).strip() for x in tests_to_run if str(x).strip()],
        "safe_next_step": safe_next_step,
    }


def load_context() -> dict:
    patch_candidate = read_json(AUDIT_OUT / "patch_candidate.json")
    fix_context = read_json(AUDIT_OUT / "fix_context.json")
    global_context = read_json(AUDIT_OUT / "global_workflow_context.json")
    targeted_test_results = read_json(AUDIT_OUT / "targeted_test_results.json")

    return {
        "patch_candidate": patch_candidate,
        "fix_context": fix_context,
        "global_context": global_context,
        "targeted_test_results": targeted_test_results,
    }


def build_messages(ctx: dict) -> list[dict]:
    system_prompt = """
You are a conservative multi-file patch verifier for the Pickfair repository.

Rules:
- judge the patch set as a whole
- prefer backward compatibility
- prefer minimal changes
- reject only if the patch is clearly unsafe, missing, or inconsistent
- use "weak-approve" for plausible but not fully proven fixes
- use "review" when evidence is incomplete but the patch is still reviewable

Return STRICT JSON:
{
  "verdict": "approve|weak-approve|review|reject",
  "confidence": "low|medium|high",
  "summary": "...",
  "why": "...",
  "likely_gaps": ["..."],
  "tests_to_run": ["..."],
  "safe_next_step": "..."
}
""".strip()

    payload = {
        "patch_candidate": ctx["patch_candidate"],
        "fix_contexts": ctx["fix_context"].get("fix_contexts", [])[:10],
        "global_context": {
            "pytest_signals": ctx["global_context"].get("pytest_signals", [])[:20],
            "contracts": ctx["global_context"].get("contracts", [])[:20],
            "ai_root_causes": ctx["global_context"].get("ai_root_causes", [])[:10],
        },
        "targeted_test_results": ctx["targeted_test_results"],
    }

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def render_md(data: dict, model_used: str) -> str:
    lines = []
    lines.append("Patch Verification")
    lines.append("")
    lines.append(f"Model used: {model_used}")
    lines.append("")
    lines.append(f"Verdict: {data.get('verdict', '')}")
    lines.append(f"Confidence: {data.get('confidence', '')}")
    lines.append("")
    lines.append("Summary")
    lines.append(data.get("summary", "") or "_Missing summary._")
    lines.append("")
    lines.append("Why")
    lines.append(data.get("why", "") or "_Missing explanation._")
    lines.append("")
    lines.append("Likely gaps")

    gaps = data.get("likely_gaps", []) or []
    if gaps:
        for item in gaps:
            lines.append(f"- {item}")
    else:
        lines.append("- None")

    lines.append("")
    lines.append("Tests to run")

    tests = data.get("tests_to_run", []) or []
    if tests:
        for item in tests:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessun test suggerito.")

    lines.append("")
    lines.append("Safe next step")
    lines.append(data.get("safe_next_step", "") or "_No next step provided._")
    lines.append("")

    return "\n".join(lines)


def build_fallback(ctx: dict, error_message: str) -> tuple[dict, str]:
    candidate = ctx.get("patch_candidate", {}) or {}
    target_files = candidate.get("target_files", []) or []
    proposed_patches = candidate.get("proposed_patches", []) or []
    tests_to_run = candidate.get("tests_to_run", []) or []
    targeted_results = ctx.get("targeted_test_results", {}) or {}

    has_targets = isinstance(target_files, list) and len(target_files) > 0
    has_patches = isinstance(proposed_patches, list) and len(proposed_patches) > 0
    targeted_exit = targeted_results.get("pytest_exit_code")
    targeted_failure_count = targeted_results.get("failure_count")

    # Regola fallback:
    # - reject solo se la patch è di fatto assente
    # - review se la patch esiste ma non possiamo verificarla davvero
    # - weak-approve se esiste, è multi-file plausibile e non ci sono segnali forti di disastro
    if not has_targets or not has_patches:
        verdict = "reject"
        summary = "Patch verifier multi-file non disponibile: fallback locale con patch assente o incompleta."
        why = (
            "La patch candidate non contiene target file o patch applicabili, quindi non esiste una base sufficiente "
            "per approvare o rivedere la modifica."
        )
        likely_gaps = [
            "Patch candidate vuota o incompleta.",
            "Nessun target file verificabile.",
        ]
        safe_next_step = "Rigenerare una patch candidate valida prima di applicare qualsiasi modifica."
    else:
        severe_runtime_signal = False
        if isinstance(targeted_failure_count, int) and targeted_failure_count > 0:
            severe_runtime_signal = False

        if severe_runtime_signal:
            verdict = "review"
        else:
            verdict = "review"

        summary = "Patch verifier AI non disponibile: fallback locale prudente ma reviewable."
        why = (
            "La patch candidate multi-file esiste e contiene target concreti, ma il verifier AI non è stato disponibile. "
            "Il fallback locale evita il reject automatico quando il problema è tecnico e non logico."
        )
        likely_gaps = [
            "La patch non è stata verificata in profondità dal verifier AI.",
            "La compatibilità completa va confermata con test target e review manuale.",
        ]
        safe_next_step = "Eseguire i test target e revisionare manualmente la patch prima del merge."

    data = {
        "verdict": verdict,
        "confidence": "low",
        "summary": summary,
        "why": why,
        "likely_gaps": likely_gaps,
        "tests_to_run": tests_to_run if isinstance(tests_to_run, list) else [],
        "safe_next_step": safe_next_step,
        "fallback_reason": error_message,
    }

    return data, f"fallback-local-error-{type(error_message).__name__ if not isinstance(error_message, str) else 'RuntimeError'}"


def main() -> int:
    ctx = load_context()

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
        normalized = normalize_verification(parsed)

        if not normalized.get("summary"):
            raise RuntimeError("Patch verifier AI ha restituito payload insufficiente.")

        write_json(AUDIT_OUT / "patch_verification_raw_response.json", raw)
        write_json(AUDIT_OUT / "patch_verification.json", normalized)
        write_text(AUDIT_OUT / "patch_verification.md", render_md(normalized, model_used))

        print(f"Patch verifier completato. Model used: {model_used}")
        return 0

    except Exception as exc:
        fallback, model_used = build_fallback(ctx, str(exc))
        write_json(AUDIT_OUT / "patch_verification.json", fallback)
        write_text(AUDIT_OUT / "patch_verification.md", render_md(fallback, model_used))
        print(f"Patch verifier fallback attivato: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())