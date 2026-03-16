#!/usr/bin/env python3

import json
import subprocess
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"
MAX_TARGETS = 12


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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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


def repo_exists(rel_path: str) -> bool:
    rel_path = normalize_path(rel_path)
    if not rel_path:
        return False
    return (ROOT / rel_path).exists()


def is_test_file(rel_path: str) -> bool:
    rel = normalize_path(rel_path).lower()
    return rel.startswith("tests/") and rel.endswith(".py")


def is_runtime_python(rel_path: str) -> bool:
    rel = normalize_path(rel_path).lower()
    return rel.endswith(".py") and not rel.startswith("tests/") and not rel.startswith(".github/")


def path_to_pytest_guesses(runtime_file: str) -> list[str]:
    rel = normalize_path(runtime_file)
    if not rel:
        return []

    stem = Path(rel).stem
    guesses = [
        f"tests/test_{stem}.py",
        f"tests/contracts/test_{stem}.py",
        f"tests/guardrails/test_{stem}.py",
    ]
    return guesses


def collect_targets() -> list[str]:
    targets = []

    patch_candidate_payload = read_json(AUDIT_OUT / "patch_candidate.json")
    candidate = patch_candidate_payload.get("patch_candidate") or {}
    if not isinstance(candidate, dict):
        candidate = {}

    target_file = normalize_path(candidate.get("target_file", ""))
    related_source_file = normalize_path(candidate.get("related_source_file", ""))

    if target_file:
        targets.append(target_file)
    if related_source_file and related_source_file not in targets:
        targets.append(related_source_file)

    for t in candidate.get("related_tests", []) or []:
        t = normalize_path(t)
        if t and t not in targets:
            targets.append(t)

    tf_context = read_json(AUDIT_OUT / "test_failure_context.json")
    for item in tf_context.get("test_failure_contexts", []) or []:
        tf = normalize_path(item.get("target_file", ""))
        rs = normalize_path(item.get("related_source_file", ""))
        if tf and tf not in targets:
            targets.append(tf)
        if rs and rs not in targets:
            targets.append(rs)
        for t in item.get("related_tests", []) or []:
            t = normalize_path(t)
            if t and t not in targets:
                targets.append(t)

    fix_context = read_json(AUDIT_OUT / "fix_context.json")
    for item in fix_context.get("fix_contexts", []) or []:
        tf = normalize_path(item.get("target_file", ""))
        rs = normalize_path(item.get("related_source_file", ""))
        if tf and tf not in targets:
            targets.append(tf)
        if rs and rs not in targets:
            targets.append(rs)
        for t in item.get("related_tests", []) or []:
            t = normalize_path(t)
            if t and t not in targets:
                targets.append(t)

    final = []
    seen = set()
    for item in targets:
        item = normalize_path(item)
        if not item or item in seen:
            continue
        seen.add(item)
        final.append(item)

    return final[:MAX_TARGETS]


def resolve_pytest_targets(raw_targets: list[str]) -> list[str]:
    resolved = []
    seen = set()

    for rel in raw_targets:
        rel = normalize_path(rel)
        if not rel:
            continue

        if is_test_file(rel) and repo_exists(rel):
            if rel not in seen:
                resolved.append(rel)
                seen.add(rel)
            continue

        if is_runtime_python(rel):
            for guess in path_to_pytest_guesses(rel):
                if repo_exists(guess) and guess not in seen:
                    resolved.append(guess)
                    seen.add(guess)

    return resolved


def run_one_pytest(target: str) -> dict:
    cmd = ["python", "-m", "pytest", "-q", target]
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    out = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    status = "passed" if result.returncode == 0 else "failed"

    return {
        "target": target,
        "returncode": result.returncode,
        "status": status,
        "output": out[:12000],
    }


def build_markdown(results: list[dict], summary: dict) -> str:
    lines = []
    lines.append("Targeted Test Results")
    lines.append("")
    lines.append(f"Targets considered: {summary.get('target_count', 0)}")
    lines.append(f"Targets executed: {summary.get('executed_count', 0)}")
    lines.append(f"Failure count: {summary.get('failure_count', 0)}")
    lines.append("")

    if not results:
        lines.append("No targeted tests available.")
        return "\n".join(lines)

    for item in results:
        lines.append(f"## {item.get('target', '')}")
        lines.append(f"- status: {item.get('status', '')}")
        lines.append(f"- returncode: {item.get('returncode', '')}")
        output = str(item.get("output", "")).strip()
        if output:
            lines.append("")
            lines.append("```text")
            lines.append(output[:4000])
            lines.append("```")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    raw_targets = collect_targets()
    pytest_targets = resolve_pytest_targets(raw_targets)

    results = []
    failure_count = 0

    for target in pytest_targets:
        result = run_one_pytest(target)
        results.append(result)
        if result["returncode"] != 0:
            failure_count += 1

    summary = {
        "target_count": len(raw_targets),
        "executed_count": len(pytest_targets),
        "failure_count": failure_count,
        "targets": pytest_targets,
        "raw_targets": raw_targets,
    }

    payload = {
        "summary": summary,
        "results": results,
        "failure_count": failure_count,
        "targets": pytest_targets,
        "raw_targets": raw_targets,
    }

    write_json(AUDIT_OUT / "targeted_test_results.json", payload)
    write_text(AUDIT_OUT / "targeted_test_results.md", build_markdown(results, summary))

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())