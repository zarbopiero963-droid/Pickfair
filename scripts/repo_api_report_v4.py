import ast
import json
from pathlib import Path
from collections import defaultdict

ROOT = Path(".")

ARTIFACTS = ROOT / "artifacts"
TEST_DIR = ROOT / "tests"

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    "artifacts",
    "scripts",
    ".github",
}


def should_skip(path):
    return any(p in IGNORE_DIRS for p in path.parts)


def iter_python_files():
    for p in ROOT.rglob("*.py"):
        if should_skip(p):
            continue
        yield p


def module_name(path):
    rel = str(path).replace("\\", "/")
    rel = rel[:-3] if rel.endswith(".py") else rel
    rel = rel.replace("/", ".")
    if rel.endswith(".__init__"):
        rel = rel[:-9]
    return rel


def parse_file(path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(text)
    return text, tree


def get_imports(tree):
    imports = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.append(n.name)

        if isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    return imports


def get_classes(tree):

    classes = []

    for node in tree.body:

        if isinstance(node, ast.ClassDef):

            methods = []

            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.append(item.name)

            classes.append(
                {
                    "name": node.name,
                    "methods": methods,
                }
            )

    return classes


def get_functions(tree):

    funcs = []

    for node in tree.body:

        if isinstance(node, ast.FunctionDef):
            funcs.append(node.name)

    return funcs


def analyze_repo():

    files = []

    dep_graph = defaultdict(set)

    for path in iter_python_files():

        if "tests" in str(path):
            continue

        text, tree = parse_file(path)

        mod = module_name(path)

        imports = get_imports(tree)

        funcs = get_functions(tree)

        classes = get_classes(tree)

        for imp in imports:
            dep_graph[mod].add(imp)

        files.append(
            {
                "file": str(path),
                "module": mod,
                "functions": funcs,
                "classes": classes,
                "imports": imports,
                "lines": len(text.splitlines()),
            }
        )

    return files, dep_graph


def find_risky_modules(files):

    ranked = []

    for f in files:

        score = f["lines"] + len(f["imports"]) * 5 + len(f["classes"]) * 10

        ranked.append((score, f["file"], f["module"]))

    ranked.sort(reverse=True)

    return ranked[:20]


def load_tests():

    tests = []

    if not TEST_DIR.exists():
        return tests

    for p in TEST_DIR.rglob("test_*.py"):
        tests.append(str(p))

    return tests


def find_modules_without_tests(files, tests):

    missing = []

    for f in files:

        name = f["module"].split(".")[-1]

        found = False

        for t in tests:
            if name in t:
                found = True

        if not found:
            missing.append(f)

    return missing


def find_dead_code(files, tests):

    dead = []

    for f in files:

        for fn in f["functions"]:

            found = False

            for t in tests:
                if fn in t:
                    found = True

            if not found and not fn.startswith("_"):

                dead.append(
                    {
                        "module": f["module"],
                        "symbol": fn,
                    }
                )

    return dead


def main():

    print("Scanning repository...")

    files, deps = analyze_repo()

    tests = load_tests()

    risky = find_risky_modules(files)

    missing_tests = find_modules_without_tests(files, tests)

    dead = find_dead_code(files, tests)

    report = {
        "summary": {
            "files": len(files),
            "tests": len(tests),
        },
        "files": files,
        "dependency_graph": {k: list(v) for k, v in deps.items()},
        "top_risky_modules": risky,
        "modules_without_tests": missing_tests,
        "dead_code_candidates": dead,
    }

    ARTIFACTS.mkdir(exist_ok=True)

    (ARTIFACTS / "repo_api_report_v4.json").write_text(
        json.dumps(report, indent=2)
    )

    print("Report generated")

    print("artifacts/repo_api_report_v4.json")


if __name__ == "__main__":
    main()