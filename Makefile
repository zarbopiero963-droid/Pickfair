PYTHON ?= python
PIP ?= pip
PYTEST ?= pytest

.PHONY: install lint typecheck security audit test ci shallow-tests test-cleanup-priority

install:
	$(PIP) install -r requirements.txt
	@if [ -f requirements-dev.txt ]; then $(PIP) install -r requirements-dev.txt; fi
	$(PIP) install ruff mypy bandit pip-audit

lint:
	ruff check .

typecheck:
	mypy . || true

security:
	bandit -r . -x tests,docs,.venv,__pycache__

audit:
	pip-audit || true

test:
	$(PYTEST) tests -q

shallow-tests:
	$(PYTHON) scripts/find_shallow_tests.py

test-cleanup-priority:
	$(PYTHON) scripts/prioritize_test_cleanup.py

ci: lint typecheck security audit test