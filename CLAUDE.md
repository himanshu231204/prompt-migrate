# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

PromptMigrate is an Alembic-inspired, local-first, stdlib-only Python (≥ 3.10) CLI for declarative migrations of AI prompt and agent configuration: ordered JSON revisions, per-environment applied state, reversible upgrade/downgrade, integrity and drift checks.

All rules, the architecture, the current baseline and scope are in [`AGENTS.md`](AGENTS.md); read it before any change. Design docs start at `docs/HANDOFF.md`.

## Commands

```bash
python -m pip install -e ".[dev]"                     # optional; pyproject sets pythonpath=src for pytest
python -m pytest -q                                   # all tests
python -m pytest tests/test_core.py::PromptMigrateTests::test_state_drift_detected   # one test
python -m pytest tests/security                       # one suite: unit, integration, contract, security
PYTHONPATH=src python -m unittest discover -s tests -v   # original unittest suite (select with -k)
PYTHONPATH=src python -m promptmigrate --project <dir> history   # CLI from source
```

PowerShell: `$env:PYTHONPATH='src'`. No linter or type checker is configured. Test helpers are in `tests/pmtest.py`; `tests/` is not a package.
