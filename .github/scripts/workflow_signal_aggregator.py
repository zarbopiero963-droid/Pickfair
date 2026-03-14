#!/usr/bin/env python3

import json
import re
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"
AUDIT_RAW = ROOT / "audit_raw"


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


def extract_error_signals(pytest_log: str, limit: int = 50) -> list[str]:
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

    found: list[str] = []

    for raw in pytest_log.splitlines():
        line = raw.strip()
        if not line:
            continue

        for pattern in patterns:
            if re.match(pattern, line):
                found.append(line)
                break

        if len(found) >= limit:
            break

    return found


def build_context() -> dict:
    audit_machine = read_json(AUDIT_OUT / "audit_machine.json")
    ai_reasoning = read_json(AUDIT_OUT / "ai_reasoning.json")
    fix_context = read_json(AUDIT_OUT / "fix_context.json")

    pytest_log = read_text(AUDIT_RAW / "pytest.log")
    priority_fix_order = read_text(AUDIT_OUT / "priority_fix_order.md")
    root_cause = read_text(AUDIT_OUT / "root_cause.md")
    fix_suggestions = read_text(AUDIT_OUT / "fix_suggestions.md")
    targeted_tests = read_text(AUDIT_OUT / "targeted_tests.md")

    return {
        "compile_ok": audit_machine.get("compile_ok"),
        "pytest_code": audit_machine.get("pytest_code"),
        "contracts": audit_machine.get("contracts", []),
        "smells": audit_machine.get("smells", {}),
        "ranking": audit_machine.get("ranking", []),
        "unused_classes": audit_machine.get("unused_classes", []),
        "unused_functions": audit_machine.get("unused_functions", []),
        "ai_summary": ai_reasoning.get("summary", ""),
        "ai_root_causes": ai_reasoning.get("root_causes", []),
        "ai_fix_suggestions": ai_reasoning.get("fix_suggestions", []),
        "ai_targeted_tests": ai_reasoning.get("targeted_tests", []),
        "fix_contexts": fix_context.get("fix_contexts", []),
        "pytest_signals": extract_error_signals(pytest_log),
        "rendered_priority_fix_order": priority_fix_order[:12000],
        "rendered_root_cause": root_cause[:12000],
        "rendered_fix_suggestions": fix_suggestions[:12000],
        "rendered_targeted_tests": targeted_tests[:12000],
    }


def render_markdown(context: dict) -> str:
    lines: list[str] = []
    lines.append("Global Workflow Context")
    lines.append("")
    lines.append("Questo file aggrega i segnali principali prodotti dalla pipeline di audit.")
    lines.append("")

    lines.append("Stato base")
    lines.append(f"- compile_ok: {context.get('compile_ok')}")
    lines.append(f"- pytest_code: {context.get('pytest_code')}")
    lines.append(f"- contract_count: {len(context.get('contracts', []))}")
    lines.append(f"- fix_context_count: {len(context.get('fix_contexts', []))}")
    lines.append("")

    lines.append("Top pytest signals")
    signals = context.get("pytest_signals", [])
    if signals:
        for item in signals[:20]:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessun segnale estratto.")
    lines.append("")

    lines.append("AI root causes")
    root_causes = context.get("ai_root_causes", [])
    if root_causes:
        for item in root_causes[:10]:
            title = item.get("title", "Root cause")
            why = item.get("why_it_happens", "")
            lines.append(f"- {title}: {why}")
    else:
        lines.append("- Nessuna root cause disponibile.")
    lines.append("")

    lines.append("Fix contexts")
    fix_contexts = context.get("fix_contexts", [])
    if fix_contexts:
        for item in fix_contexts[:20]:
            lines.append(
                f"- {item.get('target_file', 'unknown')} | "
                f"priority={item.get('priority', 'P?')} | "
                f"symbols={item.get('required_symbols', [])}"
            )
    else:
        lines.append("- Nessun fix context disponibile.")
    lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    context = build_context()
    write_json(AUDIT_OUT / "global_workflow_context.json", context)
    write_text(AUDIT_OUT / "global_workflow_context.md", render_markdown(context))
    print(render_markdown(context))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())