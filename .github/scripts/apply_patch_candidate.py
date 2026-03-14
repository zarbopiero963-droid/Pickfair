#!/usr/bin/env python3

import json
import re
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


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd or ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        out = (proc.stdout or "") + ("\n" if proc.stdout and proc.stderr else "") + (proc.stderr or "")
        return proc.returncode, out
    except Exception as exc:
        return 999, f"{type(exc).__name__}: {exc}"


def extract_target_file_and_new_block(diff_text: str) -> tuple[str, str]:
    """
    Supporta patch candidate semplici nel formato:
    *** Update File: path.py
    @@
    ... eventuale contesto ...
    + nuove righe

    Estrae:
    - target_file
    - blocco di righe aggiunte consecutive dopo il primo hunk
    """
    target_match = re.search(r"^\*\*\*\s+Update File:\s+(.+)$", diff_text, flags=re.MULTILINE)
    if not target_match:
        raise ValueError("Impossibile trovare '*** Update File:' nella patch candidate.")

    target_file = target_match.group(1).strip()

    lines = diff_text.splitlines()
    inside_hunk = False
    added_lines: list[str] = []

    for line in lines:
        if line.startswith("@@"):
            inside_hunk = True
            continue

        if not inside_hunk:
            continue

        if line.startswith("*** End Patch"):
            break

        if line.startswith("+") and not line.startswith("+++"):
            added_lines.append(line[1:])

    if not added_lines:
        raise ValueError("Nessuna riga aggiunta trovata nella patch candidate.")

    return target_file, "\n".join(added_lines).rstrip() + "\n"


def insert_after_anchor(file_text: str, block: str) -> str:
    anchor = 'DEFAULT_UPDATE_URL = "https://api.github.com/repos/petiro/Pickfair/releases/latest"'
    if anchor not in file_text:
        raise ValueError("Anchor DEFAULT_UPDATE_URL non trovato nel file target.")
    if "class AutoUpdater:" in file_text:
        return file_text

    replacement = anchor + "\n\n" + block.rstrip() + "\n"
    return file_text.replace(anchor, replacement, 1)


def apply_auto_updater_patch(target_file: str, diff_text: str) -> str:
    path = ROOT / target_file
    if not path.exists():
        raise FileNotFoundError(f"File target non trovato: {target_file}")

    original = read_text(path)
    _, block = extract_target_file_and_new_block(diff_text)
    updated = insert_after_anchor(original, block)
    path.write_text(updated, encoding="utf-8")
    return str(path.relative_to(ROOT)).replace("\\", "/")


def load_patch_and_verification() -> tuple[dict, dict]:
    patch_candidate = read_json(AUDIT_OUT / "patch_candidate.json")
    patch_verification = read_json(AUDIT_OUT / "patch_verification.json")
    return patch_candidate, patch_verification


def should_apply(verification: dict) -> tuple[bool, str]:
    verdict = (verification.get("verdict") or "").strip().lower()
    if verdict in {"approve", "weak-approve"}:
        return True, verdict
    return False, verdict or "unknown"


def git_commit(target_file: str, summary: str) -> dict:
    result = {}

    code, out = run(["git", "status", "--short"])
    result["git_status_before"] = out
    if code != 0:
        result["git_status_before_code"] = code
        return result

    code, out = run(["git", "add", target_file])
    result["git_add_code"] = code
    result["git_add_output"] = out
    if code != 0:
        return result

    commit_msg = f"Apply AI patch candidate: {summary[:72]}".strip()
    code, out = run(["git", "commit", "-m", commit_msg])
    result["git_commit_code"] = code
    result["git_commit_output"] = out
    result["git_commit_message"] = commit_msg
    return result


def main() -> int:
    patch_candidate, patch_verification = load_patch_and_verification()

    if not patch_candidate:
        msg = "Patch candidate mancante."
        write_text(AUDIT_OUT / "patch_apply_report.md", msg + "\n")
        print(msg)
        return 0

    approved, verdict = should_apply(patch_verification)
    if not approved:
        msg = f"Patch non applicata. Verdict verifier: {verdict}"
        write_text(AUDIT_OUT / "patch_apply_report.md", msg + "\n")
        print(msg)
        return 0

    target_file = (patch_candidate.get("target_file") or "").strip()
    proposed_patch = patch_candidate.get("proposed_patch") or ""
    summary = patch_candidate.get("summary") or "no-summary"

    if not target_file or not proposed_patch:
        msg = "Patch candidate incompleta: target_file o proposed_patch mancanti."
        write_text(AUDIT_OUT / "patch_apply_report.md", msg + "\n")
        print(msg)
        return 0

    report: list[str] = []
    report.append("Patch Apply Report")
    report.append("")
    report.append(f"Verifier verdict: {verdict}")
    report.append(f"Target file: {target_file}")
    report.append(f"Summary: {summary}")
    report.append("")

    try:
        applied_target = apply_auto_updater_patch(target_file, proposed_patch)
        report.append(f"Patch applicata a: {applied_target}")
        report.append("")

        git_info = git_commit(applied_target, summary)
        report.append("Git results")
        report.append(f"- git_add_code: {git_info.get('git_add_code')}")
        report.append(f"- git_commit_code: {git_info.get('git_commit_code')}")
        report.append("")
        report.append("git commit output")
        report.append(git_info.get("git_commit_output", ""))

        write_text(AUDIT_OUT / "patch_apply_report.md", "\n".join(report) + "\n")
        write_json(
            AUDIT_OUT / "patch_apply_report.json",
            {
                "applied": True,
                "target_file": applied_target,
                "verdict": verdict,
                "summary": summary,
                "git": git_info,
            },
        )
        print(f"Patch applicata a {applied_target}")
        return 0

    except Exception as exc:
        report.append(f"Errore applicazione patch: {type(exc).__name__}: {exc}")
        write_text(AUDIT_OUT / "patch_apply_report.md", "\n".join(report) + "\n")
        write_json(
            AUDIT_OUT / "patch_apply_report.json",
            {
                "applied": False,
                "target_file": target_file,
                "verdict": verdict,
                "summary": summary,
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
        print(f"Errore applicazione patch: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())