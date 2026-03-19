#!/usr/bin/env python3

import ast
import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"
AUDIT_RAW = ROOT / "audit_raw"

MAX_RANKING = 20
MAX_SIGNALS = 80

SKIP_PREFIXES = (
    ".git/",
    ".venv/",
    "venv/",
    "__pycache__/",
    "audit_out/",
    "audit_raw/",
)


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


def should_skip(path: Path) -> bool:
    rel = normalize_path(path.relative_to(ROOT))
    return any(rel.startswith(prefix) for prefix in SKIP_PREFIXES)


def iter_python_files():
    for path in ROOT.rglob("*.py"):
        if not path.is_file():
            continue
        if should_skip(path):
            continue
        yield path


def collect_contracts_from_machine(audit_machine: dict) -> list:
    contracts = audit_machine.get("contracts", [])
    if isinstance(contracts, list):
        return contracts
    return []


def collect_pytest_signals_from_machine(audit_machine: dict) -> list[str]:
    signals = audit_machine.get("pytest_signals", [])
    if isinstance(signals, list):
        return [str(x).strip() for x in signals if str(x).strip()]
    return []


def extract_pytest_signals_from_log(pytest_log: str) -> list[str]:
    if not pytest_log.strip():
        return []

    patterns = (
        "ImportError",
        "ModuleNotFoundError",
        "AttributeError",
        "TypeError",
        "RuntimeError",
        "AssertionError",
        "KeyError",
        "NameError",
        "FAILED ",
        "ERROR ",
        "cannot import name",
    )

    found = []
    seen = set()

    for raw in pytest_log.splitlines():
        line = raw.strip()
        if not line:
            continue
        if not any(p in line for p in patterns):
            continue
        if line in seen:
            continue
        seen.add(line)
        found.append(line)
        if len(found) >= MAX_SIGNALS:
            break

    return found


def analyze_python_file(path: Path) -> dict:
    rel = normalize_path(path.relative_to(ROOT))
    source = read_text(path)
    lines = source.splitlines()

    result = {
        "file": rel,
        "parse_ok": True,
        "class_count": 0,
        "function_count": 0,
        "method_count": 0,
        "line_count": len(lines),
        "if_count": 0,
        "try_count": 0,
        "import_count": 0,
        "public_symbol_count": 0,
        "complexity_score": 0,
    }

    try:
        tree = ast.parse(source)
    except Exception:
        result["parse_ok"] = False
        result["complexity_score"] = len(lines)
        return result

    public_symbols = 0
    class_count = 0
    function_count = 0
    method_count = 0
    if_count = 0
    try_count = 0
    import_count = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_count += 1
            if not node.name.startswith("_"):
                public_symbols += 1
        elif isinstance(node, ast.FunctionDef):
            parent_is_class = False
            for maybe_parent in tree.body:
                if isinstance(maybe_parent, ast.ClassDef) and node in maybe_parent.body:
                    parent_is_class = True
                    break
            if parent_is_class:
                method_count += 1
            else:
                function_count += 1
            if not node.name.startswith("_"):
                public_symbols += 1
        elif isinstance(node, ast.AsyncFunctionDef):
            function_count += 1
            if not node.name.startswith("_"):
                public_symbols += 1
        elif isinstance(node, ast.If):
            if_count += 1
        elif isinstance(node, ast.Try):
            try_count += 1
        elif isinstance(node, ast.Import | ast.ImportFrom):
            import_count += 1

    result["class_count"] = class_count
    result["function_count"] = function_count
    result["method_count"] = method_count
    result["if_count"] = if_count
    result["try_count"] = try_count
    result["import_count"] = import_count
    result["public_symbol_count"] = public_symbols
    result["complexity_score"] = (
        len(lines)
        + class_count * 6
        + function_count * 4
        + method_count * 3
        + if_count * 2
        + try_count * 2
    )
    return result


def rank_fragile_files(file_stats: list[dict]) -> list[dict]:
    prod = []
    for item in file_stats:
        file_path = item.get("file", "")
        if file_path.startswith("tests/") or file_path.startswith(".github/"):
            continue
        prod.append(item)

    prod.sort(
        key=lambda x: (
            -int(x.get("complexity_score", 0) or 0),
            -int(x.get("public_symbol_count", 0) or 0),
            x.get("file", ""),
        )
    )
    return prod[:MAX_RANKING]


def detect_contracts_missing(contracts: list) -> list[list[str]]:
    cleaned = []
    for item in contracts:
        if not isinstance(item, list | tuple) or len(item) < 2:
            continue
        file_path = normalize_path(item[0])
        symbol = str(item[1]).strip()
        if not file_path or not symbol:
            continue
        cleaned.append([file_path, symbol])
    return cleaned


def build_markdown_report(
    *,
    pytest_code: int,
    contracts: list,
    pytest_signals: list[str],
    ranking: list[dict],
) -> str:
    lines = []
    lines.append("Repo Ultra Audit Narrative")
    lines.append("")
    lines.append("## Pytest status")
    lines.append(f"Return code: {pytest_code}")
    lines.append("")
    lines.append("## Contracts missing")
    if contracts:
        for file_path, symbol in contracts[:20]:
            lines.append(f"- {file_path} :: {symbol}")
    else:
        lines.append("No missing contracts detected.")
    lines.append("")
    lines.append("## Pytest signals")
    if pytest_signals:
        for line in pytest_signals[:30]:
            lines.append(f"- {line}")
    else:
        lines.append("No pytest signals detected.")
    lines.append("")
    lines.append("## File ranking")
    if ranking:
        for item in ranking[:10]:
            lines.append(
                f"- {item.get('file','')} | score={item.get('complexity_score',0)} | "
                f"public={item.get('public_symbol_count',0)} | "
                f"lines={item.get('line_count',0)}"
            )
    else:
        lines.append("No ranking available.")
    return "\n".join(lines)


def main() -> int:
    audit_machine = read_json(AUDIT_OUT / "audit_machine.json")
    pytest_log = read_text(AUDIT_RAW / "pytest.log")

    compile_ok = bool(audit_machine.get("compile_ok", True))
    pytest_code = audit_machine.get("pytest_code", 0)
    if not isinstance(pytest_code, int):
        pytest_code = 0

    contracts = detect_contracts_missing(collect_contracts_from_machine(audit_machine))
    pytest_signals = collect_pytest_signals_from_machine(audit_machine)
    if not pytest_signals:
        pytest_signals = extract_pytest_signals_from_log(pytest_log)

    file_stats = [analyze_python_file(path) for path in iter_python_files()]
    ranking = rank_fragile_files(file_stats)

    machine_payload = {
        "compile_ok": compile_ok,
        "pytest_code": pytest_code,
        "pytest_signals": pytest_signals[:MAX_SIGNALS],
        "contracts": contracts,
        "ranking_top10": ranking[:10],
    }

    report_md = build_markdown_report(
        pytest_code=pytest_code,
        contracts=contracts,
        pytest_signals=pytest_signals,
        ranking=ranking,
    )

    write_json(AUDIT_OUT / "audit_machine.json", machine_payload)
    write_text(AUDIT_OUT / "repo_ultra_audit_narrative.md", report_md)

    print(report_md)
    print("")
    print(json.dumps(machine_payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())