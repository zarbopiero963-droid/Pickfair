#!/usr/bin/env python3

import json
import subprocess
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


def unique_keep_order(items: list[str]) -> list[str]:
    out = []
    seen = set()
    for item in items:
        item = str(item).strip()
        if not item or item in seen:
            continue
        out.append(item)
        seen.add(item)
    return out


def collect_targets() -> list[str]:
    failing_tests_data = read_json(AUDIT_OUT / "failing_tests.json")
    fix_context_data = read_json(AUDIT_OUT / "fix_context.json")
    test_failure_context_data = read_json(AUDIT_OUT / "test_failure_context.json")

    targets: list[str] = []

    for item in failing_tests_data.get("targets", []) or []:
        test_file = str(item.get("test_file", "")).strip()
        if test_file.startswith("tests/"):
            targets.append(test_file)

    for item in test_failure_context_data.get("test_failure_contexts", []) or []:
        test_file = str(item.get("target_file", "")).strip()
        if test_file.startswith("tests/"):
            targets.append(test_file)

    for item in fix_context_data.get("fix_contexts", []) or []:
        for test_file in item.get("related_tests", []) or []:
            test_file = str(test_file).strip()
            if test_file.startswith("tests/"):
                targets.append(test_file)

    targets = unique_keep_order(targets)

    # Manteniamo il set piccolo e mirato
    return targets[:10]


def extract_failure_lines(output: str) -> list[str]:
    patterns = (
        "FAILED ",
        "ERROR ",
        "ImportError",
        "ModuleNotFoundError",
        "AttributeError",
        "TypeError",
        "RuntimeError",
        "AssertionError",
        "KeyError",
        "NameError",
        "cannot import name",
    )

    lines = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        if any(p in line for p in patterns):
            lines.append(line)

    return lines[:200]


def main() -> int:
    targets = collect_targets()

    if not targets:
        result = {
            "status": "no-targets",
            "targets": [],
            "pytest_exit_code": None,
            "failure_count": 0,
            "failure_lines": [],
        }
        write_json(AUDIT_OUT / "targeted_test_results.json", result)
        write_text(AUDIT_OUT / "targeted_test_results.md", "No targeted tests available.\n")
        print("No targeted tests available.")
        return 0

    cmd = ["pytest", "-q", *targets]

    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    output = (proc.stdout or "") + ("\n" if proc.stdout and proc.stderr else "") + (proc.stderr or "")
    write_text(AUDIT_RAW / "targeted_pytest.log", output)

    failure_lines = extract_failure_lines(output)

    result = {
        "status": "completed",
        "targets": targets,
        "pytest_exit_code": proc.returncode,
        "failure_count": len(failure_lines),
        "failure_lines": failure_lines,
    }

    md_lines = [
        "Targeted Test Results",
        "",
        f"Pytest exit code: {proc.returncode}",
        f"Failure count: {len(failure_lines)}",
        "",
        "Targets:",
    ]

    for item in targets:
        md_lines.append(f"- {item}")

    md_lines.append("")
    md_lines.append("Failure lines:")
    if failure_lines:
        for line in failure_lines:
            md_lines.append(f"- {line}")
    else:
        md_lines.append("- None")

    md_lines.append("")

    write_json(AUDIT_OUT / "targeted_test_results.json", result)
    write_text(AUDIT_OUT / "targeted_test_results.md", "\n".join(md_lines))

    print("\n".join(md_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())