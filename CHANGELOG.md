# Changelog

All notable changes to PromptMigrate. Before 1.0, CLI and file contracts may change; such changes are marked **Contract**.

## Unreleased

- Added an SVG banner to the README showing PromptMigrate's ordered revision flow and verified local environment state.
- Corrected README and handoff documentation to include the shipped `plan` command and native Windows/macOS CI coverage; refreshed the documented test baseline and suite location. Brought `PRD.md`, `ROADMAP.md` and `LOW_LEVEL_DESIGN.md` up to date with the shipped `plan`, exit codes, JSON output, typed errors and strict loader. Moved all agent rules and the architecture overview from `CLAUDE.md` into `AGENTS.md`.
- Compacted `AGENTS.md` without dropping rules, and added a "Before every commit" rule: each commit updates `CHANGELOG.md` and `docs/ROADMAP.md`.

### Phase 1 cycle 2 — protocol v1 and canonical revision hashes (PR 8)

- Revision files with `"format_version": 1` are read as protocol v1 (ADR-026): exactly six top-level keys, and a
  `v1:`-tagged SHA-256 of the canonical parsed object as checksum, so line endings, whitespace and key order no
  longer count for them. Any other `format_version` value, or an unknown key in a v1 file, is a `SchemaError`
  (exit 3). Files without `format_version` stay v0, unchanged.

### Phase 1 cycle 2 — freeze v0 artifact semantics (PR 7)

- Recorded ADR-025: a revision file without `format_version` is v0, its meaning is frozen, and its checksum stays
  SHA-256 of the raw bytes. Added byte-exact v0 and CRLF fixtures with pinned checksums and characterization tests.
  The CRLF false-tamper risk is now documented in `MIGRATION_PROTOCOL.md` and pinned as a strict xfail.
  No code, CLI, file-format or checksum change.
- Recorded the post-PR 7 test baseline in TESTING_STRATEGY.md and HANDOFF.md, and clarified the v0 line-ending risk wording.

### Phase 1 cycle 1 — exit codes and `--output json` (PR 6)

- **Contract:** handled errors now exit by type: 3 for schema/source errors, 4 for drift, integrity and conflicts, 5
  for storage, `sqlite3` and `OSError` failures. Other handled errors (uninitialized project, undeclared environment,
  unknown target, pending revisions) still exit 1. Usage errors stay 2. Scripts testing for exactly 1 must change.
- Added global `--output {text,json}` (default `text`). JSON prints one `promptmigrate.output/1` envelope on stdout
  for every command, success or handled error; PromptMigrate warnings are listed in it instead of printed to stderr.
  Default text output is unchanged. See `docs/CLI_SPEC.md` and ADR-024.
- New `promptmigrate.output`; every command, including `plan`, exposes `execute(args)` returning an `output.Result`.

### Phase 1 cycle 1 — read-only `plan`

- Added `promptmigrate plan [--env E] [--target head|-1|base|<revision>]`: a read-only preview of what `upgrade` or
  `downgrade` would do. It verifies the environment like `check`, writes nothing and infers the direction from the
  target. **Contract:** new command; no change to existing commands, output or error messages.
- Target resolution moved into the pure `promptmigrate.plan` module, shared by `upgrade`, `downgrade` and `plan`.
  A hypothesis property test checks that `plan` matches what the commands apply (ADR-023).

### Community files

- Added `examples/multi-agent-basic/`: two agent drafts and a cross-platform `run.py` that walks the full lifecycle.
  `tests/contract/test_examples.py` runs it on every test run.
- Added `CONTRIBUTING.md` (setup, rules, a "where does X live" table), `CODE_OF_CONDUCT.md` (Contributor
  Covenant 2.1), a root `SECURITY.md` (private reporting through GitHub), and issue and pull request templates.
- CodeRabbit now reviews draft pull requests (`reviews.auto_review.drafts: true` in `.coderabbit.yaml`).
- `docs/ROADMAP.md` marks the six completed Phase 1 cycle 1 items. `plan`, exit codes 0–5 and `--output json`
  remain open.

### Phase 1 cycle 1 — package layout refactor

- `promptmigrate.protocol` is now a package: `limits`, `jsonloader`, `equality` and `rules`. It re-exports every
  previous name. Limits are read at call time from `protocol.limits`, so tests patch them there.
- `promptmigrate.store` is now a package: `environments`, `lock` and `sqlite`. It re-exports every previous name.
  `root_dir`/`require_init` live in the new `promptmigrate.project`. Environment-name syntax moved to
  `protocol.rules.validate_environment_name`.
- `core.py` is now a re-export facade (ADR-022). Logic lives in `project`, `revisions`, `draftdiff`, `apply` and
  one `commands.<verb>` module per CLI verb; `cli.py` only parses and dispatches. `promptmigrate.__all__` exposes the
  same public names as `core`. Monkeypatching `core` or `cli` no longer changes behaviour; patch the defining module.
- Tests are grouped by suite in `tests/{unit,integration,contract,security}/`. The original `test_core.py` stays at
  the root. Helpers that one test module imported from another moved to `tests/pmtest.py`.
- No CLI, file-format or checksum change: CLI output is byte-identical to the previous release.

### Phase 1 cycle 1 — PR 4: declared environments and read-only state reads

- **Contract:** `init` declares `dev` and `staging` in `.promptmigrate/environments.json`. `env add <name>` adds a declaration atomically; `env list` reports each declared name and whether its local SQLite file exists.
- **Contract:** environment names are resolved case-insensitively using canonical manifest spelling, including CLI status labels. Undeclared names fail before DB access. Legacy projects without a manifest are inferred in memory as `dev`, `staging` and every validly named `states/*.sqlite3` stem (stems no release could have created are ignored); the first successful `upgrade`, `downgrade` or `env add` persists that manifest and prints one adoption warning. A rejected command writes no manifest.
- **Contract:** `check`, `current`, and `get` use read-only SQLite connections; missing state is the empty base state. Reads never create or repair database files. Existing incomplete/corrupt DBs, WAL-mode DBs, and state symlinks fail as storage errors.
- Production-like environment names warn that their state remains local SQLite. No provider deployment or production activation is added.

### Phase 1 cycle 1 — PR 3b: secret safeguard

- **Contract:** `revision` refuses to write a secret-like value in any new `after` value or in its message. It raises
  `SecretDetectedError` (a `SchemaError`) listing name, JSON path and rule only, and writes no file. A value copied
  from history into `before` does not block; it prints `SecretInHistoryWarning`, because it is already committed and
  the credential must be rotated.
- **Contract:** `diff` and `get` replace each flagged string with `<redacted:RULE>` and print one
  `SecretRedactedWarning`. Stored data and revision files are unchanged. Redacted output must not be used as a config
  source.
- `check` warns once per revision, name, path and rule about secret-like values in history (including commit
  messages), and about allowlist entries that matched nothing. Warnings do not change the exit code.
- `history` replaces a flagged commit message with `<redacted:RULE>` and prints one `SecretRedactedWarning`.
- False positives go in `.promptmigrate/secret-allowlist.json` (Git-tracked, strictly parsed). An entry applies only
  when its name, path, rule and the SHA-256 fingerprint of the exact value all match. A commit message is allowlisted
  with `"name": "(message)", "path": "/message"`. Allowlist entries must be unique by (name, path, rule,
  fingerprint); a duplicate is rejected.
- Detection is heuristic: it can miss secrets, and it does nothing for secrets already in Git history.
- New module `promptmigrate.secretscan`; new `core` functions `load_allowlist`, `redacted_diff`, `redacted_config`,
  `redacted_history` and `audit_secrets`. `get_config` and `draft_diff` still return unredacted data.

### Phase 1 cycle 1 — PR 3: strict parsing, compatibility tiers, canonical equality

- **Contract:** drafts and revision files are parsed strictly. Duplicate keys, `NaN`/`Infinity`/`-Infinity`, number
  literals that overflow to infinity (such as `1e400`), JSON nested too deep to parse, and files that resolve outside
  `.promptmigrate/` are rejected everywhere (tier A). This also applies when `versions/` or `drafts/` is itself a
  symlink pointing outside `.promptmigrate/`: every file in it is rejected.
- **Contract:** configs compare by canonical JSON, so `1`, `1.0` and `true` are distinct. A `1` → `true` draft edit
  now produces a revision, and bool/int drift in an env DB is detected. A revision hand-edited to rely on the old
  conflation now fails with `unexpected current value`.
- **Contract:** new hygiene and limit rules (tier B) reject drafts and newly generated revisions: reserved-field types
  (`model` string, `parameters` object, `tools` list, `response_schema` object or `null`), config depth above 64,
  drafts over 1 MiB or symlinked, draft names equal case-insensitively, and revision files over 16 MiB (checked before
  writing). Existing revision files that break them still load, and the CLI prints
  `Warning: revision <id>: <rule> (accepted for compatibility; create a new revision to fix)` on stderr.
- Errors are typed (`InitializationError`, `SchemaError`, `RevisionGraphError`, `MigrationConflictError`,
  `DriftError`, `IntegrityError`, `TargetError`, `PendingRevisionsError`), all subclasses of `MigrationError`.
  Messages and exit code 1 are unchanged until PR 6, except that an OS error while reading a revision file is now
  reported as `Unreadable migration <file>: …`.
- New modules `promptmigrate.errors` and `promptmigrate.protocol`; `promptmigrate.core` keeps every existing name.
- Tests: the three PR 3 strict xfails now pass; added error-type, strict-parsing, canonical-equality, new-content,
  legacy-warning and CLI-warning suites, plus `tests/fixtures/legacy_breaking/hand_edited_bool_int`.

### Phase 1 cycle 1 — PR 2: characterization tests and legacy fixtures

- Tests only; no behaviour change.
- Pinned: revision-graph errors, upgrade/downgrade target rules, CLI text output and exit codes, and the README
  five-minute example as a smoke test.
- Pinned as strict xfails, each naming its fixing PR: undeclared env reports OK and read commands create files (PR 4);
  `1`/`true` equality, duplicate JSON keys and `NaN` (PR 3).
- Added: legacy compatibility fixtures under `tests/fixtures/legacy/`, which must stay usable for the whole cycle.

### Phase 1 cycle 1 — PR 1: connection lifecycle and cross-OS CI

- Fixed: every command closes its SQLite connection. Leaked connections kept `states/<env>.sqlite3` locked, so on
  Windows 5 of 7 tests errored during cleanup.
- Test fix: `test_state_drift_detected` closes the SQLite connection it opens itself (assertions unchanged).
- Added: `dev` extra (`pytest`, `hypothesis`, `pytest-cov`). pytest now finds `src/` without `PYTHONPATH`.
- CI: Ubuntu, Windows and macOS × Python 3.10, 3.12, 3.13, run with pytest.
