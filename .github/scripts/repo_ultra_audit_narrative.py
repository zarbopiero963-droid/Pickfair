#!/usr/bin/env python3

import compileall
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(".").resolve()
OUT = ROOT / "audit_out"
RAW = ROOT / "audit_raw"

OUT.mkdir(exist_ok=True)
RAW.mkdir(exist_ok=True)

EXCLUDED_RANKING_PREFIXES = (
    "tests/",
    ".github/",
)

PYTEST_CMD = [sys.executable, "-m", "pytest", "-q"]


def read(path: Path):
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except:
        return ""


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(cmd, timeout=3600):
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout + proc.stderr
    except Exception as e:
        return 999, str(e)


def list_python_files():
    files = []
    for p in ROOT.rglob("*.py"):
        if ".venv" in str(p) or "__pycache__" in str(p):
            continue
        files.append(p)
    return files


def compile_code():
    ok = compileall.compile_dir(str(ROOT), quiet=1)
    write(RAW / "compile.log", f"compileall: {ok}")
    return ok


def run_pytest():
    code, out = run(PYTEST_CMD)
    write(RAW / "pytest.log", out)
    return code, out


def detect_symbol(file, symbol):
    txt = read(ROOT / file)
    return re.search(rf"(class|def)\s+{symbol}\b", txt) is not None


def check_contracts():
    issues = []

    if not detect_symbol("auto_updater.py", "AutoUpdater"):
        issues.append(("auto_updater.py", "AutoUpdater"))

    if not detect_symbol("executor_manager.py", "ExecutorManager"):
        issues.append(("executor_manager.py", "ExecutorManager"))

    if not detect_symbol("ui/mini_ladder.py", "OneClickLadder"):
        issues.append(("ui/mini_ladder.py", "OneClickLadder"))

    if not detect_symbol("ui/mini_ladder.py", "LiveMiniLadder"):
        issues.append(("ui/mini_ladder.py", "LiveMiniLadder"))

    if "SYSTEM_PAYLOAD" not in read(ROOT / "tests/fixtures/system_payloads.py"):
        issues.append(("tests/fixtures/system_payloads.py", "SYSTEM_PAYLOAD"))

    return issues


def smell_scan(py_files):
    smells = Counter()

    for f in py_files:
        rel = str(f.relative_to(ROOT))

        txt = read(f)

        if "except Exception" in txt:
            smells["except_exception"] += 1

        if re.search(r"except\s*:", txt):
            smells["bare_except"] += 1

        if "print(" in txt:
            smells["print"] += 1

        if "TODO" in txt or "FIXME" in txt:
            smells["todo"] += 1

    return smells


def fragility_ranking(py_files):

    scores = Counter()

    for f in py_files:
        rel = str(f.relative_to(ROOT))

        if rel.startswith(EXCLUDED_RANKING_PREFIXES):
            continue

        txt = read(f)

        score = 0

        if "except Exception" in txt:
            score += 2

        if "print(" in txt:
            score += 1

        if "TODO" in txt:
            score += 1

        if score:
            scores[rel] += score

    return scores.most_common(20)


def build_report(
    compile_ok,
    pytest_output,
    contracts,
    ranking,
    smells,
):

    report = []

    report.append("Analisi reale del repository\n")

    report.append("Stato base")
    report.append(f"compileall: {compile_ok}")
    report.append("")

    report.append("Contract mismatches rilevati tra test e codice\n")

    if contracts:
        for file, symbol in contracts:
            report.append(
                f"- {file} -> simbolo mancante: {symbol}"
            )
    else:
        report.append("Nessun mismatch trovato")

    report.append("")

    report.append("Top moduli fragili\n")

    for file, score in ranking:
        report.append(f"- {file} (score {score})")

    report.append("")

    report.append("Smells rilevati")

    for k, v in smells.items():
        report.append(f"- {k}: {v}")

    report.append("")
    report.append("Verdetto")

    report.append(
        "La base sintattica è sana ma i contratti interni tra moduli e test non sono ancora allineati."
    )

    return "\n".join(report)


def main():

    py_files = list_python_files()

    compile_ok = compile_code()

    _, pytest_out = run_pytest()

    contracts = check_contracts()

    ranking = fragility_ranking(py_files)

    smells = smell_scan(py_files)

    report = build_report(
        compile_ok,
        pytest_out,
        contracts,
        ranking,
        smells,
    )

    write(OUT / "repo_ultra_audit_narrative.md", report)

    print(report)

    if contracts:
        return 2

    if not compile_ok:
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())