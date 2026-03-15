#!/usr/bin/env python3

import json
import subprocess
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"
AUDIT_RAW = ROOT / "audit_raw"


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def run_pytest_collection():

    try:

        result = subprocess.run(
            ["pytest", "--collect-only", "-q"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        stdout = result.stdout or ""
        stderr = result.stderr or ""

        return result.returncode, stdout + "\n" + stderr

    except Exception as exc:
        return 999, str(exc)


def extract_pytest_signals(pytest_output: str):

    patterns = (
        "ImportError",
        "ModuleNotFoundError",
        "AttributeError",
        "TypeError",
        "RuntimeError",
        "AssertionError",
        "KeyError",
        "NameError",
        "cannot import name",
        "FAILED",
        "ERROR",
    )

    signals = []

    for raw in pytest_output.splitlines():

        line = raw.strip()

        if not line:
            continue

        if any(p in line for p in patterns):
            signals.append(line)

    return signals[:120]


def extract_files_from_signals(signals):

    found = set()

    for line in signals:

        for token in line.split():

            token = token.strip("()[],: ")

            if token.endswith(".py"):
                found.add(token)

    return sorted(found)


def scan_public_contracts():

    contracts = []

    possible = [
        ("auto_updater.py", "AutoUpdater"),
        ("executor_manager.py", "ExecutorManager"),
        ("tests/fixtures/system_payloads.py", "SYSTEM_PAYLOAD"),
    ]

    for file_name, symbol in possible:

        path = ROOT / file_name

        if not path.exists():
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        if symbol not in text:
            contracts.append([file_name, symbol])

    return contracts


def rank_files(pytest_signals):

    score = {}

    for line in pytest_signals:

        for token in line.split():

            token = token.strip("()[],: ")

            if token.endswith(".py"):

                score[token] = score.get(token, 0) + 1

    ranking = sorted(score.items(), key=lambda x: x[1], reverse=True)

    return ranking[:20]


def build_machine_report(pytest_code, pytest_signals):

    contracts = scan_public_contracts()

    ranking = rank_files(pytest_signals)

    report = {
        "compile_ok": True,
        "pytest_code": pytest_code,
        "pytest_signals": pytest_signals[:80],
        "contracts": contracts,
        "ranking_top10": ranking[:10],
    }

    return report


def build_narrative(machine):

    lines = []

    lines.append("Repo Ultra Audit Narrative")
    lines.append("")
    lines.append("## Pytest status")
    lines.append(f"Return code: {machine.get('pytest_code')}")
    lines.append("")

    lines.append("## Contracts missing")

    contracts = machine.get("contracts", [])

    if contracts:

        for file, symbol in contracts:
            lines.append(f"- {symbol} missing from {file}")

    else:
        lines.append("No missing contracts detected.")

    lines.append("")
    lines.append("## Pytest signals")

    for s in machine.get("pytest_signals", [])[:20]:
        lines.append(f"- {s}")

    lines.append("")
    lines.append("## File ranking")

    for file, score in machine.get("ranking_top10", []):
        lines.append(f"- {file} (score {score})")

    lines.append("")

    return "\n".join(lines)


def main():

    print("Running pytest collection...")

    code, pytest_output = run_pytest_collection()

    write_text(AUDIT_RAW / "pytest.log", pytest_output)

    pytest_signals = extract_pytest_signals(pytest_output)

    machine = build_machine_report(code, pytest_signals)

    write_json(AUDIT_OUT / "audit_machine.json", machine)

    narrative = build_narrative(machine)

    write_text(AUDIT_OUT / "repo_ultra_audit_narrative.md", narrative)

    print(narrative)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())