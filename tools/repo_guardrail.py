import ast
import json
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(".").resolve()
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


def normalize(path: Path) -> str:
    return str(path).replace("\\", "/")


def resolve_root(root: Path) -> Path:
    return Path(root).resolve()


def should_skip(path: Path) -> bool:
    return any(part in IGNORE_DIRS for part in path.parts)


def is_public_api_file(path: Path, root: Path = ROOT) -> bool:
    root = resolve_root(root)
    path = Path(path).resolve()

    if should_skip(path):
        return False

    rel = normalize(path.relative_to(root))

    if "/" not in rel:
        return True

    top = rel.split("/", 1)[0]
    return top in PUBLIC_API_ROOTS


def iter_python_files(root: Path = ROOT):
    root = resolve_root(root)

    for path in root.rglob("*.py"):
        if not is_public_api_file(path, root):
            continue
        yield path


def module_name(path: Path, root: Path = ROOT) -> str:
    root = resolve_root(root)
    path = Path(path).resolve()

    rel = normalize(path.relative_to(root))

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


def build_public_api_snapshot(root: Path = ROOT):
    root = resolve_root(root)
    snapshot = {}

    for path in sorted(iter_python_files(root)):
        text = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(text, filename=str(path))
        mod = module_name(path, root)

        classes = {}
        functions = {}

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                functions[node.name] = ast_signature(node)

            elif isinstance(node, ast.ClassDef):
                if node.name.startswith("_"):
                    continue

                methods = {}

                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if item.name.startswith("_"):
                            continue
                        methods[item.name] = ast_signature(item)

                classes[node.name] = {"methods": methods}

        snapshot[mod] = {
            "classes": classes,
            "functions": functions,
        }

    return snapshot


def extract_top_level_dependencies(root: Path = ROOT):
    root = resolve_root(root)
    deps = defaultdict(set)

    public_modules = {module_name(p, root) for p in iter_python_files(root)}

    for path in iter_python_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(text, filename=str(path))
        src = module_name(path, root)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for mod in public_modules:
                        if alias.name == mod or alias.name.startswith(mod + "."):
                            deps[src].add(mod)

            elif isinstance(node, ast.ImportFrom):
                if not node.module:
                    continue

                for mod in public_modules:
                    if node.module == mod or node.module.startswith(mod + "."):
                        deps[src].add(mod)

    return {k: sorted(v) for k, v in deps.items()}


def build_dependency_graph(root: Path = ROOT):
    root = resolve_root(root)
    return extract_top_level_dependencies(root)


def reverse_dependency_graph(graph: dict):
    reverse = defaultdict(set)

    for src, targets in graph.items():
        for tgt in targets:
            reverse[tgt].add(src)

    return {k: sorted(v) for k, v in reverse.items()}


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_api():
    data = build_public_api_snapshot(ROOT)
    save_json(API_SNAPSHOT, data)
    print("Saved:", API_SNAPSHOT)


def snapshot_deps():
    data = build_dependency_graph(ROOT)
    save_json(DEPS_SNAPSHOT, data)
    print("Saved:", DEPS_SNAPSHOT)


def snapshot_scope():
    files = []

    for path in ROOT.rglob("*"):
        if path.is_file() and not should_skip(path):
            files.append(normalize(path.relative_to(ROOT)))

    save_json(SCOPE_SNAPSHOT, {"allowed_files": sorted(files)})
    print("Saved:", SCOPE_SNAPSHOT)


def check_deps():
    expected = load_json(DEPS_SNAPSHOT)
    current = build_dependency_graph(ROOT)

    if expected != current:
        print("Dependency graph changed")
        print("Run: python tools/repo_guardrail.py snapshot-deps")
        sys.exit(1)

    print("Dependency graph OK")


def check_scope(allowed_files_path: Path, changed_files):
    allowed = load_json(allowed_files_path)

    if not allowed:
        print("No allowed scope snapshot found.")
        print("Run: python tools/repo_guardrail.py snapshot-scope")
        return 1

    allowed_files = set(allowed.get("allowed_files", []))
    changed_files = [normalize(Path(p)) for p in changed_files]

    violations = [p for p in changed_files if p not in allowed_files]

    if violations:
        print("Changed files out of allowed scope:")
        for item in violations:
            print(f" - {item}")
        return 1

    print("Scope OK")
    return 0


def impact_analysis(root: Path, changed_paths):
    root = resolve_root(root)
    graph = build_dependency_graph(root)
    reverse_graph = reverse_dependency_graph(graph)

    changed_modules = set()

    for raw_path in changed_paths:
        p = Path(raw_path)

        if p.exists() and p.suffix == ".py":
            p = p.resolve()
            if is_public_api_file(p, root):
                changed_modules.add(module_name(p, root))
            continue

        normalized = normalize(p)
        if normalized.endswith(".py"):
            guess = normalized[:-3].replace("/", ".")
            if guess.endswith(".__init__"):
                guess = guess[:-9]
            changed_modules.add(guess)

    impacted = set(changed_modules)
    queue = list(changed_modules)

    while queue:
        current = queue.pop(0)

        for caller in reverse_graph.get(current, []):
            if caller not in impacted:
                impacted.add(caller)
                queue.append(caller)

    return {
        "changed_modules": sorted(changed_modules),
        "impacted_modules": sorted(impacted),
    }


def main():
    if len(sys.argv) < 2:
        print("Commands:")
        print("snapshot-api")
        print("snapshot-deps")
        print("snapshot-scope")
        print("check-deps")
        print("check-scope <files...>")
        print("impact <files...>")
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

    elif cmd == "check-scope":
        code = check_scope(SCOPE_SNAPSHOT, sys.argv[2:])
        sys.exit(code)

    elif cmd == "impact":
        result = impact_analysis(ROOT, sys.argv[2:])
        print(json.dumps(result, indent=2, ensure_ascii=False))

    else:
        print("Unknown command:", cmd)
        sys.exit(1)


if __name__ == "__main__":
    main()