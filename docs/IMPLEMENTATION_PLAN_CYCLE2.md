# IMPLEMENTATION PLAN — PromptMigrate spec as of 2026-11-05 ("5-11-2026")

> **Baseline:** verified 2026-11-05 on Windows 11 / Python 3.11.9 → `python -m pytest -q` = `713 passed, 18 skipped, 33 warnings`; unittest → `Ran 7 tests ... OK`. Phase 1 Cycle 1 (PRs 1–6 + 3b) is complete.
>
> **Scope:** Phase 1 Cycle 2 (harden the migration core) plus resolution of the high-priority Open Questions. No dashboards, no cloud registries, no Postgres, no eval gates — those are Phase 2+. Per AGENTS.md: change no code until this plan is agreed; then proceed one tested PR at a time.

---

## 1. Current state (verified baseline)

**Shipped (never claim more):** `init`, `revision`, `history`, `diff`, `current`, `upgrade`, `downgrade`, `plan`, `check`, `get`, `env add`, `env list`; `--output json`; exit codes 0–5.

**Architecture in place (ADR-022):** `protocol/` → `secretscan.py` → `project.py` → `revisions.py` + `store/` → `draftdiff.py`, `plan.py`, `apply.py`, `output.py` → `commands/<verb>.py` → `cli.py`. `core.py` is a re-export facade.

**State model:** Git-tracked `drafts/<name>.json` and `versions/<12hex>_<slug>.json`; per-env local SQLite `states/<env>.sqlite3` (`applied_revisions` ledger + `prompts`); declared `environments.json`. Checksum = SHA-256 of raw revision file bytes. One linear chain; `upgrade`/`downgrade` run `BEGIN IMMEDIATE` → `_verify()` → `_apply_changes()` → commit.

**Not shipped (never claim otherwise):** `eval`, `export`, `promote`, `reconcile`, cloud adapters, SDK, Postgres, RBAC, signed revisions, real production activation, audit log, append-only events.

**Open questions to settle in this plan (from docs/OPEN_QUESTIONS.md):** Q1 format_version/stability, Q4 source hashing/canonical signatures, Q5 concurrency/collision, Q6 transaction granularity, Q7 `--env prod` naming, Q3 safe deletion policy, Q8 export bridge, Q9 security guardrails, Q10 compatibility testing.

---

## 2. Guiding constraints (from AGENTS.md / ROADMAP.md)

- **TDD Iron Law:** no production code without a watched-failing test. RED → GREEN → REFACTOR → run the **whole** suite.
- **Fail closed:** drift, corrupt history, unexpected state, partial writes all block.
- **One local SQLite transaction** for config + ledger; no LLM/provider calls inside it; no remote writes disguised as transactional.
- **Revisions are JSON only;** no executable revision code; no change to revision format/checksum semantics without an explicit format version.
- **Runtime stdlib-only;** dev deps in `[project.optional-dependencies] dev`.
- **`check` is integrity, not evaluation.** `--env prod` means only a local `prod.sqlite3` file.
- **Before every commit:** update `CHANGELOG.md` (Unreleased), tick `docs/ROADMAP.md`, and sync `docs/CLI_SPEC.md` / `docs/MIGRATION_PROTOCOL.md` / `docs/DECISIONS.md` if behavior changes.
- **Git:** `<type>/<short-description>` branch, merge `--no-ff` into `main`, conventional commits, no AI attribution, don't push unless asked.
- **Merge gate:** whole suite green on this Windows machine with real pasted output.

---

## 3. Prioritized PR plan (Cycle 2)

Each PR below lists: goal, TDD tests to write first (RED), minimal code (GREEN), refactor, and acceptance criteria. PRs must be done in order where dependencies exist.

### PR 7 — Protocol v1 + canonical revision hashes (freeze v0.x artifact semantics)

**Open questions resolved:** Q1 (format_version stability), Q4 (source hashing/canonical signatures).

**Goal:** Add an explicit `format_version` field to revision artifacts. Keep raw-byte SHA-256 checksum for v0 artifacts (backward compat). Introduce a canonical-artifact hash (canonical JSON serialization) for v1 artifacts to eliminate the CRLF/whitespace false-tamper risk. Ship a tested reader/migration path so v0 revisions remain readable after the format evolves.

**TDD tests (write first, expect failure):**
- `tests/unit/test_protocol_v1.py`: v0 artifact without `format_version` loads; v1 artifact with `format_version: 1` loads; unknown/unsupported `format_version` raises `SchemaError`.
- `tests/unit/test_canonical_artifact_hash.py`: canonical hash differs under CRLF vs LF normalization for same logical content; v0 checksum stays raw-byte; v1 artifact carries both `checksum` (raw) and `artifact_sha256` (canonical).
- `tests/unit/test_revision_reader_migration.py`: reading a v0 revision produces a usable `Revision` object; reading v1 uses canonical hash for verification on apply.
- `tests/integration/test_format_migration.py`: apply a v0 revision to an env, then check/upgrade still works; apply a v1 revision verifies canonical hash.

**Minimal code:**
- `protocol/format.py` (new): `format_version` constant, `artifact_hash(raw_bytes, format_version)` selector, canonical serialization bytes.
- `revisions.py`: parse optional `format_version`; store both checksums on `Revision`; `load_revisions` validates format_version tier; emit `LegacyRevisionWarning` for v0 (accepted for compatibility).
- `apply.py`: `_verify` checks the hash appropriate to the artifact's format_version.

**Refactor:** keep `Revision.checksum` (raw, for v0 ledger) and add `Revision.artifact_sha256` (optional, v1).

**Acceptance criteria:**
- Existing v0 fixture revisions still load and apply (no silent change to applied checksums).
- A whitespace-only edit to a v1 artifact is detected via canonical hash; a whitespace-only edit to a v0 artifact is detected via raw-byte hash (unchanged behavior).
- Unknown `format_version` fails closed with `SchemaError`.
- Whole suite green.

### PR 8 — Atomic revision file generation + collision handling (Open Question Q5)

**Goal:** Make `revision` write its artifact atomically (temp file in same dir → `os.replace`) and make revision IDs collision-resistant when two developers/pipelines generate from the same source head. After a Git merge, branches are detected (no auto-merge) — this PR only hardens generation, not merge resolution.

**TDD tests (write first):**
- `tests/unit/test_atomic_revision_write.py`: writing a revision leaves no temp file on success; on failure (e.g., disk full simulated), no partial `.json` remains in `versions/`.
- `tests/unit/test_revision_id_collision.py`: two concurrent generations at the same head produce distinct IDs; retry-with-backoff on ID collision.
- `tests/integration/test_concurrent_revision_generation.py`: two processes generating at the same head do not corrupt `versions/`.

**Minimal code:**
- `revisions.py` / `commands/revision.py`: generate ID, write to `versions/<id>_<slug>.json.tmp`, `fsync`, `os.replace` to final name; on ID collision, derive a new ID (e.g., incorporate timestamp/nonce) and retry bounded times.

**Refactor:** extract `write_revision_artifact(artifact, project_dir)` helper.

**Acceptance criteria:**
- No temp files left after `revision`.
- Collision never silently overwrites an existing revision file.
- `--output json` unaffected.
- Whole suite green.

### PR 9 — `validate` command (ROADMAP remaining item)

**Goal:** Add `promptmigrate validate` that checks drafts, revision files, and environment state without mutating anything. Reports schema errors, secret-like values, drift risk, and graph problems with exit codes.

**TDD tests (write first):**
- `tests/unit/test_validate_command.py`: valid project → exit 0; invalid draft → `SchemaError` exit 3; tampered applied revision → `IntegrityError` exit 4; undeclared env → exit 1.
- `tests/cli/test_validate_cli.py`: `--output json` envelope shape; text output lists problems; read-only (no state file created).

**Minimal code:**
- `commands/validate.py`: `execute(args)` reusing `load_revisions`, `project.read_drafts`, `apply._verify`-style checks via read-only store connections; returns `output.Result`.
- `cli.py`: register `validate` subcommand.

**Refactor:** share verification logic between `validate`, `check`, `plan`, `upgrade`, `downgrade` without duplication.

**Acceptance criteria:**
- `validate` never writes (no DB creation, no manifest adoption).
- Same `Error:` text as `check` for drift/tampering.
- Whole suite green.

### PR 10 — Concurrency tests + fault-injection suite (ROADMAP remaining item)

**Goal:** Harden confidence in transactional guarantees under failure. No behavior change — tests only (characterization + new fault injection).

**TDD tests (write first — these define expected behavior):**
- `tests/integration/test_fault_injection.py`: failure after writing one prompt row but before ledger insert → whole transaction rolls back (env unchanged).
- `tests/integration/test_fault_injection.py`: applied migration file mutated → next `check`/`apply` blocks with `IntegrityError` exit 4.
- `tests/integration/test_fault_injection.py`: env prompt manually changed → `DriftError` blocks `upgrade`/`downgrade`/`plan`.
- `tests/integration/test_concurrent_upgrade.py`: two `upgrade` processes cannot corrupt state; one wins, the other gets a clear storage/busy error.
- `tests/integration/test_fault_injection.py`: truncated/modified applied revision bytes rejected; extra unexpected prompt in `prompts` table rejected as drift.

**Minimal code:** test scaffolding only (monkeypatch `sqlite3.connect` to raise mid-transaction, or use a wrapper that fails on Nth execute). No production code change unless a test reveals a gap.

**Acceptance criteria:**
- All fault-injection tests pass; no partial commits observable.
- Whole suite green (including existing 713).

### PR 11 — Package-install smoke tests + README-as-tests (ROADMAP remaining item)

**Goal:** Verify a clean `pip install -e .` works and README commands execute as smoke tests.

**TDD tests (write first):**
- `tests/contract/test_package_install.py`: fresh venv, `pip install -e .[dev]`, `promptmigrate --help` exits 0.
- `tests/contract/test_readme_example.py`: run the README five-minute example in a temp dir end-to-end (init → env add → revision → plan → upgrade → check → get → downgrade).

**Minimal code:** test-only; may add a `Dockerfile.ci` or CI job for package install on Linux/macOS/Windows (per TESTING_STRATEGY.md stage 5).

**Acceptance criteria:**
- Fresh install + full README walkthrough passes on Windows.
- CI matrix: Linux Docker + native Windows + macOS, Python 3.10/3.12/3.13.
- Whole suite green.

### PR 12 — Append-only events table + `rebase` for unapplied revisions (ROADMAP remaining item)

**Goal:** Add an append-only `events` table to each env SQLite (audit trail of applies/reverts) and a `rebase` command to reorder/squash unapplied (source-only) revisions before they are applied to any env.

**Open question:** Q6 (transaction granularity) — `rebase` operates on source files only (no env DB), so no transaction semantics needed there; `upgrade`/`downgrade` stay one transaction per command (already implemented).

**TDD tests (write first):**
- `tests/unit/test_events_table.py`: `upgrade`/`downgrade` append an event row (revision, direction, applied_at) in the same transaction as config+ledger; `check`/`get` never write events.
- `tests/unit/test_rebase.py`: `rebase` reorders unapplied revisions; `rebase` refuses if any revision in the range is already applied to any declared env.
- `tests/integration/test_rebase_cli.py`: `rebase` CLI updates file order/slugs; `load_revisions` still linear.

**Minimal code:**
- `store/sqlite.py`: `events` table DDL; `apply.py` `migrate()` inserts event row.
- `commands/rebase.py` (new): `execute(args)`.

**Refactor:** shared event-writing helper inside `apply.py`.

**Acceptance criteria:**
- Events table append-only (no UPDATE/DELETE on it).
- `rebase` cannot rebase applied revisions (fail closed).
- Whole suite green.

### PR 13 — Safe deletion policy + `--env prod` naming + security guardrails (Open Questions Q3, Q7, Q9)

**Goal:** Resolve three open questions:
- Q3: deletion of a named config requires explicit `--allow-delete` (or confirmation) in `revision` generation.
- Q7: `prod`/`production`/`live` names keep the explicit local-only warning (do not disallow or rename — avoids breaking existing users; documented as local-only).
- Q9: secret guardrails — allowlist by fingerprint (already in PR 3b); review false-positive rate; no token-shaped literals in fixtures (build from `"sk-" + "0" * 24` at runtime).

**TDD tests (write first):**
- `tests/unit/test_deletion_policy.py`: revision deleting a config without `--allow-delete` → `SchemaError`; with `--allow-delete` → allowed.
- `tests/unit/test_production_name_warning.py`: `--env prod`/`production`/`live` emits `ProductionNameWarning`; still operates on local SQLite.
- `tests/unit/test_secret_guardrails.py`: token-shaped values built at runtime from fragments are blocked/redacted; no token literals in fixtures.

**Minimal code:** `commands/revision.py` `--allow-delete` flag; warnings already exist (`ProductionNameWarning`); `secretscan.py` reviewed allowlist.

**Acceptance criteria:**
- Deletion opt-in; no silent deletes.
- Production-name warning text unchanged; local-only semantics preserved.
- No committed token-shaped literals.
- Whole suite green.

### PR 14 — `export` command (MVP runtime-integration bridge, Open Question Q8)

**Goal:** Add `promptmigrate get --export`? No — a new `export` command that writes the current applied config of an environment to a JSON bundle (local file only), for consumption by an application resolver. No provider calls, no activation claims.

**TDD tests (write first):**
- `tests/unit/test_export_command.py`: `export --env dev --out bundle.json` writes applied prompts; missing env → exit 1; `--output json` envelope includes `path`.
- `tests/cli/test_export_cli.py`: export is read-only on the env DB (opens `mode=ro`).

**Minimal code:** `commands/export.py` reading `_actual(db)` via read-only store connection and writing canonical JSON to `--out`.

**Acceptance criteria:**
- Export never mutates env state.
- Output is canonical JSON (redacted secrets per policy).
- Whole suite green.

### PR 15 — Compatibility testing (Open Question Q10)

**Goal:** Add tests comparing application code/tool schemas to a revision before deployment (read-only compatibility check). No enforcement in CLI yet — test the comparison primitives.

**TDD tests (write first):**
- `tests/unit/test_compatibility.py`: compare a config's `tools` list and `response_schema` against a declared capability set; report mismatches without mutating.

**Acceptance criteria:**
- Compatibility check is pure (no I/O, no provider).
- Documented as opt-in, pre-deployment guidance only.
- Whole suite green.

---

## 4. Test acceptance criteria (merge gate)

| Criterion | How verified |
|---|---|
| Whole suite green on Windows | `python -m pytest -q` → all pass; real output pasted in PR |
| unittest suite unchanged | `PYTHONPATH=src python -m unittest discover -s tests -v` → `Ran 7 tests ... OK` |
| CI matrix | Linux Docker + native Windows + macOS × Python 3.10/3.12/3.13 |
| No secrets in fixtures/logs | grep for token literals; runtime fragments only |
| `--env prod` local-only | `ProductionNameWarning` on prod/production/live |
| Revision format unchanged for v0 | raw-byte checksum still used; v0 fixtures apply unchanged |
| `CHANGELOG.md` + `docs/ROADMAP.md` updated | each commit |
| Docs synced on behavior change | `CLI_SPEC.md`, `MIGRATION_PROTOCOL.md`, `DECISIONS.md` |

---

## 5. Risks / contradictions (severity)

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| R1 | `format_version`/`artifact_sha256` change could be seen as a checksum-semantics change | High | Explicit format version; v0 raw-byte checksum untouched; tested v0→v1 reader path |
| R2 | Concurrent revision generation still allows Git branches after merge | Medium | No auto-merge; `load_revisions` rejects branches with actionable error |
| R3 | `rebase` on unapplied revisions could be misused on applied history | High | `rebase` refuses any revision already applied to any declared env |
| R4 | `export` bundle could be mistaken for a production release | Medium | Docs + warning: local file only, no activation implied |
| R5 | CRLF false-tamper on v0 artifacts remains | Low | Accepted for v0; fixed for v1 via canonical hash |

---

## 6. Proposed ADR updates

- **ADR-003 (JSON declarative revisions):** add `format_version` field note; v0 raw-byte checksum, v1 canonical `artifact_sha256`.
- **New ADR — Protocol v1 canonical artifact hashing:** define canonical serialization bytes and which hash is stored in the ledger per format version.
- **New ADR — Atomic artifact writes:** temp-file + `os.replace` for revision generation.
- **New ADR — Deletion policy:** `--allow-delete` required to generate a revision with `after: null`.
- **ADR-012 (declared environments):** confirm `prod`/`production`/`live` remain local-only with warning (no rename/disallow).

---

## 7. First 3 steps (test acceptance criteria)

1. **PR 7 (protocol v1):** RED — add `tests/unit/test_protocol_v1.py` and `test_canonical_artifact_hash.py`; watch them fail; implement `protocol/format.py` + `revisions.py` changes; GREEN; run whole suite.
2. **PR 8 (atomic writes):** RED — add `tests/unit/test_atomic_revision_write.py`; implement atomic write in `commands/revision.py`; GREEN; run whole suite.
3. **PR 9 (validate):** RED — add `tests/unit/test_validate_command.py`; implement `commands/validate.py` + CLI registration; GREEN; run whole suite.

After each PR: update `CHANGELOG.md` (Unreleased), tick `docs/ROADMAP.md`, sync behavior docs, then branch `<type>/<short-description>` and merge `--no-ff` into `main`.