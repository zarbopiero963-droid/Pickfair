#!/usr/bin/env python3

import json
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


def load_ai_governance() -> str:
    """
    Load repository governance documents that guide the AI reasoning layer.
    These documents define architecture rules and fix protocols.
    """
    path = AUDIT_RAW / "ai_governance_context.md"
    if not path.exists():
        return ""
    try:
        return read_text(path)[:20000]
    except Exception:
        return ""


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
    governance = load_ai_governance()

    system_prompt = f"""
You are a senior Python repository auditor working inside a GitHub Actions CI pipeline.

Repository governance documents:
{governance}

Rules:
1. Be precise and conservative.
2. Do not invent files, symbols, or fixes.
3. Use only the provided reduced audit context.
4. Focus on the most important root causes first.
5. Prefer backward-compatible fixes when tests expect old public symbols.
6. Never suggest direct changes to main; assume changes go through a PR.
7. Prefer the minimum viable fix that restores the public contract.

Return STRICT JSON with this schema:
{{
  "summary": "short paragraph",
  "root_causes": [
    {{
      "title": "string",
      "why_it_happens": "string",
      "evidence": ["string"],
      "severity": "P0|P1|P2"
    }}
  ],
  "fix_suggestions": [
    {{
      "title": "string",
      "files": ["file.py"],
      "change": "string",
      "risk": "low|medium|high"
    }}
  ],
  "targeted_tests": [
    {{
      "reason": "string",
      "tests": ["tests/file.py"]
    }}
  ]
}}
""".strip()

    user_payload = {
        "task": "Analyze the reduced repository audit context and identify the most important root causes and lowest-risk fixes.",
        "context": reduced,
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
        "summary": "AI response was not valid JSON.",
        "root_causes": [],
        "fix_suggestions": [],
        "targeted_tests": [],
        "raw_content": content,
    }


def fallback_outputs(reduced: dict) -> dict:
    contracts = reduced.get("contracts", [])

    summary = (
        "Il layer AI non è disponibile oppure non ha restituito un JSON valido. "
        "Il verdetto resta basato sull’audit deterministico."
    )

    root_causes = []
    if contracts:
        root_causes.append(
            {
                "title": "Rottura dei contratti pubblici",
                "why_it_happens": "I test si aspettano simboli pubblici che i moduli non esportano più.",
                "evidence": [f"{file} -> {symbol}" for file, symbol in contracts[:5]],
                "severity": "P0",
            }
        )

    fix_suggestions = []
    for file, symbol in contracts[:5]:
        fix_suggestions.append(
            {
                "title": f"Ripristinare {symbol}",
                "files": [file],
                "change": f"Aggiungere o ripristinare il simbolo pubblico {symbol} con compatibilità retroattiva minima.",
                "risk": "low",
            }
        )

    targeted_tests = [
        {
            "reason": "Rilanciare prima i test direttamente collegati ai contract mismatch.",
            "tests": [
                "tests/test_auto_updater.py",
                "tests/test_executor_manager_shutdown.py",
                "tests/test_executor_manager_parallel.py",
                "tests/test_new_components.py",
                "tests/test_toolbar_live.py",
                "tests/contracts/test_payload_snapshots.py",
            ],
        }
    ]

    return {
        "summary": summary,
        "root_causes": root_causes,
        "fix_suggestions": fix_suggestions,
        "targeted_tests": targeted_tests,
    }


def render_root_cause_md(data: dict, model_used: str) -> str:
    lines = []
    lines.append("AI Root Cause Analysis")
    lines.append("")
    lines.append(f"Model used: {model_used}")
    lines.append("")
    lines.append(data.get("summary", "Nessun sommario disponibile."))
    lines.append("")

    lines.append("Root causes")
    if data.get("root_causes"):
        for item in data["root_causes"]:
            lines.append(f"- {item.get('title', 'Sconosciuto')} [{item.get('severity', 'P?')}]")
            lines.append(f"  - perché: {item.get('why_it_happens', '')}")
            for ev in item.get("evidence", []):
                lines.append(f"  - evidenza: {ev}")
    else:
        lines.append("- Nessuna root cause disponibile.")
    lines.append("")

    return "\n".join(lines) + "\n"


def render_fix_suggestions_md(data: dict, model_used: str) -> str:
    lines = []
    lines.append("AI Fix Suggestions")
    lines.append("")
    lines.append(f"Model used: {model_used}")
    lines.append("")

    if data.get("fix_suggestions"):
        for item in data["fix_suggestions"]:
            lines.append(f"- {item.get('title', 'Fix suggestion')}")
            files = item.get("files", [])
            if files:
                lines.append(f"  - file: {', '.join(files)}")
            lines.append(f"  - modifica: {item.get('change', '')}")
            lines.append(f"  - rischio: {item.get('risk', 'unknown')}")
    else:
        lines.append("- Nessun fix suggestion disponibile.")
    lines.append("")

    return "\n".join(lines) + "\n"


def render_targeted_tests_md(data: dict, model_used: str) -> str:
    lines = []
    lines.append("AI Targeted Tests")
    lines.append("")
    lines.append(f"Model used: {model_used}")
    lines.append("")

    if data.get("targeted_tests"):
        for item in data["targeted_tests"]:
            lines.append(f"- motivo: {item.get('reason', '')}")
            for test in item.get("tests", []):
                lines.append(f"  - {test}")
    else:
        lines.append("- Nessun targeted test disponibile.")
    lines.append("")

    return "\n".join(lines) + "\n"


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
        raw = resp.get("raw", {})

        parsed = parse_json_content(content)

        write_json(AUDIT_OUT / "openrouter_raw_response.json", raw)
        write_json(AUDIT_OUT / "ai_reasoning.json", parsed)
        write_text(AUDIT_OUT / "root_cause.md", render_root_cause_md(parsed, model_used))
        write_text(AUDIT_OUT / "fix_suggestions.md", render_fix_suggestions_md(parsed, model_used))
        write_text(AUDIT_OUT / "targeted_tests.md", render_targeted_tests_md(parsed, model_used))

        print(f"AI reasoning layer completato. Model used: {model_used}")
        return 0

    except Exception as exc:
        fallback = fallback_outputs(reduced)
        model_used = f"fallback-local-error-{type(exc).__name__}"
        fallback["summary"] = (
            f"Il layer AI ha fallito ({type(exc).__name__}: {exc}). "
            "È stato scritto un fallback locale basato sull’audit deterministico."
        )

        write_json(AUDIT_OUT / "ai_reasoning.json", fallback)
        write_text(AUDIT_OUT / "root_cause.md", render_root_cause_md(fallback, model_used))
        write_text(AUDIT_OUT / "fix_suggestions.md", render_fix_suggestions_md(fallback, model_used))
        write_text(AUDIT_OUT / "targeted_tests.md", render_targeted_tests_md(fallback, model_used))

        print(f"AI reasoning layer fallito: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())