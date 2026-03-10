import ast
import json
from pathlib import Path

ROOT = Path(".")

report = {
    "files": [],
    "functions": [],
    "imports": [],
}

for file in ROOT.rglob("*.py"):

    if "venv" in str(file) or ".venv" in str(file):
        continue

    try:
        tree = ast.parse(file.read_text())
    except Exception:
        continue

    report["files"].append(str(file))

    for node in ast.walk(tree):

        if isinstance(node, ast.FunctionDef):

            report["functions"].append({
                "file": str(file),
                "function": node.name,
                "line": node.lineno
            })

        if isinstance(node, ast.Import):

            for n in node.names:
                report["imports"].append({
                    "file": str(file),
                    "module": n.name
                })

        if isinstance(node, ast.ImportFrom):

            report["imports"].append({
                "file": str(file),
                "module": node.module
            })


Path("repo_autopsy_report.json").write_text(
    json.dumps(report, indent=2)
)

print("REPO AUTOPSY GENERATED")
print("FILES:", len(report["files"]))
print("FUNCTIONS:", len(report["functions"]))
print("IMPORTS:", len(report["imports"]))