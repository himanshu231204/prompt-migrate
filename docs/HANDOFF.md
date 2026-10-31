# PromptMigrate — Architecture & Product Handoff

> **Working project name:** PromptMigrate  
> **Tagline:** Alembic for production AI prompts and agent configurations.  
> **Status:** design/handoff + an **existing local-only Python prototype**, not a production-ready deployment platform.  
> **Updated:** 2026-10-29  
> **Primary goal:** give Claude or another engineer enough context to critique, refine, and implement the project without changing its core intent.

## Read this first

**PromptMigrate is an open-source, CLI-first, migration-based control system for prompts and AI agent configuration.** It manages *ordered, reviewable, reproducible* changes through revisions with explicit dependencies, integrity checks, drift detection, environment state, upgrades, and downgrades. The long-term goal is **safe activation of complete, compatible AI configuration releases** in production.

It is **not** another prompt editor, observability platform, chat UI, LLM gateway, or hosted prompt registry. It may integrate with those systems later.

## Why build it?

AI applications routinely deploy prompt, model, tool, and output-contract changes independently. Teams can lose track of what is active, introduce incompatible changes across agents, make unreviewed production edits, and struggle to reproduce or roll back an incident. Git history by itself does **not** tell you what an environment currently runs. Prompt registries already solve important parts of versioning and labels; PromptMigrate focuses on ordered **change application and environment-state verification**.

## Recommended reading order

| Order | File | Purpose |
|---|---|---|
| 1 | [PROJECT.md](PROJECT.md) | Vision, why now, users, examples, positioning |
| 2 | [PROBLEM_STATEMENT.md](PROBLEM_STATEMENT.md) | Production failure modes and success criteria |
| 3 | [COMPETITIVE_LANDSCAPE.md](COMPETITIVE_LANDSCAPE.md) | Existing projects and real differentiation |
| 4 | [PRD.md](PRD.md) | Requirements, user journeys, acceptance criteria |
| 5 | [ARCHITECTURE.md](ARCHITECTURE.md) | High-level design and deployment boundaries |
| 6 | [LOW_LEVEL_DESIGN.md](LOW_LEVEL_DESIGN.md) | Internal components, algorithms, storage, errors |
| 7 | [MIGRATION_PROTOCOL.md](MIGRATION_PROTOCOL.md) | Revision format, invariants, upgrade/downgrade semantics |
| 8 | [CLI_SPEC.md](CLI_SPEC.md) | Commands and UX contract |
| 9 | [SECURITY.md](SECURITY.md) | Threat model, non-guarantees, safeguards |
| 10 | [TESTING_STRATEGY.md](TESTING_STRATEGY.md) | Failure injection and release criteria |
| 11 | [EVALUATION_AND_RELEASES.md](EVALUATION_AND_RELEASES.md) | Future eval gates and release activation architecture |
| 12 | [ROADMAP.md](ROADMAP.md) | Phased open-source delivery |
| 13 | [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Recommended work breakdown and acceptance gates |
| 14 | [DECISIONS.md](DECISIONS.md) | Decisions and recommended defaults |
| 15 | [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | Architecture questions to settle |
| 16 | [EXAMPLE_WORKFLOW.md](EXAMPLE_WORKFLOW.md) | Concrete multi-agent scenario |
| 17 | [REFERENCES.md](REFERENCES.md) | Official inspiration and competitor sources |
| 18 | [CLAUDE.md](../CLAUDE.md) | Instructions for Claude working in this repository |
| 19 | CLAUDE_DISCUSSION_PROMPT.md | Ready-to-copy first conversation prompt (not included in this repo) |

## Agreed direction versus recommended defaults

**Agreed:** build an open-source **CLI and migration engine first**; take conceptual inspiration from Alembic; focus on production AI prompt/configuration changes; develop HLD and LLD before adding a dashboard.

**Recommended defaults, not separately approved:** Python 3.10+, JSON revision artifacts, a linear dependency chain, SQLite local state, full before/after snapshots, and no provider integration in the initial MVP. These defaults match the previous starter and should be challenged only with an explicit trade-off analysis.

## Existing prototype: verified baseline

The `promptmigrate-starter` prototype was imported into this repository unchanged on 2026-10-30: `src/promptmigrate/core.py`, `src/promptmigrate/cli.py`, `tests/test_core.py`, `pyproject.toml`.

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

Implemented there: `init`, `revision`, `diff`, `history`, `current`, `upgrade`, `downgrade`, `check`, `get`; Git-trackable JSON revisions; per-environment **local** SQLite files; snapshots; checksums of raw migration files at apply time; state drift detection; one linear history; multi-prompt changes in one SQLite transaction.

**Not implemented/verified:** strict config schema, `plan`, evaluation gates, external providers, shared production ledger, centralized rollout, distributed consistency, signed artifacts, comprehensive concurrency/fault injection, audit-grade access controls. The prototype's `prod` environment name is only a *local SQLite file*, never a deployment to a production system.

## Guiding architectural rule

> Separate **desired state** (drafts), **versioned state** (migrations), **applied state** (environment ledger/configuration), and **runtime active state** (what deployed applications actually resolve). Local MVP models the first three; production integration must explicitly close the gap to the fourth.

## Where to begin with Claude

Read [CLAUDE.md](../CLAUDE.md), then start a discussion with Claude. First ask for an architecture review and gaps, not immediate wholesale implementation.

## License and naming

The existing starter declares MIT. PromptMigrate remains a **working name**; check repository/package/trademark availability before public publishing. These documents are proposals; the repository implementation remains the source of truth for what actually works.
