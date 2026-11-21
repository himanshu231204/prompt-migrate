# ROADMAP — From local prototype to reliable open-source project

> Milestones are **plans**, not shipping promises. Status checked against the code on 2026-11-16.

## Phase 0 — Existing proof of concept

**State:** implemented and 7 tests passed in prior starter; limited assurance.

- [x] Python package and `promptmigrate` CLI entry point.
- [x] Workspace initialization and JSON drafts.
- [x] JSON before/after revision generation.
- [x] Linear `down_revision` chain and history replay.
- [x] Local SQLite per-environment state.
- [x] Upgrade, downgrade, current, check, get, diff.
- [x] Applied checksums and local drift checks.
- [x] Multi-config changes inside one SQLite transaction.
- [ ] Broad fault-injection and cross-platform verification.

## Phase 1 — Harden migration core (first implementation priority)

**Status:** in progress. Phase 1 is delivered in cycles. Cycle 1 is complete; cycle 2 is under way (v0 frozen, ADR-025; protocol v1, ADR-026; `restamp`, ADR-027; no-clobber revision writes, PR 10; source-only `validate`, ADR-028). The integrity guidance now distinguishes v0 raw-byte checks from v1 canonical-content checks. Package-install smoke tests are shipped (PR #67, #13; hardened in PR #78); CI passed on `main` at `059a1b9`. Finishing cycle 2 does **not** finish Phase 1.

### Cycle 1 (PRs 1–6 + 3b)

- [x] Connection lifecycle fix; Linux Docker CI matrix across Python 3.10, 3.12 and 3.13, plus native Windows and macOS jobs (`.github/workflows/ci.yml`). Linux/macOS support is claimed only after a remote CI run passes. (2026-11-16: PRs and `main` run Windows 3.10/3.13 and macOS 3.13; the full native matrix runs weekly; one `ci-pass` check gates merges.)
- [x] Characterization tests and legacy compatibility fixtures (`tests/fixtures/legacy`, `tests/fixtures/legacy_breaking`).
- [x] Strict parsing (duplicate keys, NaN, size/depth, symlinks), compatibility tiers, canonical equality (`protocol/`).
- [x] Heuristic secret safeguard: `revision` blocks, `diff`/`get` redact, reviewed allowlist (`secretscan.py`).
- [x] Declared environments; read commands never write (`store/`, `env add`, `env list`).
- [x] Refactor core into testable modules incrementally, without breaking the CLI (ADR-022; `core.py` is a re-export facade).
- [x] Read-only `plan` with a property-based plan==apply test (`plan.py`, `commands/plan.py`).
- [x] Typed errors, exit codes 0–5, `--output json` (`output.py`; schema `promptmigrate.output/1`; ADR-024).

### Remaining after cycle 1 (cycle 2+)

- [x] Freeze v0.x artifact semantics formally; protocol v1 with canonical revision hashes (fixes the CRLF false-tamper risk for new revisions).
  - 2026-11-13: v0 frozen (ADR-025); protocol v1 with canonical checksums shipped, and new revisions are v1 with LF line endings (ADR-026). Baseline after PR 8: 802 passed, 18 skipped.
  - 2026-11-13: explicit `restamp` for v0 ledger rows whose mismatch is line endings only (ADR-027). Baseline after PR 9: 854 passed, 18 skipped.
  - 2026-11-14: review fix: `restamp` removed from the docs' list of commands that reject an eligible line-ending-only row with exit 4 (it re-stamps and succeeds). Baseline unchanged: 854 passed, 18 skipped.
- [x] Atomic revision file generation and collision handling.
  - 2026-11-14: `revision` writes through `project.write_new_file` under the project lock: no overwrite, no partial file where hard links are supported, colliding ids regenerated (I17). CLI_SPEC notes the no-hard-link fallback is not crash-atomic. New files get the umask mode from the OS at creation; the process umask is never read or changed. Baseline after PR 10: 883 passed, 19 skipped.
- [x] CLI `--version` flag: prints package version via `importlib.metadata` with fallback to `__version__` (PR 70, #16).
- [x] Package-install smoke tests (#13, PR #67): wheel and sdist install into separate virtual environments outside the checkout, then run a full CLI round trip. The import guard also verifies namespace package portions (PR #78). The round trip also runs the installed `validate` in text mode (an `OK: ` line) and JSON mode (`data.revisions`), so a package that loses the command fails the smoke test (#87). Baseline on `main` at `059a1b9`: 890 passed, 19 skipped (Windows 11, Python 3.11.9).
- [x] Static type checking (#20): `mypy` runs over `src/` in lenient mode with the config in `pyproject.toml`, CI's `type-check` job covers Python 3.10/3.12/3.13, and the real type errors it found are fixed; the gate checks every CI platform from any host. `mypy` is a dev-only dependency capped at one minor release (`>=2.4,<2.5`); runtime stays stdlib-only. Baseline: 913 passed, 3 skipped (Linux, Python 3.13.18).
- [x] `validate` command (#10).
  - 2026-11-16: `StrictValidationError` (exit 3) is added. Baseline: 893 passed, 19 skipped.
  - 2026-11-16: source-only `validate [--strict] [--drafts-clean]` is shipped (ADR-028). It never touches `states/` (I19). Baseline after PR 11: 925 passed, 21 skipped; 930 passed, 21 skipped after merging `main` with #20 (Windows 11, Python 3.11.9). Running it in the install smoke test is follow-up #87.
- [x] Concurrency tests for concurrent `upgrade` runs (#11): `tests/integration/test_concurrent_upgrade.py` runs two real processes doing `upgrade head --env dev` on one project; exactly one applies the pending revisions, the other sees nothing to do or fails closed; `prompts` equals replay of the applied ledger prefix with no duplicate ledger rows. Passes on Windows, Linux and macOS CI (no sleeps-as-synchronization). Baseline: 933 passed, 22 skipped (Windows 11, Python 3.11.9).
- [x] Fault injection in the `apply.py` transaction (#12): `tests/integration/test_apply_fault_injection.py` raises at every read, write and commit point of `upgrade`/`downgrade` (35 tests, both directions, plus 6 typed-error checks on the read points); each fault leaves rows and ledger unchanged, `check` clean, connections closed and a retry succeeding. An AST guard fails when `apply.migrate` gains an uncovered call. Mutation check: committing per step turns 15 tests red. It also fixes #93: the `prompts` read inside `apply.migrate` now raises `StorageError` like `_verify` (one shared `_stored_state` helper; exit code 5 unchanged). Baseline: 981 passed, 22 skipped (Windows 11, Python 3.11.9).
- [ ] The rest of the fault-injection suite (#31, #32, #33); the lock and file-mode follow-ups (#79) are fixed.
- [x] README quick-start commands run as a CLI smoke test against a temporary project (#21).
- [x] Append-only events table (#14, ADR-029): `store/events.py`; `upgrade`, `downgrade` and `restamp` append events in the ledger's transaction; old state DBs are adopted on their first successful mutation; triggers reject `UPDATE`/`DELETE`; fault injection proves an event never exists without its ledger change and vice versa. Baseline: 1011 passed, 22 skipped (Windows 11, Python 3.11.9). A command to read events is follow-up work.
- [ ] `rebase` for unapplied revisions (#15): ADR-030 accepted; not yet implemented.

**Exit:** correct, stable local CLI with comprehensive automated evidence and honest documentation.

## Phase 2 — Evaluation and policy gates

- [ ] Evaluation suite interface and policy config format.
- [ ] Golden datasets and rule-based checks.
- [ ] Pluggable LLM-judge evaluators as optional plugins, with uncertainty handling.
- [ ] Evaluation report bound to candidate content hash.
- [ ] CI required-pass gate / explicit failure reason.
- [ ] Critical checks for tool permission and output schema compatibility.

**Exit:** candidate revision requires verifiable quality evidence for opted-in workflows.

## Phase 3 — Real production release protocol

- [ ] Immutable configuration bundle / release manifest.
- [ ] Central PostgreSQL environment state and audit trail.
- [ ] Release prepare/verify/activate lifecycle and CAS pointer.
- [ ] Python runtime SDK with pinning/caching/compatibility controls.
- [ ] Idempotent adapter interface + at least one supported provider integration.
- [ ] Reconciliation for external partial failures and drift.
- [ ] Real promotion and rollback controls with approvals.

**Exit:** can safely demonstrate end-to-end staging→production deployment under injected failures, without partial activation.

## Phase 4 — Stable community release

- [x] Python version classifiers in pyproject.toml match the CI matrix (3.10, 3.12, 3.13).
- [ ] Stable protocol compatibility/versioning policy.
- [ ] Maintainer security disclosure process and supply-chain checks.
- [ ] Contributor guide, examples for several frameworks. (Started early, 2026-11-03: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue and PR templates, and a root `SECURITY.md` pointing to GitHub private vulnerability reporting. 2026-11-05: `AGENTS.md` holds every rule for AI coding agents, including updating this file and `CHANGELOG.md` on each commit. 2026-11-15: `AGENTS.md` gained commands, code style and issue/PR rules; every tool-specific agent file now points to it. 2026-11-16: `AGENTS.md` was restructured after large open-source agent files and gained a top summary of the highest-damage rules, a Working style section and an Ask first / Never boundaries list. The backlog is filed as single-task GitHub issues, with one milestone per phase. An advisory Open CodeReview bot comments on PRs and is outside the merge gate.)
- [ ] Published PyPI package and documented upgrade migration policy. (2026-11-19: `promptmigrate-cli` 0.1.0 is published on PyPI by the trusted-publishing `release` workflow (#55); the maintainer release guide is `docs/RELEASING.md`. The documented upgrade policy (#56) remains.)
- [ ] Cross-platform docs and support matrix.
- [ ] Public comparison and case studies grounded in measured behavior.

## Deliberate non-goals early

No SaaS dashboard, no visual prompt editor, no paid cloud control plane, no direct model-weight handling, no proprietary protocol, and no blanket promises that prompt versions imply reproducible LLM outputs.

## First next step

Phase 1 cycle 2 is under way. Protocol v1 is shipped (ADR-026), so new revisions are immune to formatting-only changes; integrity guidance now reflects the separate v0 and v1 rules. `restamp`, an explicit, opt-in re-stamp of v0 ledger rows whose mismatch is line endings only, is shipped (ADR-027); v0 hash semantics are unchanged. Verifying commands name `restamp` when a mismatch is line endings only. Revision files are never overwritten, and are written atomically where hard links are supported (PR 10); the no-hard-link fallback is not crash-atomic. Package-install smoke tests are shipped (PR #67). The README quick-start runs as a separate CLI smoke test (#21). The source-only `validate` command is shipped (#10, ADR-028). The concurrent `upgrade` test (#11) is shipped (`tests/integration/test_concurrent_upgrade.py`, two real processes coordinated with multiprocessing events, no sleeps; 933 passed, 22 skipped on Windows 11 / Python 3.11.9). The lock and file-mode follow-ups (#79) are done. The `apply.py` transaction fault-injection suite (#12) is shipped (`tests/integration/test_apply_fault_injection.py`; 981 passed, 22 skipped on Windows 11 / Python 3.11.9) and fixes #93. The append-only events table (#14, ADR-029) is shipped. `promptmigrate-cli` 0.1.0 is on PyPI (#55), and the maintainer release guide is `docs/RELEASING.md`. Next: implement `rebase` (#15) per accepted ADR-030, then the rest of the fault-injection suite (#31, #32, #33). Use [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) and [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md), and keep to small tested PRs.
The README now also explains the local v0 line-ending-drift recovery path via `restamp` (#104).
