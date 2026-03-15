#!/usr/bin/env python3

import json
import subprocess
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


def repo_file_exists(rel_path: str) -> bool:
    if not rel_path:
        return False
    path = ROOT / rel_path
    return path.exists() and path.is_file()


def is_python_file(rel_path: str) -> bool:
    return normalize_path(rel_path).lower().endswith(".py")


def is_generated_test(rel_path: str) -> bool:
    return normalize_path(rel_path).lower().startswith("tests/generated/")


def is_runtime_python(rel_path: str) -> bool:
    rel = normalize_path(rel_path).lower()
    return rel.endswith(".py") and not rel.startswith("tests/") and not rel.startswith(".github/")


def run_cmd(args: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        out = (result.stdout or "") + ("\n" if result.stdout and result.stderr else "") + (result.stderr or "")
        return result.returncode == 0, out.strip()
    except Exception as e:
        return False, str(e)


def file_changed(rel_path: str) -> bool:
    ok, out = run_cmd(["git", "diff", "--name-only", "--", rel_path])
    if not ok:
        return False
    changed = [x.strip() for x in out.splitlines() if x.strip()]
    return rel_path in changed


def any_changed(paths: list[str]) -> list[str]:
    changed = []
    for rel in paths:
        rel = normalize_path(rel)
        if rel and file_changed(rel):
            changed.append(rel)
    return changed


def safe_py_compile(rel_path: str) -> tuple[bool, str]:
    return run_cmd(["python", "-m", "py_compile", rel_path])


def try_ruff_fix(rel_path: str) -> list[str]:
    details = []

    ok, out = run_cmd(["python", "-m", "ruff", "check", rel_path, "--fix"])
    details.append(f"ruff check --fix: {'ok' if ok else 'failed'}")
    if out:
        details.append(out[:4000])

    ok2, out2 = run_cmd(["python", "-m", "ruff", "format", rel_path])
    details.append(f"ruff format: {'ok' if ok2 else 'failed'}")
    if out2:
        details.append(out2[:4000])

    return details


def apply_generated_test(target_file: str) -> tuple[bool, str, list[str], list[str]]:
    details = []
    changed = []

    if not repo_file_exists(target_file):
        return False, "Generated nominal test file not found on disk.", details, changed

    content = read_text(ROOT / target_file)
    if not content.strip():
        return False, "Generated nominal test file exists but is empty.", details, changed

    if file_changed(target_file):
        changed.append(target_file)
        return True, "Generated nominal test file exists and contains real changes.", details, changed

    return True, "Generated nominal test file exists and is ready for PR.", details, changed


def apply_runtime_python_fix(target_file: str, related_source_file: str) -> tuple[bool, str, list[str], list[str]]:
    details = []
    candidate_paths = [target_file]
    if related_source_file and related_source_file != target_file:
        candidate_paths.append(related_source_file)

    for rel in candidate_paths:
        if not repo_file_exists(rel):
            details.append(f"Target missing: {rel}")
            continue
        if not is_python_file(rel):
            details.append(f"Not a python file: {rel}")
            continue

        details.extend(try_ruff_fix(rel))

        ok, out = safe_py_compile(rel)
        details.append(f"py_compile {rel}: {'ok' if ok else 'failed'}")
        if out:
            details.append(out[:2000])

    changed = any_changed(candidate_paths)

    if changed:
        return True, "Runtime/local patch applied with real file modifications.", details, changed

    return False, "No real runtime modification was produced by local patching.", details, changed


def apply_test_python_fix(target_file: str) -> tuple[bool, str, list[str], list[str]]:
    details = []

    if not repo_file_exists(target_file):
        return False, "Target test file not found.", details, []

    if not is_python_file(target_file):
        return False, "Target test file is not Python.", details, []

    details.extend(try_ruff_fix(target_file))

    ok, out = safe_py_compile(target_file)
    details.append(f"py_compile {target_file}: {'ok' if ok else 'failed'}")
    if out:
        details.append(out[:2000])

    changed = any_changed([target_file])

    if changed:
        return True, "Test file patched locally with real modifications.", details, changed

    return False, "No real modification produced on test target.", details, changed


def render_markdown(report: dict) -> str:
    lines = []
    lines.append("Patch Apply Report")
    lines.append("")
    lines.append(f"Applied: {'YES' if report.get('applied') else 'NO'}")
    lines.append(f"Strategy: {report.get('strategy', '')}")
    lines.append(f"Target file: {report.get('target_file', '')}")
    lines.append(f"Related source file: {report.get('related_source_file', '')}")
    lines.append(f"Issue type: {report.get('issue_type', '')}")
    lines.append(f"Classification: {report.get('classification', '')}")
    lines.append("")
    lines.append("Summary")
    lines.append(report.get("summary", ""))
    lines.append("")
    lines.append("Details")
    details = report.get("details", []) or []
    if details:
        for item in details:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessun dettaglio disponibile.")
    lines.append("")
    lines.append("Applied targets")
    targets = report.get("applied_targets", []) or []
    if targets:
        for item in targets:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessun file applicato.")
    return "\n".join(lines)


def main() -> int:
    candidate_payload = read_json(AUDIT_OUT / "patch_candidate.json")
    candidate = candidate_payload.get("patch_candidate") or {}

    target_file = normalize_path(candidate.get("target_file", ""))
    related_source_file = normalize_path(candidate.get("related_source_file", ""))
    strategy = str(candidate.get("strategy", "")).strip()
    issue_type = str(candidate.get("issue_type", "")).strip()
    classification = str(candidate.get("classification", "")).strip()
    notes = [str(x).strip() for x in (candidate.get("notes", []) or []) if str(x).strip()]

    report = {
        "applied": False,
        "strategy": strategy,
        "target_file": target_file,
        "related_source_file": related_source_file,
        "issue_type": issue_type,
        "classification": classification,
        "summary": "",
        "details": [],
        "applied_targets": [],
        "target_files": [],
    }

    if not candidate:
        report["summary"] = "No patch candidate available."
        report["details"] = ["patch_candidate.json does not contain a viable patch_candidate."]
        write_json(AUDIT_OUT / "patch_apply_report.json", report)
        write_text(AUDIT_OUT / "patch_apply_report.md", render_markdown(report))
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    if not target_file:
        report["summary"] = "Patch candidate missing target file."
        report["details"] = ["The selected patch candidate has no target_file."]
        write_json(AUDIT_OUT / "patch_apply_report.json", report)
        write_text(AUDIT_OUT / "patch_apply_report.md", render_markdown(report))
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    ok = False
    summary = ""
    details = []
    changed = []

    if is_generated_test(target_file) or strategy == "generate_nominal_test":
        ok, summary, details, changed = apply_generated_test(target_file)

    elif is_runtime_python(target_file):
        ok, summary, details, changed = apply_runtime_python_fix(target_file, related_source_file)

    elif is_python_file(target_file):
        ok, summary, details, changed = apply_test_python_fix(target_file)

    else:
        summary = "Unsupported target type for local patch application."
        details = [f"Unsupported target_file: {target_file}"]

    report["applied"] = bool(ok and changed)
    report["summary"] = summary
    report["details"] = details + notes
    report["applied_targets"] = changed
    report["target_files"] = list(changed)

    if ok and not changed:
        report["applied"] = False
        report["summary"] = "Patch logic ran, but no real file diff was produced."

    write_json(AUDIT_OUT / "patch_apply_report.json", report)
    write_text(AUDIT_OUT / "patch_apply_report.md", render_markdown(report))

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())