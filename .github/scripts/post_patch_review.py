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


def is_generated_test(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith("tests/generated/")


def is_guardrail_test(path_str: str) -> bool:
    return normalize_path(path_str).lower().startswith("tests/guardrails/")


def is_runtime_python(path_str: str) -> bool:
    rel = normalize_path(path_str).lower()
    return rel.endswith(".py") and not rel.startswith("tests/") and not rel.startswith(".github/")


def is_contract_file(path_str: str) -> bool:
    path_str = normalize_path(path_str)
    return path_str in {
        "auto_updater.py",
        "executor_manager.py",
        "tests/fixtures/system_payloads.py",
    }


def build_md(data: dict) -> str:
    lines = []
    lines.append("Post Patch Review")
    lines.append("")
    lines.append(f"Verdict: {data.get('review_verdict', '')}")
    lines.append("")
    lines.append(f"Summary: {data.get('summary', '')}")
    lines.append("")
    lines.append(f"Contract restored: {'YES' if data.get('contract_restored') else 'NO'}")
    lines.append(f"Minimal change: {'YES' if data.get('minimal_change') else 'NO'}")
    lines.append(f"Logic preserved: {'YES' if data.get('logic_preserved') else 'NO'}")
    lines.append("")
    lines.append("Reasons")
    reasons = data.get("reasons", []) or []
    if reasons:
        for item in reasons:
            lines.append(f"- {item}")
    else:
        lines.append("- Nessuna reason disponibile.")
    return "\n".join(lines)


def main() -> int:
    verification = read_json(AUDIT_OUT / "patch_verification.json")
    apply_report = read_json(AUDIT_OUT / "patch_apply_report.json")
    targeted_tests = read_json(AUDIT_OUT / "targeted_test_results.json")
    candidate_payload = read_json(AUDIT_OUT / "patch_candidate.json")

    verdict = str(verification.get("verdict", "")).strip().lower()
    candidate = candidate_payload.get("patch_candidate") or {}

    target = normalize_path(apply_report.get("target_file") or candidate.get("target_file") or "")
    related = normalize_path(apply_report.get("related_source_file") or candidate.get("related_source_file") or "")
    strategy = str(apply_report.get("strategy") or candidate.get("strategy") or "").strip()
    issue_type = str(apply_report.get("issue_type") or candidate.get("issue_type") or "").strip()
    classification = str(apply_report.get("classification") or candidate.get("classification") or "").strip()
    applied = bool(apply_report.get("applied", False))

    failures = targeted_tests.get("failure_count")
    if not isinstance(failures, int):
        failures = None

    executed_targets = targeted_tests.get("targets", []) or []

    review = {
        "review_verdict": "reject",
        "minimal_change": False,
        "logic_preserved": False,
        "contract_restored": False,
        "summary": "",
        "reasons": [],
    }

    if not applied:
        review["review_verdict"] = "reject"
        review["summary"] = "Patch was not applied."
        review["reasons"] = [
            f"Verifier verdict: {verdict or 'unknown'}",
            "Apply stage did not produce a real committable diff.",
        ]

    elif verdict in {"approve", "weak-approve"}:
        review["minimal_change"] = True
        review["logic_preserved"] = True

        if is_contract_file(target) and issue_type == "missing_public_contract":
            review["contract_restored"] = True

        if failures == 0:
            review["review_verdict"] = "approve"
            review["summary"] = "Patch verified and targeted tests passed."
            review["reasons"] = [
                f"Patch verifier verdict: {verdict}",
                f"Patch strategy: {strategy or 'unknown'}",
                f"Target file: {target or 'unknown'}",
                f"Executed targeted tests: {len(executed_targets)}",
            ]
        elif failures is None and is_runtime_python(target):
            review["review_verdict"] = "weak-approve"
            review["summary"] = "Runtime patch applied with real diff, but no targeted tests were available."
            review["reasons"] = [
                f"Patch verifier verdict: {verdict}",
                f"Target runtime file: {target or 'unknown'}",
                "No targeted runtime tests available; keeping conservative weak-approve.",
            ]
        else:
            review["review_verdict"] = "weak-approve"
            review["summary"] = "Patch acceptable but targeted tests still show failures."
            review["reasons"] = [
                f"Patch verifier verdict: {verdict}",
                f"Target file: {target or 'unknown'}",
                f"Targeted test failures: {failures}",
            ]

    elif verdict == "review":
        review["minimal_change"] = classification in {"AUTO_FIX_SAFE", "AUTO_FIX_REVIEW"}
        review["logic_preserved"] = classification in {"AUTO_FIX_SAFE", "AUTO_FIX_REVIEW"}
        review["contract_restored"] = bool(is_contract_file(target) and issue_type == "missing_public_contract")

        if is_runtime_python(target) and failures == 0:
            review["review_verdict"] = "approve"
            review["summary"] = "Runtime patch was review-level but targeted tests passed."
            review["reasons"] = [
                f"Target runtime file: {target}",
                "Review-level patch promoted because targeted tests are green.",
            ]
        elif is_runtime_python(target) and failures is None:
            review["review_verdict"] = "review"
            review["summary"] = "Runtime patch changed code, but there is no targeted test evidence yet."
            review["reasons"] = [
                f"Target runtime file: {target}",
                "No targeted tests available for runtime module.",
                "Keeping review verdict conservatively.",
            ]
        elif is_guardrail_test(target):
            review["review_verdict"] = "review"
            review["summary"] = "Guardrail test patch remains review-only."
            review["reasons"] = [
                "Guardrail tests are sensitive by design.",
                f"Target file: {target or 'unknown'}",
            ]
        else:
            review["review_verdict"] = "review"
            review["summary"] = "Patch requires human or deeper AI review."
            review["reasons"] = [
                "Verifier flagged patch as reviewable but not safe for blind approval.",
                f"Strategy: {strategy or 'unknown'}",
                f"Target: {target or 'unknown'}",
                f"Classification: {classification or 'unknown'}",
            ]

    else:
        review["review_verdict"] = "reject"
        review["summary"] = "Patch rejected by verifier."
        review["reasons"] = [
            f"Verifier verdict: {verdict or 'unknown'}",
            "Patch not considered safe to keep in the loop.",
        ]

    if related and related != target:
        review["reasons"].append(f"Related source file: {related}")

    write_json(AUDIT_OUT / "post_patch_review.json", review)
    write_text(AUDIT_OUT / "post_patch_review.md", build_md(review))

    print(json.dumps(review, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())