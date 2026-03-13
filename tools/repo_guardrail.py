import ast
import json
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(".")
GUARDRAILS_DIR = ROOT / "guardrails"

API_SNAPSHOT = GUARDRAILS_DIR / "public_api_snapshot.json"
DEPS_SNAPSHOT = GUARDRAILS_DIR / "allowed_dependencies.json"
SCOPE_SNAPSHOT = GUARDRAILS_DIR / "allowed_scope_files.json"

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
    "tools",
    ".github",
    "tests",
    "guardrails",
}

PUBLIC_API_ROOTS = {
    "core",
    "controllers",
    "app_modules",
    "ai",
    "ui",
}


def normalize(p: Path):
    return str(p).replace("\\", "/")


def should_skip(path: Path):
    return any(part in IGNORE_DIRS for part in path.parts)


def is_public_api_file(path: Path):
    if should_skip(path):
        return False

    rel = normalize(path)

    if "/" not in rel:
        return True

    top = rel.split("/")[0]
    return top in PUBLIC_API_ROOTS


def iter_python_files():
    for p in ROOT.rglob("*.py"):
        if not is_public_api_file(p):
            continue
        yield p


def module_name(path: Path):
    rel = normalize(path.relative_to(ROOT))

    if rel.endswith(".py"):
        rel = rel[:-3]

    rel = rel.replace("/", ".")

    if rel.endswith(".__init__"):
        rel = rel[:-9]

    return rel


def ast_signature(node):
    args = node.args

    positional = [a.arg for a in args.posonlyargs + args.args]
    kwonly = [a.arg for a in args.kwonlyargs]

    return {
        "name": node.name,
        "positional": positional,
        "kwonly": kwonly,
        "vararg": args.vararg.arg if args.vararg else None,
        "kwarg": args.kwarg.arg if args.kwarg else None,
    }


def build_public_api_snapshot():
    snapshot = {}

    for path in sorted(iter_python_files()):
        text = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(text)
        module = module_name(path)

        classes = {}
        functions = {}

        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                if node.name.startswith("_"):
                    continue
                functions[node.name] = ast_signature(node)

            elif isinstance(node, ast.ClassDef):
                if node.name.startswith("_"):
                    continue

                methods = {}

                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        if item.name.startswith("_"):
                            continue
                        methods[item.name] = ast_signature(item)

                classes[node.name] = {"methods": methods}

        snapshot[module] = {
            "classes": classes,
            "functions": functions,
        }

    return snapshot


def build_dependency_graph():
    deps = defaultdict(set)

    modules = {module_name(p) for p in iter_python_files()}

    for path in iter_python_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(text)
        src = module_name(path)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for mod in modules:
                        if alias.name == mod or alias.name.startswith(mod + "."):
                            deps[src].add(mod)

            elif isinstance(node, ast.ImportFrom):
                if not node.module:
                    continue

                for mod in modules:
                    if node.module == mod or node.module.startswith(mod + "."):
                        deps[src].add(mod)

    return {k: sorted(v) for k, v in deps.items()}


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_api():
    data = build_public_api_snapshot()
    save_json(API_SNAPSHOT, data)
    print("Saved:", API_SNAPSHOT)


def snapshot_deps():
    data = build_dependency_graph()
    save_json(DEPS_SNAPSHOT, data)
    print("Saved:", DEPS_SNAPSHOT)


def snapshot_scope():
    files = []

    for p in ROOT.rglob("*"):
        if p.is_file() and not should_skip(p):
            files.append(normalize(p.relative_to(ROOT)))

    save_json(SCOPE_SNAPSHOT, {"allowed_files": sorted(files)})
    print("Saved:", SCOPE_SNAPSHOT)


def check_deps():
    expected = load_json(DEPS_SNAPSHOT)
    current = build_dependency_graph()

    if expected != current:
        print("Dependency graph changed")
        print("Run: python tools/repo_guardrail.py snapshot-deps")
        sys.exit(1)

    print("Dependency graph OK")


def main():
    if len(sys.argv) < 2:
        print("Commands:")
        print("snapshot-api")
        print("snapshot-deps")
        print("snapshot-scope")
        print("check-deps")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "snapshot-api":
        snapshot_api()
    elif cmd == "snapshot-deps":
        snapshot_deps()
    elif cmd == "snapshot-scope":
        snapshot_scope()
    elif cmd == "check-deps":
        check_deps()
    else:
        print("Unknown command:", cmd)
        sys.exit(1)


if __name__ == "__main__":
    main()