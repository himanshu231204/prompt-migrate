# TESTING STRATEGY — Correctness before production

## Testing philosophy

Treat the tool as a **state transition engine** with data integrity at risk. Test invariants and failures, not merely happy-path CLI output. Use deterministic fixtures and no live LLM/API calls for core tests.

## Existing baseline

Run from the repository root:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

| Date | Platform | Result |
|---|---|---|
| 2026-10-29 | Linux (reported in the original handoff, not re-run here) | `Ran 7 tests ... OK` |
| 2026-10-30 | Windows 11, Python 3.11.9 | `Ran 7 tests ... FAILED (errors=5)` — 2 pass; 5 error in temp-dir cleanup because SQLite connections are never closed (to be fixed by Phase 1 cycle 1, PR 1 — see `ROADMAP.md`) |
| 2026-10-30 (after PR 1) | Windows 11, Python 3.11.9 | `python -m pytest -q` → `17 passed`; unittest → original 7 `OK` |
| 2026-10-30 (after PR 2) | Windows 11, Python 3.11.9 | `python -m pytest -q` → `45 passed, 1 skipped, 5 xfailed` |
| 2026-10-31 (after PR 3) | Windows 11, Python 3.11.9 | `python -m pytest -q` → `147 passed, 7 skipped, 2 xfailed` |
| 2026-11-01 (after PR 3b) | Windows 11, Python 3.11.9 | `python -m pytest -q` → `262 passed, 8 skipped, 2 xfailed` |
| 2026-11-01 (after PR 4) | Windows 11, Python 3.11.9 | `.venv/Scripts/python -m pytest -q -rxXs` → `469 passed, 16 skipped, 33 warnings`; original unittest suite → `Ran 7 tests ... OK` |
| 2026-11-03 (after the package layout refactor, suite directories and multi-agent example) | Windows 11, Python 3.11.9 | `python -m pytest -q` → `620 passed, 18 skipped, 33 warnings`; original unittest suite → `Ran 7 tests ... OK` |
| 2026-11-05 (after PR 5, `plan`) | Linux, Python 3.13.18 | `python -m pytest -q` → `681 passed, 1 skipped, 39 warnings` (Windows/macOS not re-run for this change) |

GitHub Actions runs the complete suite inside Linux Docker containers, and natively on `windows-latest` and
`macos-latest`, for Python 3.10, 3.12 and 3.13. The native jobs cover the store's Windows-only paths and macOS's
case-insensitive filesystem. Python 3.11 remains covered by the local Windows merge gate (`AGENTS.md`).

Tests currently cover: initial revision and two environments; downgrade; checksum tampering; local drift; bad before-state preconditions; deletion/recovery; invalid environment name; no-op revision; multi-prompt revision/rollback. Phase 1 cycle 1 PR 2 added characterization tests (revision-graph errors, upgrade/downgrade targets, CLI text output and exit codes, the README example), five strict xfails for known bugs, and eight legacy-history compatibility fixtures. PR 3 added error-type, strict-parsing, canonical-equality, new-content, legacy-warning and CLI-warning tests, and removed three of the five xfails. PR 3b added secret-rule unit tests (built from runtime fragments, never literals), revision blocking, output redaction, history and stale-allowlist warnings. PR 4 adds declared-environment schema/adoption, canonical resolution, atomic manifest replacement, read-only SQLite contracts, malformed/missing storage, connection lifecycle, concurrent manifest and initial DB setup, and CLI output/warning coverage. Windows symlink and case-collision paths skip on this host and remain unverified here. PR 6 adds the exit-code table and JSON envelope contract tests. This is **proof of a local prototype**, not extensive production verification.

## Where tests live

| Directory | Suite |
|---|---|
| `tests/test_core.py` | the original seven starter tests; kept at the root so `unittest discover -s tests` still finds them |
| `tests/unit/` | A — parser, graph, strict loader, equality, content rules, errors, legacy compatibility, known bugs, module layout |
| `tests/property/` | B — `hypothesis` state-machine tests (created by PR 5) |
| `tests/integration/` | C — SQLite lifecycle, environment store, locking, declared environments |
| `tests/contract/` | D — CLI exit codes, stdout/stderr, warnings, reads never write |
| `tests/security/` | E — secret scanner, redaction, allowlist, revision blocking |

Shared helpers live in `tests/pmtest.py` and fixtures in `tests/fixtures/`. Test modules never import each other.
Basenames stay unique across directories, because pytest's default `prepend` import mode needs that.

## Required suites

### A. Unit (parser, graph, diff)

- Empty repo, missing files, invalid JSON, wrong object shapes.
- Duplicate/malformed IDs; missing root; two roots; branches; missing parent; cycles.
- Replay deterministic regardless of file iteration order.
- Unicode prompt content, whitespace, nested parameter changes.
- Correct create/update/delete operations, null semantics, no-op reject.
- Invalid prompt/config names and malicious paths.

### B. State-machine / property-based

- For all valid chains: applying to revision `r` yields same state as replay to `r`.
- For all reversible chains: upgrade then downgrade to prior point yields prior state.
- `upgrade head` twice is idempotent.
- Permutations of independent config names do not change logical result.
- Invariant: applied chain is always a prefix of validated source chain.
- Error path leaves config and ledger unchanged.

### C. SQLite integration

- Apply 2+ revisions atomically.
- Delete in same revision as update; rollback restores both.
- Interrupt at checkpoints and verify rollback/no partial ledger update.
- Simulate SQLite busy lock, connection failure, malformed DB, no write permissions.
- Concurrent `upgrade` processes cannot corrupt state; test busy/serialization behavior.
- Truncated/modified applied revision bytes rejected.
- Tampered current `prompts` table and unexpected extra prompt rejected.

### D. CLI contract tests

- `--project` from different working directory.
- `--help`, invalid argument/target, exit codes, stdout/stderr.
- Commands reflect README examples exactly.
- `diff`, `history`, `plan` (when added) do not modify state.
- JSON output stable once published (`test_json_output.py`: one envelope per command, errors, warnings list, redaction).
- Exit codes 0–5 (`test_exit_codes.py`: error class → code table, every `MigrationError` subclass covered, one end-to-end case per code, warnings never change the code).

### E. Security and limits

- No API keys or bearer tokens in revisions/log output.
- Filesystem path traversal and symlink rejection/handling.
- Oversized and deeply nested malicious JSON.
- Atomic file generation and collision-resistant revision IDs.
- Arbitrary code execution attempts rejected (JSON-only).
- Dependency/source-history modification after apply fails.

### F. Future provider and production tests

- Idempotent provider prepare, retry on timeout/429, partial remote failure.
- Release manifest content hash and signature validation.
- Postgres concurrent promotions use compare-and-swap generation.
- Runtime never serves partial release; caches honor release pinning.
- Rollback pointer restores previous bundle while in-flight requests remain consistent.
- Remote drift and reconciliation do not overwrite unknown changes automatically.
- Evaluate integration against Langfuse/MLflow where adapters exist.

## Failure injection matrix

| Fault | Expected outcome |
|---|---|
| Failure after updating one prompt but before ledger insert | Whole local SQLite transaction rolls back |
| Applied migration file mutated | Next check/apply blocks |
| Environment prompt manually changed | Drift error blocks |
| Two revisions created concurrently at same source head | Detect branch; no auto-merge |
| Unknown parent file | Reject source history |
| External provider write fails halfway (future) | Release pointer unchanged; prepare retried/reconciled |
| Two production CI jobs promote simultaneously (future) | At most one wins CAS; loser re-reads state |
| Runtime cannot reach controller (future) | Serve verified pinned release per explicit cache policy |

## Suggested CI stages

1. Static checks / format and type checks.
2. Unit, graph, property-based, SQLite integration and CLI tests run as one full suite in the Linux Docker test image
   (`Dockerfile.ci`) for each supported CI Python version.
3. SQLite integration and fault-injection tests.
4. CLI documentation examples as executable smoke tests.
5. Build/package install tests on Linux, macOS, Windows (when supported).
6. Security scans and dependency checks.
7. Future adapter/evaluation tests (separate jobs, secrets isolated).

## Exit criteria for hardened v0.1

- All must-have PRD acceptance cases automated.
- No known corruption or partial commit in crash/failure tests.
- Clear errors for invalid graph, drift, and target mismatch.
- Documentation is accurate (local-only safety prominently stated).
- CI green across supported Python versions/platforms.
- Basic release artifact install/CLI smoke test works.

## Metrics

Record test counts/coverage and measured performance in CI when available; do not invent performance, scale limits, or coverage percentages in public docs.
