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

LOW_PRIORITY_MODULES = {
    "__init__",
    "build",
    "theme",
    "trading_config",
}

LOW_PRIORITY_FILES = {
    "build.py",
    "theme.py",
    "trading_config.py",
}


def should_skip(path: Path) -> bool:
    return any(part in IGNORE_DIRS for part in path.parts)


def iter_python_files():
    for p in ROOT.rglob("*.py"):
        if should_skip(p):
            continue
        yield p


def normalize_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def module_name(path: Path) -> str:
    rel = normalize_path(path)
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
            for alias in node.names:
                imports.append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    return imports


def get_functions(tree: ast.Module):
    funcs = []

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            funcs.append(
                {
                    "name": node.name,
                    "line": getattr(node, "lineno", None),
                }
            )

    return funcs


def get_classes(tree: ast.Module):
    classes = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = []

            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.append(
                        {
                            "name": item.name,
                            "line": getattr(item, "lineno", None),
                        }
                    )

            classes.append(
                {
                    "name": node.name,
                    "line": getattr(node, "lineno", None),
                    "methods": methods,
                }
            )

    return classes


def get_call_names(tree: ast.AST):
    names = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func

            if isinstance(func, ast.Name):
                names.add(func.id)

            elif isinstance(func, ast.Attribute):
                names.add(func.attr)

    return sorted(names)


def get_string_literals(tree: ast.AST):
    out = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            if value:
                out.add(value)

    return sorted(out)


def build_public_symbols(file_info):
    public = []

    for fn in file_info["functions"]:
        if not fn["name"].startswith("_"):
            public.append(fn["name"])

    for cls in file_info["classes"]:
        if not cls["name"].startswith("_"):
            public.append(cls["name"])

        for method in cls["methods"]:
            if not method["name"].startswith("_"):
                public.append(f"{cls['name']}.{method['name']}")

    return sorted(public)


def analyze_repo():
    files = []
    dep_graph = defaultdict(set)

    for path in iter_python_files():
        if "tests" in normalize_path(path):
            continue

        text, tree = parse_file(path)

        mod = module_name(path)
        imports = get_imports(tree)
        functions = get_functions(tree)
        classes = get_classes(tree)
        calls = get_call_names(tree)

        for imp in imports:
            dep_graph[mod].add(imp)

        file_info = {
            "file": normalize_path(path),
            "module": mod,
            "functions": functions,
            "classes": classes,
            "imports": imports,
            "calls": calls,
            "lines": len(text.splitlines()),
        }
        file_info["public_symbols"] = build_public_symbols(file_info)

        files.append(file_info)

    return files, dep_graph


def load_tests():
    tests = []

    if not TEST_DIR.exists():
        return tests

    for path in TEST_DIR.rglob("test_*.py"):
        text, tree = parse_file(path)

        imports = get_imports(tree)
        calls = get_call_names(tree)
        strings = get_string_literals(tree)

        test_names = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                test_names.append(node.name)

        tests.append(
            {
                "file": normalize_path(path),
                "module": module_name(path),
                "imports": imports,
                "calls": calls,
                "strings": strings,
                "test_names": test_names,
                "text_lower": text.lower(),
            }
        )

    return tests


def looks_like_direct_test_match(file_info, test_file):
    module_short = file_info["module"].split(".")[-1].lower()
    file_short = Path(file_info["file"]).stem.lower()
    test_path = test_file["file"].lower()

    if module_short in LOW_PRIORITY_MODULES:
        return True

    if file_short in LOW_PRIORITY_MODULES:
        return True

    patterns = {
        module_short,
        file_short,
    }

    return any(p and p in test_path for p in patterns)


def symbol_has_nominal_test(file_info, symbol, tests):
    module_name_full = file_info["module"].lower()
    module_short = file_info["module"].split(".")[-1].lower()
    symbol_simple = symbol.split(".")[-1].lower()
    symbol_full = symbol.lower()

    for test in tests:
        imports_blob = " ".join(test["imports"]).lower()
        calls_blob = " ".join(test["calls"]).lower()
        names_blob = " ".join(test["test_names"]).lower()
        strings_blob = " ".join(test["strings"]).lower()
        text_blob = test["text_lower"]

        if module_name_full in imports_blob or module_short in test["file"].lower():
            if (
                symbol_simple in calls_blob
                or symbol_simple in names_blob
                or symbol_simple in strings_blob
                or symbol_simple in text_blob
                or symbol_full in text_blob
            ):
                return True

        if symbol_simple in names_blob and module_short in test["file"].lower():
            return True

    return False


def find_modules_without_direct_tests(files, tests):
    missing = []

    for file_info in files:
        file_name = Path(file_info["file"]).name
        module_short = file_info["module"].split(".")[-1]

        if file_name in LOW_PRIORITY_FILES or module_short in LOW_PRIORITY_MODULES:
            continue

        if file_name == "__init__.py":
            continue

        found = False
        for test in tests:
            if looks_like_direct_test_match(file_info, test):
                found = True
                break

        if not found:
            missing.append(
                {
                    "module": file_info["module"],
                    "file": file_info["file"],
                }
            )

    return missing


def find_uncovered_public_symbols(files, tests):
    uncovered = []

    for file_info in files:
        file_name = Path(file_info["file"]).name
        module_short = file_info["module"].split(".")[-1]

        if file_name in LOW_PRIORITY_FILES or module_short in LOW_PRIORITY_MODULES:
            continue

        for symbol in file_info["public_symbols"]:
            if not symbol_has_nominal_test(file_info, symbol, tests):
                uncovered.append(
                    {
                        "module": file_info["module"],
                        "file": file_info["file"],
                        "symbol": symbol,
                    }
                )

    return uncovered


def build_internal_usage_index(files):
    used_names = defaultdict(set)

    for file_info in files:
        src = file_info["module"]
        for name in file_info["calls"]:
            used_names[name].add(src)

    return used_names


def find_dead_code_candidates(files, uncovered_symbols):
    uncovered_set = {
        (item["module"], item["symbol"])
        for item in uncovered_symbols
    }

    used_names = build_internal_usage_index(files)

    dead = []

    for file_info in files:
        file_name = Path(file_info["file"]).name
        module_short = file_info["module"].split(".")[-1]

        if file_name in LOW_PRIORITY_FILES or module_short in LOW_PRIORITY_MODULES:
            continue

        for fn in file_info["functions"]:
            name = fn["name"]

            if name.startswith("_"):
                continue

            if (file_info["module"], name) not in uncovered_set:
                continue

            internal_users = used_names.get(name, set())

            if internal_users:
                continue

            dead.append(
                {
                    "module": file_info["module"],
                    "file": file_info["file"],
                    "symbol": name,
                    "line": fn["line"],
                }
            )

    return dead


def find_risky_modules(files, uncovered_symbols, missing_modules):
    uncovered_count = defaultdict(int)
    for item in uncovered_symbols:
        uncovered_count[item["module"]] += 1

    missing_modules_set = {item["module"] for item in missing_modules}

    ranked = []

    for f in files:
        file_name = Path(f["file"]).name
        module_short = f["module"].split(".")[-1]

        if file_name in LOW_PRIORITY_FILES or module_short in LOW_PRIORITY_MODULES:
            continue

        score = (
            f["lines"]
            + len(f["imports"]) * 5
            + len(f["classes"]) * 10
            + len(f["functions"]) * 2
            + uncovered_count[f["module"]] * 8
            + (25 if f["module"] in missing_modules_set else 0)
        )

        ranked.append(
            {
                "score": score,
                "file": f["file"],
                "module": f["module"],
                "uncovered_public_symbols": uncovered_count[f["module"]],
                "has_direct_test_file": f["module"] not in missing_modules_set,
            }
        )

    ranked.sort(key=lambda x: (-x["score"], x["file"]))

    return ranked[:25]


def main():
    print("Scanning repository...")

    files, deps = analyze_repo()
    tests = load_tests()

    missing_direct_tests = find_modules_without_direct_tests(files, tests)
    uncovered_public_symbols = find_uncovered_public_symbols(files, tests)
    dead_code_candidates = find_dead_code_candidates(files, uncovered_public_symbols)
    top_risky_modules = find_risky_modules(
        files,
        uncovered_public_symbols,
        missing_direct_tests,
    )

    report = {
        "summary": {
            "files": len(files),
            "tests": len(tests),
            "modules_without_direct_tests": len(missing_direct_tests),
            "uncovered_public_symbols": len(uncovered_public_symbols),
            "dead_code_candidates": len(dead_code_candidates),
        },
        "files": files,
        "dependency_graph": {k: sorted(list(v)) for k, v in deps.items()},
        "top_risky_modules": top_risky_modules,
        "modules_without_direct_tests": missing_direct_tests,
        "uncovered_public_symbols": uncovered_public_symbols,
        "dead_code_candidates": dead_code_candidates,
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