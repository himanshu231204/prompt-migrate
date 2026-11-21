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
**Consequence:** the CRLF false-tamper risk remains for v0 files: a revision written with CRLF on Windows and checked out as LF fails `check`. It is pinned as a strict xfail; protocol v1 (PR 8) will remove it for new revisions, and an explicit re-stamp (PR 9) is planned for affected v0 rows. No code, CLI, file-format or checksum change in this PR. Update: the generator part was resolved by ADR-026 (new revisions are v1); the xfail now passes. v0 rows whose file changed only in line endings can be accepted explicitly with `restamp` (ADR-027).

## ADR-026 — Protocol v1: canonical content hash

**Status:** implemented (Phase 1 cycle 2, PR 8).  
**Decision:** a revision file whose top-level `format_version` is the JSON integer `1` is a v1 artifact. It must have exactly the keys `format_version`, `revision`, `down_revision`, `message`, `created_at` and `changes`; any other key is a tier-A `SchemaError` ("Unknown top-level key in <file>: <keys>"), so a v1 file cannot carry fields that readers silently ignore. Any other `format_version` value (`0`, `2`, `true`, `1.0`, `"1"`, `null`, …) is a tier-A `SchemaError` ("Unsupported format_version in <file>"); the type test is `type(x) is int`, consistent with ADR-003a. All other v0 rules (ids, metadata, change shape, tiers, BOM) apply unchanged. The v1 checksum is `"v1:" + SHA-256(protocol.canonical(parsed file))`: whitespace, line endings, key order and JSON string escapes do not count, and every parsed value does. A file without `format_version` stays v0 (ADR-025). The ledger schema is unchanged: v0 rows hold a bare 64-hex digest and v1 rows the `v1:` value, so the two can never be equal, and `apply._verify` still compares strings. Histories may mix v0 and v1 (`Revision.format_version`). The generator (`promptmigrate revision`) writes every new revision as v1, UTF-8 with LF line endings on every OS, and its size check counts those exact bytes. A v1 file containing an unpaired surrogate escape is a tier-A `SchemaError` ("Invalid string in <file>: unpaired surrogate"), because it has no UTF-8 canonical form.  
**Why:** removes the CRLF false-tamper risk (R4) for v1 files without weakening tamper detection and without reinterpreting any applied v0 checksum.  
**Consequence:** a v1 checksum is tamper detection relative to an environment ledger, not an author signature. A PromptMigrate version without v1 support loads a v1 file as v0 (it ignores the unknown key) and stores a raw-byte checksum, so an environment touched by both versions fails closed with "Migration file was modified after apply". Tested in `tests/unit/test_protocol_v1.py` and `tests/integration/test_protocol_v1_integrity.py` (I16).

## ADR-027 — Explicit line-ending-only re-stamp of v0 ledger rows; v0 hash semantics unchanged

**Status:** implemented (Phase 1 cycle 2, PR 9).  
**Decision:** `promptmigrate restamp --env <env>` re-stamps the ledger checksum of an applied v0 revision when, and only when, the stored digest equals the SHA-256 of the current file re-saved with LF or with CRLF: the stored digest equals the current file normalised to all-LF or all-CRLF, and only for a UTF-8 file. `load_revisions` computes those two digests (`revisions.line_ending_variants`) from the bytes it already read and keeps them in `Revision.line_ending_checksums`, but only when `json.loads`'s own encoding detection (`json.detect_encoding`) says the file is UTF-8 (with or without a BOM); a v0 file in another encoding (and every v1 file) gets an empty set, so no file is re-read later. `restamp` resolves the declared environment, takes the project lock and `BEGIN IMMEDIATE`, sets `applied_revisions.checksum` to the current raw digest for each such row, then runs the full `_verify` in the same transaction. Any other mismatch (a v1 row, a non-UTF-8 v0 file, a value edit, a diverging or longer ledger) raises the normal `IntegrityError` and drift raises `DriftError`; either rolls back, so nothing is written. An absent state database is base state: success, nothing created. `restamp` writes nothing else: no manifest adoption, no `prompts` change. The v0 checksum stays the raw-byte SHA-256 (ADR-025), and `check`, `plan`, `get` and `current` never re-stamp. Every command that verifies an environment other than `restamp` still fails such a row with `IntegrityError` (exit 4), and its message names the recovery: ``Migration file was modified after apply: <id> (line endings only; run `promptmigrate restamp --env <env>` to accept)``. Variants are computed only for UTF-8 files; a v0 file in another encoding never qualifies.  
**Why:** v0 revisions written with CRLF on Windows and normalised to LF by Git fail `check` although no value changed (R4). Accepting that implicitly would weaken tamper detection for every v0 file; an explicit, all-or-nothing command keeps every other mismatch fatal.  
**Consequence:** a re-stamp appends a `restamp` event (ADR-029). Tested in `tests/integration/test_restamp.py` (I20) and `tests/unit/test_line_endings.py`.

## ADR-028 — `validate` is source-only; warnings fail only under `--strict`

**Status:** implemented (Phase 1 cycle 2, PR 11, #10).  
**Decision:** `promptmigrate validate [--strict] [--drafts-clean]` checks the files a Git checkout carries and nothing else. In order, it runs `revisions.load_revisions` (both format versions, graph, replay, tier A errors, tier B warnings), `project.read_drafts`, `store.read_environments` **only when `environments.json` exists** (without a manifest, `read_environments` would infer declarations from `states/`), `project.load_allowlist`, and `commands.check.audit_secrets`, which is reused unchanged. It never resolves an environment and never reads, creates or modifies anything under `states/` (I19). Any tier-A error exits 3. With `--drafts-clean`, a non-empty `draft_diff` raises `SchemaError` "Drafts differ from head: <names>". With `--strict`, any PromptMigrate warning raises `StrictValidationError` (a `SchemaError`, exit 3) "validate --strict: <n> warning(s)". Here n counts distinct (category, message) pairs, the same dedup that JSON output uses, because history is loaded more than once. The warnings are still printed (text) or listed (JSON). Without `--strict`, warnings never change the exit code.  
**Why:** CI needs a gate that runs on a fresh checkout before any environment exists, and that cannot be confused with `check`, which verifies applied state. Legacy tier-B files and secrets already in history are accepted for compatibility (ADR-025 and PR 3b), so failing on them by default would break existing projects. `--strict` lets a project opt in once it is clean.  
**Consequence:** `validate` says nothing about any environment's state; pair it with `upgrade` and `check` for that. When a tier-A error aborts, warnings recorded before it are not reported. Tested in `tests/integration/test_validate.py`, including a patched `store.sqlite._states_dir` that raises.

## ADR-029 — Append-only `events` table in each environment state DB

**Status:** implemented (Phase 1 cycle 3, #14); accepted 2026-11-19.  
**Decision:** each `states/<env>.sqlite3` gets a table `events(seq INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT NOT NULL, command TEXT NOT NULL CHECK (command IN ('upgrade','downgrade','restamp')), revision TEXT NOT NULL, checksum TEXT NOT NULL, previous_checksum TEXT)`. One row is written per revision a command applies, reverts or re-stamps, in the same SQLite transaction (`BEGIN IMMEDIATE`) as the `prompts` and `applied_revisions` changes, so an event exists if and only if its ledger change committed. For `upgrade`, `checksum` is the checksum written to the ledger; for `downgrade`, the checksum of the ledger row removed; for `restamp`, the new checksum, with the old one in `previous_checksum` (NULL otherwise). `occurred_at` is `datetime.now(timezone.utc).isoformat()`. Events hold ids, checksums, a timestamp and the command only: never config content, drafts, messages or secrets. Three triggers (`events_no_update`, `events_no_delete`, and `events_no_replace`, which rejects an `INSERT` that reuses an existing `seq` because `INSERT OR REPLACE` would otherwise delete the old row without firing the `DELETE` trigger) `RAISE(ABORT)`, so the table is append-only for every PromptMigrate code path and for accidental SQL. The table is created lazily with `CREATE TABLE IF NOT EXISTS` inside the mutating transaction after `_verify` succeeds. A state DB written by an older release is therefore adopted on its first successful mutation, a rejected command writes nothing, and a mutation with nothing to do (no steps, no stale rows) creates no table. Read-only commands neither require nor create the table. If an `events` table already exists with different columns, the mutating command raises `StorageError` and writes nothing. Events are not part of `_verify`: they do not change what counts as drift or integrity failure.  
**Why:** `downgrade` deletes ledger rows (AGENTS.md architecture rule 6), so today an environment cannot say what was applied and reverted, or when, and `restamp` (ADR-027) leaves no trace. Putting the log in the environment's own DB and transaction avoids a second store that could disagree with the ledger; the triggers make accidental rewriting fail loudly.  
**Consequence:** the log is an audit aid, not tamper-proof: anyone with write access to the SQLite file can drop the triggers or the file, and an environment deleted from disk loses its log. It records no actor, host or reason (a later ADR may add them). There is no CLI to read events yet; a read command (for example `history --events`) is follow-up work, and tests read the table through `sqlite3`. Events before this release do not exist and are not reconstructed. No revision-format, checksum or JSON-envelope change; the `applied_revisions` and `prompts` schemas are unchanged. Postgres audit trails stay Phase 4.

## ADR-030 — `rebase` re-parents an unapplied branch after a Git merge, minting new ids

**Status:** accepted 2026-11-19 (Phase 1 cycle 3, #15); not yet implemented.  
**Decision:** `promptmigrate rebase [--onto <tip-id>]` repairs one fork in source history, the result of two Git branches that each ran `revision` from the same head. `load_revisions` is intentionally not fork-tolerant: it keeps raising on any fork (architecture rule 2, ADR-025), so every other command still fails closed on a forked history. `rebase` therefore brings its own loader, used by no other command, to read the revision files. It supports exactly one fork point with exactly two branches, each a linear chain; any other shape raises `RevisionGraphError` and writes nothing. The branch ending at `<tip-id>` stays; the other branch is moved onto that tip. A revision is *applied* when its id is a ledger row in any declared environment (`environments.json`). Rebase reads every declared environment's ledger under the project lock, read-only and without creating a state DB. An unreadable or corrupt ledger fails closed. `--onto` is optional when exactly one branch has applied revisions (that branch stays), and required when neither does. Moving any applied revision, or `--onto` naming the branch that must move, raises `MigrationConflictError` and writes nothing. Each moved revision, oldest first, gets a **new** id (the generator `revision` uses, avoiding every existing id), its `down_revision` set to the previous kept or moved revision, and its `before` snapshots recomputed from the replayed new parent. A moved revision is checked against the prompt names touched by every revision on the other branch: rebase collects each branch's touched-prompt set and rejects any intersection — including when both branches set a prompt to the same `after` — raising `MigrationConflictError` naming the prompt and writing nothing. Rejection happens before any file is written; the recompute still doubles as the conflict check, so every non-conflicting `before` is unchanged. `after`, `message` and `created_at` are carried over unchanged. Every moved file is written as v1 (ADR-026) with an atomic write, whatever its previous format version; no format version or checksum rule changes (ADR-025). After a conflict leaves the fork intact, resolve it by editing the conflicting revision file directly (its `before`/`after`, not through `revision`, which still raises on the fork), then re-run `rebase`. Rebase requires every input revision file to be Git-tracked and clean before it starts; uncommitted working-tree contents are not preserved by rebase and would be lost if the process crashes mid-write. All new files are written first, then the old files are removed tip-first, then the result is checked with `load_revisions` and a full replay. A crash between those steps leaves both chains on disk plus possibly a partial `.tmp` file; `load_revisions` reports the existing branching error, nothing is lost, Git restores the pre-rebase state, and any leftover `.tmp` file in `versions/` should be removed before re-running. Rebase never opens a state DB for writing, never touches `prompts`, ledgers or events (ADR-029), and never edits drafts.  
**Why:** the project must load as one linear chain (architecture rule 2), so a merge that forks history has no other repair today. Changing the id makes a moved revision a new artifact: the old id can never be mistaken for it in a ledger, and the v0/v1 checksum rules stay as they are. Refusing applied revisions follows the rule never to edit applied history (AGENTS.md Boundaries). Failing on any prompt both branches touched avoids inventing merge semantics, and because every non-conflicting `before` is unchanged, the recompute doubles as the conflict check.  
**Consequence:** the applied check sees only local environments. An environment elsewhere that already applied the old id will not find it in source and fails closed at its next `check`/`upgrade`; rebase does not fix such an environment, and `docs/MIGRATION_PROTOCOL.md` will say to rebase before applying merged revisions anywhere. Moved revisions lose their original ids and filenames. Three or more branches, more than one fork, auto-merging prompts, an `--env` scoped check and a `--dry-run` preview are out of scope. The implementation PR adds `commands/rebase.py`, the rebase-only fork-tolerant loader in `revisions.py` (a separate function; `load_revisions` stays strict), tests for the two-branch merge, a conflicting prompt, an applied revision (refused), corrupt ledger, crash between write and delete, and v0 inputs written as v1, and updates `docs/MIGRATION_PROTOCOL.md` (merge workflow) and `docs/CLI_SPEC.md`. Those tests are written and watched failing before any code (Iron Law).
