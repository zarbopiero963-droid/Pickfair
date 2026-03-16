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
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


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


def build_md(data: dict) -> str:
    lines = []
    lines.append("Patch Verification")
    lines.append("")
    lines.append(f"Verdict: {data.get('verdict', '')}")
    lines.append(f"Confidence: {data.get('confidence', '')}")
    lines.append("")
    lines.append("Summary")
    lines.append(data.get("summary", ""))
    lines.append("")
    lines.append("Why")
    why = data.get("why", []) or []
    if why:
        for item in why:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessun dettaglio disponibile.")
    lines.append("")
    lines.append("Likely gaps")
    gaps = data.get("likely_gaps", []) or []
    if gaps:
        for item in gaps:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessun gap rilevato.")
    lines.append("")
    lines.append("Tests to run")
    tests = data.get("tests_to_run", []) or []
    if tests:
        for item in tests:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessun test suggerito.")
    lines.append("")
    lines.append("Safe next step")
    lines.append(data.get("safe_next_step", ""))
    return "\n".join(lines)


def main() -> int:
    candidate_payload = read_json(AUDIT_OUT / "patch_candidate.json")
    apply_report = read_json(AUDIT_OUT / "patch_apply_report.json")
    targeted = read_json(AUDIT_OUT / "targeted_test_results.json")
    classification_payload = read_json(AUDIT_OUT / "issue_classification.json")

    candidate = candidate_payload.get("patch_candidate") or {}
    target_file = normalize_path(candidate.get("target_file", ""))
    related_file = normalize_path(candidate.get("related_source_file", ""))
    strategy = str(candidate.get("strategy", "")).strip()
    issue_type = str(candidate.get("issue_type", "")).strip()
    classification = str(candidate.get("classification", "")).strip()

    applied = bool(apply_report.get("applied", False))
    changed_files = [normalize_path(x) for x in (apply_report.get("applied_targets", []) or []) if normalize_path(x)]

    failure_count = targeted.get("failure_count")
    if not isinstance(failure_count, int):
        failure_count = None

    summary = targeted.get("summary", {}) or {}
    executed_count = int(summary.get("executed_count", 0) or 0)
    executed_targets = targeted.get("targets", []) or []

    verdict = "reject"
    confidence = "high"
    why = []
    likely_gaps = []
    tests_to_run = list(executed_targets[:8])
    safe_next_step = "Resubmit with a concrete patch and validating evidence."
    short_summary = ""

    if not candidate:
        short_summary = "No actionable patch was provided."
        why.append("patch_candidate.json does not contain a viable patch candidate.")
        likely_gaps.append("Missing target file or strategy.")
        safe_next_step = "Generate a valid patch candidate first."

    elif not applied:
        short_summary = "Patch candidate did not produce a real committable diff."
        why.append("Apply stage reported no real file changes.")
        why.append(f"Target file: {target_file or 'unknown'}")
        likely_gaps.append("Local patching strategy did not modify the target file.")
        likely_gaps.append("The selected candidate may need a smarter diff generator.")
        safe_next_step = "Refine the patch generation logic for this target."

    else:
        why.append(f"Target file: {target_file or 'unknown'}")
        why.append(f"Related source file: {related_file or 'none'}")
        why.append(f"Strategy: {strategy or 'unknown'}")
        why.append(f"Issue type: {issue_type or 'unknown'}")
        why.append(f"Classification: {classification or 'unknown'}")
        why.append(f"Changed files: {', '.join(changed_files) if changed_files else 'none'}")

        if is_generated_test(target_file):
            if classification == "AUTO_FIX_SAFE":
                verdict = "approve"
                confidence = "high"
                short_summary = "Generated nominal test patch is safe and committable."
                safe_next_step = "Proceed to post-patch review and PR evaluation."
            else:
                verdict = "review"
                confidence = "medium"
                short_summary = "Generated test patch exists but classification is not fully safe."
                safe_next_step = "Keep under review before merging."

        elif is_runtime_python(target_file):
            if issue_type == "runtime_failure":
                if failure_count == 0 and executed_count > 0:
                    verdict = "approve"
                    confidence = "high"
                    short_summary = "Runtime patch changed real code and targeted tests passed."
                    safe_next_step = "Proceed to post-patch review and PR evaluation."
                elif executed_count == 0 and classification in {"AUTO_FIX_SAFE", "AUTO_FIX_REVIEW"}:
                    verdict = "review"
                    confidence = "medium"
                    short_summary = "Runtime patch changed code, but no targeted test evidence is available."
                    likely_gaps.append("No targeted tests executed for runtime target.")
                    safe_next_step = "Keep as reviewable patch until stronger evidence exists."
                elif failure_count is not None and failure_count > 0:
                    verdict = "reject"
                    confidence = "high"
                    short_summary = "Runtime patch changed code but targeted tests still fail."
                    likely_gaps.append(f"Targeted failures remain: {failure_count}.")
                    safe_next_step = "Do not keep the patch without better evidence."
                else:
                    verdict = "review"
                    confidence = "medium"
                    short_summary = "Runtime patch is plausible but evidence is incomplete."
                    safe_next_step = "Keep under review."

            elif issue_type == "lint_failure":
                if classification == "AUTO_FIX_SAFE":
                    verdict = "approve"
                    confidence = "high"
                    short_summary = "Lint-oriented runtime patch produced real changes and is safe to continue."
                    safe_next_step = "Proceed to post-patch review."
                else:
                    verdict = "review"
                    confidence = "medium"
                    short_summary = "Lint-oriented runtime patch changed code but should remain reviewable."
                    safe_next_step = "Keep under review."

            elif issue_type == "ci_failure":
                verdict = "review"
                confidence = "medium"
                short_summary = "CI-linked runtime patch changed code, but CI-only failures are not enough for blind approval."
                likely_gaps.append("The failing signal comes from external CI and may need stronger local reproduction.")
                safe_next_step = "Keep under review until local evidence improves."

            else:
                verdict = "review"
                confidence = "medium"
                short_summary = "Runtime patch changed code, but issue type is not specific enough for full approval."
                likely_gaps.append("Issue type is too generic for blind approval.")
                safe_next_step = "Keep under review."

        elif is_test_python(target_file):
            if is_guardrail_test(target_file):
                verdict = "review"
                confidence = "medium"
                short_summary = "Guardrail test patch is committable but should remain under review."
                likely_gaps.append("Guardrail tests are sensitive and should not be auto-approved.")
                safe_next_step = "Keep under review."
            elif classification == "AUTO_FIX_SAFE":
                verdict = "approve"
                confidence = "medium"
                short_summary = "Test patch changed code and is safe enough to continue."
                safe_next_step = "Proceed to post-patch review."
            else:
                verdict = "review"
                confidence = "medium"
                short_summary = "Test patch changed code but should remain reviewable."
                safe_next_step = "Keep under review."

        else:
            verdict = "review"
            confidence = "low"
            short_summary = "Patch changed files, but target type is not recognized strongly enough."
            likely_gaps.append("Unknown target type.")
            safe_next_step = "Keep under review."

    result = {
        "verdict": verdict,
        "confidence": confidence,
        "summary": short_summary,
        "why": why,
        "likely_gaps": likely_gaps,
        "tests_to_run": tests_to_run,
        "safe_next_step": safe_next_step,
    }

    write_json(AUDIT_OUT / "patch_verification.json", result)
    write_text(AUDIT_OUT / "patch_verification.md", build_md(result))

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())