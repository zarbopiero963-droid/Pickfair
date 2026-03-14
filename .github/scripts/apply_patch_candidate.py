#!/usr/bin/env python3

import json
import re
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
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def extract_patch_body(target_file: str, patch_text: str) -> str:
    patch_text = patch_text.strip()

    if "*** Begin Patch" in patch_text:
        match = re.search(
            rf"\*\*\*\s+Update File:\s+{re.escape(target_file)}\s*(.*?)(\*\*\*\s+End Patch|$)",
            patch_text,
            re.S,
        )
        if match:
            return match.group(1).strip()

    return patch_text


def split_hunks(patch_body: str) -> list[list[str]]:
    lines = patch_body.splitlines()
    hunks = []
    current = []

    for line in lines:
        if line.startswith("@@"):
            if current:
                hunks.append(current)
            current = []
            continue
        current.append(line)

    if current:
        hunks.append(current)

    return hunks


def apply_custom_hunks_to_text(original_text: str, patch_text: str, target_file: str) -> str:
    patch_body = extract_patch_body(target_file, patch_text)
    hunks = split_hunks(patch_body)

    if not hunks:
        raise ValueError(f"Nessun hunk applicabile trovato per {target_file}")

    updated_text = original_text

    for hunk in hunks:
        original_lines = []
        new_lines = []

        for line in hunk:
            if line.startswith("-"):
                original_lines.append(line[1:])
            elif line.startswith("+"):
                new_lines.append(line[1:])
            elif line.startswith(" "):
                original_lines.append(line[1:])
                new_lines.append(line[1:])
            else:
                original_lines.append(line)
                new_lines.append(line)

        original_chunk = "\n".join(original_lines).strip("\n")
        new_chunk = "\n".join(new_lines).strip("\n")

        if not original_chunk:
            raise ValueError(f"Hunk senza contesto utile per {target_file}")

        replaced = False
        candidates = [
            original_chunk,
            original_chunk + "\n",
            "\n" + original_chunk,
            "\n" + original_chunk + "\n",
        ]

        for candidate in candidates:
            if candidate in updated_text:
                replacement = new_chunk
                if candidate.startswith("\n") and not replacement.startswith("\n"):
                    replacement = "\n" + replacement
                if candidate.endswith("\n") and not replacement.endswith("\n"):
                    replacement = replacement + "\n"

                updated_text = updated_text.replace(candidate, replacement, 1)
                replaced = True
                break

        if not replaced:
            raise ValueError(
                f"Impossibile trovare il contesto del patch nel file {target_file}"
            )

    return updated_text


def apply_patch_to_file(target_file: str, patch_text: str) -> str:
    path = ROOT / target_file
    if not path.exists():
        raise FileNotFoundError(f"File target non trovato: {target_file}")

    original_text = read_text(path)
    updated_text = apply_custom_hunks_to_text(original_text, patch_text, target_file)
    path.write_text(updated_text, encoding="utf-8")
    return str(path.relative_to(ROOT)).replace("\\", "/")


def load_patch_and_verification() -> tuple[dict, dict]:
    patch_candidate = read_json(AUDIT_OUT / "patch_candidate.json")
    patch_verification = read_json(AUDIT_OUT / "patch_verification.json")
    return patch_candidate, patch_verification


def should_apply(verification: dict) -> tuple[bool, str]:
    verdict = str(verification.get("verdict", "")).strip().lower()
    if verdict in {"approve", "weak-approve"}:
        return True, verdict
    return False, verdict or "unknown"


def main() -> int:
    patch_candidate, patch_verification = load_patch_and_verification()

    if not patch_candidate:
        msg = "Patch candidate mancante."
        write_text(AUDIT_OUT / "patch_apply_report.md", msg + "\n")
        write_json(AUDIT_OUT / "patch_apply_report.json", {"applied": False, "error": msg})
        print(msg)
        return 0

    approved, verdict = should_apply(patch_verification)
    if not approved:
        msg = f"Patch non applicata. Verdict verifier: {verdict}"
        write_text(AUDIT_OUT / "patch_apply_report.md", msg + "\n")
        write_json(
            AUDIT_OUT / "patch_apply_report.json",
            {
                "applied": False,
                "verdict": verdict,
                "error": msg,
            },
        )
        print(msg)
        return 0

    target_files = patch_candidate.get("target_files", []) or []
    proposed_patches = patch_candidate.get("proposed_patches", []) or []
    summary = patch_candidate.get("summary") or "no-summary"

    if not target_files or not proposed_patches:
        msg = "Patch candidate incompleta: target_files o proposed_patches mancanti."
        write_text(AUDIT_OUT / "patch_apply_report.md", msg + "\n")
        write_json(
            AUDIT_OUT / "patch_apply_report.json",
            {
                "applied": False,
                "verdict": verdict,
                "summary": summary,
                "error": msg,
            },
        )
        print(msg)
        return 0

    report: list[str] = []
    report.append("Patch Apply Report")
    report.append("")
    report.append(f"Verifier verdict: {verdict}")
    report.append(f"Summary: {summary}")
    report.append("")
    report.append("Target files:")
    for file in target_files:
        report.append(f"- {file}")
    report.append("")

    applied_targets = []
    errors = []

    for item in proposed_patches:
        target_file = str(item.get("target_file", "")).strip()
        patch_text = str(item.get("patch", "")).strip()

        if not target_file or not patch_text:
            errors.append(f"Patch item non valido: {item}")
            continue

        try:
            applied_target = apply_patch_to_file(target_file, patch_text)
            applied_targets.append(applied_target)
        except Exception as exc:
            errors.append(f"{target_file}: {type(exc).__name__}: {exc}")

    applied = len(applied_targets) > 0 and not errors

    report.append("Applied targets:")
    if applied_targets:
        for target in applied_targets:
            report.append(f"- {target}")
    else:
        report.append("- Nessun file applicato.")
    report.append("")

    if errors:
        report.append("Errors:")
        for err in errors:
            report.append(f"- {err}")
        report.append("")

    if applied:
        report.append("La patch multi-file è stata applicata nel workspace del runner.")
        report.append("Il commit/push verrà fatto successivamente dallo step branch/PR del workflow.")
    else:
        report.append("La patch multi-file non è stata applicata completamente.")

    write_text(AUDIT_OUT / "patch_apply_report.md", "\n".join(report) + "\n")
    write_json(
        AUDIT_OUT / "patch_apply_report.json",
        {
            "applied": applied,
            "applied_targets": applied_targets,
            "target_files": target_files,
            "verdict": verdict,
            "summary": summary,
            "errors": errors,
        },
    )

    if applied:
        print(f"Patch multi-file applicata a {len(applied_targets)} file.")
    else:
        print("Patch multi-file non applicata completamente.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())