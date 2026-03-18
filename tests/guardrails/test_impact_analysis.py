from pathlib import Path

import pytest

from tools.repo_guardrail import impact_analysis

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("changed_files", "expected_changed_modules", "expected_impacted_modules"),
    [
        (
            [],
            [],
            [],
        ),
        (
            ["controllers/dutching_controller.py"],
            ["controllers.dutching_controller"],
            ["controllers.dutching_controller"],
        ),
        (
            ["telegram_listener.py"],
            ["telegram_listener"],
            ["telegram_listener", "main", "app_modules.telegram_module"],
        ),
    ],
)
def test_impact_analysis_returns_expected_modules(
    changed_files,
    expected_changed_modules,
    expected_impacted_modules,
):
    result = impact_analysis(ROOT, changed_files)

    assert set(result.keys()) == {
        "changed_modules",
        "impacted_modules",
        "impacted_paths",
    }

    assert result["changed_modules"] == expected_changed_modules
    assert isinstance(result["impacted_modules"], list)
    assert isinstance(result["impacted_paths"], list)

    for module_name in expected_impacted_modules:
        assert module_name in result["impacted_modules"]


def test_impact_analysis_paths_are_python_paths():
    result = impact_analysis(
        ROOT,
        ["controllers/dutching_controller.py", "telegram_listener.py"],
    )

    for path in result["impacted_paths"]:
        assert path.endswith(".py")
        assert "/" in path or path.endswith(".py")