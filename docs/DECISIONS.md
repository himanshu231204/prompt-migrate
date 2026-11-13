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

## ADR-022 — Concept-named package layout behind a stable `core` facade

**Status:** implemented (Phase 1 cycle 1, package layout refactor). Supersedes the module list in the Phase 1 design spec §4 and the proposed layout in `LOW_LEVEL_DESIGN.md` §1.  
**Decision:** each concept has one module or package: `protocol/` (limits, strict JSON loader, canonical equality, config and name rules), `project.py` (workspace, drafts, allowlist), `revisions.py` (revision files, graph, replay), `draftdiff.py`, `store/` (environments, lock, SQLite connections), `apply.py` (verify and write applied state), and `commands/` (one module per CLI verb: its use-case function plus `run(args)`). `cli.py` only parses and dispatches. `core.py` and the package root re-export the previous public names and define nothing. Imports point down a fixed layer order; `tests/unit/test_module_layout.py` enforces it.  
**Why:** a contributor can find where something lives from its name, and `plan` (PR 5), `--output json` (PR 6), evaluation gates and release activation each get an obvious new module instead of growing one file.  
**Consequence:** internal calls go through module attributes (`project.read_drafts(...)`), so a test patches the defining module; patching `core` or `cli` no longer changes behaviour. The one exception is `apply.canonical`, imported by name so that a test can fail a state write without affecting `same()`. No CLI, file-format or checksum change.

## ADR-023 — `plan` infers direction and shares target resolution with `upgrade` and `downgrade`

**Status:** implemented (Phase 1 cycle 1, PR 5).  
**Decision:** `plan --target` accepts `head`, `-1`, `base` or a revision id. There is no direction flag: the direction follows from where the target lies relative to the verified applied position (later is an upgrade, earlier a downgrade, equal a no-op). Target resolution lives in the pure module `plan.py` and is called by `upgrade`, `downgrade` and `plan` alike. `plan` reads through the read-only SQLite connection and `_verify`, so it fails closed on drift and tampering and never writes.  
**Why:** a preview that resolves targets differently from the commands it previews is worse than none. A single resolver, plus a property test that compares `plan` with what `upgrade`/`downgrade` apply on random histories, makes disagreement a test failure.  
**Consequence:** `plan` is a snapshot, not a lock: another process may change the environment before the real command runs, which re-verifies under `BEGIN IMMEDIATE`. `plan` previews environment migrations only; `diff` remains the drafts-versus-head comparison. Existing error messages are unchanged. Text output only; `--output json` and exit codes arrive with PR 6.

## ADR-024 — Exit codes 0–5 and a versioned JSON envelope owned by `output.py`

**Status:** implemented (Phase 1 cycle 1, PR 6).  
**Decision:** each command exposes `execute(args) -> output.Result` (JSON-safe `data` plus the exact text it printed before). `output.py` renders text or one `promptmigrate.output/1` JSON envelope and holds the only error-to-exit-code table: `SchemaError`/`RevisionGraphError` → 3, `DriftError`/`IntegrityError`/`MigrationConflictError` → 4, `StorageError`/`sqlite3.Error`/`OSError` → 5, other handled errors → 1, argparse → 2. Codes 6 and 7 stay reserved. In JSON mode handled errors and PromptMigrate warnings are in the envelope, not on stderr; warnings from other libraries still reach stderr.  
**Why:** CI needs to tell "bad source" from "drift" from "storage" without parsing messages, and tools need stable output. Keeping code 1 for uninitialized project, undeclared environment, unknown target and pending revisions keeps scripts that test for non-zero working. `OSError` is storage (5) because a CI job can retry or alert on it; `MigrationConflictError` is 4 because the state does not match the revision's `before`.  
**Consequence:** default text output is byte-identical. Some failures that exited 1 now exit 3, 4 or 5; scripts testing for exactly 1 must change. New commands (`plan`) only supply `execute`. The JSON schema changes additively within `/1`.

## ADR-025 — v0 revision artifact semantics are frozen

**Status:** implemented (Phase 1 cycle 2, PR 7).  
**Decision:** a revision file without `format_version` is a v0 artifact, and its meaning is frozen. It needs the top-level keys `revision`, `down_revision`, `message`, `created_at` and `changes`; other top-level keys are tolerated and ignored; a UTF-8 BOM is accepted; tier rules (ADR-020) apply unchanged. Its checksum is SHA-256 of the raw file bytes, so any byte change after apply, line endings included, is an `IntegrityError` for that environment. Byte-exact fixtures in `tests/fixtures/v0_frozen/` and `tests/fixtures/crlf/` (marked `-text`) and the digests in `tests/fixtures/v0_checksums.json` enforce this (`tests/unit/test_v0_frozen.py`).  
**Why:** existing histories and env ledgers must never change meaning. Every future protocol change gets a new `format_version` with its own reader, not a reinterpretation of v0.  
**Consequence:** the CRLF false-tamper risk remains for v0 files: a revision written with CRLF on Windows and checked out as LF fails `check`. It is pinned as a strict xfail; protocol v1 (PR 8) will remove it for new revisions, and an explicit re-stamp (PR 9) is planned for affected v0 rows. No code, CLI, file-format or checksum change in this PR. Update: the generator part was resolved by ADR-026 (new revisions are v1); the xfail now passes. v0 rows applied with CRLF are still affected until the planned re-stamp.

## ADR-026 — Protocol v1: canonical content hash

**Status:** implemented (Phase 1 cycle 2, PR 8).  
**Decision:** a revision file whose top-level `format_version` is the JSON integer `1` is a v1 artifact. It must have exactly the keys `format_version`, `revision`, `down_revision`, `message`, `created_at` and `changes`; any other key is a tier-A `SchemaError` ("Unknown top-level key in <file>: <keys>"), so a v1 file cannot carry fields that readers silently ignore. Any other `format_version` value (`0`, `2`, `true`, `1.0`, `"1"`, `null`, …) is a tier-A `SchemaError` ("Unsupported format_version in <file>"); the type test is `type(x) is int`, consistent with ADR-003a. All other v0 rules (ids, metadata, change shape, tiers, BOM) apply unchanged. The v1 checksum is `"v1:" + SHA-256(protocol.canonical(parsed file))`: whitespace, line endings, key order and JSON string escapes do not count, and every parsed value does. A file without `format_version` stays v0 (ADR-025). The ledger schema is unchanged: v0 rows hold a bare 64-hex digest and v1 rows the `v1:` value, so the two can never be equal, and `apply._verify` still compares strings. Histories may mix v0 and v1 (`Revision.format_version`). The generator (`promptmigrate revision`) writes every new revision as v1, UTF-8 with LF line endings on every OS, and its size check counts those exact bytes. A v1 file containing an unpaired surrogate escape is a tier-A `SchemaError` ("Invalid string in <file>: unpaired surrogate"), because it has no UTF-8 canonical form.  
**Why:** removes the CRLF false-tamper risk (R4) for v1 files without weakening tamper detection and without reinterpreting any applied v0 checksum.  
**Consequence:** a v1 checksum is tamper detection relative to an environment ledger, not an author signature. A PromptMigrate version without v1 support loads a v1 file as v0 (it ignores the unknown key) and stores a raw-byte checksum, so an environment touched by both versions fails closed with "Migration file was modified after apply". Tested in `tests/unit/test_protocol_v1.py` and `tests/integration/test_protocol_v1_integrity.py` (I16).
