#!/usr/bin/env python3

import ast
import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"

EXCLUDED_PREFIXES = (
    ".git/",
    ".venv/",
    "venv/",
    "__pycache__/",
    "audit_out/",
    "audit_raw/",
)


def should_skip(path: Path) -> bool:
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    return any(rel.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def iter_python_files():
    for path in ROOT.rglob("*.py"):
        if not path.is_file():
            continue
        if should_skip(path):
            continue
        yield path


def runtime_module_paths() -> list[str]:
    result = []
    for path in iter_python_files():
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel.startswith("tests/") or rel.startswith(".github/"):
            continue
        result.append(rel)
    return sorted(result)


def existing_test_files() -> list[str]:
    result = []
    for path in iter_python_files():
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel.startswith("tests/"):
            result.append(rel)
    return sorted(result)


def extract_public_symbols(path: Path) -> list[dict]:
    source = read_text(path)
    rel = str(path.relative_to(ROOT)).replace("\\", "/")

    try:
        tree = ast.parse(source)
    except Exception:
        return []

    symbols = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            symbols.append({"file": rel, "symbol": node.name, "kind": "function"})
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            symbols.append({"file": rel, "symbol": node.name, "kind": "class"})
    return symbols


def module_has_nominal_test(module_file: str, test_files: list[str]) -> bool:
    stem = Path(module_file).stem.lower()
    for tf in test_files:
        low = tf.lower()
        if stem in low:
            return True
    return False


def main() -> int:
    runtime_modules = runtime_module_paths()
    test_files = existing_test_files()

    all_public_symbols = []
    for path in iter_python_files():
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel.startswith("tests/") or rel.startswith(".github/"):
            continue
        all_public_symbols.extend(extract_public_symbols(path))

    modules_without_direct_tests = [
        {"file": module}
        for module in runtime_modules
        if not module_has_nominal_test(module, test_files)
    ]

    public_symbols_without_nominal_tests = []
    for item in all_public_symbols:
        if not module_has_nominal_test(item["file"], test_files):
            public_symbols_without_nominal_tests.append(item)

    result = {
        "modules_without_direct_tests": modules_without_direct_tests[:300],
        "public_symbols_without_nominal_tests": public_symbols_without_nominal_tests[:500],
        "dead_code_candidates": [],
        "shallow_test_files": [],
    }

    write_json(AUDIT_OUT / "repo_api_report_v4.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())