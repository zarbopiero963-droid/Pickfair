import json
from pathlib import Path

from tools.repo_guardrail import extract_top_level_dependencies

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_DEPS_PATH = ROOT / "guardrails" / "allowed_dependencies.json"


def test_allowed_dependencies_manifest_exists_and_is_not_empty():
    assert ALLOWED_DEPS_PATH.exists(), "Missing guardrails/allowed_dependencies.json"

    data = json.loads(ALLOWED_DEPS_PATH.read_text(encoding="utf-8"))
    allowed = data.get("allowed_dependencies", [])

    assert isinstance(allowed, list)
    assert allowed, "allowed_dependencies.json contains no allowed dependencies"


def test_no_unapproved_top_level_dependencies():
    allowed = set(
        json.loads(ALLOWED_DEPS_PATH.read_text(encoding="utf-8")).get(
            "allowed_dependencies",
            [],
        )
    )
    current = set(extract_top_level_dependencies(ROOT))

    unexpected = sorted(current - allowed)

    assert not unexpected, (
        "New top-level dependencies detected:\n"
        + "\n".join(f"- {dep}" for dep in unexpected)
    )


def test_dependency_graph_values_are_lists_of_module_names():
    graph = extract_top_level_dependencies(ROOT)

    assert isinstance(graph, dict)
    assert graph, "Dependency graph is empty"

    for module_name, deps in graph.items():
        assert isinstance(module_name, str)
        assert isinstance(deps, list)
        assert all(isinstance(dep, str) for dep in deps)