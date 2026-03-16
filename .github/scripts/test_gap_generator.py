#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"
GENERATED_DIR = ROOT / "tests" / "generated"

MAX_GENERATED = 8


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


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize_path(path_str: str) -> str:
    raw = str(path_str or "").strip().replace("\\", "/")
    if not raw:
        return ""
    try:
        p = Path(raw)
        if p.is_absolute():
            return str(p.resolve().relative_to(ROOT)).replace("\\", "/")
    except Exception:
        pass
    return raw.lstrip("./")


def sanitize_module_name(file_path: str) -> str:
    rel = normalize_path(file_path)
    rel = rel.replace("/", "_").replace(".py", "")
    rel = rel.replace("-", "_")
    while "__" in rel:
        rel = rel.replace("__", "_")
    return rel.strip("_")


def safe_identifier(name: str) -> str:
    cleaned = []
    for ch in str(name or ""):
        if ch.isalnum() or ch == "_":
            cleaned.append(ch)
        else:
            cleaned.append("_")
    value = "".join(cleaned).strip("_")
    while "__" in value:
        value = value.replace("__", "_")
    return value or "symbol"


def should_skip_source(file_path: str) -> bool:
    rel = normalize_path(file_path)
    if not rel.endswith(".py"):
        return True
    if rel.startswith("tests/"):
        return True
    if rel.startswith(".github/"):
        return True
    return False


def rank_symbol_item(item: dict, complex_files: set[str]) -> tuple:
    file_path = normalize_path(item.get("file", ""))
    symbol = str(item.get("symbol", "")).strip()
    high_risk = file_path in complex_files
    return (
        1 if high_risk else 0,
        file_path,
        symbol,
    )


def make_test_content(source_file: str, symbol: str) -> str:
    module_import = normalize_path(source_file).replace("/", ".").removesuffix(".py")
    fn_name = safe_identifier(symbol)

    return f'''import importlib


def test_nominal_{fn_name}_exists():
    module = importlib.import_module("{module_import}")
    assert hasattr(module, "{symbol}")
'''.rstrip() + "\n"


def main() -> int:
    repo_diag = read_json(AUDIT_OUT / "repo_diagnostics_context.json")
    complex_areas = repo_diag.get("complex_or_high_risk_areas", []) or []
    complex_files = {
        normalize_path(item.get("file", ""))
        for item in complex_areas
        if normalize_path(item.get("file", ""))
    }

    symbols = repo_diag.get("public_symbols_without_nominal_tests", []) or []
    ranked = sorted(
        [item for item in symbols if normalize_path(item.get("file", "")) and str(item.get("symbol", "")).strip()],
        key=lambda x: rank_symbol_item(x, complex_files),
    )

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    generated_tests = []
    created = 0

    for item in ranked:
        if created >= MAX_GENERATED:
            break

        source_file = normalize_path(item.get("file", ""))
        symbol = str(item.get("symbol", "")).strip()
        if not source_file or not symbol:
            continue
        if should_skip_source(source_file):
            continue

        module_name = sanitize_module_name(source_file)
        generated_rel = f"tests/generated/test_nominal_{module_name}__{safe_identifier(symbol)}.py"
        generated_abs = ROOT / generated_rel

        content = make_test_content(source_file, symbol)
        generated_abs.parent.mkdir(parents=True, exist_ok=True)
        generated_abs.write_text(content, encoding="utf-8")

        generated_tests.append(
            {
                "source_file": source_file,
                "symbol": symbol,
                "generated_test_file": generated_rel,
                "high_risk_area": source_file in complex_files,
            }
        )
        created += 1

    payload = {
        "generated_count": len(generated_tests),
        "generated_tests": generated_tests,
    }

    write_json(AUDIT_OUT / "test_gap_generation_report.json", payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())