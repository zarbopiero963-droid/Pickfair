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
    patch_verification = read_json(AUDIT_OUT / "patch_verification.json")
    fix_context = read_json(AUDIT_OUT / "fix_context.json")
    global_context = read_json(AUDIT_OUT / "global_workflow_context.json")
    patch_apply_report = read_json(AUDIT_OUT / "patch_apply_report.json")

    target_files = patch_candidate.get("target_files", []) or []

    related_fix_contexts = []
    for item in fix_context.get("fix_contexts", []):
        target_file = str(item.get("target_file", "")).strip()
        if target_file in target_files:
            related_fix_contexts.append(item)

    target_file_texts_after_apply = {}
    for target_file in target_files:
        target_path = ROOT / target_file
        if target_path.exists():
            target_file_texts_after_apply[target_file] = read_text(target_path)[:30000]
        else:
            target_file_texts_after_apply[target_file] = ""

    return {
        "patch_candidate": patch_candidate,
        "patch_verification": patch_verification,
        "patch_apply_report": patch_apply_report,
        "related_fix_contexts": related_fix_contexts,
        "global_context": {
            "pytest_signals": global_context.get("pytest_signals", [])[:20],
            "ai_root_causes": global_context.get("ai_root_causes", [])[:10],
            "contracts": global_context.get("contracts", [])[:20],
        },
        "target_file_texts_after_apply": target_file_texts_after_apply,
    }


def build_messages(ctx: dict) -> list[dict]:
    system_prompt = """
You are a senior Python post-patch reviewer working on the Pickfair repository.

Your task is to decide whether the already-applied multi-file patch is strong enough to justify creating a PR.

Be conservative.
Prefer "review" over "approve" whenever evidence is incomplete.
Use "approve" ONLY if all of the following appear true from the provided evidence:
1. The required contracts or symbols appear restored across the patch set.
2. The changes are minimal and localized.
3. The existing logic appears preserved.
4. The patch verifier was positive and consistent.
5. The applied file contents reflect the intended fixes.

If any of those are uncertain, use "review".
If the patch appears wrong, incomplete, unrelated, or risky, use "reject".

Return STRICT JSON with this schema:
{
  "contract_restored": true|false,
  "minimal_change": true|false,
  "logic_preserved": true|false,
  "verifier_consistent": true|false,
  "final_verdict": "approve|review|reject",
  "confidence": "low|medium|high",
  "notes": ["string"]
}
""".strip()

    user_payload = {
        "task": "Review the applied coordinated multi-file patch result and determine whether it is strong enough to open a PR.",
        "patch_candidate": ctx["patch_candidate"],
        "patch_verification": ctx["patch_verification"],
        "patch_apply_report": ctx["patch_apply_report"],
        "related_fix_contexts": ctx["related_fix_contexts"],
        "global_context": ctx["global_context"],
        "target_file_texts_after_apply": ctx["target_file_texts_after_apply"],
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
        "contract_restored": False,
        "minimal_change": False,
        "logic_preserved": False,
        "verifier_consistent": False,
        "final_verdict": "review",
        "confidence": "low",
        "notes": ["Model output was not valid JSON."],
        "raw_content": content,
    }


def normalize_review(data: dict, ctx: dict) -> dict:
    contract_restored = bool(data.get("contract_restored", False))
    minimal_change = bool(data.get("minimal_change", False))
    logic_preserved = bool(data.get("logic_preserved", False))
    verifier_consistent = bool(data.get("verifier_consistent", False))
    final_verdict = str(data.get("final_verdict", "review")).strip().lower()
    confidence = str(data.get("confidence", "low")).strip().lower()
    notes = data.get("notes", [])

    if not isinstance(notes, list):
        notes = [str(notes)]

    if final_verdict not in {"approve", "review", "reject"}:
        final_verdict = "review"

    if confidence not in {"low", "medium", "high"}:
        confidence = "low"

    apply_report = ctx.get("patch_apply_report", {})
    applied = bool(apply_report.get("applied", False))

    if not applied:
        final_verdict = "reject"
        if "The coordinated patch was not fully applied." not in notes:
            notes.append("The coordinated patch was not fully applied.")

    if final_verdict == "approve":
        if not (contract_restored and minimal_change and logic_preserved and verifier_consistent and applied):
            final_verdict = "review"
            notes.append(
                "Approve downgraded to review because the evidence was not strong enough on all required dimensions."
            )

    if not contract_restored:
        final_verdict = "reject"
        if "Required contracts or symbols do not appear restored." not in notes:
            notes.append("Required contracts or symbols do not appear restored.")

    return {
        "contract_restored": contract_restored,
        "minimal_change": minimal_change,
        "logic_preserved": logic_preserved,
        "verifier_consistent": verifier_consistent,
        "final_verdict": final_verdict,
        "confidence": confidence,
        "notes": notes,
    }


def render_md(data: dict, model_used: str) -> str:
    lines = []
    lines.append("Post Patch Review")
    lines.append("")
    lines.append(f"Model: {model_used}")
    lines.append("")
    lines.append(f"Final verdict: {data.get('final_verdict', 'unknown')}")
    lines.append(f"Confidence: {data.get('confidence', 'unknown')}")
    lines.append("")
    lines.append(f"Contract restored: {data.get('contract_restored')}")
    lines.append(f"Minimal change: {data.get('minimal_change')}")
    lines.append(f"Logic preserved: {data.get('logic_preserved')}")
    lines.append(f"Verifier consistent: {data.get('verifier_consistent')}")
    lines.append("")
    lines.append("Notes")

    notes = data.get("notes", [])
    if notes:
        for note in notes:
            lines.append(f"- {note}")
    else:
        lines.append("- Nessuna nota disponibile.")

    lines.append("")
    return "\n".join(lines)


def fallback_review(ctx: dict) -> dict:
    patch_candidate = ctx.get("patch_candidate", {})
    patch_verification = ctx.get("patch_verification", {})
    patch_apply_report = ctx.get("patch_apply_report", {})

    verifier_verdict = str(patch_verification.get("verdict", "")).strip().lower()
    applied = bool(patch_apply_report.get("applied", False))
    target_files = patch_candidate.get("target_files", []) or []

    if verifier_verdict == "reject" or not applied:
        final_verdict = "reject"
    else:
        final_verdict = "review"

    return {
        "contract_restored": False,
        "minimal_change": True if applied else False,
        "logic_preserved": True if applied else False,
        "verifier_consistent": verifier_verdict in {"approve", "weak-approve", "reject"},
        "final_verdict": final_verdict,
        "confidence": "low",
        "notes": [
            "Fallback locale usato perché il post patch review AI non era disponibile.",
            f"Patch targets: {target_files}",
            f"Verifier precedente: {verifier_verdict or 'unknown'}",
            f"Patch applied: {applied}",
            "Fallback non concede mai approve automatico; al massimo review.",
        ],
    }


def main() -> int:
    ctx = load_context()

    patch_candidate = ctx.get("patch_candidate", {})
    if not patch_candidate:
        data = {
            "contract_restored": False,
            "minimal_change": False,
            "logic_preserved": False,
            "verifier_consistent": False,
            "final_verdict": "reject",
            "confidence": "low",
            "notes": ["Manca audit_out/patch_candidate.json"],
        }
        write_json(AUDIT_OUT / "post_patch_review.json", data)
        write_text(AUDIT_OUT / "post_patch_review.md", render_md(data, "no-patch-candidate"))
        print("Post patch review: nessuna patch candidate disponibile.")
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
        normalized = normalize_review(parsed, ctx)

        write_json(AUDIT_OUT / "post_patch_review_raw_response.json", raw)
        write_json(AUDIT_OUT / "post_patch_review.json", normalized)
        write_text(AUDIT_OUT / "post_patch_review.md", render_md(normalized, model_used))

        print(f"Post patch AI review completed. Model used: {model_used}")
        return 0

    except Exception as exc:
        data = fallback_review(ctx)
        model_used = f"fallback-local-error-{type(exc).__name__}"
        write_json(AUDIT_OUT / "post_patch_review.json", data)
        write_text(AUDIT_OUT / "post_patch_review.md", render_md(data, model_used))
        print(f"Post patch AI review failed: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())