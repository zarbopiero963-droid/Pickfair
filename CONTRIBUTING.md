# Contributing to Pickfair

Thank you for contributing to Pickfair.

## Development baseline

- Python 3.11
- Ruff for linting
- MyPy for type checking
- Bandit for security scanning
- pip-audit for dependency vulnerability audit
- pytest for test suite execution

## Before pushing changes

Run:

```bash
make lint
make typecheck
make security
make audit
make test
make shallow-tests
make test-cleanup-priority