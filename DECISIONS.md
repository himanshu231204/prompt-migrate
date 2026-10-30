# ARCHITECTURE DECISION RECORD (ADR INDEX)

Each ADR documents a decision and its rationale. **Confirmed** means the conversation established it; **recommended** means it is an engineering default pending user review.

## ADR-001 — CLI first, not dashboard

**Status:** confirmed.  
**Decision:** build CLI + migration engine before UI.  
**Why:** easier open-source adoption, automation, correctness testing, integration and CI/CD.  
**Consequences:** prioritize command API, portable files, state transitions; postpone dashboard.

## ADR-002 — Alembic migration mental model

**Status:** confirmed.  
**Decision:** explicit revision lineage and upgrade/downgrade, with environment applied state.  
**Why:** familiar reliable operational model.  
**Consequences:** history graph and precondition validation are first-class.

## ADR-003 — JSON declarative revisions

**Status:** recommended and implemented in starter.  
**Decision:** JSON config drafts and immutable-in-practice before/after snapshots; no executable migrations.  
**Why:** readable Git diffs, deterministic replay, safer review.  
**Tradeoff:** larger files, schema evolution, need to scan for secrets.

## ADR-004 — Linear revisions in MVP

**Status:** recommended and implemented in starter.  
**Decision:** only one root/head; reject branches/merge histories.  
**Why:** reduce complexity while proving state invariants.  
**Tradeoff:** collaborators must resolve conflicting revisions manually. Later allow DAG + merge with explicit semantics.

## ADR-005 — SQLite local environment state

**Status:** recommended and implemented in starter.  
**Decision:** independent local DB per `--env` name.  
**Why:** zero server dependency, transactions.  
**Limit:** not real production rollout nor shared multi-machine state.

## ADR-006 — Full snapshot changes

**Status:** recommended and implemented in starter.  
**Decision:** each change includes exact `before` and `after` JSON object/null.  
**Why:** deterministic upgrade/rollback and preconditions.  
**Tradeoff:** Git storage and secret-retention risk.

## ADR-007 — Provider-neutral core

**Status:** recommended.  
**Decision:** no requirement for Langfuse/Foundry/OpenAI/LangGraph in migration core.  
**Why:** open-source reusability; existing registries remain complementary.  
**Consequence:** separate adapter interfaces and runtime SDK later.

## ADR-008 — Production atomic *activation*, not distributed writes

**Status:** recommended target.  
**Decision:** prepare immutable artifacts; only switch one shared active release pointer atomically after verification.  
**Why:** external provider APIs cannot generally share one ACID transaction.  
**Caveat:** runtime must resolve same release and implement cache/session policy.

## ADR-009 — Evaluation is distinct from migration integrity

**Status:** recommended target.  
**Decision:** `check` validates state consistency; `eval`/promotion gates validate behavior separately.  
**Why:** syntactically correct prompts can still regress.  
**Consequence:** version evaluation evidence by candidate release content hash.

## ADR-010 — Working brand and release status

**Status:** provisional.  
**Decision:** use PromptMigrate until naming checks. Prototype version `0.1.0` doesn't imply production maturity.  
**Consequence:** review PyPI/GitHub/trademark names before public release.
