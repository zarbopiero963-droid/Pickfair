import ast
import json
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(".")
GUARDRAILS_DIR = ROOT / "guardrails"
SNAPSHOT_PATH = GUARDRAILS_DIR / "public_api_snapshot.json"
DEPENDENCIES_PATH = GUARDRAILS_DIR / "allowed_dependencies.json"
ALLOWED_FILES_PATH = GUARDRAILS_DIR / "allowed_scope_files.json"

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
    "ai",
    "app_modules",
    "controllers",
    "core",
    "ui",
}

LOW_PRIORITY_ROOT_FILES = {
    "build.py",
    "theme.py",
    "trading_config.py",
    "main.py",
}


def normalize_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def module_name_from_path(path: Path, root: Path = ROOT) -> str:
    rel = path.relative_to(root)
    rel_str = normalize_path(rel)
    if rel_str.endswith(".py"):
        rel_str = rel_str[:-3]
    rel_str = rel_str.replace("/", ".")
    if rel_str.endswith(".__init__"):
        rel_str = rel_str[:-9]
    return rel_str


def should_skip(path: Path) -> bool:
    return any(part in IGNORE_DIRS for part in path.parts)


def is_public_api_file(path: Path) -> bool:
    if should_skip(path):
        return False

    rel = normalize_path(path)

    if "/" not in rel:
        return Path(rel).name not in LOW_PRIORITY_ROOT_FILES

    top = rel.split("/", 1)[0]
    return top in PUBLIC_API_ROOTS


def iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if not is_public_api_file(path):
            continue
        yield path


def ast_signature(node):
    def unparse_or_none(value):
        if value is None:
            return None
        try:
            return ast.unparse(value)
        except Exception:
            return None

    args = node.args

    positional = [a.arg for a in args.posonlyargs + args.args]
    positional_with_defaults = []

    all_pos = args.posonlyargs + args.args
    defaults = args.defaults or []
    default_offset = len(all_pos) - len(defaults)

    for idx, arg in enumerate(all_pos):
        if idx >= default_offset:
            positional_with_defaults.append(arg.arg)

    kwonly = [a.arg for a in args.kwonlyargs]

    return {
        "name": node.name,
        "positional": positional,
        "positional_with_defaults": positional_with_defaults,
        "kwonly": kwonly,
        "vararg": args.vararg.arg if args.vararg else None,
        "kwarg": args.kwarg.arg if args.kwarg else None,
        "returns": unparse_or_none(getattr(node, "returns", None)),
    }


def build_public_api_snapshot(root: Path):
    snapshot = {}

    for path in sorted(iter_python_files(root)):
        text = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(text, filename=str(path))
        module = module_name_from_path(path, root)

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

                classes[node.name] = {
                    "methods": methods,
                }

        snapshot[module] = {
            "classes": classes,
            "functions": functions,
        }

    return snapshot


def extract_top_level_dependencies(root: Path):
    deps = defaultdict(set)

    known_modules = {module_name_from_path(p, root) for p in iter_python_files(root)}

    for path in iter_python_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(text, filename=str(path))
        src_module = module_name_from_path(path, root)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for known in known_modules:
                        if alias.name == known or alias.name.startswith(known + "."):
                            deps[src_module].add(known)

            elif isinstance(node, ast.ImportFrom):
                if not node.module:
                    continue
                for known in known_modules:
                    if node.module == known or node.module.startswith(known + "."):
                        deps[src_module].add(known)

    return {k: sorted(v) for k, v in deps.items()}


def build_dependency_graph(root: Path):
    return extract_top_level_dependencies(root)


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def check_dependencies(allowed_dependencies_path: Path, root: Path):
    expected = load_json(allowed_dependencies_path)
    current = build_dependency_graph(root)

    if not expected:
        print("No allowed dependency snapshot found.")
        print("Create it with: python tools/repo_guardrail.py snapshot-deps")
        return 1

    if current != expected:
        print("Dependency graph changed.")
        print("If intentional, regenerate with:")
        print("python tools/repo_guardrail.py snapshot-deps")
        return 1

    print("Dependency graph OK")
    return 0


def check_scope(allowed_files_path: Path, changed_files):
    allowed = load_json(allowed_files_path)

    if not allowed:
        print("No allowed scope file found.")
        print("Create it with: python tools/repo_guardrail.py snapshot-scope")
        return 1

    allowed_files = set(allowed.get("allowed_files", []))
    changed_files = [normalize_path(Path(f)) for f in changed_files]

    violations = [f for f in changed_files if f not in allowed_files]

    if violations:
        print("Changed files out of allowed scope:")
        for item in violations:
            print(f" - {item}")
        return 1

    print("Scope OK")
    return 0


def impact_analysis(root: Path, changed_paths):
    graph = build_dependency_graph(root)
    changed_modules = set()

    for path_str in changed_paths:
        path = Path(path_str)
        if path.exists() and path.suffix == ".py" and is_public_api_file(path):
            changed_modules.add(module_name_from_path(path, root))
        else:
            rel = normalize_path(path)
            if rel.endswith(".py"):
                mod = rel[:-3].replace("/", ".")
                if mod.endswith(".__init__"):
                    mod = mod[:-9]
                changed_modules.add(mod)

    impacted = set(changed_modules)

    changed = True
    while changed:
        changed = False
        for src, deps in graph.items():
            if any(dep in impacted for dep in deps) and src not in impacted:
                impacted.add(src)
                changed = True

    result = {
        "changed_modules": sorted(changed_modules),
        "impacted_modules": sorted(impacted),
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def snapshot_api():
    snapshot = build_public_api_snapshot(ROOT)
    save_json(SNAPSHOT_PATH, snapshot)
    print(f"Saved {SNAPSHOT_PATH}")
    return 0


def snapshot_deps():
    deps = build_dependency_graph(ROOT)
    save_json(DEPENDENCIES_PATH, deps)
    print(f"Saved {DEPENDENCIES_PATH}")
    return 0


def snapshot_scope():
    allowed_files = sorted(
        normalize_path(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if path.is_file() and not should_skip(path)
    )
    save_json(ALLOWED_FILES_PATH, {"allowed_files": allowed_files})
    print(f"Saved {ALLOWED_FILES_PATH}")
    return 0


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python tools/repo_guardrail.py snapshot-api")
        print("  python tools/repo_guardrail.py snapshot-deps")
        print("  python tools/repo_guardrail.py snapshot-scope")
        print("  python tools/repo_guardrail.py check-deps")
        print("  python tools/repo_guardrail.py check-scope <files...>")
        print("  python tools/repo_guardrail.py impact <files...>")
        return 1

    cmd = sys.argv[1]

    if cmd == "snapshot-api":
        return snapshot_api()

    if cmd == "snapshot-deps":
        return snapshot_deps()

    if cmd == "snapshot-scope":
        return snapshot_scope()

    if cmd == "check-deps":
        return check_dependencies(DEPENDENCIES_PATH, ROOT)

    if cmd == "check-scope":
        return check_scope(ALLOWED_FILES_PATH, sys.argv[2:])

    if cmd == "impact":
        return impact_analysis(ROOT, sys.argv[2:])

    print(f"Unknown command: {cmd}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())