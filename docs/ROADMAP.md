# ROADMAP — From local prototype to reliable open-source project

> Milestones are **plans**, not shipping promises. Status checked against the code on 2026-11-05.

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

**Status:** in progress. Phase 1 is delivered in cycles. Finishing cycle 1 does **not** finish Phase 1.

### Cycle 1 (PRs 1–6 + 3b)

- [x] Connection lifecycle fix; Linux Docker CI matrix across Python 3.10, 3.12 and 3.13, plus native Windows and macOS jobs (`.github/workflows/ci.yml`). Linux/macOS support is claimed only after a remote CI run passes.
- [x] Characterization tests and legacy compatibility fixtures (`tests/fixtures/legacy`, `tests/fixtures/legacy_breaking`).
- [x] Strict parsing (duplicate keys, NaN, size/depth, symlinks), compatibility tiers, canonical equality (`protocol/`).
- [x] Heuristic secret safeguard: `revision` blocks, `diff`/`get` redact, reviewed allowlist (`secretscan.py`).
- [x] Declared environments; read commands never write (`store/`, `env add`, `env list`).
- [x] Refactor core into testable modules incrementally, without breaking the CLI (ADR-022; `core.py` is a re-export facade).
- [x] Read-only `plan` with a property-based plan==apply test (`plan.py`, `commands/plan.py`).
- [x] Typed errors, exit codes 0–5, `--output json` (`output.py`; schema `promptmigrate.output/1`; ADR-024).

### Remaining after cycle 1 (cycle 2+)

- [ ] Freeze v0.x artifact semantics formally; protocol v1 with canonical revision hashes (fixes the CRLF false-tamper risk).
- [ ] Atomic revision file generation and collision handling.
- [ ] `validate` command.
- [ ] Concurrency tests and the fault-injection suite.
- [ ] Package-install smoke tests.
- [ ] Append-only events table; `rebase` for unapplied revisions.

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

- [ ] Stable protocol compatibility/versioning policy.
- [ ] Maintainer security disclosure process and supply-chain checks.
- [ ] Contributor guide, examples for several frameworks. (Started early, 2026-11-03: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue and PR templates, and a root `SECURITY.md` pointing to GitHub private vulnerability reporting.)
- [ ] Published PyPI package and documented upgrade migration policy.
- [ ] Cross-platform docs and support matrix.
- [ ] Public comparison and case studies grounded in measured behavior.

## Deliberate non-goals early

No SaaS dashboard, no visual prompt editor, no paid cloud control plane, no direct model-weight handling, no proprietary protocol, and no blanket promises that prompt versions imply reproducible LLM outputs.

## First next step

Phase 1 cycle 1 is complete. Start cycle 2 with the "Remaining after cycle 1" items above, beginning with protocol v1 and canonical revision hashes. Use [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) and [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md), and keep to small tested PRs.
