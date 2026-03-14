#!/usr/bin/env python3

import json
import os
import re
import sys
from pathlib import Path

import requests

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"
AUDIT_RAW = ROOT / "audit_raw"

AUDIT_OUT.mkdir(exist_ok=True)
AUDIT_RAW.mkdir(exist_ok=True)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


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

    reduced = {
        "compile_ok": audit_machine.get("compile_ok"),
        "pytest_code": audit_machine.get("pytest_code"),
        "contracts": contracts,
        "smells": smells,
        "ranking_top10": ranking,
        "pytest_signals": extract_top_pytest_lines(pytest_log, max_lines=40),
    }
    return reduced


def build_messages(reduced: dict) -> list[dict]:
    system_prompt = """You are a senior Python repository auditor working on a GitHub Actions CI pipeline.

Goals:
1. Be precise and conservative.
2. Do not invent files, symbols, or fixes.
3. Use ONLY the provided reduced audit context.
4. Focus on the highest-value root cause(s), not everything.
5. Keep output concise but actionable.
6. Prefer backward-compatible fixes where tests expect old public symbols.
7. Assume the team wants minimal-risk fixes on a separate PR, never direct changes to main.

Return STRICT JSON with this schema:
{
  "summary": "short paragraph",
  "root_causes": [
    {
      "title": "string",
      "why_it_happens": "string",
      "evidence": ["string", "..."],
      "severity": "P0|P1|P2"
    }
  ],
  "fix_suggestions": [
    {
      "title": "string",
      "files": ["file1.py", "file2.py"],
      "change": "string",
      "risk": "low|medium|high"
    }
  ],
  "targeted_tests": [
    {
      "reason": "string",
      "tests": ["tests/...", "..."]
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


def call_openrouter(model: str, messages: list[dict], api_key: str) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
    }

    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def extract_content(resp_json: dict) -> str:
    try:
        return resp_json["choices"][0]["message"]["content"]
    except Exception:
        return ""


def parse_json_content(content: str) -> dict:
    content = content.strip()

    # raw JSON
    try:
        return json.loads(content)
    except Exception:
        pass

    # fenced JSON
    fence_match = re.search(r"```json\s*(.*?)\s*```", content, re.S)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except Exception:
            pass

    # generic fenced block
    fence_match = re.search(r"```\s*(.*?)\s*```", content, re.S)
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
    ranking = reduced.get("ranking_top10", [])

    summary = (
        "Il layer AI non è disponibile oppure non ha restituito un JSON valido. "
        "Il verdetto resta basato sull’audit deterministico."
    )

    root_causes = []
    if contracts:
        root_causes.append({
            "title": "Rottura dei contratti pubblici",
            "why_it_happens": "I test si aspettano simboli pubblici che i moduli non esportano più.",
            "evidence": [f"{file} -> {symbol}" for file, symbol in contracts[:5]],
            "severity": "P0",
        })

    fix_suggestions = []
    for file, symbol in contracts[:5]:
        fix_suggestions.append({
            "title": f"Ripristinare {symbol}",
            "files": [file],
            "change": f"Aggiungere o ripristinare il simbolo pubblico {symbol} con compatibilità retroattiva minima.",
            "risk": "low",
        })

    targeted_tests = [{
        "reason": "Rilanciare prima i test direttamente collegati ai contract mismatch.",
        "tests": [
            "tests/test_auto_updater.py",
            "tests/test_executor_manager_shutdown.py",
            "tests/test_new_components.py",
            "tests/test_toolbar_live.py",
            "tests/contracts/test_payload_snapshots.py",
        ],
    }]

    return {
        "summary": summary,
        "root_causes": root_causes,
        "fix_suggestions": fix_suggestions,
        "targeted_tests": targeted_tests,
        "ranking_top10": ranking,
    }


def render_root_cause_md(data: dict) -> str:
    lines = []
    lines.append("AI Root Cause Analysis")
    lines.append("")
    lines.append(data.get("summary", "Nessun sommario disponibile."))
    lines.append("")

    lines.append("Root causes")
    for item in data.get("root_causes", []):
        lines.append(f"- {item.get('title', 'Sconosciuto')} [{item.get('severity', 'P?')}]")
        lines.append(f"  - perché: {item.get('why_it_happens', '')}")
        for ev in item.get("evidence", []):
            lines.append(f"  - evidenza: {ev}")
    if not data.get("root_causes"):
        lines.append("- Nessuna root cause disponibile.")
    lines.append("")

    return "\n".join(lines) + "\n"


def render_fix_suggestions_md(data: dict) -> str:
    lines = []
    lines.append("AI Fix Suggestions")
    lines.append("")

    for item in data.get("fix_suggestions", []):
        lines.append(f"- {item.get('title', 'Fix suggestion')}")
        files = item.get("files", [])
        if files:
            lines.append(f"  - file: {', '.join(files)}")
        lines.append(f"  - modifica: {item.get('change', '')}")
        lines.append(f"  - rischio: {item.get('risk', 'unknown')}")
    if not data.get("fix_suggestions"):
        lines.append("- Nessun fix suggestion disponibile.")
    lines.append("")

    return "\n".join(lines) + "\n"


def render_targeted_tests_md(data: dict) -> str:
    lines = []
    lines.append("AI Targeted Tests")
    lines.append("")

    for item in data.get("targeted_tests", []):
        lines.append(f"- motivo: {item.get('reason', '')}")
        for test in item.get("tests", []):
            lines.append(f"  - {test}")
    if not data.get("targeted_tests"):
        lines.append("- Nessun targeted test disponibile.")
    lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    model_triage = os.getenv("OPENROUTER_MODEL_TRIAGE", "qwen/qwen3-coder-next").strip()

    audit_machine = load_audit_machine()
    pytest_log = load_pytest_log()

    reduced = reduce_context(audit_machine, pytest_log)
    write_json(AUDIT_OUT / "ai_reduced_context.json", reduced)

    if not api_key:
        fallback = fallback_outputs(reduced)
        write_json(AUDIT_OUT / "ai_reasoning.json", fallback)
        write_text(AUDIT_OUT / "root_cause.md", render_root_cause_md(fallback))
        write_text(AUDIT_OUT / "fix_suggestions.md", render_fix_suggestions_md(fallback))
        write_text(AUDIT_OUT / "targeted_tests.md", render_targeted_tests_md(fallback))
        print("OPENROUTER_API_KEY non trovato: scritto fallback locale.")
        return 0

    try:
        messages = build_messages(reduced)
        resp_json = call_openrouter(model_triage, messages, api_key)
        write_json(AUDIT_OUT / "openrouter_raw_response.json", resp_json)

        content = extract_content(resp_json)
        parsed = parse_json_content(content)

        write_json(AUDIT_OUT / "ai_reasoning.json", parsed)
        write_text(AUDIT_OUT / "root_cause.md", render_root_cause_md(parsed))
        write_text(AUDIT_OUT / "fix_suggestions.md", render_fix_suggestions_md(parsed))
        write_text(AUDIT_OUT / "targeted_tests.md", render_targeted_tests_md(parsed))

        print("AI reasoning layer completato.")
        return 0

    except Exception as exc:
        fallback = fallback_outputs(reduced)
        fallback["summary"] = (
            f"Il layer AI ha fallito ({type(exc).__name__}: {exc}). "
            "È stato scritto un fallback locale basato sull’audit deterministico."
        )
        write_json(AUDIT_OUT / "ai_reasoning.json", fallback)
        write_text(AUDIT_OUT / "root_cause.md", render_root_cause_md(fallback))
        write_text(AUDIT_OUT / "fix_suggestions.md", render_fix_suggestions_md(fallback))
        write_text(AUDIT_OUT / "targeted_tests.md", render_targeted_tests_md(fallback))
        print(f"AI reasoning layer fallito: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())