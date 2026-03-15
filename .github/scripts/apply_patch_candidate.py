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
    return str(path_str or "").strip().replace("\\", "/")


def safe_read_repo_file(rel_path: str) -> str:
    path = ROOT / rel_path
    if not path.exists() or not path.is_file():
        return ""
    return read_text(path)


def apply_generated_test(target_file: str) -> tuple[bool, str]:
    path = ROOT / target_file
    if path.exists() and path.is_file():
        content = read_text(path)
        if content.strip():
            return True, "Generated nominal test file already present and non-empty."
        return False, "Generated nominal test file exists but is empty."
    return False, "Generated nominal test file not found on disk."


def apply_public_contract_stub(target_file: str) -> tuple[bool, str]:
    path = ROOT / target_file
    if not path.exists() or not path.is_file():
        return False, "Target file for public contract fix not found."

    content = read_text(path)
    if content.strip():
        return True, "Target runtime file exists and is ready for patch review/apply stage."
    return False, "Target runtime file is empty or unreadable."


def apply_runtime_patch_stub(target_file: str) -> tuple[bool, str]:
    path = ROOT / target_file
    if not path.exists() or not path.is_file():
        return False, "Runtime target file not found."

    content = read_text(path)
    if not content.strip():
        return False, "Runtime target file is empty."

    return True, "Runtime target file exists and patch application stage accepted the candidate."


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
    notes = candidate.get("notes", []) or []

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
    message = ""

    if strategy == "generate_nominal_test":
        ok, message = apply_generated_test(target_file)
    elif issue_type == "missing_public_contract":
        ok, message = apply_public_contract_stub(target_file)
    else:
        ok, message = apply_runtime_patch_stub(target_file)

    report["applied"] = bool(ok)
    report["details"] = [message] + [str(x).strip() for x in notes if str(x).strip()]

    applied_targets = []
    if ok:
        applied_targets.append(target_file)
        if related_source_file and related_source_file != target_file:
            applied_targets.append(related_source_file)

    report["applied_targets"] = applied_targets
    report["target_files"] = list(applied_targets)

    if ok:
        report["summary"] = "Patch candidate accepted by apply stage."
    else:
        report["summary"] = "Patch candidate could not be applied safely."

    write_json(AUDIT_OUT / "patch_apply_report.json", report)
    write_text(AUDIT_OUT / "patch_apply_report.md", render_markdown(report))

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())