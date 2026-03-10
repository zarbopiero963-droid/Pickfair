import ast
import csv
import json
import os
import traceback
from collections import defaultdict
from pathlib import Path

ROOT = Path(".").resolve()
OUT_DIR = ROOT / "autopsy"
OUT_DIR.mkdir(exist_ok=True)

IGNORE_DIRS = {
    ".git",
    ".github",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "build",
    "dist",
}

PYTHON_FILES = []


def is_ignored(path: Path) -> bool:
    return any(part in IGNORE_DIRS for part in path.parts)


def discover_python_files() -> list[Path]:
    files = []
    for p in ROOT.rglob("*.py"):
        rel = p.relative_to(ROOT)
        if is_ignored(rel):
            continue
        files.append(p)
    return sorted(files)


def safe_unparse(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "<unparse_error>"


class FileAutopsy(ast.NodeVisitor):
    def __init__(self, relpath: str):
        self.relpath = relpath
        self.imports = []
        self.from_imports = []
        self.functions = []
        self.classes = []
        self.calls = []
        self.assignments = []
        self.errors = []
        self.current_class = None
        self.current_function = None

    def _current_scope(self) -> str:
        if self.current_class and self.current_function:
            return f"{self.current_class}.{self.current_function}"
        if self.current_class:
            return self.current_class
        if self.current_function:
            return self.current_function
        return "<module>"

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(
                {
                    "module": alias.name,
                    "asname": alias.asname,
                    "lineno": node.lineno,
                }
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        mod = node.module or ""
        for alias in node.names:
            self.from_imports.append(
                {
                    "module": mod,
                    "name": alias.name,
                    "asname": alias.asname,
                    "level": node.level,
                    "lineno": node.lineno,
                }
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        prev_class = self.current_class
        self.current_class = node.name
        self.classes.append(
            {
                "name": node.name,
                "lineno": node.lineno,
                "end_lineno": getattr(node, "end_lineno", node.lineno),
                "bases": [safe_unparse(b) for b in node.bases],
            }
        )
        self.generic_visit(node)
        self.current_class = prev_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        prev_function = self.current_function
        self.current_function = node.name
        self.functions.append(
            {
                "name": node.name,
                "qualname": self._current_scope(),
                "lineno": node.lineno,
                "end_lineno": getattr(node, "end_lineno", node.lineno),
                "args": [a.arg for a in node.args.args],
                "kwonlyargs": [a.arg for a in node.args.kwonlyargs],
                "vararg": node.args.vararg.arg if node.args.vararg else None,
                "kwarg": node.args.kwarg.arg if node.args.kwarg else None,
            }
        )
        self.generic_visit(node)
        self.current_function = prev_function

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        prev_function = self.current_function
        self.current_function = node.name
        self.functions.append(
            {
                "name": node.name,
                "qualname": self._current_scope(),
                "lineno": node.lineno,
                "end_lineno": getattr(node, "end_lineno", node.lineno),
                "args": [a.arg for a in node.args.args],
                "kwonlyargs": [a.arg for a in node.args.kwonlyargs],
                "vararg": node.args.vararg.arg if node.args.vararg else None,
                "kwarg": node.args.kwarg.arg if node.args.kwarg else None,
                "async": True,
            }
        )
        self.generic_visit(node)
        self.current_function = prev_function

    def visit_Assign(self, node: ast.Assign):
        try:
            targets = [safe_unparse(t) for t in node.targets]
            value = safe_unparse(node.value)
            self.assignments.append(
                {
                    "scope": self._current_scope(),
                    "targets": targets,
                    "value": value,
                    "lineno": node.lineno,
                }
            )
        except Exception as e:
            self.errors.append(f"Assign parse error line {node.lineno}: {e}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        try:
            func_name = safe_unparse(node.func)
            self.calls.append(
                {
                    "scope": self._current_scope(),
                    "call": func_name,
                    "lineno": node.lineno,
                    "args_count": len(node.args),
                    "kwargs_count": len(node.keywords),
                }
            )
        except Exception as e:
            self.errors.append(f"Call parse error line {node.lineno}: {e}")
        self.generic_visit(node)


def parse_file(path: Path) -> dict:
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    result = {
        "file": rel,
        "ok": True,
        "syntax_error": None,
        "traceback": None,
        "imports": [],
        "from_imports": [],
        "classes": [],
        "functions": [],
        "calls": [],
        "assignments": [],
        "errors": [],
        "lines": 0,
    }

    try:
        text = path.read_text(encoding="utf-8")
        result["lines"] = len(text.splitlines())
        tree = ast.parse(text, filename=rel)
        visitor = FileAutopsy(rel)
        visitor.visit(tree)

        result["imports"] = visitor.imports
        result["from_imports"] = visitor.from_imports
        result["classes"] = visitor.classes
        result["functions"] = visitor.functions
        result["calls"] = visitor.calls
        result["assignments"] = visitor.assignments
        result["errors"] = visitor.errors

    except SyntaxError as e:
        result["ok"] = False
        result["syntax_error"] = {
            "msg": e.msg,
            "lineno": e.lineno,
            "offset": e.offset,
            "text": e.text,
        }
    except Exception:
        result["ok"] = False
        result["traceback"] = traceback.format_exc()

    return result


def build_import_edges(file_results: list[dict]) -> list[dict]:
    edges = []
    for fr in file_results:
        src = fr["file"]
        for imp in fr["imports"]:
            edges.append(
                {
                    "src_file": src,
                    "edge_type": "import",
                    "target": imp["module"],
                    "lineno": imp["lineno"],
                }
            )
        for imp in fr["from_imports"]:
            prefix = "." * int(imp.get("level", 0) or 0)
            mod = f"{prefix}{imp['module']}" if imp["module"] else prefix
            target = f"{mod}:{imp['name']}"
            edges.append(
                {
                    "src_file": src,
                    "edge_type": "from_import",
                    "target": target,
                    "lineno": imp["lineno"],
                }
            )
    return edges


def build_call_edges(file_results: list[dict]) -> list[dict]:
    edges = []
    for fr in file_results:
        src = fr["file"]
        for c in fr["calls"]:
            edges.append(
                {
                    "src_file": src,
                    "scope": c["scope"],
                    "edge_type": "call",
                    "target": c["call"],
                    "lineno": c["lineno"],
                    "args_count": c["args_count"],
                    "kwargs_count": c["kwargs_count"],
                }
            )
    return edges


def write_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_dot_graph(path: Path, edges: list[dict], graph_name: str):
    lines = [f'digraph "{graph_name}" {{', "  rankdir=LR;", '  node [shape=box];']
    for edge in edges:
        src = str(edge.get("src_file", "")).replace('"', '\\"')
        dst = str(edge.get("target", "")).replace('"', '\\"')
        label = str(edge.get("edge_type", "")).replace('"', '\\"')
        lines.append(f'  "{src}" -> "{dst}" [label="{label}"];')
    lines.append("}")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    print("=== REPO AUTOPSY START ===")

    py_files = discover_python_files()
    print(f"Python files trovati: {len(py_files)}")

    file_results = []
    syntax_failures = []

    for path in py_files:
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        print(f"\n[SCAN] {rel}")
        result = parse_file(path)
        file_results.append(result)

        if result["ok"]:
            print(
                f"✅ OK | lines={result['lines']} "
                f"imports={len(result['imports']) + len(result['from_imports'])} "
                f"classes={len(result['classes'])} "
                f"functions={len(result['functions'])} "
                f"calls={len(result['calls'])}"
            )
        else:
            print(f"❌ FAIL | {rel}")
            if result["syntax_error"]:
                se = result["syntax_error"]
                print(
                    f"   SyntaxError line {se['lineno']} col {se['offset']}: {se['msg']}"
                )
                if se.get("text"):
                    print(f"   >>> {se['text'].rstrip()}")
            if result["traceback"]:
                print(result["traceback"])
            syntax_failures.append(rel)

    import_edges = build_import_edges(file_results)
    call_edges = build_call_edges(file_results)

    summary = {
        "repo_root": str(ROOT),
        "python_files_total": len(py_files),
        "files_ok": sum(1 for r in file_results if r["ok"]),
        "files_failed": sum(1 for r in file_results if not r["ok"]),
        "syntax_failures": syntax_failures,
        "total_import_edges": len(import_edges),
        "total_call_edges": len(call_edges),
        "generated_files": [
            "autopsy/file_autopsy.json",
            "autopsy/autopsy_summary.json",
            "autopsy/import_edges.csv",
            "autopsy/call_edges.csv",
            "autopsy/import_graph.dot",
            "autopsy/call_graph.dot",
        ],
    }

    write_json(OUT_DIR / "file_autopsy.json", file_results)
    write_json(OUT_DIR / "autopsy_summary.json", summary)
    write_csv(OUT_DIR / "import_edges.csv", import_edges)
    write_csv(OUT_DIR / "call_edges.csv", call_edges)
    write_dot_graph(OUT_DIR / "import_graph.dot", import_edges, "import_graph")
    write_dot_graph(OUT_DIR / "call_graph.dot", call_edges, "call_graph")

    # Tentativo PNG se graphviz è disponibile
    try:
        os.system(f'dot -Tpng "{OUT_DIR / "import_graph.dot"}" -o "{OUT_DIR / "import_graph.png"}"')
        os.system(f'dot -Tpng "{OUT_DIR / "call_graph.dot"}" -o "{OUT_DIR / "call_graph.png"}"')
        summary["generated_files"].extend(
            [
                "autopsy/import_graph.png",
                "autopsy/call_graph.png",
            ]
        )
        write_json(OUT_DIR / "autopsy_summary.json", summary)
    except Exception:
        pass

    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if syntax_failures:
        print("\n🚨 AUTOPSY FAIL: ci sono file con SyntaxError o parse error grave.")
        for item in syntax_failures:
            print(f"❌ {item}")
        return 1

    print("\n✅ AUTOPSY OK: tutti i file Python sono stati analizzati correttamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())