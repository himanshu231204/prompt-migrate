# Changelog

All notable changes to PromptMigrate. Before 1.0, CLI and file contracts may change; such changes are marked **Contract**.

## Unreleased

### Phase 1 cycle 1 — PR 2: characterization tests and legacy fixtures

- Tests only; no behaviour change.
- Pinned: revision-graph errors, upgrade/downgrade target rules, CLI text output and exit codes, and the README
  five-minute example as a smoke test.
- Pinned as strict xfails, each naming its fixing PR: undeclared env reports OK and read commands create files (PR 4);
  `1`/`true` equality, duplicate JSON keys and `NaN` (PR 3).
- Added: legacy compatibility fixtures under `tests/fixtures/legacy/`, which must stay usable for the whole cycle.

### Phase 1 cycle 1 — PR 1: connection lifecycle and cross-OS CI

- Fixed: every command closes its SQLite connection. Leaked connections kept `states/<env>.sqlite3` locked, so on
  Windows 5 of 7 tests errored during cleanup.
- Test fix: `test_state_drift_detected` closes the SQLite connection it opens itself (assertions unchanged).
- Added: `dev` extra (`pytest`, `hypothesis`, `pytest-cov`). pytest now finds `src/` without `PYTHONPATH`.
- CI: Ubuntu, Windows and macOS × Python 3.10, 3.12, 3.13, run with pytest.
