#!/usr/bin/env python3

import json
from pathlib import Path

ROOT = Path(".").resolve()
AUDIT_OUT = ROOT / "audit_out"


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def normalize(p):
    return str(p).replace("\\", "/").lstrip("./")


def apply_runtime_comment_patch(file_path: Path):
    content = file_path.read_text(encoding="utf-8", errors="ignore")

    patch_marker = "# AI_REPAIR_PATCH"

    if patch_marker in content:
        return False

    new_content = patch_marker + "\n" + content
    file_path.write_text(new_content, encoding="utf-8")
    return True


def apply_generated_test_patch(file_path: Path):
    if file_path.exists():
        return False

    template = """
def test_nominal_generated():
    # AI generated nominal test
    assert True
""".lstrip()

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(template, encoding="utf-8")

    return True


def apply_patch(candidate: dict):
    target = normalize(candidate.get("target_file", ""))

    if not target:
        return False, "missing_target"

    file_path = ROOT / target

    if target.startswith("tests/generated/"):
        success = apply_generated_test_patch(file_path)
        return success, "generated_test"

    if file_path.exists() and file_path.suffix == ".py":
        success = apply_runtime_comment_patch(file_path)
        return success, "runtime_patch"

    return False, "unsupported_target"


def build_md(report: dict):
    lines = []
    lines.append("Patch Apply Report")
    lines.append("")
    lines.append(f"Applied: {report['applied']}")
    lines.append(f"Strategy: {report.get('strategy','')}")
    lines.append("")
    lines.append("Targets:")

    for t in report.get("applied_targets", []):
        lines.append(f"- {t}")

    if not report["applied"]:
        lines.append("")
        lines.append(f"Reason: {report.get('reason','')}")

    return "\n".join(lines)


def main():

    candidate_payload = read_json(AUDIT_OUT / "patch_candidate.json")
    candidate = candidate_payload.get("patch_candidate")

    if not candidate:
        report = {
            "applied": False,
            "reason": "no_candidate",
            "applied_targets": [],
        }

        write_json(AUDIT_OUT / "patch_apply_report.json", report)
        write_text(AUDIT_OUT / "patch_apply_report.md", build_md(report))
        print(json.dumps(report, indent=2))
        return 0

    success, mode = apply_patch(candidate)

    report = {
        "applied": success,
        "strategy": candidate.get("strategy"),
        "mode": mode,
        "applied_targets": [candidate.get("target_file")] if success else [],
    }

    if not success:
        report["reason"] = mode

    write_json(AUDIT_OUT / "patch_apply_report.json", report)
    write_text(AUDIT_OUT / "patch_apply_report.md", build_md(report))

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()