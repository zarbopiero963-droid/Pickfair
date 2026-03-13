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


def should_skip(path: Path) -> bool:
    return any(part in IGNORE_DIRS for part in path.parts)


def iter_python_files():
    for p in ROOT.rglob("*.py"):
        if should_skip(p):
            continue
        yield p


def module_name(path: Path) -> str:
    rel = str(path).replace("\\", "/")
    if rel.endswith(".py"):
        rel = rel[:-3]
    rel = rel.replace("/", ".")
    if rel.endswith(".__init__"):
        rel = rel[:-9]
    return rel


def parse_file(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(text)
    return text, tree


def get_imports(tree: ast.AST):
    imports = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.append(n.name)

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    return imports


def get_classes(tree: ast.Module):
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


def get_functions(tree: ast.Module):
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
                "file": str(path).replace("\\", "/"),
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
        score = (
            f["lines"]
            + len(f["imports"]) * 5
            + len(f["classes"]) * 10
            + len(f["functions"]) * 2
        )
        ranked.append((score, f["file"], f["module"]))

    ranked.sort(reverse=True)
    return ranked[:25]


def load_tests():
    tests = []

    if not TEST_DIR.exists():
        return tests

    for p in TEST_DIR.rglob("test_*.py"):
        tests.append(str(p).replace("\\", "/"))

    return tests


def find_modules_without_tests(files, tests):
    missing = []

    for f in files:
        short_name = f["module"].split(".")[-1]

        found = False
        for t in tests:
            if short_name in t:
                found = True
                break

        if not found:
            missing.append(
                {
                    "module": f["module"],
                    "file": f["file"],
                }
            )

    return missing


def find_dead_code(files):
    dead = []

    for f in files:
        for fn in f["functions"]:
            if fn.startswith("_"):
                continue

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
    dead = find_dead_code(files)

    report = {
        "summary": {
            "files": len(files),
            "tests": len(tests),
        },
        "files": files,
        "dependency_graph": {k: sorted(list(v)) for k, v in deps.items()},
        "top_risky_modules": risky,
        "modules_without_tests": missing_tests,
        "dead_code_candidates": dead,
    }

    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    out_file = ARTIFACTS / "repo_api_report_v4.json"
    out_file.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Generated: {out_file}")


if __name__ == "__main__":
    main()