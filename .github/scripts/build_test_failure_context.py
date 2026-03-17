#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"


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
    while raw.startswith("./"):
        raw = raw[2:]
    return raw


def repo_exists(rel_path: str) -> bool:
    rel = normalize_path(rel_path)
    return bool(rel) and (ROOT / rel).exists()


def is_runtime_python(path_str: str) -> bool:
    rel = normalize_path(path_str).lower()
    return rel.endswith(".py") and not rel.startswith("tests/") and not rel.startswith(".github/")


def is_test_python(path_str: str) -> bool:
    rel = normalize_path(path_str).lower()
    return rel.startswith("tests/") and rel.endswith(".py")


def guess_related_tests(source_file: str) -> list[str]:
    source = normalize_path(source_file)
    if not is_runtime_python(source):
        return []

    stem = Path(source).stem
    guesses = [
        f"tests/test_{stem}.py",
        f"tests/contracts/test_{stem}.py",
        f"tests/guardrails/test_{stem}.py",
    ]
    return [g for g in guesses if repo_exists(g)]


def guess_related_source(test_file: str) -> str:
    test_path = normalize_path(test_file)
    if not is_test_python(test_path):
        return ""

    name = Path(test_path).name
    stem = Path(name).stem

    candidates = []
    if stem.startswith("test_"):
        base = stem[5:]
        candidates.extend(
            [
                f"{base}.py",
                f"ai/{base}.py",
                f"core/{base}.py",
                f"controllers/{base}.py",
                f"ui/{base}.py",
            ]
        )

    for candidate in candidates:
        if repo_exists(candidate):
            return candidate
    return ""


def unique_keep(items: list[str]) -> list[str]:
    out = []
    seen = set()
    for item in items:
        value = normalize_path(item)
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def main() -> int:
    ci_payload = read_json(AUDIT_OUT / "ci_failure_context.json")
    if not ci_payload:
        ci_payload = read_json(AUDIT_OUT / "ci_failures.json")

    fix_payload = read_json(AUDIT_OUT / "fix_context.json")
    issue_payload = read_json(AUDIT_OUT / "issue_classification.json")

    contexts = []
    seen = set()

    for item in ci_payload.get("ci_failures", []) or []:
        target_file = normalize_path(item.get("target_file", ""))
        issue_type = str(item.get("issue_type", "")).strip()
        if not target_file:
            continue

        related_source = ""
        related_tests = []

        if is_runtime_python(target_file):
            related_source = target_file
            related_tests = guess_related_tests(target_file)
        elif is_test_python(target_file):
            related_source = guess_related_source(target_file)
            related_tests = [target_file]

        ctx = {
            "target_file": target_file,
            "issue_type": issue_type,
            "related_source_file": related_source,
            "related_tests": unique_keep(related_tests),
            "notes": [str(item.get("signal", "")).strip()] if str(item.get("signal", "")).strip() else [],
        }

        key = (
            ctx["target_file"],
            ctx["issue_type"],
            ctx["related_source_file"],
            tuple(ctx["related_tests"]),
        )
        if key in seen:
            continue
        seen.add(key)
        contexts.append(ctx)

    for item in fix_payload.get("fix_contexts", []) or []:
        target_file = normalize_path(item.get("target_file", ""))
        if not target_file:
            continue

        ctx = {
            "target_file": target_file,
            "issue_type": str(item.get("issue_type", "")).strip(),
            "related_source_file": normalize_path(item.get("related_source_file", "")),
            "related_tests": unique_keep(item.get("related_tests", []) or []),
            "notes": [str(x).strip() for x in (item.get("notes", []) or []) if str(x).strip()],
        }

        key = (
            ctx["target_file"],
            ctx["issue_type"],
            ctx["related_source_file"],
            tuple(ctx["related_tests"]),
        )
        if key in seen:
            continue
        seen.add(key)
        contexts.append(ctx)

    for item in issue_payload.get("issue_classification", []) or issue_payload.get("fix_contexts", []) or []:
        target_file = normalize_path(item.get("target_file", ""))
        if not target_file:
            continue

        related_source = normalize_path(item.get("related_source_file", ""))
        related_tests = unique_keep(item.get("related_tests", []) or [])

        if not related_source:
            if is_runtime_python(target_file):
                related_source = target_file
            elif is_test_python(target_file):
                related_source = guess_related_source(target_file)

        if not related_tests:
            if is_runtime_python(target_file):
                related_tests = guess_related_tests(target_file)
            elif is_test_python(target_file):
                related_tests = [target_file]

        ctx = {
            "target_file": target_file,
            "issue_type": str(item.get("issue_type", "")).strip(),
            "related_source_file": related_source,
            "related_tests": unique_keep(related_tests),
            "notes": [str(x).strip() for x in (item.get("notes", []) or []) if str(x).strip()],
        }

        key = (
            ctx["target_file"],
            ctx["issue_type"],
            ctx["related_source_file"],
            tuple(ctx["related_tests"]),
        )
        if key in seen:
            continue
        seen.add(key)
        contexts.append(ctx)

    result = {
        "test_failure_contexts": contexts,
        "summary": {
            "count": len(contexts),
        },
    }

    write_json(AUDIT_OUT / "test_failure_context.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())