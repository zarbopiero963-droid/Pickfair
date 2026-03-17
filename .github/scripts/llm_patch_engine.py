#!/usr/bin/env python3

import json
import re
from pathlib import Path

import requests

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def normalize_path(path_str: str) -> str:
    raw = str(path_str or "").strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    return raw


def extract_code_block(text: str) -> str:
    text = text.strip()

    m = re.search(r"```(?:python)?\n(.*?)```", text, flags=re.S)
    if m:
        return m.group(1).strip() + "\n"

    return text + ("\n" if not text.endswith("\n") else "")


def build_prompt(
    *,
    target_file: str,
    issue_type: str,
    notes: list[str],
    required_symbols: list[str],
    source_code: str,
) -> str:
    notes_text = "\n".join(f"- {n}" for n in notes[:12]) if notes else "- none"
    required_text = "\n".join(f"- {s}" for s in required_symbols[:8]) if required_symbols else "- none"

    return f"""You are repairing a Python file in a CI self-healing pipeline.

Return ONLY the full corrected file content.
Do not explain.
Do not wrap in markdown unless unavoidable.
Preserve behavior as much as possible.
Make the smallest real fix that addresses the issue.

Target file: {target_file}
Issue type: {issue_type}

Required symbols:
{required_text}

Notes:
{notes_text}

Rules:
- Keep the file valid Python.
- Prefer minimal edits.
- Do not add placeholders like TODO.
- Do not remove working logic unless clearly broken.
- If issue_type is lint_failure, prefer mechanical safe fixes.
- If issue_type is runtime_failure, prefer defensive or import/symbol fixes.
- If issue_type is missing_public_contract, restore missing public symbol compatibly.

Current file content:
{source_code}
"""


def call_openrouter(
    *,
    api_key: str,
    model: str,
    prompt: str,
    timeout_seconds: int = 90,
) -> tuple[bool, str]:
    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You output only corrected source code.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0,
        "max_tokens": 6000,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout_seconds)
        if resp.status_code != 200:
            return False, f"OpenRouter HTTP {resp.status_code}: {resp.text[:1000]}"

        data = resp.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        if not content.strip():
            return False, "OpenRouter returned empty content."

        return True, content
    except Exception as e:
        return False, str(e)


def generate_ai_patch(
    *,
    target_file: str,
    issue_type: str,
    notes: list[str],
    required_symbols: list[str],
    model: str,
    api_key: str,
) -> dict:
    rel = normalize_path(target_file)
    abs_path = ROOT / rel

    if not abs_path.exists():
        return {
            "ok": False,
            "reason": "target_missing",
            "patched_content": "",
            "details": [f"missing target file: {rel}"],
        }

    source_code = read_text(abs_path)
    if not source_code.strip():
        return {
            "ok": False,
            "reason": "empty_source",
            "patched_content": "",
            "details": [f"empty source file: {rel}"],
        }

    prompt = build_prompt(
        target_file=rel,
        issue_type=issue_type,
        notes=notes,
        required_symbols=required_symbols,
        source_code=source_code,
    )

    ok, response = call_openrouter(
        api_key=api_key,
        model=model,
        prompt=prompt,
    )
    if not ok:
        return {
            "ok": False,
            "reason": "llm_request_failed",
            "patched_content": "",
            "details": [response],
        }

    patched = extract_code_block(response)

    if patched.strip() == source_code.strip():
        return {
            "ok": False,
            "reason": "llm_returned_same_content",
            "patched_content": "",
            "details": ["LLM returned unchanged file content."],
        }

    return {
        "ok": True,
        "reason": "llm_patch_generated",
        "patched_content": patched,
        "details": [f"model={model}", "LLM generated candidate patch."],
    }


if __name__ == "__main__":
    # standalone debug mode
    sample = generate_ai_patch(
        target_file="example.py",
        issue_type="runtime_failure",
        notes=[],
        required_symbols=[],
        model="openai/gpt-4.1-mini",
        api_key="",
    )
    write_text(AUDIT_OUT / "llm_patch_debug.json", json.dumps(sample, indent=2, ensure_ascii=False))