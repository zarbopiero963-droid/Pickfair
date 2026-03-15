#!/usr/bin/env python3

import ast
import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"

MAX_GENERATED_TESTS = 12


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def read_json(path: Path):
    try:
        return json.loads(read_text(path))
    except Exception:
        return {}


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def normalize_module_path(file_path: str) -> str:
    path = str(file_path or "").strip().replace("\\", "/")
    if path.endswith(".py"):
        path = path[:-3]
    return path.replace("/", ".")


def normalize_test_path(file_path: str) -> str:
    path = str(file_path or "").strip().replace("\\", "/")
    stem = Path(path).stem
    return f"tests/generated/test_{stem}_nominal.py"


def is_runtime_safe_target(file_path: str) -> bool:
    path = str(file_path or "").strip().replace("\\", "/")
    if not path.endswith(".py"):
        return False
    if path.startswith("tests/"):
        return False
    if path.startswith(".github/"):
        return False
    if path.startswith("scripts/"):
        return False
    if "hft" in path.lower():
        return False
    return True


def load_runtime_symbols(file_path: str) -> dict:
    source = read_text(ROOT / file_path)
    if not source.strip():
        return {"functions": set(), "classes": set()}

    try:
        tree = ast.parse(source)
    except Exception:
        return {"functions": set(), "classes": set()}

    functions = set()
    classes = set()

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if not node.name.startswith("_"):
                functions.add(node.name)
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                classes.add(node.name)

    return {"functions": functions, "classes": classes}


def choose_candidates(diag: dict) -> list[dict]:
    public_symbols = diag.get("public_symbols_without_nominal_tests", []) or []
    modules_without_tests = diag.get("modules_without_direct_tests", []) or []
    high_risk = {
        str(item.get("file", "")).strip()
        for item in (diag.get("complex_or_high_risk_areas", []) or [])
        if str(item.get("risk", "")).strip().lower() == "high"
    }

    candidates = []
    seen = set()

    for item in public_symbols:
        file_path = str(item.get("file", "")).strip()
        symbol = str(item.get("symbol", "")).strip()
        if not file_path or not symbol:
            continue
        if not is_runtime_safe_target(file_path):
            continue
        key = (file_path, symbol)
        if key in seen:
            continue
        seen.add(key)

        candidates.append(
            {
                "file": file_path,
                "symbol": symbol,
                "kind": "public_symbol_without_nominal_test",
                "high_risk_area": file_path in high_risk,
            }
        )

    for item in modules_without_tests:
        file_path = str(item.get("file", "")).strip()
        if not file_path:
            continue
        if not is_runtime_safe_target(file_path):
            continue

        key = (file_path, "")
        if key in seen:
            continue
        seen.add(key)

        candidates.append(
            {
                "file": file_path,
                "symbol": "",
                "kind": "module_without_direct_test",
                "high_risk_area": file_path in high_risk,
            }
        )

    def score(x: dict) -> tuple[int, int]:
        kind = str(x.get("kind", ""))
        high_risk_area = bool(x.get("high_risk_area", False))

        primary = 0
        if kind == "public_symbol_without_nominal_test":
            primary = 0
        elif kind == "module_without_direct_test":
            primary = 1
        else:
            primary = 2

        risk_penalty = 1 if high_risk_area else 0
        return (primary, risk_penalty)

    candidates.sort(key=score)
    return candidates[:MAX_GENERATED_TESTS]


def build_function_test(module_name: str, symbol: str) -> str:
    return f'''import importlib


def test_{symbol}_is_importable_and_callable():
    module = importlib.import_module("{module_name}")
    assert hasattr(module, "{symbol}")
    obj = getattr(module, "{symbol}")
    assert callable(obj)
'''


def build_class_test(module_name: str, symbol: str) -> str:
    return f'''import importlib


def test_{symbol}_is_importable():
    module = importlib.import_module("{module_name}")
    assert hasattr(module, "{symbol}")
    obj = getattr(module, "{symbol}")
    assert isinstance(obj, type)
'''


def build_module_smoke_test(module_name: str) -> str:
    safe_name = module_name.replace(".", "_")
    return f'''import importlib


def test_{safe_name}_module_import_smoke():
    module = importlib.import_module("{module_name}")
    assert module is not None
'''


def generate_test_file(file_path: str, symbol: str) -> tuple[str, str, str]:
    module_name = normalize_module_path(file_path)
    test_path = normalize_test_path(file_path)
    runtime_symbols = load_runtime_symbols(file_path)

    body = []
    body.append('"""Auto-generated nominal tests from repo diagnostics."""')
    body.append("")

    if symbol:
        if symbol in runtime_symbols["classes"]:
            body.append(build_class_test(module_name, symbol).strip())
        elif symbol in runtime_symbols["functions"]:
            body.append(build_function_test(module_name, symbol).strip())
        else:
            body.append(build_module_smoke_test(module_name).strip())
    else:
        body.append(build_module_smoke_test(module_name).strip())

    body.append("")
    content = "\n".join(body)

    return test_path, module_name, content


def main() -> int:
    diag = read_json(AUDIT_OUT / "repo_diagnostics_context.json")
    candidates = choose_candidates(diag)

    generated = []

    for item in candidates:
        file_path = str(item.get("file", "")).strip()
        symbol = str(item.get("symbol", "")).strip()

        test_path, module_name, content = generate_test_file(file_path, symbol)
        write_text(ROOT / test_path, content)

        generated.append(
            {
                "source_file": file_path,
                "symbol": symbol,
                "module_name": module_name,
                "generated_test_file": test_path,
                "kind": item.get("kind", ""),
                "high_risk_area": bool(item.get("high_risk_area", False)),
            }
        )

    result = {
        "generated_count": len(generated),
        "generated_tests": generated,
    }

    write_json(AUDIT_OUT / "test_gap_generation_report.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main()) 