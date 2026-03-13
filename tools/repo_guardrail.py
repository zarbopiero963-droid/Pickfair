import ast
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "build",
    "dist",
    ".mypy_cache",
    ".ruff_cache",
}


def _iter_python_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for p in root.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in p.parts):
            continue
        files.append(p)
    return sorted(files)


def _module_name_from_path(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def _safe_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_file(path: Path) -> ast.AST:
    return ast.parse(_safe_read_text(path), filename=str(path))


def _collect_imports(tree: ast.AST) -> Set[str]:
    imports: Set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)

    return imports


def _public_function_signature(node: ast.FunctionDef) -> Dict[str, Any]:
    args = node.args

    def arg_names(arg_list: List[ast.arg]) -> List[str]:
        return [a.arg for a in arg_list]

    defaults_count = len(args.defaults)
    positional = arg_names(args.args)
    positional_defaults = positional[-defaults_count:] if defaults_count else []

    kwonly_defaults = []
    for idx, a in enumerate(args.kwonlyargs):
        has_default = args.kw_defaults[idx] is not None
        kwonly_defaults.append({"name": a.arg, "has_default": has_default})

    return {
        "name": node.name,
        "positional": positional,
        "positional_with_defaults": positional_defaults,
        "vararg": args.vararg.arg if args.vararg else None,
        "kwonly": kwonly_defaults,
        "kwarg": args.kwarg.arg if args.kwarg else None,
    }


def _collect_public_api(tree: ast.AST) -> Dict[str, Any]:
    api: Dict[str, Any] = {"functions": {}, "classes": {}}

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if not node.name.startswith("_"):
                api["functions"][node.name] = _public_function_signature(node)

        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue

            methods: Dict[str, Any] = {}
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                    methods[item.name] = _public_function_signature(item)

            api["classes"][node.name] = {"methods": methods}

    return api


def build_public_api_snapshot(root: Path) -> Dict[str, Any]:
    result: Dict[str, Any] = {}

    for pyfile in _iter_python_files(root):
        module_name = _module_name_from_path(pyfile, root)
        try:
            tree = _parse_file(pyfile)
        except SyntaxError as exc:
            result[module_name] = {
                "parse_error": f"{exc.__class__.__name__}: {exc}"
            }
            continue

        result[module_name] = _collect_public_api(tree)

    return result


def build_dependency_graph(root: Path) -> Dict[str, Any]:
    modules: Dict[str, Dict[str, Any]] = {}

    for pyfile in _iter_python_files(root):
        module_name = _module_name_from_path(pyfile, root)
        try:
            tree = _parse_file(pyfile)
            imports = sorted(_collect_imports(tree))
        except SyntaxError as exc:
            imports = [f"PARSE_ERROR::{exc}"]

        modules[module_name] = {
            "path": str(pyfile.relative_to(root)),
            "imports": imports,
        }

    reverse: Dict[str, List[str]] = {m: [] for m in modules.keys()}

    for src_module, data in modules.items():
        for imported in data["imports"]:
            if imported in reverse:
                reverse[imported].append(src_module)
            else:
                for target in modules.keys():
                    if imported == target or imported.startswith(target + "."):
                        reverse[target].append(src_module)

    reverse = {k: sorted(set(v)) for k, v in reverse.items()}

    return {
        "modules": modules,
        "reverse_dependencies": reverse,
    }


def extract_top_level_dependencies(root: Path) -> List[str]:
    deps: Set[str] = set()

    for pyfile in _iter_python_files(root):
        try:
            tree = _parse_file(pyfile)
        except SyntaxError:
            continue

        for imported in _collect_imports(tree):
            top = imported.split(".")[0]
            if not top:
                continue

            if (root / f"{top}.py").exists() or (root / top).exists():
                continue

            deps.add(top)

    return sorted(deps)


def impact_analysis(root: Path, changed_paths: List[str]) -> Dict[str, Any]:
    graph = build_dependency_graph(root)
    modules = graph["modules"]
    reverse = graph["reverse_dependencies"]

    changed_modules: List[str] = []
    for rel_path in changed_paths:
        path = (root / rel_path).resolve()
        if not path.exists() or path.suffix != ".py":
            continue
        try:
            changed_modules.append(_module_name_from_path(path, root))
        except Exception:
            continue

    impacted: Set[str] = set(changed_modules)
    queue = list(changed_modules)

    while queue:
        current = queue.pop(0)
        for dep in reverse.get(current, []):
            if dep not in impacted:
                impacted.add(dep)
                queue.append(dep)

    impacted_paths = []
    for mod in sorted(impacted):
        if mod in modules:
            impacted_paths.append(modules[mod]["path"])

    return {
        "changed_modules": sorted(changed_modules),
        "impacted_modules": sorted(impacted),
        "impacted_paths": impacted_paths,
    }


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def check_scope(allowed_files_path: Path, changed_files: List[str]) -> Tuple[bool, List[str]]:
    data = load_json(allowed_files_path)
    allowed = set(data.get("allowed_files", []))
    violations = [f for f in changed_files if f not in allowed]
    return (len(violations) == 0, violations)


def check_dependencies(
    allowed_dependencies_path: Path,
    root: Path,
) -> Tuple[bool, List[str], List[str]]:
    allowed = set(load_json(allowed_dependencies_path).get("allowed_dependencies", []))
    current = set(extract_top_level_dependencies(root))
    unexpected = sorted(current - allowed)
    missing = sorted(allowed - current)
    return (len(unexpected) == 0, unexpected, missing)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python tools/repo_guardrail.py snapshot-api")
        print("  python tools/repo_guardrail.py build-graph")
        print("  python tools/repo_guardrail.py impact file1.py file2.py")
        print("  python tools/repo_guardrail.py check-scope file1.py file2.py")
        print("  python tools/repo_guardrail.py check-deps")
        return 1

    cmd = sys.argv[1]

    if cmd == "snapshot-api":
        snapshot = build_public_api_snapshot(ROOT)
        save_json(ROOT / "guardrails" / "public_api_snapshot.json", snapshot)
        print("Saved guardrails/public_api_snapshot.json")
        return 0

    if cmd == "build-graph":
        graph = build_dependency_graph(ROOT)
        save_json(ROOT / "guardrails" / "dependency_graph.json", graph)
        print("Saved guardrails/dependency_graph.json")
        return 0

    if cmd == "impact":
        changed = sys.argv[2:]
        result = impact_analysis(ROOT, changed)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if cmd == "check-scope":
        changed = sys.argv[2:]
        ok, violations = check_scope(ROOT / "guardrails" / "allowed_files.json", changed)
        if ok:
            print("Scope OK")
            return 0
        print("Scope violation detected:")
        for item in violations:
            print(f" - {item}")
        return 2

    if cmd == "check-deps":
        ok, unexpected, missing = check_dependencies(
            ROOT / "guardrails" / "allowed_dependencies.json",
            ROOT,
        )
        if not ok:
            print("Unexpected dependencies found:")
            for dep in unexpected:
                print(f" - {dep}")
            return 2

        print("Dependencies OK")
        if missing:
            print("Declared but not detected:")
            for dep in missing:
                print(f" - {dep}")
        return 0

    print(f"Unknown command: {cmd}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
