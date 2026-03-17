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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def normalize_path(path_str: str) -> str:
    raw = str(path_str or "").replace("\\", "/").strip()
    while raw.startswith("./"):
        raw = raw[2:]
    return raw


def is_runtime_python(path_str: str) -> bool:
    rel = normalize_path(path_str).lower()
    return rel.endswith(".py") and not rel.startswith("tests/") and not rel.startswith(".github/")


def is_test_python(path_str: str) -> bool:
    rel = normalize_path(path_str).lower()
    return rel.startswith("tests/") and rel.endswith(".py")


def is_generated_test(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith("tests/generated/")


def is_guardrail_test(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith("tests/guardrails/")


def build_report(data: dict) -> str:
    lines = []
    lines.append("Patch Verification")
    lines.append("")
    lines.append(f"Verdict: {data.get('verdict', '')}")
    lines.append(f"Reason: {data.get('reason', '')}")
    lines.append("")
    lines.append(f"Applied: {'YES' if data.get('applied') else 'NO'}")
    lines.append(f"Target file: {data.get('target_file', '')}")
    lines.append(f"Issue type: {data.get('issue_type', '')}")
    lines.append(f"Classification: {data.get('classification', '')}")
    lines.append("")
    lines.append("Changed files")
    changed = data.get("changed_files", []) or []
    if changed:
        for item in changed:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("Notes")
    notes = data.get("notes", []) or []
    if notes:
        for item in notes:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def main() -> int:
    candidate_payload = read_json(AUDIT_OUT / "patch_candidate.json")
    candidate = candidate_payload.get("patch_candidate") or {}
    if not isinstance(candidate, dict):
        candidate = {}

    apply_report = read_json(AUDIT_OUT / "patch_apply_report.json")

    target_file = normalize_path(candidate.get("target_file", ""))
    issue_type = str(candidate.get("issue_type", "")).strip()
    classification = str(candidate.get("classification", "")).strip()

    applied = bool(apply_report.get("applied", False))
    changed_files = [normalize_path(x) for x in (apply_report.get("applied_targets", []) or []) if normalize_path(x)]
    details = [str(x).strip() for x in (apply_report.get("details", []) or []) if str(x).strip()]

    verdict = "reject"
    reason = "unknown"
    notes = []

    if not candidate:
        verdict = "reject"
        reason = "no_candidate"
        notes.append("patch_candidate.json does not contain a valid patch_candidate")

    elif not applied:
        verdict = "reject"
        reason = str(apply_report.get("reason", "")).strip() or "patch_not_applied"
        notes.extend(details[:6])

    elif not changed_files:
        verdict = "reject"
        reason = "no_committable_change"
        notes.append("Patch apply reported success path but no changed files were recorded.")

    elif issue_type == "missing_public_contract":
        verdict = "approve"
        reason = "contract_patch_changed_files"
        notes.append("Missing public contract target produced a real file diff.")

    elif issue_type == "runtime_failure":
        if is_runtime_python(target_file):
            verdict = "approve"
            reason = "runtime_patch_changed_runtime_file"
            notes.append("Runtime failure target produced a real diff on a runtime python file.")
        else:
            verdict = "review"
            reason = "runtime_patch_non_runtime_target"
            notes.append("Runtime failure produced a diff, but target is not a runtime python file.")

    elif issue_type == "lint_failure":
        verdict = "approve"
        reason = "lint_patch_changed_file"
        notes.append("Lint target produced a real diff.")

    elif issue_type == "test_failure":
        if is_guardrail_test(target_file):
            verdict = "review"
            reason = "guardrail_test_patch_changed"
            notes.append("Guardrail test changed: keep review-level approval.")
        else:
            verdict = "weak-approve"
            reason = "test_patch_changed_file"
            notes.append("Test patch produced a real diff.")

    elif issue_type == "missing_nominal_test":
        if is_generated_test(target_file):
            verdict = "weak-approve"
            reason = "generated_nominal_test_ready"
            notes.append("Generated nominal test exists with real diff.")
        else:
            verdict = "review"
            reason = "nominal_test_non_generated_target"
            notes.append("Nominal test issue changed a non-generated target.")

    elif issue_type == "ci_failure":
        if is_runtime_python(target_file):
            verdict = "approve"
            reason = "ci_patch_changed_runtime_file"
            notes.append("Generic CI failure was resolved via real runtime file patch.")
        elif is_test_python(target_file):
            verdict = "weak-approve"
            reason = "ci_patch_changed_test_file"
            notes.append("Generic CI failure was resolved via test file patch.")
        else:
            verdict = "review"
            reason = "ci_patch_changed_unknown_target"
            notes.append("Generic CI patch produced a diff on non-standard target.")

    else:
        verdict = "review"
        reason = "changed_files_detected"
        notes.append("Patch produced a real diff but issue type is generic or unknown.")

    if classification == "HUMAN_ONLY" and verdict in {"approve", "weak-approve"}:
        verdict = "review"
        reason = "human_only_requires_review"
        notes.append("Classification is HUMAN_ONLY, so final verifier keeps review verdict.")

    notes.extend(details[:8])

    result = {
        "verdict": verdict,
        "reason": reason,
        "applied": applied,
        "target_file": target_file,
        "issue_type": issue_type,
        "classification": classification,
        "changed_files": changed_files,
        "notes": notes[:12],
    }

    write_json(AUDIT_OUT / "patch_verification.json", result)
    write_text(AUDIT_OUT / "patch_verification.md", build_report(result))

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())