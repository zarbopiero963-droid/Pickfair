#!/usr/bin/env python3

import json
from pathlib import Path
from openrouter_model_router import call_openrouter

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"


def read_json(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def write_md(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def load_context():

    patch_candidate = read_json(AUDIT_OUT / "patch_candidate.json")
    patch_verification = read_json(AUDIT_OUT / "patch_verification.json")
    fix_context = read_json(AUDIT_OUT / "fix_context.json")

    return {
        "patch_candidate": patch_candidate,
        "patch_verification": patch_verification,
        "fix_context": fix_context
    }


def build_messages(ctx):

    system = """
You are a senior Python code reviewer.

You must verify if the patch actually solved the intended issue.

Answer these questions strictly:

1) Did the patch restore the required contract or symbol?
2) Did the patch modify only the minimal required code?
3) Did it preserve the existing logic and avoid side effects?
4) Is the patch safe considering the verifier verdict?

Return STRICT JSON:

{
 "contract_restored": true|false,
 "minimal_change": true|false,
 "logic_preserved": true|false,
 "verifier_consistent": true|false,
 "final_verdict": "approve|review|reject",
 "confidence": "low|medium|high",
 "notes": ["string"]
}
"""

    user = json.dumps(ctx, ensure_ascii=False)

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user}
    ]


def main():

    ctx = load_context()

    messages = build_messages(ctx)

    resp = call_openrouter(
        task_type="review",
        messages=messages
    )

    content = resp["content"]
    model = resp["model_used"]

    try:
        parsed = json.loads(content)
    except Exception:
        parsed = {
            "final_verdict": "review",
            "confidence": "low",
            "notes": ["Model output was not valid JSON"]
        }

    write_json(AUDIT_OUT / "post_patch_review.json", parsed)

    md = f"""
Post Patch Review

Model: {model}

Final verdict: {parsed.get("final_verdict")}

Confidence: {parsed.get("confidence")}

Contract restored: {parsed.get("contract_restored")}
Minimal change: {parsed.get("minimal_change")}
Logic preserved: {parsed.get("logic_preserved")}
Verifier consistent: {parsed.get("verifier_consistent")}

Notes
"""

    for n in parsed.get("notes", []):
        md += f"- {n}\n"

    write_md(AUDIT_OUT / "post_patch_review.md", md)

    print("Post patch AI review completed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())