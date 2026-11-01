# Changelog

All notable changes to PromptMigrate. Before 1.0, CLI and file contracts may change; such changes are marked **Contract**.

## Unreleased

### Phase 1 cycle 1 — PR 3b: secret safeguard

- **Contract:** `revision` refuses to write a secret-like value in any new `after` value or in its message. It raises
  `SecretDetectedError` (a `SchemaError`) listing name, JSON path and rule only, and writes no file. A value copied
  from history into `before` does not block; it prints `SecretInHistoryWarning`, because it is already committed and
  the credential must be rotated.
- **Contract:** `diff` and `get` replace each flagged string with `<redacted:RULE>` and print one
  `SecretRedactedWarning`. Stored data and revision files are unchanged. Redacted output must not be used as a config
  source.
- `check` warns once per revision, name, path and rule about secret-like values in history, and about allowlist entries
  that matched nothing. Warnings do not change the exit code.
- False positives go in `.promptmigrate/secret-allowlist.json` (Git-tracked, strictly parsed). An entry applies only
  when its name, path, rule and the SHA-256 fingerprint of the exact value all match.
- Detection is heuristic: it can miss secrets, and it does nothing for secrets already in Git history.
- New module `promptmigrate.secretscan`; new `core` functions `load_allowlist`, `redacted_diff`, `redacted_config`
  and `audit_secrets`. `get_config` and `draft_diff` still return unredacted data.

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
