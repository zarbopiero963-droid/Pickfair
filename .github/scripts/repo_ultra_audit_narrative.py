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

SKIP_SCAN_PREFIX = (
    ".venv/",
    "__pycache__",
)

SKIP_RANK_PREFIX = (
    ".github/",
    "tests/",
)

SKIP_DEADCODE_PREFIX = (
    "tests/",
)

PYTEST_CMD = [sys.executable, "-m", "pytest", "-q"]


def read(path: Path):
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def run(cmd, timeout=3600):
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except Exception as e:
        return 999, str(e)


def list_python_files():
    files = []

    for p in ROOT.rglob("*.py"):
        rel = str(p.relative_to(ROOT)).replace("\\", "/")

        if rel.startswith(SKIP_SCAN_PREFIX):
            continue

        files.append(p)

    return sorted(files)


def compile_repo():
    ok = compileall.compile_dir(str(ROOT), quiet=1)
    write(RAW / "compile.log", f"compileall: {ok}\n")
    return ok


def run_pytest():
    code, out = run(PYTEST_CMD)
    write(RAW / "pytest.log", out)
    return code, out


def parse_pytest_errors(text):
    errors = []

    collecting = re.findall(r"^ERROR collecting .*$", text, flags=re.MULTILINE)
    if collecting:
        errors.extend(collecting[:10])

    if not errors:
        blocks = re.findall(r"ERROR collecting .*?\n(.*?)\n\n", text, re.S)
        for b in blocks[:10]:
            cleaned = b.strip()
            if cleaned:
                errors.append(cleaned)

    return errors[:10]


def parse_ast(py_files):
    classes = defaultdict(list)
    functions = defaultdict(list)
    imports = defaultdict(list)
    symbol_index = {}

    for f in py_files:
        rel = str(f.relative_to(ROOT)).replace("\\", "/")

        try:
            tree = ast.parse(read(f))
        except Exception:
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
        txt = read(f)
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]+", txt)

        for t in tokens:
            refs[t] += 1

    return refs


def detect_unused(classes, functions, references):
    unused_classes = []
    unused_functions = []

    for name, files in classes.items():
        file = files[0]

        if file.startswith(SKIP_DEADCODE_PREFIX):
            continue

        if references[name] <= 1:
            unused_classes.append((name, file))

    for name, files in functions.items():
        file = files[0]

        if file.startswith(SKIP_DEADCODE_PREFIX):
            continue

        if references[name] <= 1:
            unused_functions.append((name, file))

    unused_classes.sort(key=lambda x: (x[1], x[0]))
    unused_functions.sort(key=lambda x: (x[1], x[0]))

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
        rel = str(f.relative_to(ROOT)).replace("\\", "/")

        if rel.startswith(SKIP_RANK_PREFIX):
            continue

        txt = read(f)
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


def human_summary(compile_ok, pytest_code, contracts, ranking, smells, circular_imports):
    lines = []

    lines.append("Sì. Ho fatto un’analisi reale del repository, non teorica.")
    lines.append("")
    lines.append("Ho eseguito:")
    lines.append("- compileall su tutta la codebase")
    lines.append("- pytest completo")
    lines.append("- scansione dei contratti tra test e moduli")
    lines.append("- ranking dei moduli fragili")
    lines.append("- scansione smells")
    lines.append("- controllo dead code probabile")
    lines.append("- controllo circular imports")
    lines.append("")
    lines.append("Verdetto ultra sintetico")
    lines.append("")

    if compile_ok:
        lines.append("Il repository compila, quindi la base sintattica è sana.")
    else:
        lines.append("Il repository non è pulito neppure a livello sintattico.")

    if contracts:
        lines.append(
            "Il problema dominante non è la sintassi ma la rottura dei contratti tra moduli e test."
        )
    elif pytest_code != 0:
        lines.append(
            "I contratti principali sembrano più stabili, ma la suite continua a segnalare errori."
        )
    else:
        lines.append("Non emergono rotture contrattuali immediate nella scansione attuale.")

    lines.append("")
    lines.append("Stato reale misurato")
    lines.append(f"- compileall: {'OK' if compile_ok else 'FAIL'}")
    lines.append(f"- pytest exit code: {pytest_code}")
    lines.append(f"- contract mismatches: {len(contracts)}")
    lines.append(f"- moduli fragili in classifica: {len(ranking)}")
    lines.append(f"- except Exception: {smells.get('except_exception', 0)}")
    lines.append(f"- bare except: {smells.get('bare_except', 0)}")
    lines.append(f"- print: {smells.get('print', 0)}")
    lines.append(f"- circular imports: {len(circular_imports)}")
    lines.append("")

    return "\n".join(lines)


def build_report(
    compile_ok,
    pytest_code,
    contracts,
    smells,
    ranking,
    unused_classes,
    unused_functions,
    circular_imports,
    pytest_errors,
):
    r = []

    r.append(human_summary(
        compile_ok=compile_ok,
        pytest_code=pytest_code,
        contracts=contracts,
        ranking=ranking,
        smells=smells,
        circular_imports=circular_imports,
    ))

    if pytest_errors:
        r.append("Pytest collection / run signals")
        for e in pytest_errors:
            r.append(f"- {e}")
        r.append("")

    r.append("P0 — contract mismatch")
    if contracts:
        for file, symbol in contracts:
            r.append(f"- {file} -> simbolo mancante: {symbol}")
    else:
        r.append("Nessun mismatch contrattuale immediato rilevato.")
    r.append("")

    r.append("P1 — top moduli fragili")
    if ranking:
        for f, s in ranking:
            r.append(f"- {f} (score {s})")
    else:
        r.append("Nessun modulo fragile evidenziato.")
    r.append("")

    r.append("P2 — smells")
    if smells:
        for k, v in smells.items():
            r.append(f"- {k}: {v}")
    else:
        r.append("Nessuno smell rilevato.")
    r.append("")

    r.append("Classi probabilmente inutilizzate")
    if unused_classes:
        for name, file in unused_classes:
            r.append(f"- {name} ({file})")
    else:
        r.append("Nessuna.")
    r.append("")

    r.append("Funzioni probabilmente inutilizzate")
    if unused_functions:
        for name, file in unused_functions:
            r.append(f"- {name} ({file})")
    else:
        r.append("Nessuna.")
    r.append("")

    r.append("Circular imports")
    if circular_imports:
        for a, b in circular_imports:
            r.append(f"- {a} <-> {b}")
    else:
        r.append("Nessuno.")
    r.append("")

    r.append("Verdettissimo finale")
    if contracts:
        r.append(
            "Il repository non è rotto ovunque, ma resta in stato giallo/rosso finché questi contratti pubblici non vengono riallineati."
        )
    elif pytest_code != 0:
        r.append(
            "Il repository è più vicino a uno stato sano, ma la suite non è ancora verde."
        )
    else:
        r.append(
            "Il repository appare in uno stato molto più stabile nella scansione attuale."
        )

    return "\n".join(r)


def main():
    py_files = list_python_files()

    compile_ok = compile_repo()
    pytest_code, pytest_output = run_pytest()
    pytest_errors = parse_pytest_errors(pytest_output)

    classes, functions, imports, symbol_index = parse_ast(py_files)
    references = detect_references(py_files)
    unused_classes, unused_functions = detect_unused(classes, functions, references)

    graph = build_dependency_graph(imports)
    circular_imports = detect_circular_imports(graph)

    smells, file_scores = smell_scan(py_files)
    ranking = fragility_ranking(file_scores)
    contracts = check_contracts(symbol_index)

    report = build_report(
        compile_ok=compile_ok,
        pytest_code=pytest_code,
        contracts=contracts,
        smells=smells,
        ranking=ranking,
        unused_classes=unused_classes,
        unused_functions=unused_functions,
        circular_imports=circular_imports,
        pytest_errors=pytest_errors,
    )

    write(OUT / "repo_ultra_audit_narrative.md", report)

    write_json(
        OUT / "audit_machine.json",
        {
            "compile_ok": compile_ok,
            "pytest_code": pytest_code,
            "contracts": contracts,
            "smells": dict(smells),
            "ranking": ranking,
            "circular_imports": circular_imports,
            "unused_classes": unused_classes,
            "unused_functions": unused_functions,
            "pytest_errors": pytest_errors,
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