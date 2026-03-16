#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"

MAX_CONTEXTS = 50
MAX_RELATED_TESTS = 5
MAX_NOTES = 6


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


def unique_keep(items, limit: int) -> list[str]:
    out = []
    seen = set()
    for item in items or []:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
        if len(out) >= limit:
            break
    return out


def guess_related_tests_for_runtime(runtime_file: str) -> list[str]:
    rel = normalize_path(runtime_file)
    if not rel:
        return []

    stem = Path(rel).stem
    guesses = [
        f"tests/test_{stem}.py",
        f"tests/contracts/test_{stem}.py",
        f"tests/guardrails/test_{stem}.py",
    ]

    existing = []
    for guess in guesses:
        if (ROOT / guess).exists():
            existing.append(guess)

    return existing[:MAX_RELATED_TESTS]


def build_from_ci_failures(ci_payload: dict) -> list[dict]:
    contexts = []
    failures = ci_payload.get("ci_failures", []) or []

    for item in failures:
        target_file = normalize_path(item.get("target_file", ""))
        if not target_file:
            continue

        issue_type = str(item.get("issue_type", "")).strip()
        error_type = str(item.get("error_type", "")).strip()
        source = str(item.get("source", "")).strip()
        job = str(item.get("job", "")).strip()
        signal = str(item.get("signal", "")).strip()

        notes = [
            f"CI failure source: {source}" if source else "",
            f"CI job: {job}" if job else "",
            f"Error type: {error_type}" if error_type else "",
            f"Signal: {signal}" if signal else "",
            "Questo contesto proviene dai workflow CI reali del repository.",
        ]

        related_tests = []
        related_source_file = ""

        if target_file.startswith("tests/"):
            related_tests = [target_file]
        elif target_file.endswith(".py") and not target_file.startswith(".github/"):
            related_source_file = target_file
            related_tests = guess_related_tests_for_runtime(target_file)

        contexts.append(
            {
                "target_file": target_file,
                "required_symbols": [],
                "related_tests": unique_keep(related_tests, MAX_RELATED_TESTS),
                "related_fixtures": [],
                "related_contracts": [],
                "notes": unique_keep(notes, MAX_NOTES),
                "priority": "P0" if issue_type in {"runtime_failure", "lint_failure", "test_failure"} else "P1",
                "issue_type": issue_type or "ci_failure",
                "related_source_file": related_source_file,
            }
        )

    return contexts


def build_from_failing_tests(failing_payload: dict) -> list[dict]:
    contexts = []
    items = failing_payload.get("failing_tests", []) or []

    for item in items:
        if isinstance(item, dict):
            target_file = normalize_path(item.get("target_file", "") or item.get("file", "") or "")
            test_name = str(item.get("test_name", "") or item.get("name", "") or "").strip()
        else:
            target_file = ""
            test_name = str(item).strip()

        if not target_file and test_name:
            if "::" in test_name:
                target_file = normalize_path(test_name.split("::", 1)[0])

        if not target_file:
            continue

        notes = [
            "Questo contesto proviene dal deterministic failing test extractor.",
            f"Failing test: {test_name}" if test_name else "",
        ]

        contexts.append(
            {
                "target_file": target_file,
                "required_symbols": [],
                "related_tests": unique_keep([target_file] if target_file.startswith("tests/") else [], MAX_RELATED_TESTS),
                "related_fixtures": [],
                "related_contracts": [],
                "notes": unique_keep(notes, MAX_NOTES),
                "priority": "P0",
                "issue_type": "test_failure",
                "related_source_file": "",
            }
        )

    return contexts


def merge_contexts(contexts: list[dict]) -> list[dict]:
    merged = {}

    for item in contexts:
        target_file = normalize_path(item.get("target_file", ""))
        if not target_file:
            continue

        if target_file not in merged:
            merged[target_file] = {
                "target_file": target_file,
                "required_symbols": [],
                "related_tests": [],
                "related_fixtures": [],
                "related_contracts": [],
                "notes": [],
                "priority": item.get("priority", "P1"),
                "issue_type": item.get("issue_type", "ci_failure"),
                "related_source_file": normalize_path(item.get("related_source_file", "")),
            }

        dst = merged[target_file]

        if str(item.get("priority", "")).upper() == "P0":
            dst["priority"] = "P0"

        issue_type = str(item.get("issue_type", "")).strip()
        if issue_type == "runtime_failure":
            dst["issue_type"] = "runtime_failure"
        elif issue_type == "lint_failure" and dst["issue_type"] != "runtime_failure":
            dst["issue_type"] = "lint_failure"
        elif issue_type == "test_failure" and dst["issue_type"] not in {"runtime_failure", "lint_failure"}:
            dst["issue_type"] = "test_failure"
        elif issue_type == "ci_failure" and not dst["issue_type"]:
            dst["issue_type"] = "ci_failure"

        if not dst.get("related_source_file") and item.get("related_source_file"):
            dst["related_source_file"] = normalize_path(item.get("related_source_file", ""))

        for key in ["required_symbols", "related_tests", "related_fixtures", "related_contracts", "notes"]:
            existing = set(dst.get(key, []))
            for value in item.get(key, []) or []:
                value = str(value).strip()
                if not value or value in existing:
                    continue
                dst[key].append(value)
                existing.add(value)

    results = []
    for item in merged.values():
        item["required_symbols"] = unique_keep(item.get("required_symbols", []), 10)
        item["related_tests"] = unique_keep(item.get("related_tests", []), MAX_RELATED_TESTS)
        item["related_fixtures"] = unique_keep(item.get("related_fixtures", []), 3)
        item["related_contracts"] = unique_keep(item.get("related_contracts", []), 3)
        item["notes"] = unique_keep(item.get("notes", []), MAX_NOTES)
        results.append(item)

    def score(x: dict):
        return (
            0 if str(x.get("priority", "")).upper() == "P0" else 1,
            0 if str(x.get("issue_type", "")).strip() == "runtime_failure" else 1,
            0 if str(x.get("issue_type", "")).strip() == "lint_failure" else 1,
            0 if normalize_path(x.get("target_file", "")).startswith("tests/") else 1,
            normalize_path(x.get("target_file", "")),
        )

    results.sort(key=score)
    return results[:MAX_CONTEXTS]


def main() -> int:
    ci_payload = read_json(AUDIT_OUT / "ci_failure_context.json")
    failing_payload = read_json(AUDIT_OUT / "failing_tests.json")

    contexts = []
    contexts.extend(build_from_ci_failures(ci_payload))
    contexts.extend(build_from_failing_tests(failing_payload))

    result = {
        "test_failure_contexts": merge_contexts(contexts),
    }

    write_json(AUDIT_OUT / "test_failure_context.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())