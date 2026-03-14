#!/usr/bin/env python3

import json
import os
import re
from pathlib import Path

from openrouter_model_router import call_openrouter

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"
AUDIT_RAW = ROOT / "audit_raw"

AUDIT_OUT.mkdir(exist_ok=True)
AUDIT_RAW.mkdir(exist_ok=True)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_audit_machine() -> dict:
    path = AUDIT_OUT / "audit_machine.json"
    if not path.exists():
        return {}
    try:
        return json.loads(read_text(path))
    except Exception:
        return {}


def load_pytest_log() -> str:
    return read_text(AUDIT_RAW / "pytest.log")


def extract_top_pytest_lines(pytest_log: str, max_lines: int = 40) -> list[str]:

    lines = []

    patterns = [
        r"^ERROR collecting .*$",
        r"^FAILED .*$",
        r".*ModuleNotFoundError.*",
        r".*ImportError.*",
        r".*AttributeError.*",
        r".*TypeError.*",
        r".*RuntimeError.*",
        r".*AssertionError.*",
        r".*KeyError.*",
        r".*NameError.*",
    ]

    for raw in pytest_log.splitlines():

        line = raw.strip()

        if not line:
            continue

        for pattern in patterns:

            if re.match(pattern, line):
                lines.append(line)
                break

        if len(lines) >= max_lines:
            break

    return lines


def reduce_context(audit_machine: dict, pytest_log: str) -> dict:

    contracts = audit_machine.get("contracts", [])[:10]
    smells = audit_machine.get("smells", {})
    ranking = audit_machine.get("ranking", [])[:10]
    unused_classes = audit_machine.get("unused_classes", [])[:10]
    unused_functions = audit_machine.get("unused_functions", [])[:10]

    return {
        "compile_ok": audit_machine.get("compile_ok"),
        "pytest_code": audit_machine.get("pytest_code"),
        "contracts": contracts,
        "smells": smells,
        "ranking_top10": ranking,
        "unused_classes_top10": unused_classes,
        "unused_functions_top10": unused_functions,
        "pytest_signals": extract_top_pytest_lines(pytest_log, max_lines=40),
    }


def build_messages(reduced: dict) -> list[dict]:

    system_prompt = """You are a senior Python repository auditor working inside a GitHub Actions CI pipeline.

Rules:
1. Be precise and conservative.
2. Do not invent files, symbols, or fixes.
3. Use only the provided reduced audit context.
4. Focus on the most important root causes first.
5. Prefer backward-compatible fixes when tests expect old public symbols.
6. Never suggest direct changes to main; assume changes go through a PR.
7. Prefer the minimum viable fix that restores the public contract.

Return STRICT JSON with this schema:
{
  "summary": "short paragraph",
  "root_causes": [
    {
      "title": "string",
      "why_it_happens": "string",
      "evidence": ["string"],
      "severity": "P0|P1|P2"
    }
  ],
  "fix_suggestions": [
    {
      "title": "string",
      "files": ["file.py"],
      "change": "string",
      "risk": "low|medium|high"
    }
  ],
  "targeted_tests": [
    {
      "reason": "string",
      "tests": ["tests/file.py"]
    }
  ]
}
""".strip()

    user_payload = {
        "task": "Analyze the reduced repository audit context and identify the most important root causes and lowest-risk fixes.",
        "context": reduced,
    }

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def extract_content(resp_json: dict) -> str:

    try:
        return resp_json["choices"][0]["message"]["content"]
    except Exception:
        return ""


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
        "summary": "AI response was not valid JSON.",
        "root_causes": [],
        "fix_suggestions": [],
        "targeted_tests": [],
        "raw_content": content,
    }


def fallback_outputs(reduced: dict) -> dict:

    contracts = reduced.get("contracts", [])

    summary = "AI layer non disponibile. Usato fallback deterministico."

    root_causes = []

    if contracts:

        root_causes.append(
            {
                "title": "Rottura contratti pubblici",
                "why_it_happens": "Test richiedono simboli pubblici mancanti.",
                "evidence": [f"{file} -> {symbol}" for file, symbol in contracts[:5]],
                "severity": "P0",
            }
        )

    return {
        "summary": summary,
        "root_causes": root_causes,
        "fix_suggestions": [],
        "targeted_tests": [],
    }


def render_root_cause_md(data: dict, model_used: str) -> str:

    lines = []
    lines.append("AI Root Cause Analysis")
    lines.append("")
    lines.append(f"Model used: {model_used}")
    lines.append("")
    lines.append(data.get("summary", ""))

    return "\n".join(lines)


def main() -> int:

    audit_machine = load_audit_machine()
    pytest_log = load_pytest_log()

    reduced = reduce_context(audit_machine, pytest_log)

    write_json(AUDIT_OUT / "ai_reduced_context.json", reduced)

    try:

        messages = build_messages(reduced)

        resp = call_openrouter(
            task_type="audit",
            messages=messages
        )

        content = resp["content"]
        model_used = resp["model_used"]

        parsed = parse_json_content(content)

        write_json(AUDIT_OUT / "ai_reasoning.json", parsed)

        write_text(
            AUDIT_OUT / "root_cause.md",
            render_root_cause_md(parsed, model_used)
        )

        print(f"AI reasoning layer completato. Model used: {model_used}")

        return 0

    except Exception as exc:

        fallback = fallback_outputs(reduced)

        write_json(AUDIT_OUT / "ai_reasoning.json", fallback)

        print(f"AI reasoning fallback: {exc}")

        return 0


if __name__ == "__main__":
    raise SystemExit(main())