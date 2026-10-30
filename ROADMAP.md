# ROADMAP — From local prototype to reliable open-source project

> Milestones are **plans**, not shipping promises. Status checked against the previously generated starter on 2026-10-29.

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

- [ ] Freeze/document v0.x artifact semantics and deprecation approach.
- [ ] Strict versioned config/revision schema.
- [ ] Refactor core into testable modules without breaking CLI.
- [ ] Read-only `plan` and `validate` commands.
- [ ] Atomic revision file generation and collision handling.
- [ ] Better typed errors and CI JSON output.
- [ ] Path/symlink, file-size, and secret scanning safeguards.
- [ ] Property-based and concurrency tests.
- [ ] CI matrix/package-install smoke tests.

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
- [ ] Contributor guide, examples for several frameworks.
- [ ] Published PyPI package and documented upgrade migration policy.
- [ ] Cross-platform docs and support matrix.
- [ ] Public comparison and case studies grounded in measured behavior.

## Deliberate non-goals early

No SaaS dashboard, no visual prompt editor, no paid cloud control plane, no direct model-weight handling, no proprietary protocol, and no blanket promises that prompt versions imply reproducible LLM outputs.

## First next step

Run a **design + code gap review** using [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) and [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md), then execute Phase 1 in small tested PRs.
