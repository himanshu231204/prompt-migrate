# CLI SPECIFICATION — `promptmigrate`

## UX goals

Familiar to Alembic users, transparent in CI, safe by default. Commands distinguish **source draft changes** from **environment state**. All examples below assume the command is installed via `python -m pip install -e .` from starter or future PyPI package.

## Implemented in current prototype

| Command | Purpose | Important behavior |
|---|---|---|
| `promptmigrate init` | Scaffold project | Creates `.promptmigrate/`, starter `assistant.json`, and declared `dev`/`staging` environments |
| `promptmigrate revision -m "message"` | Generate revision from draft delta | Rejects no-op; parent = source head; refuses drafts that break validation or limits, and secret-like values in new content, before writing; writes a protocol v1 file (`format_version: 1`, LF line endings on every OS; see `MIGRATION_PROTOCOL.md`) |
| `promptmigrate diff` | Compare drafts with source migration head | JSON diff to stdout; not env diff; secret-like values shown as <redacted:RULE> |
| `promptmigrate history` | Print ordered source revisions | Shows ID, parent, message; secret-like messages shown as <redacted:RULE> |
| `promptmigrate current --env dev` | Show env applied head | Verifies local state first |
| `promptmigrate upgrade head --env dev` | Advance to source head | SQLite transactional operation |
| `promptmigrate upgrade <revision> --env dev` | Advance to exact revision | Must be ahead of/equal to current |
| `promptmigrate downgrade -1 --env dev` | Revert one revision | Default downgrade behavior |
| `promptmigrate downgrade base --env dev` | Revert all | Restores empty source state |
| `promptmigrate downgrade <revision> --env dev` | Revert to exact revision | Must be behind/equal to current |
| `promptmigrate plan --env dev [--target head]` | Preview what `upgrade`/`downgrade` would do | Read-only: verifies the environment like `check`, writes nothing (no state file, no manifest adoption, no lock). Target is `head` (default), `-1`, `base` or a revision id; the direction is inferred from where the target lies. Lists each revision and its config changes (`create`/`update`/`delete`); prints `nothing to do` at the target. Same `Error:` text for unknown targets, drift and tampering as the commands it previews. |
| `promptmigrate check --env dev` | Check applied integrity/state drift | Does not require env at source head; warns about secrets in history and stale allowlist entries |
| `promptmigrate check --env dev --require-head` | Also require no pending revisions | Helpful for CI |
| `promptmigrate restamp --env dev` | Accept line-ending-only changes to applied v0 revisions | Mutating and all or nothing: re-stamps the ledger checksum of each applied v0 revision whose file differs from the applied bytes only in line endings (CRLF ↔ LF), then verifies the environment like `check`. Any other mismatch, any v1 row, or drift fails with the normal error and writes nothing. No state database means nothing to do; nothing is created, and no manifest is adopted. Prints `Restamped <n> revision(s) in <env>: <ids>` (`(none)` when n = 0). Leaves no audit record until the cycle-3 events table (ADR-027) |
| `promptmigrate get sql_agent --env dev` | Read applied local JSON | Only local stored config; secret-like values shown as <redacted:RULE> |
| `promptmigrate env add qa` | Declare a local environment | Atomically updates `.promptmigrate/environments.json`; prints `Added environment: qa` |
| `promptmigrate env list` | List declared environments | Prints sorted `<name>: state exists` or `<name>: no state`; never creates a database |

The environment manifest has the form `{"environments": {"dev": {}, "staging": {}}}`. Each value is an opaque JSON metadata object retained by `env add`; names are case-insensitive for identity and use the spelling stored in the manifest for filenames and output. Names match `[A-Za-z][A-Za-z0-9_-]{0,63}` and Windows device names are rejected for portability.

Existing projects without a manifest are read in memory as `dev`, `staging` and every `states/*.sqlite3` stem that matches the environment-name syntax; other stems were never PromptMigrate state and are ignored. Read-only commands never persist this adoption. `upgrade` and `downgrade` write the manifest and emit one adoption warning only after their transaction commits, so a target, history or state error leaves no manifest behind; `env add` adopts as it writes. `check`, `current` and `get` read the ledger and configs in one SQLite read transaction. An undeclared environment fails before database access or file creation.

`check`, `current`, `get`, and `env list` are read-only. They do not create missing state databases. An absent database represents the empty base state; an existing database missing either required table or using WAL journal mode is a storage error and is never repaired by a read. CLI status labels use canonical manifest spelling. `upgrade` and `downgrade` use local SQLite transactions. Production-like names (`prod`, `production`, `live`) emit a warning: these names still refer only to local SQLite files.

**Global flags:** `promptmigrate --project /path/to/project --output {text,json} <command>`. `--output` defaults to `text`.

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
| `eval --suite regression` | Run evaluation policy against candidate configuration |
| `export --env dev` | Emit immutable artifact for a runtime/CI consumer |
| `promote --from staging --to production` | Activate approved immutable release (future shared control plane) |
| `reconcile --env production` | Detect/recover provider/state inconsistencies, with explicit approval |
| `doctor` | Diagnose setup, version, permissions, and environment |

## Errors and exit status

Handled errors are typed (`errors.py`); `output.py` maps them to the exit status:

| Exit | Meaning | Error types |
|---|---|---|
| `0` | success | — |
| `1` | generic handled error | `InitializationError`, `EnvironmentNotDeclaredError`, `TargetError`, `PendingRevisionsError`, any other `MigrationError` |
| `2` | usage error | `argparse` (bad flag, unknown command, bad `--output`) |
| `3` | invalid source or schema | `SchemaError`, `SecretDetectedError`, `RevisionGraphError` |
| `4` | drift or integrity conflict | `DriftError`, `IntegrityError`, `MigrationConflictError` |
| `5` | lock or storage problem | `StorageError`, `sqlite3.Error`, `OSError` |

`6` (evaluation gate) and `7` (provider error) are reserved and not emitted: no command can produce them yet. Code `1`
keeps its pre-existing meaning, so scripts that only test for non-zero keep working. An unhandled exception still
propagates as a Python traceback.

Revision files with an unsupported `format_version` (`Unsupported format_version in <file>`), in a v1 file, an
unknown top-level key (`Unknown top-level key in <file>: <keys>`), or a string with an unpaired surrogate escape
(`Invalid string in <file>: unpaired surrogate`) are `SchemaError`s and exit 3 (see `MIGRATION_PROTOCOL.md`,
"v1 artifact").

**Warnings:** each distinct warning is printed once per invocation to stderr as `Warning: <message>`, before any
`Error: …` line. Warnings never change the exit code. Warnings come from existing revision files that break a tier-B
rule (see `MIGRATION_PROTOCOL.md`, "Strict parsing and compatibility tiers") and from the secret safeguard (redaction,
secrets in history, stale allowlist entries; see `SECURITY.md`).

## JSON output

`--output json` prints exactly one JSON object and a newline on stdout (`ensure_ascii`, no NaN), for success and for
handled errors alike. Schema `promptmigrate.output/1`:

```json
{"schema": "promptmigrate.output/1", "ok": true, "command": "upgrade", "env": "dev",
 "data": {}, "warnings": [{"category": "LegacyRevisionWarning", "message": "…"}]}
```

```json
{"schema": "promptmigrate.output/1", "ok": false, "command": "check", "env": "dev",
 "error": {"code": "conflict", "exit_code": 4, "message": "…"}, "warnings": []}
```

- `command` is the verb (`env add`, `env list` for the subcommands). `env` is the environment label, or `null` for
  commands without one.
- `error.code` is `error` (exit 1), `schema` (3), `conflict` (4) or `storage` (5). The message is the same text as the
  `Error: …` line of text mode. Error envelopes have no `data`; success envelopes have no `error`.
- `warnings` lists each distinct PromptMigrate warning once, in first-seen order. In JSON mode PromptMigrate warnings
  and handled errors are not printed to stderr. Warnings from other libraries still go to stderr, so a script that needs
  a clean stderr must not assume it is empty. Warnings never change the exit status. An unhandled exception leaves no
  envelope, so its PromptMigrate warnings are printed to stderr as in text mode, before the traceback.
- Usage errors (exit 2) are argparse text on stderr, not an envelope: parsing fails before the format is known.
- Secret-like values are redacted exactly as in text mode; `redacted` lists what was redacted.
- Within `promptmigrate.output/1`, fields are only added, never removed or retyped.

`data` by command:

| Command | `data` |
|---|---|
| `init` | `path` |
| `revision` | `revision`, `down_revision`, `message`, `path` |
| `history` | `revisions[]` (`revision`, `down_revision`, `message`), `redacted` (revision ids with a redacted message) |
| `diff` | `changes` (name → `{before, after}`, redacted), `redacted[]` |
| `current` | `revision` (`null` at base), `applied`, `total` |
| `upgrade` / `downgrade` | `direction` (`up`/`down`), `target`, `revisions[]` (ids applied or reverted, in order) |
| `plan` | `direction` (`upgrade`/`downgrade`/`none`), `start`, `target` (ids, `null` at base), `steps[]` (`revision`, `changes[]` of `name`, `kind`: `create`/`update`/`delete`/`unchanged`), in the order they would run |
| `check` | `consistent` (always `true`; inconsistency is an error), `applied`, `total` |
| `restamp` | `restamped[]` (ids whose ledger checksum was re-stamped, in ledger order) |
| `get` | `name`, `config` (redacted), `redacted[]` |
| `env add` | `name` |
| `env list` | `environments[]` (`name`, `has_state`) |

A new command adds an `execute(args) -> output.Result` and gets both formats and the error mapping from `output.py`.

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
