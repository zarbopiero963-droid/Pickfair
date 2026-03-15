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


# ----------------------------
# JSON PARSER ULTRA ROBUSTO
# ----------------------------

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

    # direct json
    try:
        return json.loads(content)
    except Exception:
        pass

    # ```json block
    fence = re.search(r"```json\s*(.*?)\s*```", content, re.S | re.I)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:
            pass

    # ``` block
    fence = re.search(r"```\s*(.*?)\s*```", content, re.S)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:
            pass

    # extract first json object
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

                    candidate = content[start:i + 1]

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


# ----------------------------
# FIX CONTEXT
# ----------------------------

def load_target_context():

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

        files_payload.append(
            {
                "target": target,
                "target_file_text": read_text(target_file)[:25000],
            }
        )

    return {
        "targets": selected,
        "files_payload": files_payload,
        "global_context": global_context,
    }


# ----------------------------
# PROMPT
# ----------------------------

def build_messages(ctx):

    system_prompt = """
You are a conservative Python patch generator working on the Pickfair repository.

Rules:
- generate minimal safe patches
- preserve backward compatibility
- avoid redesign
- fix only provided files
- restore missing public contracts
- respect tests

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
        "global_context": ctx["global_context"],
    }

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload)},
    ]


# ----------------------------
# NORMALIZATION
# ----------------------------

def normalize_patch_candidate(data, ctx):

    allowed_files = {
        item["target_file"]
        for item in ctx.get("targets", [])
    }

    patches = data.get("proposed_patches", [])

    normalized = []

    for item in patches:

        if not isinstance(item, dict):
            continue

        target_file = item.get("target_file", "").strip()
        patch = item.get("patch", "").strip()

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
        "summary": data.get("summary", ""),
        "target_files": [p["target_file"] for p in normalized],
        "why_this_fix": data.get("why_this_fix", ""),
        "proposed_patches": normalized,
        "tests_to_run": data.get("tests_to_run", []),
        "risk": data.get("risk", "unknown"),
    }


# ----------------------------
# MAIN
# ----------------------------

def main():

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

        # protezione contro patch vuote
        if not normalized["proposed_patches"]:
            raise RuntimeError("AI non ha prodotto patch valide")

        write_json(
            AUDIT_OUT / "patch_candidate.json",
            normalized,
        )

        write_text(
            AUDIT_OUT / "patch_candidate.md",
            json.dumps(normalized, indent=2),
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

        write_json(
            AUDIT_OUT / "patch_candidate.json",
            fallback,
        )

        write_text(
            AUDIT_OUT / "patch_candidate.md",
            json.dumps(fallback, indent=2),
        )

        print("Patch candidate generator fallito:", exc)

        return 0


if __name__ == "__main__":
    raise SystemExit(main())