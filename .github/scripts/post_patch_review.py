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


def normalize_review(data: dict) -> dict:
    verdict = str(data.get("final_verdict", "")).strip().lower()
    if verdict not in {"approve", "review", "reject"}:
        verdict = "review"

    confidence = str(data.get("confidence", "")).strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "medium"

    notes = data.get("notes", [])
    if not isinstance(notes, list):
        notes = []

    return {
        "final_verdict": verdict,
        "confidence": confidence,
        "contract_restored": bool(data.get("contract_restored", False)),
        "minimal_change": bool(data.get("minimal_change", False)),
        "logic_preserved": bool(data.get("logic_preserved", False)),
        "verifier_consistent": bool(data.get("verifier_consistent", False)),
        "notes": [str(x).strip() for x in notes if str(x).strip()],
    }


def load_context() -> dict:
    patch_candidate = read_json(AUDIT_OUT / "patch_candidate.json")
    patch_verification = read_json(AUDIT_OUT / "patch_verification.json")
    patch_apply_report = read_json(AUDIT_OUT / "patch_apply_report.json")
    targeted_test_results = read_json(AUDIT_OUT / "targeted_test_results.json")

    return {
        "patch_candidate": patch_candidate,
        "patch_verification": patch_verification,
        "patch_apply_report": patch_apply_report,
        "targeted_test_results": targeted_test_results,
    }


def build_messages(ctx: dict) -> list[dict]:
    system_prompt = """
You are a conservative post-patch reviewer for the Pickfair repository.

Rules:
- assess the applied patch set as a whole
- prefer minimal backward-compatible fixes
- return reject only for clearly unsafe, broken, or unapplied patch sets
- use review when evidence is incomplete but the patch remains reviewable
- use approve only when the patch looks safe and coherent

Return STRICT JSON:
{
  "final_verdict": "approve|review|reject",
  "confidence": "low|medium|high",
  "contract_restored": true,
  "minimal_change": true,
  "logic_preserved": true,
  "verifier_consistent": true,
  "notes": ["..."]
}
""".strip()

    payload = {
        "patch_candidate": ctx["patch_candidate"],
        "patch_verification": ctx["patch_verification"],
        "patch_apply_report": ctx["patch_apply_report"],
        "targeted_test_results": ctx["targeted_test_results"],
    }

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def render_md(data: dict, model_used: str) -> str:
    lines = []
    lines.append("Post Patch Review")
    lines.append("")
    lines.append(f"Model: {model_used}")
    lines.append("")
    lines.append(f"Final verdict: {data.get('final_verdict', '')}")
    lines.append(f"Confidence: {data.get('confidence', '')}")
    lines.append("")
    lines.append(f"Contract restored: {data.get('contract_restored')}")
    lines.append(f"Minimal change: {data.get('minimal_change')}")
    lines.append(f"Logic preserved: {data.get('logic_preserved')}")
    lines.append(f"Verifier consistent: {data.get('verifier_consistent')}")
    lines.append("")
    lines.append("Notes")

    notes = data.get("notes", []) or []
    if notes:
        for note in notes:
            lines.append(f"- {note}")
    else:
        lines.append("- None")

    lines.append("")
    return "\n".join(lines)


def build_fallback(ctx: dict, error_message: str) -> tuple[dict, str]:
    candidate = ctx.get("patch_candidate", {}) or {}
    verification = ctx.get("patch_verification", {}) or {}
    apply_report = ctx.get("patch_apply_report", {}) or {}

    target_files = candidate.get("target_files", []) or []
    proposed_patches = candidate.get("proposed_patches", []) or []
    verifier_verdict = str(verification.get("verdict", "")).strip().lower()
    applied = bool(apply_report.get("applied", False))

    has_targets = isinstance(target_files, list) and len(target_files) > 0
    has_patches = isinstance(proposed_patches, list) and len(proposed_patches) > 0

    contract_like_files = {
        "auto_updater.py",
        "executor_manager.py",
        "tests/fixtures/system_payloads.py",
    }
    touched_contract_files = any(f in contract_like_files for f in target_files)

    if not has_targets or not has_patches:
        verdict = "reject"
        contract_restored = False
        minimal_change = False
        logic_preserved = False
        verifier_consistent = verifier_verdict == "reject"
        notes = [
            "Fallback locale usato perché il post patch review AI non era disponibile.",
            "Patch targets assenti o patch candidate non valida.",
            f"Verifier precedente: {verifier_verdict or 'unknown'}",
            f"Patch applied: {applied}",
            "Fallback locale rifiuta patch assenti o inutilizzabili.",
        ]
    else:
        # Fallback tecnico prudente:
        # - review se la patch è applicata o comunque reviewable
        # - reject solo se verifier già reject forte e patch non applicata
        if applied and verifier_verdict in {"approve", "weak-approve", "review"}:
            verdict = "review"
        elif verifier_verdict in {"approve", "weak-approve"}:
            verdict = "review"
        elif verifier_verdict == "reject" and not applied:
            verdict = "reject"
        else:
            verdict = "review"

        contract_restored = touched_contract_files
        minimal_change = True
        logic_preserved = verifier_verdict != "reject"
        verifier_consistent = True

        notes = [
            "Fallback locale usato perché il post patch review AI non era disponibile.",
            f"Patch targets: {target_files}",
            f"Verifier precedente: {verifier_verdict or 'unknown'}",
            f"Patch applied: {applied}",
            "Fallback tecnico non concede approve automatico, ma evita reject automatico quando il problema è di disponibilità AI.",
        ]

        if touched_contract_files:
            notes.append("Sono presenti target coerenti con il ripristino di contratti pubblici chiave.")

    data = {
        "final_verdict": verdict,
        "confidence": "low",
        "contract_restored": contract_restored,
        "minimal_change": minimal_change,
        "logic_preserved": logic_preserved,
        "verifier_consistent": verifier_consistent,
        "notes": notes,
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
        normalized = normalize_review(parsed)

        write_json(AUDIT_OUT / "post_patch_review_raw_response.json", raw)
        write_json(AUDIT_OUT / "post_patch_review.json", normalized)
        write_text(AUDIT_OUT / "post_patch_review.md", render_md(normalized, model_used))

        print(f"Post patch review completato. Model used: {model_used}")
        return 0

    except Exception as exc:
        fallback, model_used = build_fallback(ctx, str(exc))
        write_json(AUDIT_OUT / "post_patch_review.json", fallback)
        write_text(AUDIT_OUT / "post_patch_review.md", render_md(fallback, model_used))
        print(f"Post patch review fallback attivato: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())