import ast
import json
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(".").resolve()

EXCLUDED_PARTS = {
    ".git",
    ".github",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "build",
    "dist",
}

REPORT_FILE = Path("repo_autopsy_report.json")
FILE_GRAPH_DOT = Path("repo_file_graph.dot")
CALL_GRAPH_DOT = Path("repo_call_graph.dot")
FILE_GRAPH_SVG = Path("repo_file_graph.svg")
CALL_GRAPH_SVG = Path("repo_call_graph.svg")


def is_python_repo_file(path: Path) -> bool:
    if path.suffix != ".py":
        return False
    parts = set(path.parts)
    return not bool(parts & EXCLUDED_PARTS)


def safe_rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


class FileAnalyzer(ast.NodeVisitor):
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.imports = []
        self.functions = []
        self.classes = []
        self.calls = []
        self.current_function = None
        self.current_class = None

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append({
                "file": self.file_path,
                "type": "import",
                "module": alias.name,
                "alias": alias.asname,
                "line": node.lineno,
            })
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        self.imports.append({
            "file": self.file_path,
            "type": "from_import",
            "module": node.module,
            "names": [a.name for a in node.names],
            "line": node.lineno,
        })
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        prev_class = self.current_class
        self.current_class = node.name

        self.classes.append({
            "file": self.file_path,
            "class": node.name,
            "line": node.lineno,
        })

        self.generic_visit(node)
        self.current_class = prev_class

    def visit_FunctionDef(self, node):
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node):
        self._handle_function(node)

    def _handle_function(self, node):
        prev_func = self.current_function

        qualname = node.name
        if self.current_class:
            qualname = f"{self.current_class}.{node.name}"

        self.current_function = qualname

        self.functions.append({
            "file": self.file_path,
            "function": node.name,
            "qualname": qualname,
            "class": self.current_class,
            "line": node.lineno,
            "args": [a.arg for a in node.args.args],
            "is_async": isinstance(node, ast.AsyncFunctionDef),
        })

        self.generic_visit(node)
        self.current_function = prev_func

    def visit_Call(self, node):
        called_name = self._extract_call_name(node.func)
        if called_name:
            self.calls.append({
                "file": self.file_path,
                "caller": self.current_function,
                "called": called_name,
                "line": node.lineno,
            })
        self.generic_visit(node)

    def _extract_call_name(self, node):
        if isinstance(node, ast.Name):
            return node.id

        if isinstance(node, ast.Attribute):
            chain = []
            cur = node
            while isinstance(cur, ast.Attribute):
                chain.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                chain.append(cur.id)
            chain.reverse()
            return ".".join(chain)

        return None


def parse_python_file(path: Path):
    try:
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content)
    except Exception as e:
        return {
            "file": safe_rel(path),
            "error": str(e),
            "imports": [],
            "functions": [],
            "classes": [],
            "calls": [],
        }

    analyzer = FileAnalyzer(safe_rel(path))
    analyzer.visit(tree)

    return {
        "file": safe_rel(path),
        "imports": analyzer.imports,
        "functions": analyzer.functions,
        "classes": analyzer.classes,
        "calls": analyzer.calls,
    }


def build_file_dependency_edges(parsed_files):
    local_modules = {}
    for item in parsed_files:
        file_path = item["file"]
        module_name = file_path[:-3].replace("/", ".")
        local_modules[module_name] = file_path

    edges = set()

    for item in parsed_files:
        src = item["file"]
        for imp in item["imports"]:
            module = imp.get("module")
            if not module:
                continue

            for local_module, local_file in local_modules.items():
                if module == local_module or module.startswith(local_module + "."):
                    if src != local_file:
                        edges.add((src, local_file))

    return sorted(edges)


def build_function_index(parsed_files):
    index = {}
    simple_index = defaultdict(list)

    for item in parsed_files:
        for fn in item["functions"]:
            key = f"{item['file']}::{fn['qualname']}"
            index[key] = fn
            simple_index[fn["function"]].append({
                "file": item["file"],
                "qualname": fn["qualname"],
            })

    return index, simple_index


def build_call_edges(parsed_files):
    _, simple_index = build_function_index(parsed_files)
    call_edges = []

    for item in parsed_files:
        file_path = item["file"]
        {
            fn["qualname"]: fn for fn in item["functions"]
        }

        for call in item["calls"]:
            caller = call.get("caller")
            called = call.get("called")

            if not caller or not called:
                continue

            candidates = simple_index.get(called.split(".")[-1], [])
            call_edges.append({
                "file": file_path,
                "caller": caller,
                "called": called,
                "line": call["line"],
                "resolved_candidates": candidates,
            })

    return call_edges


def write_file_graph_dot(edges):
    lines = [
        "digraph RepoFileGraph {",
        '  rankdir=LR;',
        '  graph [fontsize=10];',
        '  node [shape=box, style="rounded,filled", fillcolor="#eaf2ff", color="#4a6fa5", fontname="Arial"];',
        '  edge [color="#6c757d"];',
    ]

    all_nodes = set()
    for src, dst in edges:
        all_nodes.add(src)
        all_nodes.add(dst)

    for node in sorted(all_nodes):
        lines.append(f'  "{node}";')

    for src, dst in edges:
        lines.append(f'  "{src}" -> "{dst}";')

    lines.append("}")
    FILE_GRAPH_DOT.write_text("\n".join(lines), encoding="utf-8")


def write_call_graph_dot(parsed_files, call_edges):
    lines = [
        "digraph RepoCallGraph {",
        '  rankdir=LR;',
        '  graph [fontsize=10];',
        '  node [shape=ellipse, style="filled", fillcolor="#eefbea", color="#4f8a4c", fontname="Arial"];',
        '  edge [color="#7a7a7a"];',
    ]

    function_nodes = set()
    for item in parsed_files:
        for fn in item["functions"]:
            node_name = f"{item['file']}::{fn['qualname']}"
            function_nodes.add(node_name)

    for node in sorted(function_nodes):
        lines.append(f'  "{node}";')

    for call in call_edges:
        caller_file = call["file"]
        caller_name = call["caller"]
        caller_node = f"{caller_file}::{caller_name}"

        candidates = call.get("resolved_candidates") or []
        for cand in candidates:
            callee_node = f"{cand['file']}::{cand['qualname']}"
            lines.append(f'  "{caller_node}" -> "{callee_node}";')

    lines.append("}")
    CALL_GRAPH_DOT.write_text("\n".join(lines), encoding="utf-8")


def render_svg(dot_path: Path, svg_path: Path):
    try:
        subprocess.run(
            ["dot", "-Tsvg", str(dot_path), "-o", str(svg_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"✅ SVG generato: {svg_path}")
    except FileNotFoundError:
        print(f"⚠️ Graphviz 'dot' non trovato. Saltato render SVG per {dot_path.name}")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Errore render SVG {dot_path.name}: {e.stderr}")


def main():
    python_files = sorted(
        [p for p in ROOT.rglob("*.py") if is_python_repo_file(p)]
    )

    parsed_files = [parse_python_file(p) for p in python_files]

    file_edges = build_file_dependency_edges(parsed_files)
    call_edges = build_call_edges(parsed_files)

    report = {
        "summary": {
            "python_files": len(parsed_files),
            "functions": sum(len(x["functions"]) for x in parsed_files),
            "classes": sum(len(x["classes"]) for x in parsed_files),
            "imports": sum(len(x["imports"]) for x in parsed_files),
            "calls": sum(len(x["calls"]) for x in parsed_files),
            "file_dependency_edges": len(file_edges),
            "call_edges": len(call_edges),
        },
        "files": parsed_files,
        "file_dependency_edges": [
            {"from": src, "to": dst} for src, dst in file_edges
        ],
        "call_edges": call_edges,
    }

    REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"✅ Report JSON generato: {REPORT_FILE}")

    write_file_graph_dot(file_edges)
    print(f"✅ DOT file graph generato: {FILE_GRAPH_DOT}")

    write_call_graph_dot(parsed_files, call_edges)
    print(f"✅ DOT call graph generato: {CALL_GRAPH_DOT}")

    render_svg(FILE_GRAPH_DOT, FILE_GRAPH_SVG)
    render_svg(CALL_GRAPH_DOT, CALL_GRAPH_SVG)

    print("")
    print("===== REPO AUTOPSY SUMMARY =====")
    print(f"Python files: {report['summary']['python_files']}")
    print(f"Functions: {report['summary']['functions']}")
    print(f"Classes: {report['summary']['classes']}")
    print(f"Imports: {report['summary']['imports']}")
    print(f"Calls: {report['summary']['calls']}")
    print(f"File dependency edges: {report['summary']['file_dependency_edges']}")
    print(f"Call edges: {report['summary']['call_edges']}")
    print("===== END =====")


if __name__ == "__main__":
    main()