import ast
import json
import sys
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"
GUARDRAILS_DIR = ROOT / "guardrails"

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
}


def iter_python_files(root: Path) -> List[Path]:
    files = []
    for p in root.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in p.parts):
            continue
        files.append(p)
    return sorted(files)


def parse_file(path: Path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def module_name_from_path(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def collect_imports(tree: ast.AST) -> Set[str]:
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


def load_dependency_graph():
    path = GUARDRAILS_DIR / "dependency_graph.json"
    if not path.exists():
        raise RuntimeError("dependency_graph.json missing")
    return json.loads(path.read_text())


def impacted_modules(changed_files: List[str]) -> Set[str]:
    graph = load_dependency_graph()
    modules = graph["modules"]
    reverse = graph["reverse_dependencies"]

    changed = []
    for f in changed_files:
        p = ROOT / f
        if p.exists():
            changed.append(module_name_from_path(p, ROOT))

    impacted = set(changed)
    queue = list(changed)

    while queue:
        m = queue.pop(0)
        for dep in reverse.get(m, []):
            if dep not in impacted:
                impacted.add(dep)
                queue.append(dep)

    return impacted


def find_targeted_tests(changed_files: List[str]) -> Dict:

    impacted = impacted_modules(changed_files)
    selected = set()

    if TESTS_DIR.exists():

        for test_file in TESTS_DIR.rglob("test_*.py"):
            try:
                tree = parse_file(test_file)
                imports = collect_imports(tree)
            except Exception:
                continue

            for imp in imports:
                for mod in impacted:
                    if imp == mod or imp.startswith(mod):
                        selected.add(str(test_file.relative_to(ROOT)))

    return {
        "changed_files": changed_files,
        "impacted_modules": list(impacted),
        "targeted_tests": sorted(selected),
    }


def main():
    changed = sys.argv[1:]

    result = find_targeted_tests(changed)

    out = GUARDRAILS_DIR / "targeted_tests.json"
    out.write_text(json.dumps(result, indent=2))

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()