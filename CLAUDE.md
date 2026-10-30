# CLAUDE.md — AI coding/review instructions for PromptMigrate

## Mission

You are helping design and eventually implement **PromptMigrate**, an open-source Alembic-inspired CLI for **AI prompt and agent configuration migrations**. It should provide safe ordered revisions, environment state tracking, reversible changes, integrity/drift checks, and eventually policy-gated immutable release activation. **Do not redefine it as a prompt editor, LLM workflow orchestrator, SaaS dashboard, observability tool, or a generic AI agent system.**

## Start-of-session reading

Code lives in `src/promptmigrate/` and `tests/`; design docs live in `docs/`. Active specs and plans are under `docs/superpowers/`.

1. `README.md` (user-facing CLI overview) and `docs/HANDOFF.md` (handoff and known implementation status).
2. `docs/PROJECT.md`, `docs/PROBLEM_STATEMENT.md`, `docs/COMPETITIVE_LANDSCAPE.md` (why and differentiation).
3. `docs/PRD.md`, `docs/DECISIONS.md`, `docs/OPEN_QUESTIONS.md` (scope and unsettled decisions).
4. `docs/ARCHITECTURE.md`, `docs/LOW_LEVEL_DESIGN.md`, `docs/MIGRATION_PROTOCOL.md`, `docs/CLI_SPEC.md` (HLD/LLD and contracts).
5. `docs/SECURITY.md`, `docs/TESTING_STRATEGY.md`, `docs/EVALUATION_AND_RELEASES.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/ROADMAP.md`.
6. The current spec in `docs/superpowers/specs/`.

Inspect and run tests before proposing changes. The docs describe some **future** files/modules that do not exist yet.

## Confirmed goals

- Open source; migration-first; CLI first.
- Alembic-inspired revision history and environment applied state.
- AI prompts/agent configurations, not DB schema migrations.
- Design/HLD/LLD and reliability before dashboard.

## Recommended initial boundaries

- Keep Python CLI, JSON declarative revisions, linear history, and SQLite local state for MVP unless a documented ADR justifies change.
- Deterministic migrations, no LLM calls required to apply them.
- No arbitrary executable revision scripts in MVP.
- No live provider integration or 'production deployment' claim in existing starter.
- Do not confuse a local environment named `prod` with a live production target.
- Differentiate migration **integrity** checks from prompt-behavior **evaluations**.

## What has actually been verified

The starter prototype was imported into this repo on 2026-10-30 (`src/`, `tests/`). Its seven `unittest` tests reportedly passed on Linux on 2026-10-29. On Windows 11 / Python 3.11.9 on 2026-10-30, 2 passed and 5 errored during temp-dir cleanup, because SQLite connections are never closed. Fixing this is PR 1 of the Phase 1 hardening spec. The current CLI commands are `init`, `revision`, `history`, `diff`, `current`, `upgrade`, `downgrade`, `check`, `get`. State is stored in per-env local SQLite databases.

Do not claim `plan`, `eval`, `promote`, `reconcile`, cloud adapters, production SDK, Postgres service, RBAC, signed revisions, or real production activation already work.

## Design requirements

- Preserve source → applied environment state distinction.
- Preserve revision graph + before/after state preconditions.
- Validate source history and applied state before mutation.
- Fail closed on drift, corrupt history, unexpected state, or partial writes.
- Keep config/ledger updates in one local SQLite transaction.
- Plan future immutable release manifest and atomic activation pointer, not distributed ACID across remote APIs.
- Rollback never claims to undo external agent actions.
- Keep secrets out of source revisions and logs.
- Prefer backward-compatible changes with explicit format versioning.

## Engineering process

When asked to **discuss the project**:

1. Restate the goal accurately.
2. Identify architecture gaps and product differentiators.
3. Critique assumptions, list alternatives and tradeoffs.
4. Propose ADRs and incremental milestones.
5. Do **not** write or change code until explicitly requested.

When asked to **implement**:

1. Inspect repository and current tests; state baseline.
2. Choose a small scope from `IMPLEMENTATION_PLAN.md`.
3. Write tests (including failure paths) before or with changes.
4. Run the test/quality commands and report actual results.
5. Update specs/docs if behavior changes.
6. Clearly separate shipped behavior from planned capabilities.
7. Avoid unnecessary dependencies, giant rewrites, or a dashboard.

## Suggested first response to the user

“Here is my understanding: PromptMigrate is an Alembic-style, local-first CLI for declarative AI configuration migrations with reversible history and environment drift checks. The existing starter proves the concept, but production release activation and evaluation are future phases. I will review the HLD/LLD and starter, flag contradictions or missing invariants, and propose a phased hardening plan before code.”

## Report format for design/code reviews

- **Verified** (directly seen in source/test result)
- **Planned** (from these docs, not implemented)
- **Risks / contradictions** (severity, example)
- **Proposed ADR updates** (decision, alternatives, consequences)
- **Next 3 implementation steps** (tests + acceptance criteria)

## Files to consult for details

`PROJECT.md`, `ARCHITECTURE.md`, `LOW_LEVEL_DESIGN.md`, `PRD.md`, `MIGRATION_PROTOCOL.md`, `CLI_SPEC.md`, `TESTING_STRATEGY.md`, `SECURITY.md`, `EVALUATION_AND_RELEASES.md`, `DECISIONS.md`, `ROADMAP.md`, `EXAMPLE_WORKFLOW.md`, `REFERENCES.md`.
