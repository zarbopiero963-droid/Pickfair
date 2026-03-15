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


def analyze_file(path: Path) -> dict:
    source = read_text(path)
    rel = str(path.relative_to(ROOT)).replace("\\", "/")

    try:
        tree = ast.parse(source)
    except Exception:
        return {
            "file": rel,
            "classes": [],
            "functions": 0,
            "lines": len(source.splitlines()),
            "parse_ok": False,
        }

    classes = []
    functions = 0

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            method_count = sum(1 for x in node.body if isinstance(x, ast.FunctionDef))
            classes.append(
                {
                    "class_name": node.name,
                    "method_count": method_count,
                }
            )
        elif isinstance(node, ast.FunctionDef):
            functions += 1

    return {
        "file": rel,
        "classes": classes,
        "functions": functions,
        "lines": len(source.splitlines()),
        "parse_ok": True,
    }


def main() -> int:
    files = [analyze_file(p) for p in iter_python_files()]

    prod_top_classes = []
    for item in files:
        if item["file"].startswith("tests/") or item["file"].startswith(".github/"):
            continue
        for cls in item["classes"]:
            prod_top_classes.append(
                {
                    "file": item["file"],
                    "class_name": cls["class_name"],
                    "method_count": cls["method_count"],
                }
            )

    prod_top_classes.sort(
        key=lambda x: (-int(x.get("method_count", 0)), x.get("file", ""), x.get("class_name", ""))
    )

    result = {
        "python_file_count": len(files),
        "prod_top_classes": prod_top_classes[:50],
        "files": files[:200],
    }

    write_json(AUDIT_OUT / "repo_autopsy_summary.json", result)
    write_json(AUDIT_OUT / "repo_autopsy.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())