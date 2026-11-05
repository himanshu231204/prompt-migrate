# CLI SPECIFICATION — `promptmigrate`

## UX goals

Familiar to Alembic users, transparent in CI, safe by default. Commands distinguish **source draft changes** from **environment state**. All examples below assume the command is installed via `python -m pip install -e .` from starter or future PyPI package.

## Implemented in current prototype

| Command | Purpose | Important behavior |
|---|---|---|
| `promptmigrate init` | Scaffold project | Creates `.promptmigrate/`, starter `assistant.json`, and declared `dev`/`staging` environments |
| `promptmigrate revision -m "message"` | Generate revision from draft delta | Rejects no-op; parent = source head; refuses drafts that break validation or limits, and secret-like values in new content, before writing |
| `promptmigrate diff` | Compare drafts with source migration head | JSON diff to stdout; not env diff; secret-like values shown as <redacted:RULE> |
| `promptmigrate history` | Print ordered source revisions | Shows ID, parent, message; secret-like messages shown as <redacted:RULE> |
| `promptmigrate current --env dev` | Show env applied head | Verifies local state first |
| `promptmigrate upgrade head --env dev` | Advance to source head | SQLite transactional operation |
| `promptmigrate upgrade <revision> --env dev` | Advance to exact revision | Must be ahead of/equal to current |
| `promptmigrate downgrade -1 --env dev` | Revert one revision | Default downgrade behavior |
| `promptmigrate downgrade base --env dev` | Revert all | Restores empty source state |
| `promptmigrate downgrade <revision> --env dev` | Revert to exact revision | Must be behind/equal to current |
| `promptmigrate plan --env dev [--target head]` | Preview what `upgrade`/`downgrade` would do | Read-only: verifies the environment like `check`, writes nothing (no state file, no manifest adoption, no lock). Target is `head` (default), `-1`, `base` or a revision id; the direction is inferred from where the target lies. Lists each revision and its config changes (`create`/`update`/`delete`); prints `nothing to do` at the target. Same `Error:` text for unknown targets, drift and tampering as the commands it previews. Text output only until `--output json` |
| `promptmigrate check --env dev` | Check applied integrity/state drift | Does not require env at source head; warns about secrets in history and stale allowlist entries |
| `promptmigrate check --env dev --require-head` | Also require no pending revisions | Helpful for CI |
| `promptmigrate get sql_agent --env dev` | Read applied local JSON | Only local stored config; secret-like values shown as <redacted:RULE> |
| `promptmigrate env add qa` | Declare a local environment | Atomically updates `.promptmigrate/environments.json`; prints `Added environment: qa` |
| `promptmigrate env list` | List declared environments | Prints sorted `<name>: state exists` or `<name>: no state`; never creates a database |

The environment manifest has the form `{"environments": {"dev": {}, "staging": {}}}`. Each value is an opaque JSON metadata object retained by `env add`; names are case-insensitive for identity and use the spelling stored in the manifest for filenames and output. Names match `[A-Za-z][A-Za-z0-9_-]{0,63}` and Windows device names are rejected for portability.

Existing projects without a manifest are read in memory as `dev`, `staging` and every `states/*.sqlite3` stem that matches the environment-name syntax; other stems were never PromptMigrate state and are ignored. Read-only commands never persist this adoption. `upgrade` and `downgrade` write the manifest and emit one adoption warning only after their transaction commits, so a target, history or state error leaves no manifest behind; `env add` adopts as it writes. `check`, `current` and `get` read the ledger and configs in one SQLite read transaction. An undeclared environment fails before database access or file creation.

`check`, `current`, `get`, and `env list` are read-only. They do not create missing state databases. An absent database represents the empty base state; an existing database missing either required table or using WAL journal mode is a storage error and is never repaired by a read. CLI status labels use canonical manifest spelling. `upgrade` and `downgrade` use local SQLite transactions. Production-like names (`prod`, `production`, `live`) emit a warning: these names still refer only to local SQLite files.

**Global flag:** `promptmigrate --project /path/to/project <command>`.

## Developer example

```bash
python -m pip install -e .
mkdir demo-app && cd demo-app
promptmigrate init
# edit .promptmigrate/drafts/assistant.json
promptmigrate revision -m "initial assistant"
promptmigrate history
promptmigrate upgrade head --env dev
promptmigrate check --env dev --require-head
promptmigrate get assistant --env dev
# edit the draft again
promptmigrate diff
promptmigrate revision -m "improve instructions"
promptmigrate upgrade head --env staging
promptmigrate current --env staging
promptmigrate downgrade -1 --env staging
```

## Target commands: **proposed, not yet implemented**

| Command | Contract |
|---|---|
| `validate` | Validate all source/drafts against strict schema and revisions |
| `--output json` | Machine-readable output for every command (design syntax TBD) |
| `eval --suite regression` | Run evaluation policy against candidate configuration |
| `export --env dev` | Emit immutable artifact for a runtime/CI consumer |
| `promote --from staging --to production` | Activate approved immutable release (future shared control plane) |
| `reconcile --env production` | Detect/recover provider/state inconsistencies, with explicit approval |
| `doctor` | Diagnose setup, version, permissions, and environment |

## Errors and exit status

**Current baseline:** `0` on success, `1` for handled domain/storage errors. Argument parsing follows `argparse` behavior
(typically `2` for usage failures). Handled errors are typed (`SchemaError`, `RevisionGraphError`,
`MigrationConflictError`, `DriftError`, `IntegrityError`, `TargetError`, `PendingRevisionsError`, `InitializationError`,
all subclasses of `MigrationError`); the detailed exit-code mapping arrives with the JSON contract.

**Warnings:** each distinct warning is printed once per invocation to stderr as `Warning: <message>`, before any
`Error: …` line. Warnings never change the exit code. Warnings come from existing revision files that break a tier-B
rule (see `MIGRATION_PROTOCOL.md`, "Strict parsing and compatibility tiers") and from the secret safeguard (redaction,
secrets in history, stale allowlist entries; see `SECURITY.md`).

**Proposed taxonomy:** `0` success, `2` usage, `3` invalid source/schema, `4` drift/integrity conflict, `5` lock/storage problem, `6` evaluation gate failure, `7` provider error. Introduce only after contract tests and documentation update.

## Output policy

- Human output must always indicate environment, target/current revision, applied count, and actionable error.
- `plan` and `diff` must never mutate environment state.
- Production-labeled local paths need explicit warning until real production support exists.
- Secret-like values are blocked in new revision content at `revision` and redacted in `diff`/`get` output, by
  heuristic detection. Detection can miss secrets. Allowlisted values (bound to a fingerprint) are shown. Secrets
  already in history are only warned about and redacted in output; they stay in the files and in Git and must be
  rotated. Redacted output (`redacted` non-empty) must not be used as a config source.
- Avoid success claims after remote asynchronous operations unless they have been observed/confirmed (future).

## CLI acceptance test examples

- Wrong parent rejects apply.
- Deleted draft results in an explicit delete operation.
- `upgrade head` twice is idempotent.
- `check` detects modified applied migration bytes.
- Staging can remain behind dev without failing `check` unless `--require-head` is set.
- `downgrade -1` from base returns no changes.
