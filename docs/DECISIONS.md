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

## ADR-003a — Canonical equality

**Status:** implemented (Phase 1 cycle 1, PR 3).  
**Decision:** configs are compared by canonical JSON in preconditions, `diff` and drift detection. `1`, `1.0` and `true` are distinct.  
**Why:** Python `==` treats `1 == 1.0 == True`, so a `1` → `true` edit produced no revision and bool/int drift in an env DB went unnoticed.  
**Consequence:** a revision hand-edited to rely on the conflation fails closed. Generated revisions and env DBs are unaffected, because JSON number types survive parsing and storage.

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

## ADR-012 — Declared environments and read-only state inspection

**Status:** implemented (Phase 1 cycle 1, PR 4).
**Decision:** `.promptmigrate/environments.json` is the authority for environment names and metadata. Names resolve case-insensitively to the manifest spelling, including CLI status labels. Existing projects without a manifest are inferred in memory (`dev`, `staging`, plus validly named state-file stems) for reads, and persisted atomically after the first successful mutation; a rejected command writes nothing. The rewritten manifest keeps the existing file's permission bits (new files follow the umask).
**Why:** prevent accidental state-file creation for typos, make environment listing explicit, and ensure inspection cannot repair or mutate applied state.
**Consequence:** reads use SQLite `mode=ro`; absent databases mean base state, while incomplete/corrupt databases, WAL-mode databases, and symlinked state paths fail closed. Writes initialize only absent databases and retain local transactional semantics. Selecting `prod`, `production`, or `live` for an operation emits a warning; no remote activation is implied.

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

## ADR-020 — Compatibility tiers for validation rules

**Status:** implemented (Phase 1 cycle 1, PR 3).  
**Decision:** tier A (ambiguous or unsafe input) fails closed everywhere. Tier B (hygiene and limits) is enforced on drafts and newly generated revisions, and only warned about (`LegacyRevisionWarning`) in existing revision files.  
**Why:** existing histories can legitimately break rules the starter never had. Rejecting them would block every command, including the `downgrade` needed to recover.  
**Consequence:** `before` values are never validated as new content. Per-config rules are reported once, at the revision whose `after` introduced the violation. Non-finite numbers, including literals that overflow to infinity, are tier A in revision files too. The starter wrote `Infinity` for an overflowing draft number, so such a history now fails closed and must be corrected by hand.

## ADR-021 — Heuristic secret safeguard with a fingerprinted allowlist

**Status:** implemented (Phase 1 cycle 1, PR 3b).  
**Decision:** pattern-based detection blocks secret-like values in new revision content, redacts them in `diff`/`get` output, and warns about them in history. False positives go in a Git-tracked allowlist whose entries bind name, JSON path, rule and the SHA-256 fingerprint of the exact value.  
**Why:** Git keeps every committed revision forever, so the cheapest place to stop a leaked credential is before the file is written. Binding an entry to a fingerprint means a real credential that replaces a documented example is caught again.  
**Consequence:** detection is heuristic and can miss secrets; it does nothing for secrets already in history, which must be rotated. A value copied from history into `before` never blocks, so a leak can always be removed.
