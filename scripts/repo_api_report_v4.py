import ast
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(".")
ARTIFACTS = ROOT / "artifacts"
TESTS_DIR = ROOT / "tests"

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
}


def should_skip(path: Path) -> bool:
    return any(part in IGNORE_DIRS for part in path.parts)


def iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if should_skip(path):
            continue
        yield path


def normalize_path(path: Path) -> str:
    return path.as_posix().lstrip("./")


def module_name_from_path(path: Path) -> str:
    rel = normalize_path(path)
    if rel.endswith(".py"):
        rel = rel[:-3]
    rel = rel.replace("/", ".")
    if rel.endswith(".__init__"):
        rel = rel[: -len(".__init__")]
    return rel


def safe_read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def ast_to_str(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def build_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    parts: list[str] = []

    posonly = list(node.args.posonlyargs)
    regular = list(node.args.args)
    defaults = list(node.args.defaults)

    all_pos = posonly + regular
    default_offset = len(all_pos) - len(defaults)

    for idx, arg in enumerate(all_pos):
        piece = arg.arg
        ann = ast_to_str(arg.annotation)
        if ann:
            piece += f": {ann}"
        if idx >= default_offset:
            default_expr = defaults[idx - default_offset]
            default_text = ast_to_str(default_expr)
            if default_text is not None:
                piece += f" = {default_text}"
        parts.append(piece)

    if posonly:
        parts.insert(len(posonly), "/")

    if node.args.vararg:
        piece = f"*{node.args.vararg.arg}"
        ann = ast_to_str(node.args.vararg.annotation)
        if ann:
            piece += f": {ann}"
        parts.append(piece)
    elif node.args.kwonlyargs:
        parts.append("*")

    for kwarg, kwdefault in zip(node.args.kwonlyargs, node.args.kw_defaults):
        piece = kwarg.arg
        ann = ast_to_str(kwarg.annotation)
        if ann:
            piece += f": {ann}"
        if kwdefault is not None:
            default_text = ast_to_str(kwdefault)
            if default_text is not None:
                piece += f" = {default_text}"
        parts.append(piece)

    if node.args.kwarg:
        piece = f"**{node.args.kwarg.arg}"
        ann = ast_to_str(node.args.kwarg.annotation)
        if ann:
            piece += f": {ann}"
        parts.append(piece)

    ret = ast_to_str(node.returns)
    if ret:
        return f"({', '.join(parts)}) -> {ret}"
    return f"({', '.join(parts)})"


def call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        root = call_name(node.value)
        if root:
            return f"{root}.{node.attr}"
        return node.attr
    return None


def attach_parents(tree: ast.AST):
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child.parent = parent  # type: ignore[attr-defined]


def parse_with_parents(source: str, filename: str) -> ast.Module:
    tree = ast.parse(source, filename=filename)
    attach_parents(tree)
    return tree


class ModuleAnalyzer(ast.NodeVisitor):
    def __init__(self, file_path: Path, source: str):
        self.file_path = file_path
        self.source = source
        self.module = module_name_from_path(file_path)
        self.imports: list[dict[str, Any]] = []
        self.top_level_functions: list[dict[str, Any]] = []
        self.classes: list[dict[str, Any]] = []
        self.global_assignments: list[dict[str, Any]] = []
        self.string_constants: list[str] = []
        self.call_names: list[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(
                {
                    "type": "import",
                    "module": alias.name,
                    "alias": alias.asname,
                    "line": getattr(node, "lineno", None),
                }
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        self.imports.append(
            {
                "type": "from",
                "module": node.module,
                "level": node.level,
                "names": [{"name": n.name, "alias": n.asname} for n in node.names],
                "line": getattr(node, "lineno", None),
            }
        )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        if isinstance(getattr(node, "parent", None), ast.Module):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.global_assignments.append(
                        {
                            "name": target.id,
                            "value": ast_to_str(node.value),
                            "line": getattr(node, "lineno", None),
                        }
                    )
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        if isinstance(getattr(node, "parent", None), ast.Module):
            if isinstance(node.target, ast.Name):
                self.global_assignments.append(
                    {
                        "name": node.target.id,
                        "annotation": ast_to_str(node.annotation),
                        "value": ast_to_str(node.value),
                        "line": getattr(node, "lineno", None),
                    }
                )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if isinstance(getattr(node, "parent", None), ast.Module):
            self.top_level_functions.append(self._function_payload(node, False))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        if isinstance(getattr(node, "parent", None), ast.Module):
            self.top_level_functions.append(self._function_payload(node, True))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        if isinstance(getattr(node, "parent", None), ast.Module):
            class_info = {
                "name": node.name,
                "bases": [ast_to_str(b) for b in node.bases if ast_to_str(b)],
                "line": getattr(node, "lineno", None),
                "docstring": ast.get_docstring(node),
                "attributes": [],
                "methods": [],
            }

            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            class_info["attributes"].append(
                                {
                                    "name": target.id,
                                    "value": ast_to_str(item.value),
                                    "line": getattr(item, "lineno", None),
                                }
                            )
                elif isinstance(item, ast.AnnAssign):
                    if isinstance(item.target, ast.Name):
                        class_info["attributes"].append(
                            {
                                "name": item.target.id,
                                "annotation": ast_to_str(item.annotation),
                                "value": ast_to_str(item.value),
                                "line": getattr(item, "lineno", None),
                            }
                        )
                elif isinstance(item, ast.FunctionDef):
                    class_info["methods"].append(self._method_payload(item, False))
                elif isinstance(item, ast.AsyncFunctionDef):
                    class_info["methods"].append(self._method_payload(item, True))

            self.classes.append(class_info)

        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, str):
            value = node.value.strip()
            if value:
                self.string_constants.append(value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        name = call_name(node.func)
        if name:
            self.call_names.append(name)
        self.generic_visit(node)

    def _function_payload(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool) -> dict[str, Any]:
        decorators = [ast_to_str(d) for d in node.decorator_list if ast_to_str(d)]
        return {
            "name": node.name,
            "async": is_async,
            "signature": build_signature(node),
            "line": getattr(node, "lineno", None),
            "docstring": ast.get_docstring(node),
            "decorators": decorators,
        }

    def _method_payload(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool) -> dict[str, Any]:
        decorators = [ast_to_str(d) for d in node.decorator_list if ast_to_str(d)]
        method_type = "instance"
        if "staticmethod" in decorators:
            method_type = "staticmethod"
        elif "classmethod" in decorators:
            method_type = "classmethod"

        return {
            "name": node.name,
            "async": is_async,
            "signature": build_signature(node),
            "line": getattr(node, "lineno", None),
            "docstring": ast.get_docstring(node),
            "decorators": decorators,
            "method_type": method_type,
        }


def analyze_file(path: Path) -> dict[str, Any]:
    source = safe_read(path)
    analyzer = ModuleAnalyzer(path, source)

    try:
        tree = parse_with_parents(source, str(path))
        analyzer.visit(tree)
    except SyntaxError as e:
        return {
            "file": normalize_path(path),
            "module": module_name_from_path(path),
            "syntax_error": str(e),
        }

    metrics = {
        "line_count": len(source.splitlines()),
        "top_level_functions": len(analyzer.top_level_functions),
        "classes": len(analyzer.classes),
        "imports": len(analyzer.imports),
        "global_assignments": len(analyzer.global_assignments),
    }

    public_symbols = set()

    for fn in analyzer.top_level_functions:
        if not fn["name"].startswith("_"):
            public_symbols.add(fn["name"])

    for cls in analyzer.classes:
        if not cls["name"].startswith("_"):
            public_symbols.add(cls["name"])
        for method in cls["methods"]:
            if not method["name"].startswith("_"):
                public_symbols.add(f"{cls['name']}.{method['name']}")

    return {
        "file": normalize_path(path),
        "module": analyzer.module,
        "metrics": metrics,
        "imports": analyzer.imports,
        "top_level_functions": analyzer.top_level_functions,
        "classes": analyzer.classes,
        "globals": analyzer.global_assignments,
        "public_symbols": sorted(public_symbols),
        "call_names": sorted(set(analyzer.call_names)),
        "string_constants_sample": sorted(set(analyzer.string_constants))[:50],
        "content_hash": hashlib.sha256(source.encode("utf-8", errors="ignore")).hexdigest(),
    }


def load_test_files() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    if not TESTS_DIR.exists():
        return items

    for path in sorted(TESTS_DIR.rglob("test_*.py")):
        if should_skip(path):
            continue

        source = safe_read(path)

        try:
            tree = parse_with_parents(source, str(path))
        except SyntaxError:
            continue

        tests = []
        imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                call_names = []
                string_constants = []

                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        name = call_name(sub.func)
                        if name:
                            call_names.append(name)
                    elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        s = sub.value.strip()
                        if s:
                            string_constants.append(s)

                tests.append(
                    {
                        "name": node.name,
                        "line": getattr(node, "lineno", None),
                        "calls": sorted(set(call_names)),
                        "strings": sorted(set(string_constants)),
                    }
                )

        items.append(
            {
                "file": normalize_path(path),
                "module": module_name_from_path(path),
                "imports": sorted(set(imports)),
                "tests": tests,
                "source_hash": hashlib.sha256(source.encode("utf-8", errors="ignore")).hexdigest(),
            }
        )

    return items


def resolve_relative_import(current_module: str, imported_module: str | None, level: int) -> str:
    parts = current_module.split(".")
    base = parts[:-level] if level > 0 else parts
    if imported_module:
        return ".".join(base + imported_module.split("."))
    return ".".join(base)


def build_internal_dependency_graph(files_data: list[dict[str, Any]]) -> dict[str, list[str]]:
    known_modules = {item["module"] for item in files_data if "module" in item}
    graph: dict[str, set[str]] = defaultdict(set)

    for item in files_data:
        src = item.get("module")
        if not src:
            continue

        for imp in item.get("imports", []):
            mod = imp.get("module")
            if imp.get("type") == "import" and mod:
                for known in known_modules:
                    if mod == known or mod.startswith(f"{known}."):
                        graph[src].add(known)
            elif imp.get("type") == "from" and mod:
                level = imp.get("level", 0)
                if level == 0:
                    for known in known_modules:
                        if mod == known or mod.startswith(f"{known}."):
                            graph[src].add(known)
                else:
                    resolved = resolve_relative_import(src, mod, level)
                    for known in known_modules:
                        if resolved == known or resolved.startswith(f"{known}."):
                            graph[src].add(known)

    return {k: sorted(v) for k, v in graph.items()}


def find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    visited = set()
    stack = []
    on_stack = set()
    cycles = []

    def dfs(node: str):
        visited.add(node)
        stack.append(node)
        on_stack.add(node)

        for neigh in graph.get(node, []):
            if neigh not in visited:
                dfs(neigh)
            elif neigh in on_stack:
                try:
                    idx = stack.index(neigh)
                    cycle = stack[idx:] + [neigh]
                    if cycle not in cycles:
                        cycles.append(cycle)
                except ValueError:
                    pass

        stack.pop()
        on_stack.remove(node)

    for n in graph:
        if n not in visited:
            dfs(n)

    return cycles


def estimate_test_coverage_nominal(files_data: list[dict[str, Any]], test_files: list[dict[str, Any]]) -> dict[str, Any]:
    symbol_to_tests: dict[str, list[str]] = defaultdict(list)
    module_to_tests: dict[str, list[str]] = defaultdict(list)

    for test_file in test_files:
        test_path = test_file["file"]
        imports_blob = " ".join(test_file["imports"]).lower()

        for file_info in files_data:
            module = file_info["module"]
            base = module.split(".")[-1].lower()
            if base in test_path.lower() or base in imports_blob:
                module_to_tests[module].append(test_path)

        for test_case in test_file["tests"]:
            text_blob = " ".join(test_case["calls"] + test_case["strings"]).lower()
            test_name = test_case["name"].lower()

            for file_info in files_data:
                module = file_info["module"]

                for symbol in file_info.get("public_symbols", []):
                    simple = symbol.split(".")[-1].lower()
                    owner = symbol.split(".")[0].lower()

                    if (
                        simple in test_name
                        or simple in text_blob
                        or owner in test_name
                        or owner in text_blob
                    ):
                        symbol_to_tests[f"{module}:{symbol}"].append(test_path)

    covered = []
    uncovered = []

    for file_info in files_data:
        module = file_info["module"]

        for symbol in file_info.get("public_symbols", []):
            key = f"{module}:{symbol}"
            matched = sorted(set(symbol_to_tests.get(key, [])))
            if matched:
                covered.append({"module": module, "symbol": symbol, "tests": matched})
            else:
                uncovered.append({"module": module, "symbol": symbol})

    modules_without_tests = []
    for file_info in files_data:
        module = file_info["module"]
        tests = sorted(set(module_to_tests.get(module, [])))
        if not tests:
            modules_without_tests.append({"module": module, "file": file_info["file"]})

    return {
        "covered_symbols": covered,
        "uncovered_symbols": uncovered,
        "modules_without_nominal_tests": modules_without_tests,
    }


def detect_dead_code_candidates(files_data: list[dict[str, Any]], coverage_nominal: dict[str, Any]) -> list[dict[str, Any]]:
    covered_keys = {f"{x['module']}:{x['symbol']}" for x in coverage_nominal["covered_symbols"]}
    candidates = []

    for file_info in files_data:
        module = file_info["module"]

        for fn in file_info.get("top_level_functions", []):
            name = fn["name"]
            if name.startswith("_"):
                continue
            if f"{module}:{name}" not in covered_keys:
                candidates.append(
                    {"type": "function", "module": module, "symbol": name, "line": fn["line"]}
                )

        for cls in file_info.get("classes", []):
            cls_name = cls["name"]
            if not cls_name.startswith("_") and f"{module}:{cls_name}" not in covered_keys:
                candidates.append(
                    {"type": "class", "module": module, "symbol": cls_name, "line": cls["line"]}
                )

            for method in cls.get("methods", []):
                name = method["name"]
                if name.startswith("_"):
                    continue
                symbol = f"{cls_name}.{name}"
                if f"{module}:{symbol}" not in covered_keys:
                    candidates.append(
                        {"type": "method", "module": module, "symbol": symbol, "line": method["line"]}
                    )

    return candidates


def build_architecture_map(files_data: list[dict[str, Any]]) -> dict[str, list[str]]:
    groups = {
        "core": [],
        "controllers": [],
        "ai": [],
        "app_modules": [],
        "ui": [],
        "root_modules": [],
        "other": [],
    }

    for file_info in files_data:
        path = file_info["file"]

        if path.startswith("core/"):
            groups["core"].append(path)
        elif path.startswith("controllers/"):
            groups["controllers"].append(path)
        elif path.startswith("ai/"):
            groups["ai"].append(path)
        elif path.startswith("app_modules/"):
            groups["app_modules"].append(path)
        elif path.startswith("ui/"):
            groups["ui"].append(path)
        elif "/" not in path:
            groups["root_modules"].append(path)
        else:
            groups["other"].append(path)

    for k in groups:
        groups[k] = sorted(groups[k])

    return groups


def build_trading_engine_map(files_data: list[dict[str, Any]], dependency_graph: dict[str, list[str]]) -> dict[str, Any]:
    interesting = []
    keywords = [
        "trading_engine",
        "dutching_controller",
        "telegram_listener",
        "betfair_client",
        "order_manager",
        "event_bus",
        "safety_layer",
        "risk_middleware",
        "wom_engine",
        "market_tracker",
        "tick_dispatcher",
        "tick_storage",
        "simulation_broker",
        "database",
        "safe_mode",
    ]

    for item in files_data:
        mod = item["module"]
        if any(k in mod for k in keywords):
            interesting.append(mod)

    nodes = sorted(set(interesting))
    edges = []

    for src in nodes:
        for dst in dependency_graph.get(src, []):
            if dst in nodes:
                edges.append({"from": src, "to": dst})

    return {"nodes": nodes, "edges": edges}


def score_complexity(file_info: dict[str, Any], dependency_graph: dict[str, list[str]]) -> int:
    metrics = file_info.get("metrics", {})
    module = file_info.get("module", "")
    deps = len(dependency_graph.get(module, []))
    public_symbols = len(file_info.get("public_symbols", []))
    methods = sum(len(c.get("methods", [])) for c in file_info.get("classes", []))
    classes = len(file_info.get("classes", []))
    functions = len(file_info.get("top_level_functions", []))
    lines = metrics.get("line_count", 0)

    return (
        lines
        + deps * 8
        + public_symbols * 4
        + methods * 5
        + classes * 12
        + functions * 3
    )


def top_risky_modules(files_data: list[dict[str, Any]], dependency_graph: dict[str, list[str]], limit: int = 30) -> list[dict[str, Any]]:
    ranked = []
    for file_info in files_data:
        ranked.append(
            {
                "file": file_info["file"],
                "module": file_info["module"],
                "score": score_complexity(file_info, dependency_graph),
                "dependency_count": len(dependency_graph.get(file_info["module"], [])),
                "line_count": file_info.get("metrics", {}).get("line_count", 0),
                "public_symbols": len(file_info.get("public_symbols", [])),
            }
        )

    ranked.sort(key=lambda x: (-x["score"], -x["dependency_count"], x["file"]))
    return ranked[:limit]


def classify_priority(score: int) -> str:
    if score >= 260:
        return "P0"
    if score >= 150:
        return "P1"
    return "P2"


def build_refactor_priority(files_data: list[dict[str, Any]], dependency_graph: dict[str, list[str]], coverage_nominal: dict[str, Any]) -> list[dict[str, Any]]:
    uncovered_by_module = defaultdict(int)
    for item in coverage_nominal["uncovered_symbols"]:
        uncovered_by_module[item["module"]] += 1

    rows = []
    for file_info in files_data:
        module = file_info["module"]
        base_score = score_complexity(file_info, dependency_graph)
        uncovered = uncovered_by_module[module]
        final_score = base_score + uncovered * 10

        rows.append(
            {
                "priority": classify_priority(final_score),
                "module": module,
                "file": file_info["file"],
                "score": final_score,
                "base_score": base_score,
                "uncovered_public_symbols": uncovered,
                "dependency_count": len(dependency_graph.get(module, [])),
                "line_count": file_info.get("metrics", {}).get("line_count", 0),
            }
        )

    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    rows.sort(key=lambda x: (priority_order[x["priority"]], -x["score"], x["file"]))
    return rows


def build_fix_priorities(files_data: list[dict[str, Any]], coverage_nominal: dict[str, Any], dead_code: list[dict[str, Any]], cycles: list[list[str]]) -> list[dict[str, Any]]:
    uncovered_by_module = defaultdict(list)
    for item in coverage_nominal["uncovered_symbols"]:
        uncovered_by_module[item["module"]].append(item["symbol"])

    dead_by_module = defaultdict(list)
    for item in dead_code:
        dead_by_module[item["module"]].append(item["symbol"])

    cycle_modules = set()
    for cycle in cycles:
        for m in cycle:
            cycle_modules.add(m)

    out = []

    for file_info in files_data:
        module = file_info["module"]
        reasons = []

        uncovered = uncovered_by_module.get(module, [])
        dead = dead_by_module.get(module, [])

        if module in cycle_modules:
            reasons.append("circular_import")
        if len(uncovered) >= 8:
            reasons.append("many_uncovered_public_symbols")
        if len(dead) >= 6:
            reasons.append("many_dead_code_candidates")
        if file_info.get("metrics", {}).get("line_count", 0) >= 500:
            reasons.append("large_file")

        if not reasons:
            continue

        severity_score = (
            (40 if module in cycle_modules else 0)
            + len(uncovered) * 3
            + len(dead) * 2
            + min(file_info.get("metrics", {}).get("line_count", 0) // 100, 10)
        )

        out.append(
            {
                "priority": "P0" if severity_score >= 70 else "P1" if severity_score >= 35 else "P2",
                "module": module,
                "file": file_info["file"],
                "severity_score": severity_score,
                "reasons": reasons,
                "uncovered_public_symbols_sample": uncovered[:10],
                "dead_code_sample": dead[:10],
            }
        )

    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    out.sort(key=lambda x: (priority_order[x["priority"]], -x["severity_score"], x["file"]))
    return out


def current_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    files = {}
    for item in data["files"]:
        files[item["file"]] = {
            "module": item["module"],
            "hash": item["content_hash"],
            "line_count": item.get("metrics", {}).get("line_count", 0),
            "public_symbols": item.get("public_symbols", []),
        }

    return {
        "summary": data["summary"],
        "files": files,
        "top_risky_modules": data["top_risky_modules"],
        "circular_imports": data["circular_imports"],
    }


def diff_snapshots(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    if not previous:
        return {
            "has_previous_snapshot": False,
            "added_files": [],
            "removed_files": [],
            "changed_files": [],
            "summary_diff": {},
        }

    prev_files = previous.get("files", {})
    cur_files = current.get("files", {})

    prev_keys = set(prev_files.keys())
    cur_keys = set(cur_files.keys())

    added = sorted(cur_keys - prev_keys)
    removed = sorted(prev_keys - cur_keys)

    changed = []
    for key in sorted(prev_keys & cur_keys):
        if prev_files[key].get("hash") != cur_files[key].get("hash"):
            changed.append(
                {
                    "file": key,
                    "old_hash": prev_files[key].get("hash"),
                    "new_hash": cur_files[key].get("hash"),
                    "old_lines": prev_files[key].get("line_count"),
                    "new_lines": cur_files[key].get("line_count"),
                }
            )

    prev_summary = previous.get("summary", {})
    cur_summary = current.get("summary", {})
    summary_diff = {}

    all_summary_keys = set(prev_summary.keys()) | set(cur_summary.keys())
    for key in sorted(all_summary_keys):
        if prev_summary.get(key) != cur_summary.get(key):
            summary_diff[key] = {
                "old": prev_summary.get(key),
                "new": cur_summary.get(key),
            }

    return {
        "has_previous_snapshot": True,
        "added_files": added,
        "removed_files": removed,
        "changed_files": changed,
        "summary_diff": summary_diff,
    }


def summary(files_data: list[dict[str, Any]], test_files: list[dict[str, Any]], graph: dict[str, list[str]], cycles: list[list[str]], dead_code: list[dict[str, Any]]) -> dict[str, Any]:
    class_count = 0
    method_count = 0
    function_count = 0
    public_symbol_count = 0

    for item in files_data:
        function_count += len(item.get("top_level_functions", []))
        public_symbol_count += len(item.get("public_symbols", []))
        for cls in item.get("classes", []):
            class_count += 1
            method_count += len(cls.get("methods", []))

    return {
        "python_files": len(files_data),
        "test_files": len(test_files),
        "classes": class_count,
        "methods": method_count,
        "top_level_functions": function_count,
        "public_symbols": public_symbol_count,
        "dependency_edges": sum(len(v) for v in graph.values()),
        "cycle_count": len(cycles),
        "dead_code_candidates": len(dead_code),
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown(path: Path, data: dict[str, Any]) -> None:
    lines = []
    lines.append("# Repository API Report V4")
    lines.append("")
    lines.append("## Summary")
    lines.append("")

    for key, value in data["summary"].items():
        lines.append(f"- {key}: **{value}**")

    lines.append("")
    lines.append("## Refactor Priority Ranking")
    lines.append("")
    for item in data["refactor_priority"][:30]:
        lines.append(
            f"- **{item['priority']}** `{item['module']}` "
            f"(score={item['score']}, uncovered={item['uncovered_public_symbols']}, deps={item['dependency_count']})"
        )

    lines.append("")
    lines.append("## Fix Priority Suggestions")
    lines.append("")
    for item in data["fix_priorities"][:30]:
        lines.append(
            f"- **{item['priority']}** `{item['module']}` "
            f"(severity={item['severity_score']}, reasons={', '.join(item['reasons'])})"
        )

    lines.append("")
    lines.append("## Top Risk Modules")
    lines.append("")
    for item in data["top_risky_modules"][:20]:
        lines.append(
            f"- `{item['module']}` — score={item['score']}, deps={item['dependency_count']}, "
            f"lines={item['line_count']}, public_symbols={item['public_symbols']}"
        )

    lines.append("")
    lines.append("## Snapshot Diff")
    lines.append("")
    diff = data["snapshot_diff"]
    if not diff["has_previous_snapshot"]:
        lines.append("- No previous snapshot found.")
    else:
        lines.append(f"- Added files: **{len(diff['added_files'])}**")
        lines.append(f"- Removed files: **{len(diff['removed_files'])}**")
        lines.append(f"- Changed files: **{len(diff['changed_files'])}**")
        if diff["summary_diff"]:
            lines.append("")
            lines.append("### Summary Changes")
            for key, val in diff["summary_diff"].items():
                lines.append(f"- `{key}`: `{val['old']}` -> `{val['new']}`")

    lines.append("")
    lines.append("## Circular Imports")
    lines.append("")
    if data["circular_imports"]:
        for cycle in data["circular_imports"]:
            lines.append(f"- `{' -> '.join(cycle)}`")
    else:
        lines.append("- None detected")

    lines.append("")
    lines.append("## Modules Without Nominal Tests")
    lines.append("")
    for item in data["coverage_nominal"]["modules_without_nominal_tests"][:50]:
        lines.append(f"- `{item['module']}` (`{item['file']}`)")

    lines.append("")
    lines.append("## Public Symbols Without Nominal Tests")
    lines.append("")
    for item in data["coverage_nominal"]["uncovered_symbols"][:100]:
        lines.append(f"- `{item['module']}` :: `{item['symbol']}`")

    lines.append("")
    lines.append("## Dead Code Candidates")
    lines.append("")
    for item in data["dead_code_candidates"][:100]:
        lines.append(f"- `{item['module']}` :: `{item['symbol']}` ({item['type']})")

    lines.append("")
    lines.append("## Trading Engine Map")
    lines.append("")
    lines.append("### Nodes")
    for node in data["trading_engine_map"]["nodes"]:
        lines.append(f"- `{node}`")
    lines.append("")
    lines.append("### Edges")
    for edge in data["trading_engine_map"]["edges"]:
        lines.append(f"- `{edge['from']}` -> `{edge['to']}`")

    path.write_text("\n".join(lines), encoding="utf-8")


def write_fix_priority_report(path: Path, data: dict[str, Any]) -> None:
    lines = []
    lines.append("# Repository Fix Priority Report V4")
    lines.append("")
    lines.append("## P0 / P1 / P2")
    lines.append("")

    for item in data["fix_priorities"]:
        lines.append(
            f"- **{item['priority']}** `{item['module']}` "
            f"(severity={item['severity_score']})"
        )
        lines.append(f"  - file: `{item['file']}`")
        lines.append(f"  - reasons: `{', '.join(item['reasons'])}`")
        if item["uncovered_public_symbols_sample"]:
            lines.append(
                f"  - uncovered sample: `{', '.join(item['uncovered_public_symbols_sample'][:5])}`"
            )
        if item["dead_code_sample"]:
            lines.append(
                f"  - dead code sample: `{', '.join(item['dead_code_sample'][:5])}`"
            )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    files_data = []
    for path in sorted(iter_python_files(ROOT)):
        if normalize_path(path).startswith("tests/"):
            continue
        files_data.append(analyze_file(path))

    test_files = load_test_files()
    dependency_graph = build_internal_dependency_graph(files_data)
    cycles = find_cycles(dependency_graph)
    coverage_nominal = estimate_test_coverage_nominal(files_data, test_files)
    dead_code = detect_dead_code_candidates(files_data, coverage_nominal)
    architecture_map = build_architecture_map(files_data)
    trading_engine_map = build_trading_engine_map(files_data, dependency_graph)
    risky = top_risky_modules(files_data, dependency_graph)
    refactor_priority = build_refactor_priority(files_data, dependency_graph, coverage_nominal)
    fix_priorities = build_fix_priorities(files_data, coverage_nominal, dead_code, cycles)

    data = {
        "summary": summary(files_data, test_files, dependency_graph, cycles, dead_code),
        "files": files_data,
        "test_files": test_files,
        "dependency_graph": dependency_graph,
        "circular_imports": cycles,
        "coverage_nominal": coverage_nominal,
        "dead_code_candidates": dead_code,
        "architecture_map": architecture_map,
        "trading_engine_map": trading_engine_map,
        "top_risky_modules": risky,
        "refactor_priority": refactor_priority,
        "fix_priorities": fix_priorities,
    }

    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    current = current_snapshot(data)
    snapshot_path = ARTIFACTS / "repo_api_report_v4_snapshot.json"
    previous = None
    if snapshot_path.exists():
        try:
            previous = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except Exception:
            previous = None

    data["snapshot_diff"] = diff_snapshots(previous, current)

    write_json(ARTIFACTS / "repo_api_report_v4.json", data)
    write_markdown(ARTIFACTS / "repo_api_report_v4.md", data)
    write_fix_priority_report(ARTIFACTS / "repo_fix_priority_report.md", data)
    write_json(snapshot_path, current)

    print("======================================================================")
    print("REPOSITORY API REPORT V4")
    print("======================================================================")
    for key, value in data["summary"].items():
        print(f"{key}: {value}")
    print()
    print("[OK] artifacts/repo_api_report_v4.json")
    print("[OK] artifacts/repo_api_report_v4.md")
    print("[OK] artifacts/repo_fix_priority_report.md")
    print("[OK] artifacts/repo_api_report_v4_snapshot.json")


if __name__ == "__main__":
    main()