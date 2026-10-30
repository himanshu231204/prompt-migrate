# CLI SPECIFICATION — `promptmigrate`

## UX goals

Familiar to Alembic users, transparent in CI, safe by default. Commands distinguish **source draft changes** from **environment state**. All examples below assume the command is installed via `python -m pip install -e .` from starter or future PyPI package.

## Implemented in current prototype

| Command | Purpose | Important behavior |
|---|---|---|
| `promptmigrate init` | Scaffold project | Creates `.promptmigrate/` and starter `assistant.json` |
| `promptmigrate revision -m "message"` | Generate revision from draft delta | Rejects no-op; parent = source head |
| `promptmigrate diff` | Compare drafts with source migration head | JSON diff to stdout; not env diff |
| `promptmigrate history` | Print ordered source revisions | Shows ID, parent, message |
| `promptmigrate current --env dev` | Show env applied head | Verifies local state first |
| `promptmigrate upgrade head --env dev` | Advance to source head | SQLite transactional operation |
| `promptmigrate upgrade <revision> --env dev` | Advance to exact revision | Must be ahead of/equal to current |
| `promptmigrate downgrade -1 --env dev` | Revert one revision | Default downgrade behavior |
| `promptmigrate downgrade base --env dev` | Revert all | Restores empty source state |
| `promptmigrate downgrade <revision> --env dev` | Revert to exact revision | Must be behind/equal to current |
| `promptmigrate check --env dev` | Check applied integrity/state drift | Does not require env at source head |
| `promptmigrate check --env dev --require-head` | Also require no pending revisions | Helpful for CI |
| `promptmigrate get sql_agent --env dev` | Read applied local JSON | Only local stored config |

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
| `plan --env dev [--target head]` | Read-only ordered migration preview, changed names, warnings |
| `validate` | Validate all source/drafts against strict schema and revisions |
| `--output json` | Machine-readable output for every command (design syntax TBD) |
| `eval --suite regression` | Run evaluation policy against candidate configuration |
| `export --env dev` | Emit immutable artifact for a runtime/CI consumer |
| `promote --from staging --to production` | Activate approved immutable release (future shared control plane) |
| `reconcile --env production` | Detect/recover provider/state inconsistencies, with explicit approval |
| `doctor` | Diagnose setup, version, permissions, and environment |

## Errors and exit status

**Current baseline:** `0` on success, `1` for handled domain/storage errors. Argument parsing follows `argparse` behavior (typically `2` for usage failures). Do not claim detailed exit-code taxonomy exists yet.

**Proposed taxonomy:** `0` success, `2` usage, `3` invalid source/schema, `4` drift/integrity conflict, `5` lock/storage problem, `6` evaluation gate failure, `7` provider error. Introduce only after contract tests and documentation update.

## Output policy

- Human output must always indicate environment, target/current revision, applied count, and actionable error.
- `plan` and `diff` must never mutate environment state.
- Production-labeled local paths need explicit warning until real production support exists.
- Secret values must never appear in logs, diffs, or JSON output if they were mistakenly included in drafts (enforce before public release).
- Avoid success claims after remote asynchronous operations unless they have been observed/confirmed (future).

## CLI acceptance test examples

- Wrong parent rejects apply.
- Deleted draft results in an explicit delete operation.
- `upgrade head` twice is idempotent.
- `check` detects modified applied migration bytes.
- Staging can remain behind dev without failing `check` unless `--require-head` is set.
- `downgrade -1` from base returns no changes.
