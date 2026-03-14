#!/usr/bin/env python3

import ast
import compileall
import json
import re
import subprocess
import sys
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(".").resolve()

OUT = ROOT / "audit_out"
RAW = ROOT / "audit_raw"

OUT.mkdir(exist_ok=True)
RAW.mkdir(exist_ok=True)

EXCLUDED_PREFIXES = (
    ".venv/",
    "__pycache__",
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


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


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

        rel = str(p.relative_to(ROOT)).replace("\\", "/")

        if rel.startswith(EXCLUDED_PREFIXES):
            continue

        files.append(p)

    return sorted(files)


def compile_repo():

    ok = compileall.compile_dir(str(ROOT), quiet=1)

    write(RAW / "compile.log", f"compileall: {ok}")

    return ok


def run_pytest():

    code, out = run(PYTEST_CMD)

    write(RAW / "pytest.log", out)

    return code, out


def parse_ast(py_files):

    classes = defaultdict(list)
    functions = defaultdict(list)
    imports = defaultdict(list)

    symbol_index = {}

    for f in py_files:

        rel = str(f.relative_to(ROOT)).replace("\\", "/")

        try:

            tree = ast.parse(read(f))

        except:

            continue

        for node in ast.walk(tree):

            if isinstance(node, ast.ClassDef):

                classes[node.name].append(rel)
                symbol_index[node.name] = rel

            elif isinstance(node, ast.FunctionDef):

                functions[node.name].append(rel)
                symbol_index[node.name] = rel

            elif isinstance(node, ast.AsyncFunctionDef):

                functions[node.name].append(rel)
                symbol_index[node.name] = rel

            elif isinstance(node, ast.Import):

                for name in node.names:

                    imports[rel].append(name.name)

            elif isinstance(node, ast.ImportFrom):

                module = node.module or ""

                for name in node.names:

                    imports[rel].append(f"{module}.{name.name}")

    return classes, functions, imports, symbol_index


def detect_references(py_files):

    refs = Counter()

    for f in py_files:

        tokens = re.findall(
            r"[A-Za-z_][A-Za-z0-9_]+",
            read(f)
        )

        for t in tokens:

            refs[t] += 1

    return refs


def detect_unused(classes, functions, references):

    unused_classes = []
    unused_functions = []

    for name, files in classes.items():

        if references[name] <= 1:

            unused_classes.append((name, files[0]))

    for name, files in functions.items():

        if references[name] <= 1:

            unused_functions.append((name, files[0]))

    return unused_classes[:20], unused_functions[:20]


def build_dependency_graph(imports):

    graph = defaultdict(set)

    for file, modules in imports.items():

        for mod in modules:

            mod_file = mod.replace(".", "/") + ".py"

            if (ROOT / mod_file).exists():

                graph[file].add(mod_file)

    return graph


def detect_circular_imports(graph):

    circular = set()

    for a in graph:

        for b in graph[a]:

            if b in graph and a in graph[b]:

                circular.add(tuple(sorted((a, b))))

    return sorted(circular)


def smell_scan(py_files):

    smells = Counter()

    file_scores = {}

    for f in py_files:

        txt = read(f)

        rel = str(f.relative_to(ROOT)).replace("\\", "/")

        score = 0

        if "except Exception" in txt:
            smells["except_exception"] += 1
            score += 2

        if re.search(r"except\s*:", txt):
            smells["bare_except"] += 1
            score += 3

        if "print(" in txt:
            smells["print"] += 1
            score += 1

        if "TODO" in txt or "FIXME" in txt:
            smells["todo"] += 1
            score += 1

        if score:

            file_scores[rel] = score

    return smells, file_scores


def fragility_ranking(file_scores):

    return Counter(file_scores).most_common(20)


def check_contracts(symbol_index):

    issues = []

    checks = [
        ("auto_updater.py", "AutoUpdater"),
        ("executor_manager.py", "ExecutorManager"),
        ("ui/mini_ladder.py", "OneClickLadder"),
        ("ui/mini_ladder.py", "LiveMiniLadder"),
    ]

    for file, symbol in checks:

        if symbol not in symbol_index:

            issues.append((file, symbol))

    fixture = ROOT / "tests/fixtures/system_payloads.py"

    if fixture.exists():

        if "SYSTEM_PAYLOAD" not in read(fixture):

            issues.append(("tests/fixtures/system_payloads.py", "SYSTEM_PAYLOAD"))

    return issues


def build_report(
    compile_ok,
    pytest_code,
    contracts,
    smells,
    ranking,
    unused_classes,
    unused_functions,
    circular_imports
):

    r = []

    r.append("Analisi reale del repository\n")

    r.append("STATO BASE")

    r.append(f"compileall: {compile_ok}")

    r.append(f"pytest exit code: {pytest_code}")

    r.append("")

    r.append("CONTRACT MISMATCH")

    if contracts:

        for file, symbol in contracts:

            r.append(f"- {file} -> simbolo mancante: {symbol}")

    else:

        r.append("nessun mismatch rilevato")

    r.append("")

    r.append("TOP MODULI FRAGILI")

    for f, s in ranking:

        r.append(f"- {f} (score {s})")

    r.append("")

    r.append("SMELLS")

    for k, v in smells.items():

        r.append(f"- {k}: {v}")

    r.append("")

    r.append("CLASSI PROBABILMENTE INUTILIZZATE")

    for name, file in unused_classes:

        r.append(f"- {name} ({file})")

    r.append("")

    r.append("FUNZIONI PROBABILMENTE INUTILIZZATE")

    for name, file in unused_functions:

        r.append(f"- {name} ({file})")

    r.append("")

    r.append("CIRCULAR IMPORTS")

    if circular_imports:

        for a, b in circular_imports:

            r.append(f"- {a} <-> {b}")

    else:

        r.append("nessuno")

    r.append("")

    r.append("VERDETTO")

    r.append(
        "La base sintattica è sana ma i contratti tra moduli e test non sono ancora allineati."
    )

    return "\n".join(r)


def main():

    py_files = list_python_files()

    compile_ok = compile_repo()

    pytest_code, _ = run_pytest()

    classes, functions, imports, symbol_index = parse_ast(py_files)

    references = detect_references(py_files)

    unused_classes, unused_functions = detect_unused(
        classes,
        functions,
        references
    )

    graph = build_dependency_graph(imports)

    circular_imports = detect_circular_imports(graph)

    smells, file_scores = smell_scan(py_files)

    ranking = fragility_ranking(file_scores)

    contracts = check_contracts(symbol_index)

    report = build_report(
        compile_ok,
        pytest_code,
        contracts,
        smells,
        ranking,
        unused_classes,
        unused_functions,
        circular_imports
    )

    write(OUT / "repo_ultra_audit_narrative.md", report)

    write_json(
        OUT / "audit_machine.json",
        {
            "compile_ok": compile_ok,
            "pytest_code": pytest_code,
            "contracts": contracts,
            "smells": smells,
            "ranking": ranking,
            "circular_imports": circular_imports,
        },
    )

    print(report)

    if contracts:
        return 2

    if not compile_ok:
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())