# MIGRATION PROTOCOL — Source format and semantics

## Purpose and status

This is the proposed **v0.x file protocol**. It documents today's starter file shape and explicitly calls out possible future protocol upgrades. Do **not** silently introduce a breaking format or reinterpret applied checksums.

## Configuration draft

Named file: `.promptmigrate/drafts/sql_agent.json` (name = `sql_agent`).

```json
{
  "messages": [
    {"role": "system", "content": "Generate read-only SQL. State assumptions."}
  ],
  "model": "provider/model-id",
  "parameters": {"temperature": 0.1, "max_output_tokens": 2048},
  "tools": [{"name": "database_query", "permission": "read_only"}],
  "response_schema": {
    "type": "object",
    "required": ["query", "explanation"]
  }
}
```

The starter **minimally validates** the shape; `tools` and `response_schema` fields are currently treated as JSON data, not automatically enforced tool contracts. A strict schema and provider-agnostic representation are future work.

## Revision artifact

File: `.promptmigrate/versions/b2c3d4e5f6a7_improve_sql_agent.json`

```json
{
  "revision": "b2c3d4e5f6a7",
  "down_revision": "a1b2c3d4e5f6",
  "message": "Improve SQL agent safety",
  "created_at": "2026-10-29T12:00:00+00:00",
  "changes": {
    "sql_agent": {
      "before": {
        "messages": [{"role": "system", "content": "Generate SQL."}]
      },
      "after": {
        "messages": [{"role": "system", "content": "Generate read-only SQL."}]
      }
    }
  }
}
```

**Snapshot rules:**

- `before: null`, `after: object` => create.
- `before: object`, `after: object` => update.
- `before: object`, `after: null` => delete.
- `before: null`, `after: null` => no-op and should be rejected by strengthened validation (not explicitly rejected by starter loader).
- A revision may contain changes for multiple named configurations.
- `down_revision: null` indicates root; later revisions point to immediate predecessor.
- Existing starter revision ID is 12 lowercase hex chars; file slug is cosmetic.
- Revision content is declarative data, **not executable Python**.

## Authoritative state model

```text
Drafts (desired) ──diff vs replay source head──> new revision
Revisions (source history) ──apply──> Local environment state (SQLite)
Local environment state ──get──> Consumer (only if explicitly integrated)
```

## Replay and change preconditions

Let `S_i` represent the reconstructed state after revision `i`; `S_0 = {}`.

For every config name `n` in revision `i`:

```text
require S_(i-1)[n] == changes[n].before
S_i[n] = changes[n].after
if after == null: remove n
```

Backward step:

```text
require S_i[n] == changes[n].after
S_(i-1)[n] = changes[n].before
if before == null: remove n
```

The executor must check all preconditions before committing any state change. The whole local migration operation uses one SQLite transaction.

## Integrity checks

The current implementation stores `SHA-256(raw revision file bytes)` in the `applied_revisions` ledger. A later change to the file — including whitespace-only modification — will be rejected for environments where that revision was applied.

- This is **tamper detection relative to that environment ledger**, not cryptographic proof of author identity.
- A future `format_version` field, canonical artifact hashing, manifest signatures, and transparency/audit trail need an explicit migration/compatibility design.
- Preexisting revisions must remain readable after schema evolution.

## Environment names

Current regex: `[A-Za-z][A-Za-z0-9_-]{0,63}`. Each name maps to a local database file under `states/`. **`--env prod` means only local `prod.sqlite3`; it does not mean actual production.**

## Revision-graph guarantees

For MVP: at most one root and one child per revision. No merge branches, disconnected history, cycles, or missing parent allowed. If there is no version file, `head` is the empty base state.

## Snapshot/storage limits to discuss

- Duplicated full configs increase repository size for frequent revisions.
- Very large prompts or templates may warrant separate content-addressed assets later.
- Raw string prompts and runtime-resolved user content must never be conflated.
- Never serialize secrets; use references like `secret://provider/credential` where needed.
- Client code and tool schema may need compatibility constraints recorded alongside config.

## Future `format_version` proposal (not implemented)

Potential fields: `format_version: 1`, `artifact_sha256`, `dependencies`, `metadata`, and `compatibility`. Define canonical serialization bytes, validation, and migration rules before shipping a public stable protocol. Do not add them experimentally without migration tests.
