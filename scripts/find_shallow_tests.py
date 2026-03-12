import ast
import json
from pathlib import Path

TESTS_DIR = Path("tests")

WEAK_ASSERT_PATTERNS = {
    "is_not_none_only": "assert x is not None / assert obj is not None",
    "bool_in_true_false": "assert value in [True, False]",
    "always_true": "assert True",
    "len_ge_zero": "assert len(x) >= 0",
    "type_only_module_import": "test only imports module/object",
}

EXCLUDED_DIR_NAMES = {"fixtures", "__pycache__"}


def is_test_function(node: ast.FunctionDef) -> bool:
    return node.name.startswith("test_")


def get_assert_nodes(func: ast.FunctionDef):
    return [n for n in ast.walk(func) if isinstance(n, ast.Assert)]


def is_name_or_attr(expr):
    return isinstance(expr, (ast.Name, ast.Attribute, ast.Subscript, ast.Call))


def classify_assert(assert_node: ast.Assert):
    test = assert_node.test

    # assert True
    if isinstance(test, ast.Constant) and test.value is True:
        return "always_true"

    # assert something is not None
    if isinstance(test, ast.Compare):
        if (
            len(test.ops) == 1
            and isinstance(test.ops[0], ast.IsNot)
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value is None
        ):
            return "is_not_none_only"

        # assert len(x) >= 0
        if (
            len(test.ops) == 1
            and isinstance(test.ops[0], ast.GtE)
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == 0
            and isinstance(test.left, ast.Call)
            and isinstance(test.left.func, ast.Name)
            and test.left.func.id == "len"
        ):
            return "len_ge_zero"

        # assert value in [True, False]
        if (
            len(test.ops) == 1
            and isinstance(test.ops[0], ast.In)
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.List)
        ):
            values = test.comparators[0].elts
            if len(values) == 2 and all(isinstance(v, ast.Constant) for v in values):
                raw = {v.value for v in values}
                if raw == {True, False}:
                    return "bool_in_true_false"

    return None


def function_is_import_smoke_only(func: ast.FunctionDef):
    body = func.body
    if not body:
        return False

    asserts = [n for n in body if isinstance(n, ast.Assert)]
    non_asserts = [n for n in body if not isinstance(n, ast.Assert)]

    if not asserts:
        return False

    allowed_stmt_types = (
        ast.Import,
        ast.ImportFrom,
        ast.Assign,
        ast.Expr,
        ast.Assert,
    )
    if not all(isinstance(n, allowed_stmt_types) for n in body):
        return False

    shallow = 0
    for a in asserts:
        kind = classify_assert(a)
        if kind in {"is_not_none_only", "bool_in_true_false"}:
            shallow += 1

    return shallow == len(asserts)


def analyze_test_file(path: Path):
    src = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        return {
            "file": str(path),
            "error": f"SyntaxError: {e}",
            "tests": [],
        }

    tests = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and is_test_function(node):
            asserts = get_assert_nodes(node)
            flags = []

            if not asserts:
                flags.append("no_asserts")

            for a in asserts:
                kind = classify_assert(a)
                if kind:
                    flags.append(kind)

            if function_is_import_smoke_only(node):
                flags.append("type_only_module_import")

            score = 0
            for f in flags:
                if f in {
                    "always_true",
                    "is_not_none_only",
                    "bool_in_true_false",
                    "len_ge_zero",
                    "type_only_module_import",
                    "no_asserts",
                }:
                    score += 1

            tests.append(
                {
                    "name": node.name,
                    "line": node.lineno,
                    "assert_count": len(asserts),
                    "flags": sorted(set(flags)),
                    "shallow_score": score,
                }
            )

    return {
        "file": str(path),
        "tests": tests,
    }


def iter_test_files():
    for path in TESTS_DIR.rglob("test_*.py"):
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        yield path


def main():
    report = []
    shallow_total = 0

    for path in sorted(iter_test_files()):
        result = analyze_test_file(path)
        if result["tests"]:
            report.append(result)
            for t in result["tests"]:
                if t["shallow_score"] > 0:
                    shallow_total += 1

    output = {
        "summary": {
            "files_scanned": len(report),
            "shallow_tests_detected": shallow_total,
        },
        "files": report,
    }

    out_dir = Path("artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "shallow_tests_report.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print("======================================================================")
    print("SHALLOW TEST ANALYSIS")
    print("======================================================================")
    print(f"Files scanned: {output['summary']['files_scanned']}")
    print(f"Shallow tests detected: {output['summary']['shallow_tests_detected']}")
    print()

    for file_result in report:
        flagged = [t for t in file_result["tests"] if t["shallow_score"] > 0]
        if not flagged:
            continue
        print(f"[FILE] {file_result['file']}")
        for t in flagged:
            print(
                f"  [TEST] {t['name']} (line {t['line']}) | "
                f"flags={', '.join(t['flags'])} | assert_count={t['assert_count']}"
            )
        print()

    print(f"[OK] Report written to: {out_path}")


if __name__ == "__main__":
    main()