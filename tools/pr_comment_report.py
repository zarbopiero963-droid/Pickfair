import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "guardrails"


def read_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def build_markdown():

    report = read_json(GUARD / "ai_reasoning_guard_report.json")
    targeted = read_json(GUARD / "targeted_tests.json")

    decision = report.get("decision", {})
    findings = report.get("findings", [])

    md = []
    md.append("## AI Guardrails Report")
    md.append("")

    md.append(f"**Final Risk:** `{decision.get('final_risk')}`")
    md.append(f"**Block Merge:** `{decision.get('block_merge')}`")
    md.append("")

    md.append("### Changed Files")
    for f in report.get("changed_files", []):
        md.append(f"- `{f}`")

    md.append("")
    md.append("### Impacted Modules")
    for m in report.get("impact_analysis", {}).get("impacted_modules", []):
        md.append(f"- `{m}`")

    md.append("")
    md.append("### Targeted Tests")
    for t in targeted.get("targeted_tests", []):
        md.append(f"- `{t}`")

    md.append("")
    md.append("### Findings")

    for f in findings[:10]:
        md.append(
            f"- `{f.get('severity')}` {f.get('category')} → {f.get('file')} : {f.get('message')}"
        )

    return "\n".join(md)


def comment_pr(body):

    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    pr = os.environ["PR_NUMBER"]

    url = f"https://api.github.com/repos/{repo}/issues/{pr}/comments"

    headers = {"Authorization": f"Bearer {token}"}

    requests.post(url, headers=headers, json={"body": body})


def main():

    if "PR_NUMBER" not in os.environ:
        return

    md = build_markdown()
    comment_pr(md)


if __name__ == "__main__":
    main()